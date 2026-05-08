"""Strategy 5：A股 ETF 等权 + 趋势倾斜。

继承 S3 (`EqualRebalanceStrategy`)，在每个再平衡日通过覆盖 `target_weights` 钩子，
按每只 ETF 的**时序趋势分数**调整权重：

- `trend_score > 0` 的 ETF 权重 ∝ 分数（再做归一化）
- `trend_score <= 0` 的 ETF 权重置 0（弱趋势退出，对应资金留作现金）
- 全体 ETF 都 ≤ 0 时全空仓

**对 S3 钩子契约的扩展**：原始 S3 假定 `target_weights` 返回 dict 的权重和 = 1，
本策略允许 `sum(weights) < 1`（含全空仓 = 0），缺失的 symbol 视作 0 权重（现金）。

为了与 S3 当前实现的严格校验（`_validate_weights` 强制 `sum == 1`，`total <= 0` 抛错）
共存，本子类**覆盖 `_validate_weights`**：

- 允许总和 ∈ [0, 1+ε]（不再强制重归一化到 1）
- 允许 `total == 0`（全空仓 → 全 0 dict）
- 仍校验非负与 keys ⊂ symbols
"""

from __future__ import annotations

import pandas as pd

# S3 父类
from strategy_lib.strategies.cn_etf_equal_rebalance import EqualRebalanceStrategy
from strategy_lib.factors.trend import DonchianPosition, MABullishScore


def _normalize_to_unit(series: pd.Series, max_abs: float) -> pd.Series:
    """把 series 除以已知的理论最大绝对值，截断到 [-1, +1]。NaN 保留。"""
    if max_abs <= 0:
        raise ValueError("max_abs 必须 > 0")
    return (series / max_abs).clip(lower=-1.0, upper=1.0)


class TrendTiltStrategy(EqualRebalanceStrategy):
    """等权 + 趋势倾斜：S3 派生，覆盖 target_weights 钩子。

    Parameters
    ----------
    ma_short, ma_mid, ma_long
        MA 多头排列得分使用的三条均线长度。
    donchian_lookback
        Donchian 通道窗口（日）。
    score_weights
        ``(w_ma, w_donchian)``。两个分数标准化到 [-1, +1] 后的权重。和不必为 1，
        只影响最终 trend_score 的尺度，不影响相对排名/方向。
    cutoff
        `trend_score <= cutoff` 的 ETF 视作空仓。默认 0（趋势翻负就退出）。
        提高 cutoff（如 0.3）相当于「弱趋势也不要」的更保守版本。
    **kwargs
        透传给 S3 父类（`symbols`, `rebalance_period`, `init_cash` 等）。
    """

    def __init__(
        self,
        *args,
        ma_short: int = 20,
        ma_mid: int = 60,
        ma_long: int = 120,
        donchian_lookback: int = 120,
        score_weights: tuple[float, float] = (1.0, 1.0),
        cutoff: float = 0.0,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._ma_factor = MABullishScore(short=ma_short, mid=ma_mid, long=ma_long)
        self._donchian_factor = DonchianPosition(lookback=donchian_lookback)
        self._score_weights = score_weights
        self._cutoff = cutoff

    # ------------------------------------------------------------------
    # 趋势得分计算（独立函数，便于单测）
    # ------------------------------------------------------------------

    def compute_trend_scores(
        self, date: pd.Timestamp, prices_panel: dict[str, pd.DataFrame]
    ) -> pd.Series:
        """对池中每只 ETF 计算 trend_score（标量）。

        Returns
        -------
        pd.Series
            index = symbol，value = trend_score (float, 可能为 NaN 表示数据不足)。
            理论范围：[-2, +2]。
        """
        scores: dict[str, float] = {}
        w_ma, w_dc = self._score_weights

        for symbol, df in prices_panel.items():
            # 用 t (date) 之前的数据计算（避免未来函数）
            df_hist = df.loc[df.index <= date]
            if df_hist.empty:
                scores[symbol] = float("nan")
                continue

            # MA 多头得分：理论 max_abs = 3
            ma_series = self._ma_factor.compute(df_hist)
            ma_norm = _normalize_to_unit(ma_series, max_abs=3.0)

            # Donchian 位置 ∈ [0, 1]，平移到 [-1, +1]：2*pos - 1
            dc_series = self._donchian_factor.compute(df_hist)
            dc_norm = (dc_series * 2 - 1).clip(lower=-1.0, upper=1.0)

            # 取最新一日（必须存在），任一为 NaN 视作整体 NaN（暖机期空仓）
            ma_last = ma_norm.iloc[-1] if len(ma_norm) else float("nan")
            dc_last = dc_norm.iloc[-1] if len(dc_norm) else float("nan")

            if pd.isna(ma_last) or pd.isna(dc_last):
                scores[symbol] = float("nan")
            else:
                scores[symbol] = w_ma * ma_last + w_dc * dc_last

        return pd.Series(scores, name="trend_score")

    # ------------------------------------------------------------------
    # 把 trend_score 转成目标权重（核心倾斜逻辑）
    # ------------------------------------------------------------------

    def _tilt_weights(self, scores: pd.Series) -> dict[str, float]:
        """趋势分数 -> 目标权重 dict。

        - 分数 NaN 或 ≤ cutoff 的 symbol 不出现在结果里（视作 0 / 现金）
        - 剩余 symbol 的权重 = 分数 / 分数和
        - 全体被过滤时返回 {}（全空仓）
        """
        positive = scores[scores.notna() & (scores > self._cutoff)]
        if positive.empty:
            return {}
        total = positive.sum()
        # positive 既然 > cutoff (>=0)，且非空，total 必 > 0
        weights = (positive / total).to_dict()
        return weights

    # ------------------------------------------------------------------
    # S3 钩子覆盖
    # ------------------------------------------------------------------

    def target_weights(
        self, date: pd.Timestamp, prices_panel: dict[str, pd.DataFrame]
    ) -> dict[str, float]:
        """覆盖 S3 的等权钩子。

        Returns
        -------
        dict[str, float]
            键 = symbol，值 = 目标权重 ∈ [0, 1]。
            **可能 sum < 1**（现金留底）甚至为 `{}`（全空仓）—— 这是对 S3 契约的扩展。
        """
        scores = self.compute_trend_scores(date, prices_panel)
        return self._tilt_weights(scores)

    # ------------------------------------------------------------------
    # 覆盖父类校验：放宽「权重和必须 = 1」「不允许全为 0」两条约束
    # ------------------------------------------------------------------

    def _validate_weights(self, weights: dict[str, float]) -> dict[str, float]:
        """放宽版校验：允许 sum ∈ [0, 1+ε]，不重归一化。

        - 缺失 symbol 视作 0
        - 仍要求非负
        - 不再强制 sum == 1（允许现金留底）
        - 不再禁止 total == 0（允许全空仓 → vectorbt 全平仓）
        - 若 sum > 1 + 1e-6 视为子类 bug，归一化到 1 防御
        """
        full = {s: float(weights.get(s, 0.0)) for s in self.symbols}
        if any(w < -1e-9 for w in full.values()):
            raise ValueError(f"target_weights 出现负值: {full}")
        full = {s: max(w, 0.0) for s, w in full.items()}
        total = sum(full.values())
        # 防御：子类返回 sum > 1 时归一化（理论上不应发生）
        if total > 1.0 + 1e-6:
            full = {s: w / total for s, w in full.items()}
        return full
