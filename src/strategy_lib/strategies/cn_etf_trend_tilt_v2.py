"""Strategy 5 v2 — A股 ETF 等权 + 趋势倾斜（连续现金 + 波动率过滤）.

继承 v1 的结构（S3 → TrendTiltStrategy），但通过覆盖关键钩子解决 v1 的两大问题：

1. **现金占比双峰** → **连续现金比例**：把 `_tilt_weights` 从「正分数 / 正分数和
   再归一化」改成「连续 score 经过 ramp → 上限 1/N」，权重和不再强制 = 1，
   缺额自动留作现金。这样 cash_ratio 随趋势强度连续变化，而不是瞬间 0↔1。

2. **避险命题未兑现** → **波动率过滤**：当池中超过 K% 的资产 60 日年化波动
   > vol_high 时，对所有权重乘以 ``vol_haircut``（默认 0.5），强制降仓。
   这是 v1 单纯靠 MA + Donchian 信号在快速下跌中反应不够的补救。

可选增强：
- ``use_continuous_score=True``：用 ``MABullishContinuous`` 替代 v1 的离散
  ``MABullishScore``，让 trend_score 在 cutoff 附近平滑而非阶跃。
- ``bond_symbol``（如 ``"511260"``）：v2 的现金缺口填充债券 ETF 暴露而非
  纯现金。控制 ``bond_max_weight`` 上限。

v2 仍然依赖 vbt sum<1 兼容性（v1 已实测验证 from_orders + targetpercent +
cash_sharing 在权重和 < 1 时正确把缺额留作 cash group 的现金）。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from strategy_lib.strategies.cn_etf_trend_tilt import (
    TrendTiltStrategy,
    _normalize_to_unit,
)
from strategy_lib.factors.trend import (
    DonchianPosition,
    MABullishContinuous,
    MABullishScore,
)
from strategy_lib.factors.volatility import AnnualizedVol


class TrendTiltV2Strategy(TrendTiltStrategy):
    """v2: 连续现金比例 + 波动率过滤 + 可选债券暴露。

    权重生成数学形式
    -----------------
    给定每只 ETF 的 ``trend_score ∈ [-2, +2]``（v1 同口径，可选连续版本）：

    1. **正分数 ramp**：
       ``raw_i = clip((score_i - cutoff) / (score_full - cutoff), 0, 1)``
       其中 ``score_full`` 是「权重达到上限的临界点」（默认 1.0，即 score=1
       时该资产拿满 1/N，超过 1 不再增加）。

    2. **不归一化**：
       ``weight_i = raw_i * (1 / N)``
       这样 sum = (Σ raw_i) / N ∈ [0, 1]，**只有所有 ETF 都 score ≥ score_full
       时才满仓**；任何一个低于 score_full 都自动留出对应比例现金。
       v1 是 ``raw_i / Σ raw_i``（任一 > 0 即归一化到 1）→ 双峰元凶。

    3. **波动率过滤**（haircut）：
       若 ``mean(vol > vol_high) ≥ vol_breadth_threshold``（即超过指定比例
       的池中资产处于高波状态），对全体权重乘以 ``vol_haircut``（默认 0.5）。

    4. **债券暴露**（可选）：
       cash_gap = 1 - sum(risky_weights) - vol_haircut_cash
       bond_w = min(cash_gap, bond_max_weight)
       将 bond_w 分配给 ``bond_symbol``（必须在 self.symbols 里）。

    Parameters
    ----------
    score_full
        ramp 饱和点。score ≥ score_full 时该资产拿满 1/N；以下线性。默认 1.0。
        v1 等价于 score_full = 0+（任一 > 0 立即满 1/N）。
    use_continuous_score
        True → 使用 ``MABullishContinuous``；False → 沿用 v1 的离散 sign 版。
    vol_lookback
        年化波动率 lookback。默认 60 日（约 3 个月）。
    vol_high
        年化波动率「高位」阈值。默认 0.30（30% 年化）。A股宽基 ETF 常态在
        15-25%，2022 / 2024-09 行情期间普遍 > 30%，作为加速触发降仓。
    vol_breadth_threshold
        ≥ 多大比例的池资产 vol > vol_high 才触发降仓。默认 0.5（半数以上）。
    vol_haircut
        触发降仓时全体权重乘以的折扣。默认 0.5（一半仓位）。设 1.0 关闭。
    bond_symbol
        现金缺口填充的债券标的（如 ``"511260"``）。需要预先在 ``symbols``
        里包含；不在则忽略。默认 None（不做债券替代）。
    bond_max_weight
        bond 替代的上限。默认 0.4（即最多 40% 仓位投债券，留一定现金）。
    """

    def __init__(
        self,
        *args,
        score_full: float = 1.0,
        use_continuous_score: bool = True,
        vol_lookback: int = 60,
        vol_high: float = 0.30,
        vol_breadth_threshold: float = 0.5,
        vol_haircut: float = 0.5,
        bond_symbol: str | None = None,
        bond_max_weight: float = 0.4,
        **kwargs,
    ) -> None:
        # 直接调 v1 的 __init__（它已设置 _ma_factor / _donchian_factor / _cutoff 等）
        super().__init__(*args, **kwargs)

        if score_full <= 0:
            raise ValueError("score_full 必须 > 0")
        if not (0 < vol_haircut <= 1):
            raise ValueError("vol_haircut 必须 ∈ (0, 1]")
        if not (0 <= vol_breadth_threshold <= 1):
            raise ValueError("vol_breadth_threshold 必须 ∈ [0, 1]")
        if vol_high <= 0:
            raise ValueError("vol_high 必须 > 0")
        if not (0 <= bond_max_weight <= 1):
            raise ValueError("bond_max_weight 必须 ∈ [0, 1]")

        self._score_full = score_full
        self._use_continuous_score = use_continuous_score
        self._vol_lookback = vol_lookback
        self._vol_high = vol_high
        self._vol_breadth_threshold = vol_breadth_threshold
        self._vol_haircut = vol_haircut
        self._bond_symbol = bond_symbol
        self._bond_max_weight = bond_max_weight

        # 替换连续版 MA 因子（保留 v1 的 _ma_factor 引用兼容继承的 compute_trend_scores）
        if use_continuous_score:
            ma_short = self._ma_factor.params["short"]
            ma_mid = self._ma_factor.params["mid"]
            ma_long = self._ma_factor.params["long"]
            self._ma_factor = MABullishContinuous(short=ma_short, mid=ma_mid, long=ma_long)

        self._vol_factor = AnnualizedVol(lookback=vol_lookback)

    # ------------------------------------------------------------------
    # 覆盖 trend score 计算：连续 MA score 已经 ∈ [-1, +1]，无需 / 3
    # ------------------------------------------------------------------
    def compute_trend_scores(
        self, date: pd.Timestamp, prices_panel: dict[str, pd.DataFrame]
    ) -> pd.Series:
        """对池中每只 ETF 计算 trend_score，bond_symbol（若指定）跳过参与计算。"""
        scores: dict[str, float] = {}
        w_ma, w_dc = self._score_weights

        for symbol, df in prices_panel.items():
            # 跳过债券 symbol：bond 由 cash_gap 调度，不参与 trend 排序
            if symbol == self._bond_symbol:
                continue

            df_hist = df.loc[df.index <= date]
            if df_hist.empty:
                scores[symbol] = float("nan")
                continue

            ma_series = self._ma_factor.compute(df_hist)
            if isinstance(self._ma_factor, MABullishContinuous):
                # 已经 ∈ (-1, +1)，无需 / 3
                ma_norm = ma_series.clip(lower=-1.0, upper=1.0)
            else:
                ma_norm = _normalize_to_unit(ma_series, max_abs=3.0)

            dc_series = self._donchian_factor.compute(df_hist)
            dc_norm = (dc_series * 2 - 1).clip(lower=-1.0, upper=1.0)

            ma_last = ma_norm.iloc[-1] if len(ma_norm) else float("nan")
            dc_last = dc_norm.iloc[-1] if len(dc_norm) else float("nan")

            if pd.isna(ma_last) or pd.isna(dc_last):
                scores[symbol] = float("nan")
            else:
                scores[symbol] = w_ma * ma_last + w_dc * dc_last

        return pd.Series(scores, name="trend_score")

    # ------------------------------------------------------------------
    # 计算波动率 breadth：高波 ETF 占池比例 (in [0, 1])
    # ------------------------------------------------------------------
    def _vol_breadth(
        self, date: pd.Timestamp, prices_panel: dict[str, pd.DataFrame]
    ) -> float:
        """返回 vol > vol_high 的资产占池比例。"""
        risky_symbols = [s for s in self.symbols if s != self._bond_symbol]
        if not risky_symbols:
            return 0.0
        n_high = 0
        n_valid = 0
        for symbol in risky_symbols:
            df = prices_panel.get(symbol)
            if df is None:
                continue
            df_hist = df.loc[df.index <= date]
            if df_hist.empty:
                continue
            vol_series = self._vol_factor.compute(df_hist)
            vol_last = vol_series.iloc[-1] if len(vol_series) else float("nan")
            if pd.isna(vol_last):
                continue
            n_valid += 1
            if vol_last > self._vol_high:
                n_high += 1
        if n_valid == 0:
            return 0.0
        return n_high / n_valid

    # ------------------------------------------------------------------
    # 核心：v2 的连续 ramp 权重
    # ------------------------------------------------------------------
    def _tilt_weights(self, scores: pd.Series) -> dict[str, float]:
        """v2: 连续 ramp + 不归一化（让 sum < 1 自然产生现金缓冲）.

        - score ≤ cutoff：raw = 0
        - cutoff < score < cutoff + score_full：raw = (score - cutoff) / score_full ∈ (0, 1)
        - score ≥ cutoff + score_full：raw = 1（饱和）

        weight_i = raw_i / N（N 为风险资产数量，不含 bond_symbol）

        Result sum 满足 ∈ [0, 1]：所有 raw=1 时满仓；半数饱和半数 0 时 50% 现金。
        """
        valid = scores.dropna()
        n_risky = max(len(valid), 1)
        weights: dict[str, float] = {}
        denom = self._score_full
        if denom <= 0:
            denom = 1e-9
        for sym, score in valid.items():
            raw = (score - self._cutoff) / denom
            raw = max(0.0, min(1.0, raw))
            if raw > 0:
                weights[sym] = raw / n_risky
        return weights

    # ------------------------------------------------------------------
    # 覆盖 target_weights：先生成 risky 权重 → 应用 vol haircut → 用 bond 填充
    # ------------------------------------------------------------------
    def target_weights(
        self, date: pd.Timestamp, prices_panel: dict[str, pd.DataFrame]
    ) -> dict[str, float]:
        scores = self.compute_trend_scores(date, prices_panel)
        risky_weights = self._tilt_weights(scores)

        # vol haircut：池中高波资产比例 ≥ 阈值时对 risky 权重降仓
        breadth = self._vol_breadth(date, prices_panel)
        haircut_applied = False
        if breadth >= self._vol_breadth_threshold and self._vol_haircut < 1.0:
            risky_weights = {s: w * self._vol_haircut for s, w in risky_weights.items()}
            haircut_applied = True

        out = dict(risky_weights)

        # bond 填充：如果指定了 bond_symbol 且其在 self.symbols 中
        if self._bond_symbol is not None and self._bond_symbol in self.symbols:
            risky_sum = sum(out.values())
            cash_gap = 1.0 - risky_sum
            # 在高波 haircut 触发的时段，更倾向用 bond 替代部分现金
            bond_w = min(cash_gap, self._bond_max_weight)
            # 但若 cash_gap 很小（< 0.05），bond 占用反而无意义，就留作纯现金
            if bond_w > 0.01:
                # 简单逻辑：bond 占 bond_max_weight × min(1, breadth + (1 - cash_gap_residual))，
                # 这里给 bond 上限固定值，剩余仍是现金。
                out[self._bond_symbol] = bond_w
        # 调试信息可外部读取（不写日志，避免重复 IO）
        self._last_breadth = breadth
        self._last_haircut_applied = haircut_applied
        return out


__all__ = ["TrendTiltV2Strategy"]
