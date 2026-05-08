"""Strategy 2 V2 — A股 ETF DCA + 阈值再平衡（做T） V2 版本。

V1 → V2 改进（解决 v1 的高抛/低吸不对称结构性偏差）：

A. **DCA 优先回流（DCA-priority routing）**：
   月度 DCA 不再机械等额买入。先看当下风险池总权重 ``w_risk`` 与目标 ``risk_target_weight``：
   - ``w_risk > target × (1 + dca_band_high)`` → DCA OFF（5000 留在 511990 不动）
   - ``w_risk < target × (1 - dca_band_low)`` → DCA BOOST（5000 × dca_boost_factor）
   - 否则 → DCA NORMAL（与 v1 相同）

   核心目的：DCA 净流入是 v1 高抛偏置的根因；v2 让 DCA 自身具备「双向调节」属性，
   让 swing 不再被迫承担「上沿调节」的单边任务。

C. **波动率自适应阈值（vol-adaptive band）**：
   ``band_t = clip(vol_band_coef × vol_ann_60d, vol_band_min, vol_band_max)``
   其中 ``vol_ann_60d`` 是过去 60 个交易日组合 NAV pct_change 的标准差 × sqrt(252)。
   warmup 期（前 60 日）固定使用 ``warmup_band``。

   核心目的：低波时更敏感（多刷震荡 alpha），高波时放宽（避免"越跌越买"反复套牢）。

不变的部分（与 v1 一致）：
- 标的池、初始资金、月度 DCA 频次、cooldown_days、adjust_ratio、目标风险权重 0.70
- T 日决策、T+1 open + slippage 成交（无未来函数）
- vbt Portfolio 构建可选（依赖未装时降级）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# 常量：共享基线（与 v1 一致）
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
class DCASwingV2Result:
    """Strategy 2 V2 自包含运行结果。"""

    portfolio: object | None
    holdings: pd.DataFrame
    weights: pd.DataFrame
    nav: pd.Series
    orders: pd.DataFrame
    metrics: dict
    diagnostics: dict = field(default_factory=dict)
    band_t: pd.Series | None = None  # 当日 swing 阈值（v2 特有）
    dca_modes: pd.Series | None = None  # 每个 DCA 触发日的模式标签（v2 特有）


# ---------------------------------------------------------------------------
# V2 策略类（不继承 v1，避免 v1 的 bug 传染）
# ---------------------------------------------------------------------------


class DCASwingV2Strategy:
    """DCA + 阈值再平衡 V2：DCA 优先回流 + 波动率自适应阈值。

    Parameters
    ----------
    cash_symbol, risk_symbols, risk_target_weight, monthly_dca_amount,
    adjust_ratio, cooldown_days, initial_cash, fees, slippage:
        与 v1 同名参数语义一致。

    dca_band_high:
        DCA OFF 触发的上沿余地（默认 0.05）。当 ``w_risk > target × (1 + dca_band_high)``
        时月度 DCA 停灌。
    dca_band_low:
        DCA BOOST 触发的下沿余地（默认 0.05）。当 ``w_risk < target × (1 - dca_band_low)``
        时月度 DCA 加速。
    dca_boost_factor:
        BOOST 模式下 DCA 金额的乘数（默认 1.5）。
    vol_lookback:
        计算实现波动率的回看天数（默认 60）。
    vol_band_coef:
        ``band_t = coef × vol_ann`` 的系数（默认 0.60）。
    vol_band_min, vol_band_max:
        ``band_t`` 的 clip 区间（默认 [0.10, 0.30]）。
    warmup_band:
        warmup（vol 数据不足）期间使用的固定阈值（默认 0.20，与 v1 一致便于早期 NAV 对比）。
    """

    def __init__(
        self,
        *,
        cash_symbol: str = DEFAULT_CASH_SYMBOL,
        risk_symbols: Iterable[str] = DEFAULT_RISK_SYMBOLS,
        risk_target_weight: float = 0.70,
        monthly_dca_amount: float = 5_000.0,
        adjust_ratio: float = 0.50,
        cooldown_days: int = 5,
        initial_cash: float = 100_000.0,
        fees: float = 0.00005,
        slippage: float = 0.0005,
        # v2 新参数
        dca_band_high: float = 0.05,
        dca_band_low: float = 0.05,
        dca_boost_factor: float = 1.5,
        vol_lookback: int = 60,
        vol_band_coef: float = 0.60,
        vol_band_min: float = 0.10,
        vol_band_max: float = 0.30,
        warmup_band: float = 0.20,
        name: str = "cn_etf_dca_swing_v2",
    ) -> None:
        self.cash_symbol = cash_symbol
        self.risk_symbols = tuple(risk_symbols)

        if not 0.0 < risk_target_weight <= 1.0:
            raise ValueError("risk_target_weight 必须在 (0, 1]")
        if not 0.0 < adjust_ratio <= 1.0:
            raise ValueError("adjust_ratio 必须在 (0, 1]")
        if cooldown_days < 0:
            raise ValueError("cooldown_days 不能为负")
        if not 0.0 <= dca_band_high < 1.0:
            raise ValueError("dca_band_high 必须在 [0, 1)")
        if not 0.0 <= dca_band_low < 1.0:
            raise ValueError("dca_band_low 必须在 [0, 1)")
        if dca_boost_factor < 1.0:
            raise ValueError("dca_boost_factor 应 >= 1.0（否则 BOOST 反而减小）")
        if vol_lookback < 5:
            raise ValueError("vol_lookback 至少 5 日")
        if not 0.0 < vol_band_min < vol_band_max < 1.0:
            raise ValueError("需 0 < vol_band_min < vol_band_max < 1")
        if not 0.0 < warmup_band < 1.0:
            raise ValueError("warmup_band 必须在 (0, 1)")

        self.risk_target_weight = float(risk_target_weight)
        self.monthly_dca_amount = float(monthly_dca_amount)
        self.adjust_ratio = float(adjust_ratio)
        self.cooldown_days = int(cooldown_days)
        self.initial_cash = float(initial_cash)
        self.fees = float(fees)
        self.slippage = float(slippage)

        self.dca_band_high = float(dca_band_high)
        self.dca_band_low = float(dca_band_low)
        self.dca_boost_factor = float(dca_boost_factor)
        self.vol_lookback = int(vol_lookback)
        self.vol_band_coef = float(vol_band_coef)
        self.vol_band_min = float(vol_band_min)
        self.vol_band_max = float(vol_band_max)
        self.warmup_band = float(warmup_band)

        self.name = name

    # ------------------------------------------------------------------
    # 公共属性
    # ------------------------------------------------------------------

    @property
    def per_risk_weight(self) -> float:
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
        missing = [s for s in self.all_symbols if s not in panel]
        if missing:
            raise KeyError(f"panel 缺少标的: {missing}")
        cols = {s: panel[s][field] for s in self.all_symbols}
        df = pd.DataFrame(cols).sort_index().dropna(how="any")
        return df

    @staticmethod
    def _month_first_trading_days(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
        s = pd.Series(index.values, index=index)
        firsts = s.groupby(index.to_period("M")).min()
        return pd.DatetimeIndex(firsts.values)

    # ------------------------------------------------------------------
    # 核心：纯 python 模拟
    # ------------------------------------------------------------------

    def simulate(self, panel: dict[str, pd.DataFrame]) -> DCASwingV2Result:
        """V2 simulate（不依赖 vectorbt）。"""
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
            }
        ]

        month_firsts = set(self._month_first_trading_days(index))

        next_allowed_idx = {s: 0 for s in self.risk_symbols}

        holdings_hist = np.zeros((n_days, n_sym), dtype=float)
        weights_hist = np.zeros((n_days, n_sym), dtype=float)
        nav_hist = np.zeros(n_days, dtype=float)
        band_hist = np.full(n_days, np.nan, dtype=float)

        pending_dca: str | None = None  # None | "NORMAL" | "OFF" | "BOOST"
        pending_rebalance: list[tuple[str, float]] = []
        dca_mode_log: list[dict] = []  # {date, mode, w_risk, dca_amount}

        # NAV diff 用于 vol 计算（rolling 60d）
        # 我们在每个 t 算「过去 vol_lookback 日」的 std，用 nav_hist[:t] 现成数据，避免未来函数

        for t in range(n_days):
            day_open = open_.iloc[t].values

            # ----  执行 pending DCA ----
            if pending_dca is not None:
                if pending_dca == "OFF":
                    # 啥都不做：5000 留在 511990
                    pass
                else:
                    dca_amount = self.monthly_dca_amount * (
                        self.dca_boost_factor if pending_dca == "BOOST" else 1.0
                    )
                    per_amount = dca_amount / len(self.risk_symbols)

                    cash_sell_price = day_open[cash_idx] * (1 - self.slippage)
                    cash_sell_size = dca_amount / cash_sell_price
                    cash_sell_size = min(cash_sell_size, shares[cash_idx])
                    actual_amount = cash_sell_size * cash_sell_price
                    shares[cash_idx] -= cash_sell_size
                    shares[cash_idx] -= (
                        cash_sell_size * cash_sell_price * self.fees
                    ) / day_open[cash_idx]
                    orders_log.append(
                        {
                            "date": index[t],
                            "symbol": self.cash_symbol,
                            "size": -cash_sell_size,
                            "kind": "dca_cash_out",
                            "price": cash_sell_price,
                        }
                    )
                    # 等额买 6 只
                    actual_per = actual_amount / len(self.risk_symbols) if actual_amount > 0 else 0.0
                    for ri, s in zip(risk_idx, self.risk_symbols, strict=True):
                        if actual_per <= 0:
                            continue
                        buy_price = day_open[ri] * (1 + self.slippage)
                        buy_size = actual_per / buy_price
                        fee_cost = actual_per * self.fees
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
                pending_dca = None

            # ---- 执行 pending swing ----
            if pending_rebalance:
                for s, amount in pending_rebalance:
                    sym_i = symbols.index(s)
                    if amount > 0:
                        buy_price = day_open[sym_i] * (1 + self.slippage)
                        cash_sell_price = day_open[cash_idx] * (1 - self.slippage)
                        max_cash = shares[cash_idx] * cash_sell_price
                        amount_eff = min(amount, max_cash)
                        if amount_eff <= 0:
                            continue
                        shares[cash_idx] -= amount_eff / cash_sell_price
                        shares[sym_i] += amount_eff / buy_price
                        fee_cost = amount_eff * self.fees * 2
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
                    elif amount < 0:
                        sell_price = day_open[sym_i] * (1 - self.slippage)
                        cash_buy_price = day_open[cash_idx] * (1 + self.slippage)
                        amount_abs = -amount
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

            # ---- 估值 ----
            day_close = close.iloc[t].values
            mkt_value = shares * day_close
            nav = float(mkt_value.sum())
            nav_hist[t] = nav
            holdings_hist[t] = shares
            weights_hist[t] = mkt_value / nav if nav > 0 else 0.0

            # ---- 计算 T 日的 band_t（仅用 t 及之前的 NAV，避免未来函数） ----
            if t >= self.vol_lookback:
                window_nav = nav_hist[t - self.vol_lookback : t + 1]  # 含 t
                rets = np.diff(window_nav) / window_nav[:-1]
                rets = rets[np.isfinite(rets)]
                if len(rets) >= 5:
                    vol_ann = float(np.std(rets, ddof=0) * np.sqrt(252))
                    band_t = float(
                        np.clip(
                            self.vol_band_coef * vol_ann,
                            self.vol_band_min,
                            self.vol_band_max,
                        )
                    )
                else:
                    band_t = self.warmup_band
            else:
                band_t = self.warmup_band
            band_hist[t] = band_t

            # ---- 决策 1：明天月度 DCA？ ----
            if t + 1 < n_days and index[t + 1] in month_firsts:
                # 三态判定：基于 T 收盘的 w_risk
                w_risk = float(weights_hist[t, risk_idx].sum())
                target = self.risk_target_weight
                if w_risk > target * (1 + self.dca_band_high):
                    pending_dca = "OFF"
                    dca_amount = 0.0
                elif w_risk < target * (1 - self.dca_band_low):
                    pending_dca = "BOOST"
                    dca_amount = self.monthly_dca_amount * self.dca_boost_factor
                else:
                    pending_dca = "NORMAL"
                    dca_amount = self.monthly_dca_amount
                dca_mode_log.append(
                    {
                        "date": index[t + 1],
                        "mode": pending_dca,
                        "w_risk_at_decision": w_risk,
                        "dca_amount": dca_amount,
                    }
                )

            # ---- 决策 2：阈值触发再平衡 ----
            if t + 1 < n_days:
                w_target = self.per_risk_weight
                upper = w_target * (1 + band_t)
                lower = w_target * (1 - band_t)
                for s, ri in zip(self.risk_symbols, risk_idx, strict=True):
                    if t < next_allowed_idx[s]:
                        continue
                    w_i = weights_hist[t, ri]
                    if w_i > upper:
                        excess = (w_i - w_target) * nav
                        amount = -excess * self.adjust_ratio
                        if abs(amount) >= 1.0:
                            pending_rebalance.append((s, amount))
                            next_allowed_idx[s] = t + 1 + self.cooldown_days
                    elif w_i < lower and w_i > 0:
                        deficit = (w_target - w_i) * nav
                        amount = deficit * self.adjust_ratio
                        if amount >= 1.0:
                            pending_rebalance.append((s, amount))
                            next_allowed_idx[s] = t + 1 + self.cooldown_days

        holdings = pd.DataFrame(holdings_hist, index=index, columns=symbols)
        weights = pd.DataFrame(weights_hist, index=index, columns=symbols)
        nav_series = pd.Series(nav_hist, index=index, name="nav")
        orders_df = pd.DataFrame(orders_log)
        band_series = pd.Series(band_hist, index=index, name="band_t")
        dca_modes_df = pd.DataFrame(dca_mode_log) if dca_mode_log else pd.DataFrame(
            columns=["date", "mode", "w_risk_at_decision", "dca_amount"]
        )

        metrics = self._compute_metrics(nav_series)
        n_dca_normal = int((dca_modes_df["mode"] == "NORMAL").sum()) if not dca_modes_df.empty else 0
        n_dca_off = int((dca_modes_df["mode"] == "OFF").sum()) if not dca_modes_df.empty else 0
        n_dca_boost = int((dca_modes_df["mode"] == "BOOST").sum()) if not dca_modes_df.empty else 0
        diagnostics = {
            "n_dca_buy_orders": int((orders_df["kind"] == "dca_buy").sum()),
            "n_swing_buy": int((orders_df["kind"] == "swing_buy").sum()),
            "n_swing_sell": int((orders_df["kind"] == "swing_sell").sum()),
            "n_dca_normal": n_dca_normal,
            "n_dca_off": n_dca_off,
            "n_dca_boost": n_dca_boost,
            "final_nav": float(nav_series.iloc[-1]),
            "final_cash_weight": float(weights[self.cash_symbol].iloc[-1]),
            "final_risk_weight": float(weights[list(self.risk_symbols)].iloc[-1].sum()),
            "band_mean": float(band_series.iloc[self.vol_lookback:].mean())
            if len(band_series) > self.vol_lookback
            else float("nan"),
            "band_min": float(band_series.iloc[self.vol_lookback:].min())
            if len(band_series) > self.vol_lookback
            else float("nan"),
            "band_max": float(band_series.iloc[self.vol_lookback:].max())
            if len(band_series) > self.vol_lookback
            else float("nan"),
        }
        return DCASwingV2Result(
            portfolio=None,
            holdings=holdings,
            weights=weights,
            nav=nav_series,
            orders=orders_df,
            metrics=metrics,
            diagnostics=diagnostics,
            band_t=band_series,
            dca_modes=dca_modes_df,
        )

    # ------------------------------------------------------------------
    # 真实回测入口（vectorbt）
    # ------------------------------------------------------------------

    def run(self, panel: dict[str, pd.DataFrame]) -> DCASwingV2Result:
        result = self.simulate(panel)
        try:
            result.portfolio = self._run_with_vbt(panel, result)
        except ImportError:
            result.portfolio = None
        return result

    def _run_with_vbt(self, panel: dict[str, pd.DataFrame], sim: DCASwingV2Result):
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
    # 指标计算（与 v1 同公式）
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
    "DCASwingV2Strategy",
    "DCASwingV2Result",
    "DEFAULT_CASH_SYMBOL",
    "DEFAULT_RISK_SYMBOLS",
]
