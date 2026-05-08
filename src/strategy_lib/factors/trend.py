"""趋势类因子：单标的视角下「价格相对自身参考」的方向与位置。

与 momentum.py 的区别：
- momentum 是横截面累计收益（A 比 B 涨得多）
- trend 是时序方向状态（A 自身现在在涨）

新增的因子在合并到 factors/__init__.py 之前，使用方需要直接 import：
    from strategy_lib.factors.trend import MABullishScore, DonchianPosition
"""

from __future__ import annotations

import pandas as pd

from strategy_lib.factors.base import Factor


class MABullishScore(Factor):
    """MA 多头排列得分。

    `score = sign(close > MA_short) + sign(MA_short > MA_mid) + sign(MA_mid > MA_long)`

    取值范围 {-3, -1, +1, +3}（中间组合产生 ±1）。+3 = 完美多头排列，-3 = 完美空头排列。
    属于离散趋势状态信号，对均线长度的具体取值相对鲁棒。
    """

    name = "ma_bullish_score"
    required_columns = ("close",)
    direction = 1

    def __init__(self, short: int = 20, mid: int = 60, long: int = 120) -> None:
        if not (short < mid < long):
            raise ValueError(f"需要 short < mid < long，得到 {short}/{mid}/{long}")
        super().__init__(short=short, mid=mid, long=long)

    def _compute(self, df: pd.DataFrame) -> pd.Series:
        c = df["close"]
        ma_s = c.rolling(self.params["short"]).mean()
        ma_m = c.rolling(self.params["mid"]).mean()
        ma_l = c.rolling(self.params["long"]).mean()
        # 三个布尔比较 -> +1/-1
        s1 = (c > ma_s).astype(float) * 2 - 1
        s2 = (ma_s > ma_m).astype(float) * 2 - 1
        s3 = (ma_m > ma_l).astype(float) * 2 - 1
        score = s1 + s2 + s3
        # 长 MA 还没 ready 时，置 NaN（避免被误判为某种方向）
        score = score.where(ma_l.notna())
        return score


class DonchianPosition(Factor):
    """Donchian 通道相对位置。

    `pos = (close - low_N) / (high_N - low_N)`，取值 ∈ [0, 1]。

    - 1.0 = 价格站在过去 N 日的最高点（强趋势顶端）
    - 0.5 = 通道中部
    - 0.0 = 价格在过去 N 日最低点（弱势）

    在 Turtle / 海龟体系里被广泛使用，对突破和趋势位置的识别很直接。
    """

    name = "donchian_position"
    required_columns = ("high", "low", "close")
    direction = 1

    def __init__(self, lookback: int = 120) -> None:
        if lookback < 2:
            raise ValueError(f"lookback 必须 >= 2，得到 {lookback}")
        super().__init__(lookback=lookback)

    def _compute(self, df: pd.DataFrame) -> pd.Series:
        n = self.params["lookback"]
        high_n = df["high"].rolling(n).max()
        low_n = df["low"].rolling(n).min()
        rng = high_n - low_n
        pos = (df["close"] - low_n) / rng
        # 通道为 0 (常量价格) 时的除零保护
        pos = pos.where(rng > 0)
        return pos


# ---------------------------------------------------------------------------
# v2 新增：连续形态的趋势因子（用于 S5 v2，避免双峰现金分布）
# ---------------------------------------------------------------------------


class MABullishContinuous(Factor):
    """连续版 MA 多头排列得分。

    与 ``MABullishScore`` 的离散 sign() 取代物：用 z-score 风格的 ``tanh`` 把
    `close/MA - 1` 平滑映射到 (-1, +1)，三层 MA 等权求和后 ÷ 3 → ∈ (-1, +1)。

    设计动机
    ---------
    v1 用 sign() 离散判定 → trend_score 跳变（±3, ±1），导致权重在 cutoff
    附近瞬间从 0 跳到 1/N、生成「双峰现金分布」。本因子改用连续函数，让
    score 沿价格相对均线的距离平滑变化，便于做权重的连续 ramp。

    `score_continuous = mean( tanh(k * (close/MA - 1)) for MA in (short, mid, long) )`
    """

    name = "ma_bullish_continuous"
    required_columns = ("close",)
    direction = 1

    def __init__(self, short: int = 20, mid: int = 60, long: int = 120, k: float = 20.0) -> None:
        if not (short < mid < long):
            raise ValueError(f"需要 short < mid < long，得到 {short}/{mid}/{long}")
        if k <= 0:
            raise ValueError("k 必须 > 0")
        super().__init__(short=short, mid=mid, long=long, k=k)

    def _compute(self, df: pd.DataFrame) -> pd.Series:
        import numpy as np

        c = df["close"]
        k = self.params["k"]
        ma_s = c.rolling(self.params["short"]).mean()
        ma_m = c.rolling(self.params["mid"]).mean()
        ma_l = c.rolling(self.params["long"]).mean()

        # tanh 把价格相对 MA 的偏离压到 (-1, +1)
        # k=20 时，close/MA - 1 = 0.05（5% 上方）→ tanh(1) ≈ 0.76，方向显著但不饱和
        d_s = np.tanh(k * (c / ma_s - 1.0))
        d_m = np.tanh(k * (c / ma_m - 1.0))
        d_l = np.tanh(k * (c / ma_l - 1.0))

        score = (d_s + d_m + d_l) / 3.0
        score = score.where(ma_l.notna())
        return score
