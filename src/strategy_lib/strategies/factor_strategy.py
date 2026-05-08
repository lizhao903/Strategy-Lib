"""两个开箱即用的因子策略模板。"""

from __future__ import annotations

import pandas as pd

from strategy_lib.factors.base import Factor
from strategy_lib.strategies.base import BaseStrategy


class SingleAssetThresholdStrategy(BaseStrategy):
    """单 asset：组合因子 z-score 越过阈值时开/平仓。

    适合单标的择时（如 BTC、SPY）。
    """

    def __init__(
        self,
        factors: list[Factor],
        weights: list[float] | None = None,
        *,
        long_threshold: float = 0.5,
        short_threshold: float = -0.5,
        allow_short: bool = False,
        name: str = "single_threshold",
    ) -> None:
        super().__init__(factors, weights, name=name)
        self.long_threshold = long_threshold
        self.short_threshold = short_threshold
        self.allow_short = allow_short

    def _generate_signals(
        self, panel: dict[str, pd.DataFrame], factor_combined: pd.DataFrame
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        entries = factor_combined > self.long_threshold
        exits = factor_combined < (
            self.short_threshold if self.allow_short else 0.0
        )
        return entries, exits


class CrossSectionalRankStrategy(BaseStrategy):
    """截面排序：每期持有因子排名前 N 的资产，等权。

    适合多标的轮动（A股选股、ETF 轮动、Crypto 篮子）。
    """

    def __init__(
        self,
        factors: list[Factor],
        weights: list[float] | None = None,
        *,
        top_n: int | None = None,
        top_pct: float | None = 0.2,
        rebalance: int = 5,
        name: str = "cs_rank",
    ) -> None:
        super().__init__(factors, weights, name=name)
        if top_n is None and top_pct is None:
            raise ValueError("必须指定 top_n 或 top_pct 之一")
        self.top_n = top_n
        self.top_pct = top_pct
        self.rebalance = rebalance

    def _generate_signals(
        self, panel: dict[str, pd.DataFrame], factor_combined: pd.DataFrame
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        ranks = factor_combined.rank(axis=1, ascending=False)
        n_assets = factor_combined.notna().sum(axis=1)
        if self.top_n is not None:
            top_threshold = pd.Series(self.top_n, index=ranks.index)
        else:
            top_threshold = (n_assets * self.top_pct).clip(lower=1)

        in_top = ranks.le(top_threshold, axis=0)

        # 周期性 rebalance：只在 rebalance 期边界采用新分组，期间持有
        rebal_mask = pd.Series(
            [i % self.rebalance == 0 for i in range(len(in_top))], index=in_top.index
        )
        held = in_top.where(rebal_mask).ffill().fillna(False).astype(bool)

        # entries: 这一期 held 但上一期没 held
        entries = held & ~held.shift(1, fill_value=False)
        exits = ~held & held.shift(1, fill_value=False)
        return entries, exits
