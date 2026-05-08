"""波动率类因子。低波动率往往伴随更高风险调整后收益（low-vol anomaly）。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from strategy_lib.factors.base import Factor


class RealizedVol(Factor):
    """已实现波动率（过去 N 日对数收益标准差）。"""

    name = "realized_vol"
    required_columns = ("close",)
    direction = -1  # 低波动 → 看多（low-vol anomaly）

    def __init__(self, lookback: int = 20) -> None:
        super().__init__(lookback=lookback)

    def _compute(self, df: pd.DataFrame) -> pd.Series:
        ret = np.log(df["close"]).diff()
        return ret.rolling(self.params["lookback"]).std()


class ATRRatio(Factor):
    """ATR 占价格比例。归一化的波动幅度。"""

    name = "atr_ratio"
    required_columns = ("high", "low", "close")
    direction = -1

    def __init__(self, period: int = 14) -> None:
        super().__init__(period=period)

    def _compute(self, df: pd.DataFrame) -> pd.Series:
        prev_close = df["close"].shift(1)
        tr = pd.concat(
            [
                df["high"] - df["low"],
                (df["high"] - prev_close).abs(),
                (df["low"] - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        atr = tr.ewm(alpha=1 / self.params["period"], adjust=False).mean()
        return atr / df["close"]


# ---------------------------------------------------------------------------
# v2 新增：年化波动率（直接转成「年化口径」便于配置阈值）
# ---------------------------------------------------------------------------


class AnnualizedVol(Factor):
    """年化已实现波动率（过去 N 日对数收益 std × √252）。

    与 ``RealizedVol`` 的差别仅在于 √252 缩放，便于策略侧直接用 0.20 / 0.30
    这种「年化口径」阈值过滤高波时段，省去到处 ×√252 的样板代码。
    """

    name = "annualized_vol"
    required_columns = ("close",)
    direction = -1  # 高波时段视作风险，向下倾斜权重

    def __init__(self, lookback: int = 60) -> None:
        if lookback < 2:
            raise ValueError(f"lookback 必须 >= 2，得到 {lookback}")
        super().__init__(lookback=lookback)

    def _compute(self, df: pd.DataFrame) -> pd.Series:
        import numpy as np

        ret = np.log(df["close"]).diff()
        return ret.rolling(self.params["lookback"]).std() * np.sqrt(252)
