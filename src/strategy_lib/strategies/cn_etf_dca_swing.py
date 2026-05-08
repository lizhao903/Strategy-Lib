"""Strategy 2 — A股 ETF DCA + 阈值再平衡（做T）。

自包含的 weight-based 策略实现，**不继承** ``BaseStrategy``（信号驱动）。

设计要点：
- 货币基金 ``511990`` 当作现金等价物（T+0、~2% 年化）
- 6 只风险 ETF 等权 + 30% 现金缓冲（默认目标 70% 风险）
- 月度第一个交易日做 DCA 净流入（从 511990 转入风险池等额买入）
- 每日盘后扫描权重偏离，触发部分再平衡（同一标的 5 日 cooldown）
- 所有触发判定基于 T 日 close，下单在 T+1 open 成交（无未来函数）

回测使用 ``vbt.Portfolio.from_orders`` 走 size + price 路线；
为避免在测试环境下硬依赖 vectorbt，``run`` 内部惰性 import。
``simulate`` 提供同等逻辑的纯 numpy/pandas 实现，给 smoke test 用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# 常量：共享基线
# ---------------------------------------------------------------------------

DEFAULT_CASH_SYMBOL = "511990"
DEFAULT_RISK_SYMBOLS: tuple[str, ...] = (
    "510300",
    "510500",
    "159915",
    "512100",
    "512880",
    "512170",
)


@dataclass
class DCASwingResult:
    """Strategy 2 自包含运行结果。"""

    portfolio: object | None  # vbt Portfolio（真实回测才有），simulate 时为 None
    holdings: pd.DataFrame  # 每日各标的份额（含 cash symbol）
    weights: pd.DataFrame  # 每日各标的权重
    nav: pd.Series  # 每日组合净值
    orders: pd.DataFrame  # 实际下单记录（symbol, date, size, kind）
    metrics: dict
    diagnostics: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 主策略类
# ---------------------------------------------------------------------------


class DCASwingStrategy:
    """DCA + 阈值再平衡（做T）策略。

    Parameters
    ----------
    cash_symbol:
        现金等价物代码，默认 ``511990`` 华宝添益。
    risk_symbols:
        风险资产池，默认 6 只 ETF。
    risk_target_weight:
        组合中风险资产合计目标权重，默认 ``0.70``；
        风险池内部按等权分配（每只 ``risk_target_weight / N``）。
    monthly_dca_amount:
        每月 DCA 净流入金额，默认 ``5000`` RMB。从 ``cash_symbol`` 等额转入风险池。
    rel_band:
        触发阈值，**相对偏离**。默认 ``0.20`` 即权重偏离目标的 ±20%。
    adjust_ratio:
        单次再平衡拉回比例，默认 ``0.50`` 即把偏离的一半拉回去。
    cooldown_days:
        同一标的触发后的冷却交易日数，默认 ``5``。
    initial_cash:
        策略起点现金，默认 ``100_000``。
    fees:
        单边佣金，默认万 0.5 = ``0.00005``。
    slippage:
        滑点，默认万 5 = ``0.0005``。
    name:
        策略实例名。
    """

    def __init__(
        self,
        *,
        cash_symbol: str = DEFAULT_CASH_SYMBOL,
        risk_symbols: Iterable[str] = DEFAULT_RISK_SYMBOLS,
        risk_target_weight: float = 0.70,
        monthly_dca_amount: float = 5_000.0,
        rel_band: float = 0.20,
        adjust_ratio: float = 0.50,
        cooldown_days: int = 5,
        initial_cash: float = 100_000.0,
        fees: float = 0.00005,
        slippage: float = 0.0005,
        name: str = "cn_etf_dca_swing",
    ) -> None:
        self.cash_symbol = cash_symbol
        self.risk_symbols = tuple(risk_symbols)
        if not 0.0 < risk_target_weight <= 1.0:
            raise ValueError("risk_target_weight 必须在 (0, 1]")
        if not 0.0 < rel_band < 1.0:
            raise ValueError("rel_band 必须在 (0, 1)")
        if not 0.0 < adjust_ratio <= 1.0:
            raise ValueError("adjust_ratio 必须在 (0, 1]")
        if cooldown_days < 0:
            raise ValueError("cooldown_days 不能为负")

        self.risk_target_weight = float(risk_target_weight)
        self.monthly_dca_amount = float(monthly_dca_amount)
        self.rel_band = float(rel_band)
        self.adjust_ratio = float(adjust_ratio)
        self.cooldown_days = int(cooldown_days)
        self.initial_cash = float(initial_cash)
        self.fees = float(fees)
        self.slippage = float(slippage)
        self.name = name

    # ------------------------------------------------------------------
    # 公共属性
    # ------------------------------------------------------------------

    @property
    def per_risk_weight(self) -> float:
        """风险池内每只标的的目标权重。"""
        return self.risk_target_weight / len(self.risk_symbols)

    @property
    def all_symbols(self) -> tuple[str, ...]:
        return (self.cash_symbol, *self.risk_symbols)

    # ------------------------------------------------------------------
    # 数据准备
    # ------------------------------------------------------------------

    def _stack_panel(
        self, panel: dict[str, pd.DataFrame], field: str
    ) -> pd.DataFrame:
        """把 panel 里某列拼成 (date, symbol) 宽表。"""
        missing = [s for s in self.all_symbols if s not in panel]
        if missing:
            raise KeyError(f"panel 缺少标的: {missing}")
        cols = {s: panel[s][field] for s in self.all_symbols}
        df = pd.DataFrame(cols)
        df = df.sort_index()
        # 内连接对齐：所有标的都有数据的交易日
        df = df.dropna(how="any")
        return df

    @staticmethod
    def _month_first_trading_days(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
        """每个月在 index 上的第一个交易日。"""
        s = pd.Series(index.values, index=index)
        firsts = s.groupby(index.to_period("M")).min()
        return pd.DatetimeIndex(firsts.values)

    # ------------------------------------------------------------------
    # 核心：纯 python 模拟（smoke test 用）
    # ------------------------------------------------------------------

    def simulate(self, panel: dict[str, pd.DataFrame]) -> DCASwingResult:
        """不依赖 vectorbt 的纯 python/pandas 回测。

        - 每日按 close 估值
        - 信号判定基于 T 日 close；下单按 T+1 open + slippage 成交
        - 收/付佣金按成交额 × fees
        - 现金不足时按可用份额比例缩单（防负持仓）
        """
        close = self._stack_panel(panel, "close")
        open_ = self._stack_panel(panel, "open")
        # 对齐
        close, open_ = close.align(open_, join="inner")
        index = close.index
        symbols = list(close.columns)
        cash_idx = symbols.index(self.cash_symbol)
        risk_idx = [symbols.index(s) for s in self.risk_symbols]

        n_days = len(index)
        n_sym = len(symbols)

        # 起始：全部 initial_cash 买入 511990（货基），形成「现金缓冲」
        shares = np.zeros(n_sym, dtype=float)
        first_open = open_.iloc[0].values
        first_open_eff = first_open * (1 + self.slippage)
        shares[cash_idx] = self.initial_cash / first_open_eff[cash_idx]
        # 起始日的「初始买入货基」也算一次买入交易
        orders_log: list[dict] = [
            {
                "date": index[0],
                "symbol": self.cash_symbol,
                "size": shares[cash_idx],
                "kind": "init_buy",
                "price": first_open_eff[cash_idx],
            }
        ]

        # 月度 DCA 触发日（次日开盘成交）
        month_firsts = set(self._month_first_trading_days(index))

        # cooldown：每个 symbol 的下一次可触发日 index
        next_allowed_idx = {s: 0 for s in self.risk_symbols}

        holdings_hist = np.zeros((n_days, n_sym), dtype=float)
        weights_hist = np.zeros((n_days, n_sym), dtype=float)
        nav_hist = np.zeros(n_days, dtype=float)

        # 待执行队列：T 日决策，T+1 执行
        pending_dca = False  # 是否要在下一日做月度 DCA
        pending_rebalance: list[tuple[str, float]] = []  # (symbol, signed_amount_in_rmb)

        for t in range(n_days):
            # ---- 上日决策的执行（T+1 open 成交）----
            day_open = open_.iloc[t].values

            if pending_dca:
                # 把 monthly_dca_amount 从货基里取出，等额买 6 只风险 ETF
                per_amount = self.monthly_dca_amount / len(self.risk_symbols)
                # 卖出货基（不含滑点；货基视作 NAV ~恒定，但仍按 open 成交）
                cash_sell_price = day_open[cash_idx] * (1 - self.slippage)
                cash_sell_size = self.monthly_dca_amount / cash_sell_price
                # 不能卖超过持仓
                cash_sell_size = min(cash_sell_size, shares[cash_idx])
                shares[cash_idx] -= cash_sell_size
                # 扣佣
                shares[cash_idx] -= (cash_sell_size * cash_sell_price * self.fees) / day_open[cash_idx]
                orders_log.append(
                    {
                        "date": index[t],
                        "symbol": self.cash_symbol,
                        "size": -cash_sell_size,
                        "kind": "dca_cash_out",
                        "price": cash_sell_price,
                    }
                )
                # 买入 6 只 ETF
                for ri, s in zip(risk_idx, self.risk_symbols, strict=True):
                    buy_price = day_open[ri] * (1 + self.slippage)
                    buy_size = per_amount / buy_price
                    fee_cost = per_amount * self.fees
                    # 把 fee 当作从货基里扣
                    fee_in_cash_size = fee_cost / day_open[cash_idx]
                    shares[cash_idx] = max(0.0, shares[cash_idx] - fee_in_cash_size)
                    shares[ri] += buy_size
                    orders_log.append(
                        {
                            "date": index[t],
                            "symbol": s,
                            "size": buy_size,
                            "kind": "dca_buy",
                            "price": buy_price,
                        }
                    )
                pending_dca = False

            if pending_rebalance:
                for s, amount in pending_rebalance:
                    sym_i = symbols.index(s)
                    if amount > 0:  # 加仓（低吸）：从货基取 amount → 买 ETF
                        buy_price = day_open[sym_i] * (1 + self.slippage)
                        cash_sell_price = day_open[cash_idx] * (1 - self.slippage)
                        # 现金不足时缩单
                        max_cash = shares[cash_idx] * cash_sell_price
                        amount_eff = min(amount, max_cash)
                        if amount_eff <= 0:
                            continue
                        shares[cash_idx] -= amount_eff / cash_sell_price
                        shares[sym_i] += amount_eff / buy_price
                        # 佣金
                        fee_cost = amount_eff * self.fees * 2  # 两腿都扣
                        shares[cash_idx] = max(
                            0.0, shares[cash_idx] - fee_cost / day_open[cash_idx]
                        )
                        orders_log.append(
                            {
                                "date": index[t],
                                "symbol": s,
                                "size": amount_eff / buy_price,
                                "kind": "swing_buy",
                                "price": buy_price,
                            }
                        )
                    elif amount < 0:  # 减仓（高抛）：卖 ETF → 入货基
                        sell_price = day_open[sym_i] * (1 - self.slippage)
                        cash_buy_price = day_open[cash_idx] * (1 + self.slippage)
                        amount_abs = -amount
                        # 持仓不足时缩单
                        max_amount = shares[sym_i] * sell_price
                        amount_eff = min(amount_abs, max_amount)
                        if amount_eff <= 0:
                            continue
                        shares[sym_i] -= amount_eff / sell_price
                        shares[cash_idx] += amount_eff / cash_buy_price
                        fee_cost = amount_eff * self.fees * 2
                        shares[cash_idx] = max(
                            0.0, shares[cash_idx] - fee_cost / day_open[cash_idx]
                        )
                        orders_log.append(
                            {
                                "date": index[t],
                                "symbol": s,
                                "size": -amount_eff / sell_price,
                                "kind": "swing_sell",
                                "price": sell_price,
                            }
                        )
                pending_rebalance = []

            # ---- T 日盘后估值 + 决策 ----
            day_close = close.iloc[t].values
            mkt_value = shares * day_close
            nav = float(mkt_value.sum())
            nav_hist[t] = nav
            holdings_hist[t] = shares
            weights_hist[t] = mkt_value / nav if nav > 0 else 0.0

            # 决策 1：明天是否月度 DCA？
            # 用「下一个 index 是月初」判定
            if t + 1 < n_days and index[t + 1] in month_firsts:
                pending_dca = True

            # 决策 2：阈值触发再平衡（基于 T 日收盘权重）
            if t + 1 < n_days:  # 没有「下一日」就别决策了
                w_target = self.per_risk_weight
                upper = w_target * (1 + self.rel_band)
                lower = w_target * (1 - self.rel_band)
                for s, ri in zip(self.risk_symbols, risk_idx, strict=True):
                    if t < next_allowed_idx[s]:
                        continue
                    w_i = weights_hist[t, ri]
                    if w_i > upper:
                        # 高抛：把偏离的 adjust_ratio 部分卖回目标
                        excess = (w_i - w_target) * nav
                        amount = -excess * self.adjust_ratio
                        if abs(amount) >= 1.0:  # 小于 1 块的不动
                            pending_rebalance.append((s, amount))
                            next_allowed_idx[s] = t + 1 + self.cooldown_days
                    elif w_i < lower and w_i > 0:
                        # 低吸（仅在已建仓后）：从货基取钱补 ETF
                        deficit = (w_target - w_i) * nav
                        amount = deficit * self.adjust_ratio
                        if amount >= 1.0:
                            pending_rebalance.append((s, amount))
                            next_allowed_idx[s] = t + 1 + self.cooldown_days

        holdings = pd.DataFrame(holdings_hist, index=index, columns=symbols)
        weights = pd.DataFrame(weights_hist, index=index, columns=symbols)
        nav_series = pd.Series(nav_hist, index=index, name="nav")
        orders_df = pd.DataFrame(orders_log)

        metrics = self._compute_metrics(nav_series)
        diagnostics = {
            "n_dca_events": int((orders_df["kind"] == "dca_buy").sum()),
            "n_swing_buy": int((orders_df["kind"] == "swing_buy").sum()),
            "n_swing_sell": int((orders_df["kind"] == "swing_sell").sum()),
            "final_nav": float(nav_series.iloc[-1]),
            "final_cash_weight": float(weights[self.cash_symbol].iloc[-1]),
            "final_risk_weight": float(
                weights[list(self.risk_symbols)].iloc[-1].sum()
            ),
        }
        return DCASwingResult(
            portfolio=None,
            holdings=holdings,
            weights=weights,
            nav=nav_series,
            orders=orders_df,
            metrics=metrics,
            diagnostics=diagnostics,
        )

    # ------------------------------------------------------------------
    # 真实回测入口（vectorbt）
    # ------------------------------------------------------------------

    def run(self, panel: dict[str, pd.DataFrame]) -> DCASwingResult:
        """真实回测：先用 ``simulate`` 跑出 size 序列，再喂给 vbt.Portfolio.from_orders。

        当前 V1 只用 ``simulate`` 的 NAV 和 orders 出指标；
        如需 vbt 的 trade analyzer，可在装好依赖后启用 ``_run_with_vbt``。
        """
        result = self.simulate(panel)
        # 尝试构造 vbt Portfolio（依赖未装时安静跳过）
        try:
            result.portfolio = self._run_with_vbt(panel, result)
        except ImportError:
            result.portfolio = None
        return result

    def _run_with_vbt(self, panel: dict[str, pd.DataFrame], sim: DCASwingResult):
        """把 simulate 产生的 orders 转 vbt Portfolio。"""
        import vectorbt as vbt  # noqa: F401

        close = self._stack_panel(panel, "close")
        open_ = self._stack_panel(panel, "open")
        size = pd.DataFrame(0.0, index=close.index, columns=close.columns)
        for _, row in sim.orders.iterrows():
            size.loc[row["date"], row["symbol"]] += row["size"]

        pf = vbt.Portfolio.from_orders(
            close=close,
            size=size,
            price=open_,
            init_cash=self.initial_cash,
            fees=self.fees,
            slippage=self.slippage,
            cash_sharing=True,
            group_by=True,
            freq="1D",
        )
        return pf

    # ------------------------------------------------------------------
    # 指标计算
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_metrics(nav: pd.Series) -> dict:
        """从 NAV 序列算共享基线要求的核心指标。"""
        if len(nav) < 2:
            return {}
        rets = nav.pct_change().dropna()
        total_return = float(nav.iloc[-1] / nav.iloc[0] - 1)
        # 假设交易日 252
        ann_factor = 252
        ann_ret = float((1 + total_return) ** (ann_factor / max(len(rets), 1)) - 1)
        ann_vol = float(rets.std(ddof=0) * np.sqrt(ann_factor))
        sharpe = float(ann_ret / ann_vol) if ann_vol > 0 else float("nan")
        # 最大回撤
        roll_max = nav.cummax()
        dd = nav / roll_max - 1
        max_dd = float(dd.min())
        calmar = float(ann_ret / abs(max_dd)) if max_dd < 0 else float("nan")
        return {
            "total_return": total_return,
            "annual_return": ann_ret,
            "annual_vol": ann_vol,
            "sharpe": sharpe,
            "max_drawdown": max_dd,
            "calmar": calmar,
            "n_days": int(len(nav)),
        }


__all__ = [
    "DCASwingStrategy",
    "DCASwingResult",
    "DEFAULT_CASH_SYMBOL",
    "DEFAULT_RISK_SYMBOLS",
]
