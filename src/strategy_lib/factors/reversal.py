"""反转类因子：短期超涨超跌后回归。"""

from __future__ import annotations

import pandas as pd

from strategy_lib.factors.base import Factor


class ShortTermReversal(Factor):
    """过去 N 天累积收益的反向。短期收益越高，未来短期越倾向回落。"""

    name = "st_reversal"
    required_columns = ("close",)
    direction = -1  # 高 → 看空

    def __init__(self, lookback: int = 5) -> None:
        super().__init__(lookback=lookback)

    def _compute(self, df: pd.DataFrame) -> pd.Series:
        c = df["close"]
        return c / c.shift(self.params["lookback"]) - 1.0


class RSIReversal(Factor):
    """RSI 偏离 50 的程度。RSI 高（超买）→ 看空。"""

    name = "rsi_reversal"
    required_columns = ("close",)
    direction = -1

    def __init__(self, period: int = 14) -> None:
        super().__init__(period=period)

    def _compute(self, df: pd.DataFrame) -> pd.Series:
        c = df["close"]
        delta = c.diff()
        up = delta.clip(lower=0)
        down = -delta.clip(upper=0)
        roll_up = up.ewm(alpha=1 / self.params["period"], adjust=False).mean()
        roll_down = down.ewm(alpha=1 / self.params["period"], adjust=False).mean()
        rs = roll_up / roll_down.replace(0, pd.NA)
        rsi = 100 - 100 / (1 + rs)
        return rsi - 50
