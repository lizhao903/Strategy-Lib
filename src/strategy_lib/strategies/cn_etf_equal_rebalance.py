"""Strategy 3 — A股 ETF 等权 + 定时再平衡 (Benchmark Suite V1).

权重驱动策略。一次性满仓 6 只 ETF，每隔 N 个交易日再平衡回等权。
**S4 (动量倾斜) / S5 (趋势倾斜) 通过覆盖 `target_weights` 钩子复用本类。**

与 ``BaseStrategy``（信号驱动，from_signals）并行存在；本类直接走 vectorbt
的 ``Portfolio.from_orders`` API（``size_type="targetpercent"``）。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class EqualRebalanceResult:
    """权重驱动策略的回测结果。"""

    portfolio: object  # vectorbt Portfolio
    target_weights: pd.DataFrame  # index=date, columns=symbol；非 rebalance 日为 NaN
    rebalance_dates: pd.DatetimeIndex
    metrics: dict


class EqualRebalanceStrategy:
    """6 只 A股 ETF 等权 + 定时再平衡。

    设计要点
    --------
    1. **权重驱动**：每个 rebalance 触发日产生一个目标权重向量，期间持有不动。
    2. **target_weights() 是钩子方法**：S4/S5 子类应**只覆盖此方法**，不要改下单逻辑。
    3. **永远满仓**：权重和恒为 1（不留现金），与 S1/S2 的关键差异。
    4. **次日成交防未来函数**：vectorbt ``from_orders`` 默认在下一根 bar 成交，
       配合 ``target_weights`` 只读 ``date`` 当日及之前的价格 → 无 lookahead。
    """

    #: 默认 6 只 ETF（与 docs/benchmark_suite_v1.md 共享基线一致）
    DEFAULT_SYMBOLS: tuple[str, ...] = (
        "510300",  # 沪深300
        "510500",  # 中证500
        "159915",  # 创业板
        "512100",  # 中证1000
        "512880",  # 证券
        "512170",  # 医疗
    )

    def __init__(
        self,
        symbols: list[str] | tuple[str, ...] | None = None,
        *,
        rebalance_period: int = 20,
        drift_threshold: float | None = None,
        name: str = "cn_etf_equal_rebalance",
    ) -> None:
        """
        Parameters
        ----------
        symbols
            标的池。默认为 V1 基线 6 只 ETF。
        rebalance_period
            日历再平衡周期（交易日数）。默认 20（约月度）。
        drift_threshold
            漂移阈值。``None`` 表示纯日历再平衡（默认）。设为如 0.05 时，
            只有任一资产 ``|w_actual - w_target| > 0.05`` 才在 rebalance 候选日触发。
        name
            策略名（用于日志/标识）。
        """
        self.symbols: list[str] = list(symbols) if symbols is not None else list(self.DEFAULT_SYMBOLS)
        if rebalance_period < 1:
            raise ValueError("rebalance_period 必须 >= 1")
        if drift_threshold is not None and drift_threshold <= 0:
            raise ValueError("drift_threshold 必须 > 0 或为 None")
        self.rebalance_period = rebalance_period
        self.drift_threshold = drift_threshold
        self.name = name

    # ------------------------------------------------------------------ #
    # 钩子方法：S4 / S5 子类覆盖这个方法实现因子倾斜
    # ------------------------------------------------------------------ #
    def target_weights(
        self, date: pd.Timestamp, prices_panel: dict[str, pd.DataFrame]
    ) -> dict[str, float]:
        """返回 ``date`` 当日的目标权重向量。

        **这是给 S4 / S5 子类覆盖的钩子方法**。基类返回等权 1/n。

        Override in subclass.

        Parameters
        ----------
        date
            当前再平衡触发日。子类应**只使用 ``date`` 当日及之前**的数据
            （即 ``prices_panel[s].loc[:date]``），避免未来函数。
        prices_panel
            ``dict[symbol -> OHLCV DataFrame]``。每个 DataFrame 至少包含
            ``close`` 列，索引为 ``DatetimeIndex``。父类传入的是完整 panel，
            子类自己负责切片到 ``date``。

        Returns
        -------
        dict[str, float]
            ``{symbol: weight}``。约束：

            - keys 必须是 ``self.symbols`` 的子集（缺失的 symbol 视为权重 0）
            - 所有权重 ``>= 0``（不允许做空）
            - **权重和必须等于 1.0**（误差 < 1e-6）；本策略永远满仓，不留现金

            违反约束会被 ``_validate_weights`` 兜底（重归一化或报错）。
        """
        # 基类：等权
        n = len(self.symbols)
        return {s: 1.0 / n for s in self.symbols}

    # ------------------------------------------------------------------ #
    # 内部：权重检查 + 再平衡日历生成 + 主循环
    # ------------------------------------------------------------------ #
    def _validate_weights(self, weights: dict[str, float]) -> dict[str, float]:
        """约束 + 兜底。返回经过校验的权重 dict（key 覆盖 self.symbols 全集）。"""
        # 补齐缺失 symbol（视为 0）
        full = {s: float(weights.get(s, 0.0)) for s in self.symbols}
        # 非负
        if any(w < -1e-9 for w in full.values()):
            raise ValueError(f"target_weights 出现负值: {full}")
        full = {s: max(w, 0.0) for s, w in full.items()}
        # 和 == 1
        total = sum(full.values())
        if total <= 0:
            raise ValueError(f"target_weights 全为 0，无法再平衡: {full}")
        if abs(total - 1.0) > 1e-6:
            # 自动重归一化（容忍 S4/S5 子类返回未归一的权重）
            full = {s: w / total for s, w in full.items()}
        return full

    def _rebalance_calendar(self, index: pd.DatetimeIndex) -> list[pd.Timestamp]:
        """生成日历再平衡候选日序列：T0 + 每 rebalance_period 个交易日。"""
        positions = list(range(0, len(index), self.rebalance_period))
        return [index[p] for p in positions]

    def _should_trigger(
        self,
        target: dict[str, float],
        current: dict[str, float],
    ) -> bool:
        """drift_threshold 模式下判断是否真的需要再平衡。"""
        if self.drift_threshold is None:
            return True
        max_drift = max(abs(target[s] - current.get(s, 0.0)) for s in self.symbols)
        return max_drift > self.drift_threshold

    def build_target_weight_panel(
        self, panel: dict[str, pd.DataFrame]
    ) -> tuple[pd.DataFrame, list[pd.Timestamp]]:
        """生成完整的目标权重 DataFrame（index=date × columns=symbol）。

        非 rebalance 触发日为 NaN（喂给 vectorbt 时表示「不下单」）。

        Returns
        -------
        weights_df
            shape=(T, n_symbols)。仅在触发日有值。
        triggered_dates
            实际触发再平衡的日期（drift_threshold 过滤后的子集）。
        """
        # 对齐索引：6 个 ETF 的共同交易日
        common_idx: pd.DatetimeIndex | None = None
        for s in self.symbols:
            if s not in panel:
                raise KeyError(f"panel 缺少 symbol: {s}")
            idx = panel[s].index
            common_idx = idx if common_idx is None else common_idx.intersection(idx)
        assert common_idx is not None
        common_idx = common_idx.sort_values()

        candidate_dates = self._rebalance_calendar(common_idx)
        weights_df = pd.DataFrame(
            np.nan, index=common_idx, columns=self.symbols, dtype="float64"
        )

        # 跟踪上一次实际持仓的权重（drift 模式用），以收盘价漂移近似
        last_weights: dict[str, float] = {s: 0.0 for s in self.symbols}
        triggered: list[pd.Timestamp] = []

        for date in candidate_dates:
            target = self._validate_weights(self.target_weights(date, panel))

            # 第一次（初始建仓）总是触发
            if not triggered:
                weights_df.loc[date, self.symbols] = [target[s] for s in self.symbols]
                last_weights = target
                triggered.append(date)
                continue

            # drift 检查
            if not self._should_trigger(target, last_weights):
                continue

            weights_df.loc[date, self.symbols] = [target[s] for s in self.symbols]
            last_weights = target
            triggered.append(date)

        return weights_df, triggered

    def run(
        self,
        panel: dict[str, pd.DataFrame],
        *,
        init_cash: float = 100_000,
        fees: float = 0.00005,
        slippage: float = 0.0005,
    ) -> EqualRebalanceResult:
        """执行回测。

        Parameters
        ----------
        panel
            ``dict[symbol -> OHLCV DataFrame]``。必须包含 ``self.symbols`` 全部。
        init_cash, fees, slippage
            V1 共享基线：100k / 万 0.5 佣金 / 万 5 滑点。
        """
        import vectorbt as vbt

        weights_df, triggered = self.build_target_weight_panel(panel)

        close = pd.DataFrame(
            {s: panel[s]["close"] for s in self.symbols}
        ).reindex(weights_df.index)

        # vectorbt: size_type="targetpercent" + size=weight；NaN 表示该 bar 不下单
        # group_by + cash_sharing 让 6 个 asset 共享同一资金池
        pf = vbt.Portfolio.from_orders(
            close=close,
            size=weights_df,
            size_type="targetpercent",
            init_cash=init_cash,
            fees=fees,
            slippage=slippage,
            group_by=True,
            cash_sharing=True,
            call_seq="auto",  # 先卖后买，避免现金不足
            freq="1D",
        )

        from strategy_lib.backtest.metrics import portfolio_metrics

        try:
            metrics = portfolio_metrics(pf)
        except Exception:  # pragma: no cover - metrics helper 在某些环境可能不可用
            metrics = {}

        return EqualRebalanceResult(
            portfolio=pf,
            target_weights=weights_df,
            rebalance_dates=pd.DatetimeIndex(triggered),
            metrics=metrics,
        )


__all__ = ["EqualRebalanceStrategy", "EqualRebalanceResult"]
