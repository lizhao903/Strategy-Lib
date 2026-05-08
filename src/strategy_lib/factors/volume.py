"""成交量类因子：量价配合 / 资金流向。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from strategy_lib.factors.base import Factor


class VolumeRatio(Factor):
    """量比：当日成交量 / 过去 N 日均量。放量看多。"""

    name = "volume_ratio"
    required_columns = ("volume",)
    direction = 1

    def __init__(self, lookback: int = 20) -> None:
        super().__init__(lookback=lookback)

    def _compute(self, df: pd.DataFrame) -> pd.Series:
        v = df["volume"]
        ma = v.rolling(self.params["lookback"]).mean()
        return v / ma


class OBVMomentum(Factor):
    """OBV（On-Balance Volume）的 N 日变动率。资金流向动量。"""

    name = "obv_momentum"
    required_columns = ("close", "volume")
    direction = 1

    def __init__(self, lookback: int = 20) -> None:
        super().__init__(lookback=lookback)

    def _compute(self, df: pd.DataFrame) -> pd.Series:
        sign = np.sign(df["close"].diff().fillna(0))
        obv = (sign * df["volume"]).cumsum()
        return obv.diff(self.params["lookback"])
