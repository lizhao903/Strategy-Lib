"""Strategy 6 — A股 ETF 价值平均法（Value Averaging, VA）。

S6 跳出 DCA 框架（S1/S2/S2v2 共享的"按固定金额定投"），改为按**目标 NAV 路径**定投：
每月第一个交易日 T 收盘评估当下 NAV 与目标 NAV 的差额：

    target(t) = init_cash × (1 + cagr_target / 12) ** months_elapsed   (复利路径，B 方案)
    gap = target(t) - NAV(t)

    gap > 0  → 从货币池抽 min(gap, max_buy_per_period, cash_value) 等额买入 6 只 ETF
    gap < 0  → 等比例减仓 6 只风险 ETF，回流货币池，金额 min(|gap|, max_sell_per_period)
    |gap| ≤ min_action_amount → 跳过

设计要点（回应 S2 v2 的「DCA 框架下不可能对称」结论）：
- 锚点：从「资产权重」（S2）切换到「NAV 路径」 → 机制层天然对称（差>0 买、差<0 卖）
- 刹车：货币池触底时拒绝杠杆，VA 退化为"全在风险池"的静态状态
- 单月上限：max_buy_per_period / max_sell_per_period 防止极端市场单次砸光货币池

不依赖 vectorbt 主真值；vbt 仅用于辅助 trade analyzer（不存在时降级）。
T 日决策、T+1 open + slippage 成交（与 S1/S2 一致防未来函数）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# 常量：共享基线（与 S1/S2 一致）
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
class ValueAveragingResult:
    """Strategy 6 VA 自包含运行结果。"""

    portfolio: object | None
    holdings: pd.DataFrame
    weights: pd.DataFrame
    nav: pd.Series
    target: pd.Series           # 目标 NAV 序列（仅在月度决策日有定义；其他日 forward-fill）
    orders: pd.DataFrame
    metrics: dict
    diagnostics: dict = field(default_factory=dict)
    actions: pd.DataFrame | None = None  # 每月动作日志：date / mode (BUY/SELL/SKIP) / gap / amount
    cash_exhausted_date: pd.Timestamp | None = None


# ---------------------------------------------------------------------------
# Strategy 类（不继承 S1/S2，独立实现）
# ---------------------------------------------------------------------------


class ValueAveragingStrategy:
    """价值平均法（VA）—— 按目标 NAV 路径定投。

    Parameters
    ----------
    cash_symbol, risk_symbols : 同 S1/S2 共享基线
    initial_cash : 起始资金（默认 100,000）
    fees, slippage : 同共享基线（万 0.5 / 万 5）
    cagr_target : 目标年化收益率，复利路径的核心参数（默认 0.08）
    max_buy_per_period : 单月最大买入 RMB（默认 15000）
    max_sell_per_period : 单月最大卖出 RMB（默认 15000）
    min_action_amount : 单月动作下限（小于此则跳过；默认 500）
    target_path_kind : 目标路径函数类型，"compound"（默认）/ "linear" / "compound_floor"
        - compound: target = init × (1 + cagr/12)^m  ← 默认 B 方案
        - linear: target = init × (1 + cagr × m / 12) （线性增长，A 方案）
        - compound_floor: target = max(init, compound) （C 方案）
    """

    def __init__(
        self,
        *,
        cash_symbol: str = DEFAULT_CASH_SYMBOL,
        risk_symbols: Iterable[str] = DEFAULT_RISK_SYMBOLS,
        initial_cash: float = 100_000.0,
        fees: float = 0.00005,
        slippage: float = 0.0005,
        cagr_target: float = 0.08,
        max_buy_per_period: float = 15_000.0,
        max_sell_per_period: float = 15_000.0,
        min_action_amount: float = 500.0,
        target_path_kind: str = "compound",
        name: str = "cn_etf_value_averaging",
    ) -> None:
        self.cash_symbol = cash_symbol
        self.risk_symbols = tuple(risk_symbols)

        if initial_cash <= 0:
            raise ValueError("initial_cash 必须为正")
        if not -0.5 < cagr_target < 1.0:
            raise ValueError("cagr_target 必须在 (-0.5, 1.0)")
        if max_buy_per_period <= 0:
            raise ValueError("max_buy_per_period 必须为正")
        if max_sell_per_period <= 0:
            raise ValueError("max_sell_per_period 必须为正")
        if min_action_amount < 0:
            raise ValueError("min_action_amount 不能为负")
        if target_path_kind not in {"compound", "linear", "compound_floor"}:
            raise ValueError(
                f"target_path_kind 必须是 'compound' / 'linear' / 'compound_floor'，"
                f"收到 {target_path_kind!r}"
            )

        self.initial_cash = float(initial_cash)
        self.fees = float(fees)
        self.slippage = float(slippage)
        self.cagr_target = float(cagr_target)
        self.max_buy_per_period = float(max_buy_per_period)
        self.max_sell_per_period = float(max_sell_per_period)
        self.min_action_amount = float(min_action_amount)
        self.target_path_kind = target_path_kind

        self.name = name

    # ------------------------------------------------------------------
    # 公共属性
    # ------------------------------------------------------------------

    @property
    def all_symbols(self) -> tuple[str, ...]:
        return (self.cash_symbol, *self.risk_symbols)

    # ------------------------------------------------------------------
    # 数据准备
    # ------------------------------------------------------------------

    def _stack_panel(self, panel: dict[str, pd.DataFrame], field_name: str) -> pd.DataFrame:
        missing = [s for s in self.all_symbols if s not in panel]
        if missing:
            raise KeyError(f"panel 缺少标的: {missing}")
        cols = {s: panel[s][field_name] for s in self.all_symbols}
        df = pd.DataFrame(cols).sort_index().dropna(how="any")
        return df

    @staticmethod
    def _month_first_trading_days(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
        s = pd.Series(index.values, index=index)
        firsts = s.groupby(index.to_period("M")).min()
        return pd.DatetimeIndex(firsts.values)

    def _target_value(self, months_elapsed: int) -> float:
        """目标 NAV 路径函数。"""
        m = max(int(months_elapsed), 0)
        if self.target_path_kind == "compound":
            return self.initial_cash * (1.0 + self.cagr_target / 12.0) ** m
        if self.target_path_kind == "linear":
            return self.initial_cash * (1.0 + self.cagr_target * m / 12.0)
        if self.target_path_kind == "compound_floor":
            v = self.initial_cash * (1.0 + self.cagr_target / 12.0) ** m
            return max(self.initial_cash, v)
        raise AssertionError("unreachable")

    # ------------------------------------------------------------------
    # 核心：纯 python 模拟
    # ------------------------------------------------------------------

    def simulate(self, panel: dict[str, pd.DataFrame]) -> ValueAveragingResult:
        close = self._stack_panel(panel, "close")
        open_ = self._stack_panel(panel, "open")
        close, open_ = close.align(open_, join="inner")
        index = close.index
        symbols = list(close.columns)
        cash_idx = symbols.index(self.cash_symbol)
        risk_idx = [symbols.index(s) for s in self.risk_symbols]

        n_days = len(index)
        n_sym = len(symbols)

        # 起始：全部 initial_cash 买入 511990
        shares = np.zeros(n_sym, dtype=float)
        first_open = open_.iloc[0].values
        first_open_eff = first_open * (1 + self.slippage)
        shares[cash_idx] = self.initial_cash / first_open_eff[cash_idx]
        orders_log: list[dict] = [
            {
                "date": index[0],
                "symbol": self.cash_symbol,
                "size": shares[cash_idx],
                "kind": "init_buy",
                "price": first_open_eff[cash_idx],
                "amount": shares[cash_idx] * first_open_eff[cash_idx],
            }
        ]

        month_firsts = self._month_first_trading_days(index)
        month_first_set = set(month_firsts)
        first_month = index[0].to_period("M")

        holdings_hist = np.zeros((n_days, n_sym), dtype=float)
        weights_hist = np.zeros((n_days, n_sym), dtype=float)
        nav_hist = np.zeros(n_days, dtype=float)
        target_hist = np.full(n_days, np.nan, dtype=float)

        # pending action：在 T 收盘决定，下一个交易日 T+1 开盘成交
        # 形如 ("BUY"|"SELL", amount, gap, target, decision_date)
        pending: tuple | None = None
        actions_log: list[dict] = []
        cash_exhausted_date: pd.Timestamp | None = None

        for t in range(n_days):
            day_open = open_.iloc[t].values

            # ---- 执行 pending action（T+1 开盘成交） ----
            if pending is not None:
                kind, amount, gap, target_val, decision_date = pending
                if kind == "BUY" and amount > 0:
                    # 货币池兑现：每只 ETF 买 amount/6
                    cash_value = float(shares[cash_idx] * day_open[cash_idx])
                    actual_amount = min(amount, cash_value)
                    actual_per = actual_amount / len(self.risk_symbols)
                    if actual_amount >= self.min_action_amount:
                        cash_sell_price = day_open[cash_idx] * (1 - self.slippage)
                        cash_sell_size = actual_amount / cash_sell_price
                        cash_sell_size = min(cash_sell_size, shares[cash_idx])
                        shares[cash_idx] -= cash_sell_size
                        # 卖货基的费用直接从货基扣
                        fee_cost_total = actual_amount * self.fees
                        shares[cash_idx] = max(
                            0.0,
                            shares[cash_idx] - fee_cost_total / day_open[cash_idx],
                        )
                        orders_log.append(
                            {
                                "date": index[t],
                                "symbol": self.cash_symbol,
                                "size": -cash_sell_size,
                                "kind": "va_cash_out",
                                "price": cash_sell_price,
                                "amount": actual_amount,
                            }
                        )
                        for ri, s in zip(risk_idx, self.risk_symbols, strict=True):
                            buy_price = day_open[ri] * (1 + self.slippage)
                            buy_size = actual_per / buy_price
                            shares[ri] += buy_size
                            # 买入端的成本（再次万 0.5）从货基里扣
                            fee_buy = actual_per * self.fees
                            shares[cash_idx] = max(
                                0.0,
                                shares[cash_idx] - fee_buy / day_open[cash_idx],
                            )
                            orders_log.append(
                                {
                                    "date": index[t],
                                    "symbol": s,
                                    "size": buy_size,
                                    "kind": "va_buy",
                                    "price": buy_price,
                                    "amount": actual_per,
                                }
                            )
                        actions_log.append(
                            {
                                "date": decision_date,
                                "execute_date": index[t],
                                "mode": "BUY",
                                "gap": gap,
                                "target": target_val,
                                "amount_planned": amount,
                                "amount_actual": actual_amount,
                            }
                        )
                        # 货币池耗尽时点（首次跌至 0）
                        if (
                            cash_exhausted_date is None
                            and shares[cash_idx] * day_open[cash_idx] < self.min_action_amount
                        ):
                            cash_exhausted_date = index[t]
                    else:
                        # 货币池不足：actual < min_action → 实际跳过；记录"BUY-NOOP"
                        actions_log.append(
                            {
                                "date": decision_date,
                                "execute_date": index[t],
                                "mode": "BUY_NOOP",
                                "gap": gap,
                                "target": target_val,
                                "amount_planned": amount,
                                "amount_actual": 0.0,
                            }
                        )
                        if cash_exhausted_date is None:
                            cash_exhausted_date = index[t]
                elif kind == "SELL" and amount > 0:
                    # 卖出：按当下市值比例分摊到 6 只 ETF
                    risk_values = np.array(
                        [shares[ri] * day_open[ri] for ri in risk_idx], dtype=float
                    )
                    risk_total = float(risk_values.sum())
                    if risk_total >= self.min_action_amount:
                        actual_amount = min(amount, risk_total)
                        proportions = risk_values / risk_total if risk_total > 0 else np.zeros(
                            len(risk_idx)
                        )
                        for ri, s, p in zip(
                            risk_idx, self.risk_symbols, proportions, strict=True
                        ):
                            sell_amount = actual_amount * p
                            if sell_amount < 1e-9:
                                continue
                            sell_price = day_open[ri] * (1 - self.slippage)
                            max_sell = shares[ri] * sell_price
                            sell_eff = min(sell_amount, max_sell)
                            shares[ri] -= sell_eff / sell_price
                            cash_buy_price = day_open[cash_idx] * (1 + self.slippage)
                            shares[cash_idx] += sell_eff / cash_buy_price
                            fee_sell = sell_eff * self.fees * 2  # 卖 ETF + 买货基
                            shares[cash_idx] = max(
                                0.0,
                                shares[cash_idx] - fee_sell / day_open[cash_idx],
                            )
                            orders_log.append(
                                {
                                    "date": index[t],
                                    "symbol": s,
                                    "size": -sell_eff / sell_price,
                                    "kind": "va_sell",
                                    "price": sell_price,
                                    "amount": sell_eff,
                                }
                            )
                        actions_log.append(
                            {
                                "date": decision_date,
                                "execute_date": index[t],
                                "mode": "SELL",
                                "gap": gap,
                                "target": target_val,
                                "amount_planned": amount,
                                "amount_actual": actual_amount,
                            }
                        )
                pending = None

            # ---- 估值（T 日 close） ----
            day_close = close.iloc[t].values
            mkt_value = shares * day_close
            nav = float(mkt_value.sum())
            nav_hist[t] = nav
            holdings_hist[t] = shares
            weights_hist[t] = mkt_value / nav if nav > 0 else 0.0

            # ---- 决策：明天是月初 → 决定 pending action ----
            if t + 1 < n_days and index[t + 1] in month_first_set:
                # 月份编号：相对第一个月
                next_month = index[t + 1].to_period("M")
                months_elapsed = (next_month - first_month).n  # int
                target_val = self._target_value(months_elapsed)
                target_hist[t] = target_val
                gap = target_val - nav
                if gap > self.min_action_amount:
                    amount = min(gap, self.max_buy_per_period)
                    pending = ("BUY", amount, gap, target_val, index[t])
                elif gap < -self.min_action_amount:
                    amount = min(-gap, self.max_sell_per_period)
                    pending = ("SELL", amount, gap, target_val, index[t])
                else:
                    actions_log.append(
                        {
                            "date": index[t],
                            "execute_date": (
                                index[t + 1] if t + 1 < n_days else index[t]
                            ),
                            "mode": "SKIP",
                            "gap": gap,
                            "target": target_val,
                            "amount_planned": 0.0,
                            "amount_actual": 0.0,
                        }
                    )

        # forward fill target series（决策日填值；其它日复用上一个）
        target_series = pd.Series(target_hist, index=index, name="target_nav")
        target_series = target_series.ffill()
        # 起始第一天填 init_cash
        target_series = target_series.fillna(self.initial_cash)

        holdings = pd.DataFrame(holdings_hist, index=index, columns=symbols)
        weights = pd.DataFrame(weights_hist, index=index, columns=symbols)
        nav_series = pd.Series(nav_hist, index=index, name="nav")
        orders_df = pd.DataFrame(orders_log)
        actions_df = pd.DataFrame(actions_log) if actions_log else pd.DataFrame(
            columns=[
                "date",
                "execute_date",
                "mode",
                "gap",
                "target",
                "amount_planned",
                "amount_actual",
            ]
        )

        metrics = self._compute_metrics(nav_series)

        n_buy = int((orders_df["kind"] == "va_buy").sum())
        n_sell = int((orders_df["kind"] == "va_sell").sum())
        n_buy_actions = int((actions_df["mode"] == "BUY").sum()) if not actions_df.empty else 0
        n_sell_actions = int((actions_df["mode"] == "SELL").sum()) if not actions_df.empty else 0
        n_skip_actions = int((actions_df["mode"] == "SKIP").sum()) if not actions_df.empty else 0
        n_noop_actions = (
            int((actions_df["mode"] == "BUY_NOOP").sum()) if not actions_df.empty else 0
        )

        diagnostics = {
            "n_va_buy_orders": n_buy,
            "n_va_sell_orders": n_sell,
            "n_buy_months": n_buy_actions,
            "n_sell_months": n_sell_actions,
            "n_skip_months": n_skip_actions,
            "n_noop_months": n_noop_actions,  # 货币池耗尽导致的"想买买不到"
            "buy_sell_ratio": (
                n_sell_actions / n_buy_actions if n_buy_actions > 0 else float("inf")
            ),
            "final_nav": float(nav_series.iloc[-1]),
            "final_target": float(target_series.iloc[-1]),
            "final_cash_weight": float(weights[self.cash_symbol].iloc[-1]),
            "final_risk_weight": float(weights[list(self.risk_symbols)].iloc[-1].sum()),
            "cash_exhausted_date": (
                str(cash_exhausted_date.date()) if cash_exhausted_date is not None else None
            ),
            "cagr_target": self.cagr_target,
            "target_path_kind": self.target_path_kind,
        }

        return ValueAveragingResult(
            portfolio=None,
            holdings=holdings,
            weights=weights,
            nav=nav_series,
            target=target_series,
            orders=orders_df,
            metrics=metrics,
            diagnostics=diagnostics,
            actions=actions_df,
            cash_exhausted_date=cash_exhausted_date,
        )

    # ------------------------------------------------------------------
    # 真实回测入口（vectorbt 可选）
    # ------------------------------------------------------------------

    def run(self, panel: dict[str, pd.DataFrame]) -> ValueAveragingResult:
        result = self.simulate(panel)
        try:
            result.portfolio = self._run_with_vbt(panel, result)
        except ImportError:
            result.portfolio = None
        return result

    def _run_with_vbt(self, panel: dict[str, pd.DataFrame], sim: ValueAveragingResult):
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
    # 指标计算（与 S2 v2 同公式）
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_metrics(nav: pd.Series) -> dict:
        if len(nav) < 2:
            return {}
        rets = nav.pct_change().dropna()
        total_return = float(nav.iloc[-1] / nav.iloc[0] - 1)
        ann_factor = 252
        ann_ret = float((1 + total_return) ** (ann_factor / max(len(rets), 1)) - 1)
        ann_vol = float(rets.std(ddof=0) * np.sqrt(ann_factor))
        sharpe = float(ann_ret / ann_vol) if ann_vol > 0 else float("nan")
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
    "ValueAveragingStrategy",
    "ValueAveragingResult",
    "DEFAULT_CASH_SYMBOL",
    "DEFAULT_RISK_SYMBOLS",
]
