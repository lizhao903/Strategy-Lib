"""策略基类。

输入：价格面板 (dict[symbol, OHLCV df]) + 策略参数
输出：StrategyResult（包含 vectorbt Portfolio 和绩效指标）
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd

from strategy_lib.factors.base import Factor


@dataclass
class StrategyResult:
    portfolio: object  # vectorbt Portfolio（避免顶层 import vectorbt）
    signals: pd.DataFrame
    factor_values: pd.DataFrame
    metrics: dict


class BaseStrategy(ABC):
    """策略基类。子类实现 `_generate_signals`，base 负责调用 vectorbt 回测。"""

    def __init__(
        self,
        factors: list[Factor],
        weights: list[float] | None = None,
        *,
        name: str = "strategy",
    ) -> None:
        self.factors = factors
        self.weights = weights or [1.0 / len(factors)] * len(factors)
        if len(self.weights) != len(factors):
            raise ValueError("weights 长度必须等于 factors 数量")
        self.name = name

    def combined_factor(self, panel: dict[str, pd.DataFrame]) -> pd.DataFrame:
        """加权组合多个因子。先 z-score 标准化，再加权求和。方向已应用。"""
        z_panels: list[pd.DataFrame] = []
        for f, w in zip(self.factors, self.weights, strict=True):
            wide = f.compute_panel(panel) * f.direction  # 统一为「越高越看多」
            mean = wide.mean(axis=1).values.reshape(-1, 1)
            std = wide.std(axis=1).replace(0, pd.NA).values.reshape(-1, 1)
            z = (wide.values - mean) / std
            z_panels.append(pd.DataFrame(z, index=wide.index, columns=wide.columns) * w)

        combined = sum(z_panels)
        return combined

    @abstractmethod
    def _generate_signals(
        self, panel: dict[str, pd.DataFrame], factor_combined: pd.DataFrame
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """返回 (entries, exits) 两个宽 DataFrame，均为 bool。"""

    def run(
        self,
        panel: dict[str, pd.DataFrame],
        *,
        init_cash: float = 10_000,
        fees: float = 0.001,
        slippage: float = 0.0005,
    ) -> StrategyResult:
        """跑回测，返回 StrategyResult。"""
        import vectorbt as vbt

        from strategy_lib.backtest.metrics import portfolio_metrics

        combined = self.combined_factor(panel)
        entries, exits = self._generate_signals(panel, combined)

        close = pd.DataFrame({s: df["close"] for s, df in panel.items()})
        close, entries = close.align(entries, join="inner")
        close, exits = close.align(exits, join="inner")

        pf = vbt.Portfolio.from_signals(
            close,
            entries=entries.fillna(False),
            exits=exits.fillna(False),
            init_cash=init_cash,
            fees=fees,
            slippage=slippage,
            freq="1D",
        )

        metrics = portfolio_metrics(pf)
        return StrategyResult(
            portfolio=pf,
            signals=entries.astype(int) - exits.astype(int),
            factor_values=combined,
            metrics=metrics,
        )
