"""动量类因子：过去表现持续。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from strategy_lib.factors.base import Factor


class MomentumReturn(Factor):
    """过去 N 天累积收益。经典截面动量因子（A股建议跳过最近 1 个月避免短期反转）。"""

    name = "mom_return"
    required_columns = ("close",)
    direction = 1

    def __init__(self, lookback: int = 20, skip: int = 0) -> None:
        super().__init__(lookback=lookback, skip=skip)

    def _compute(self, df: pd.DataFrame) -> pd.Series:
        lookback = self.params["lookback"]
        skip = self.params["skip"]
        c = df["close"]
        return c.shift(skip) / c.shift(skip + lookback) - 1.0


class VolAdjustedMomentum(Factor):
    """波动率调整动量：``mom_return(lookback, skip) / realized_vol(vol_lookback)``。

    经典 risk-adjusted momentum / "Sharpe-like" momentum，用过去 ``vol_lookback``
    日的对数收益标准差（年化与否不影响截面排序）作为分母。低波动资产在相同
    动量幅度下得分更高 —— 在跨资产类别（股 / 债 / 商品）池上意义更大，因为它
    防止「高波动资产长期主导权重」。

    Parameters
    ----------
    lookback
        动量窗口。
    skip
        跳过最近 N 天（避免短期反转）。
    vol_lookback
        波动率窗口（默认 60 日 ~ 一个季度）。
    """

    name = "mom_vol_adj"
    required_columns = ("close",)
    direction = 1

    def __init__(
        self, lookback: int = 60, skip: int = 0, vol_lookback: int = 60
    ) -> None:
        super().__init__(lookback=lookback, skip=skip, vol_lookback=vol_lookback)

    def _compute(self, df: pd.DataFrame) -> pd.Series:
        lookback = self.params["lookback"]
        skip = self.params["skip"]
        vol_lookback = self.params["vol_lookback"]
        c = df["close"]
        mom = c.shift(skip) / c.shift(skip + lookback) - 1.0
        log_ret = np.log(c).diff()
        vol = log_ret.rolling(vol_lookback).std()
        # 防 0 / NaN：vol==0 处置 NaN（截面侧统一当中性 0）
        adj = mom / vol.replace(0.0, np.nan)
        return adj


class MACDDiff(Factor):
    """MACD 差值（DIF - DEA）归一化到价格。趋势强度信号。"""

    name = "macd_diff"
    required_columns = ("close",)
    direction = 1

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9) -> None:
        super().__init__(fast=fast, slow=slow, signal=signal)

    def _compute(self, df: pd.DataFrame) -> pd.Series:
        c = df["close"]
        ema_fast = c.ewm(span=self.params["fast"], adjust=False).mean()
        ema_slow = c.ewm(span=self.params["slow"], adjust=False).mean()
        dif = ema_fast - ema_slow
        dea = dif.ewm(span=self.params["signal"], adjust=False).mean()
        return (dif - dea) / c
