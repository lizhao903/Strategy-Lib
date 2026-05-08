"""Strategy 4 — A股 ETF 等权 + 动量倾斜.

派生自 Strategy 3 的 `EqualRebalanceStrategy`，仅覆盖 `target_weights` 钩子：
按横截面动量 z-score 把权重从 1/N 线性倾斜，clip 到 [w_min, w_max] 再归一化。
仍然 100% 满仓、无现金缓冲。
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

import numpy as np
import pandas as pd

from strategy_lib.factors.momentum import MomentumReturn

try:  # pragma: no cover - 取决于 S3 subagent 的产出节奏
    from strategy_lib.strategies.cn_etf_equal_rebalance import EqualRebalanceStrategy
except ImportError as _e:  # pragma: no cover
    # 容错：S3 还没落地时先用一个最小 stub 让本模块可被 import。
    # 实际运行回测时 S3 必须已就位。
    class EqualRebalanceStrategy:  # type: ignore[no-redef]
        """占位父类。S3 落地后会被真实实现替换。

        约定的钩子契约：
          target_weights(date, prices_panel) -> dict[symbol, weight]
        其中 weights 非负、和=1。
        """

        def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: D401
            self._import_error = _e

        def target_weights(
            self,
            date: pd.Timestamp | _dt.date,
            prices_panel: dict[str, pd.DataFrame],
        ) -> dict[str, float]:
            symbols = list(prices_panel)
            if not symbols:
                return {}
            w = 1.0 / len(symbols)
            return {s: w for s in symbols}


class MomentumTiltStrategy(EqualRebalanceStrategy):
    """等权 + 动量倾斜.

    Parameters
    ----------
    lookback : int
        主动量因子的 lookback 天数（默认 20）。
    secondary_lookback : int | None
        可选的二级动量 lookback（如 60）。两者 z-score 后等权融合。None 表示不启用。
    alpha : float
        倾斜强度。raw 权重 = 1/N + alpha * z / N。alpha=0 等权；alpha=1 对应 1σ 资产权重 ≈ 2/N。
    w_min, w_max : float
        单资产权重上下限（clip 阈值）。clip 后再归一化使 sum(w)=1。
    """

    def __init__(
        self,
        *args: Any,
        lookback: int = 20,
        secondary_lookback: int | None = None,
        alpha: float = 1.0,
        w_min: float = 0.05,
        w_max: float = 0.40,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        if alpha < 0:
            raise ValueError("alpha 必须 >= 0")
        if not (0.0 <= w_min < w_max <= 1.0):
            raise ValueError("需要 0 <= w_min < w_max <= 1")
        self.lookback = lookback
        self.secondary_lookback = secondary_lookback
        self.alpha = alpha
        self.w_min = w_min
        self.w_max = w_max

        self._mom_primary = MomentumReturn(lookback=lookback)
        self._mom_secondary = (
            MomentumReturn(lookback=secondary_lookback)
            if secondary_lookback is not None
            else None
        )

    # ------------------------------------------------------------------
    # 核心钩子
    # ------------------------------------------------------------------

    def target_weights(
        self,
        date: pd.Timestamp | _dt.date,
        prices_panel: dict[str, pd.DataFrame],
    ) -> dict[str, float]:
        """按动量倾斜生成 `date` 当天的目标权重。

        无可用动量（数据不足/全部 NaN）时降级为等权。
        """
        symbols = list(prices_panel)
        n = len(symbols)
        if n == 0:
            return {}
        if n == 1:
            return {symbols[0]: 1.0}

        ts = pd.Timestamp(date)

        # 1. 计算每个 symbol 在 date 当天的动量值
        scores = self._momentum_scores(ts, prices_panel)

        # 2. 缺值降级
        if scores.isna().all():
            w_eq = 1.0 / n
            return {s: w_eq for s in symbols}

        # 3. 横截面 z-score（NaN 当作 0 = 中性）
        z = self._zscore(scores).fillna(0.0)

        # 4. 线性倾斜 → clip → 归一化
        weights = self._tilt_weights(z)

        return {s: float(weights.loc[s]) for s in symbols}

    # ------------------------------------------------------------------
    # 内部辅助（公开命名以便测试）
    # ------------------------------------------------------------------

    def _momentum_scores(
        self,
        date: pd.Timestamp,
        prices_panel: dict[str, pd.DataFrame],
    ) -> pd.Series:
        """对 panel 中的每个 symbol 取 `date` 当天的动量得分。

        启用 secondary lookback 时，两者各自横截面 z-score 后等权平均。
        """
        symbols = list(prices_panel)
        primary = self._row_at(self._mom_primary.compute_panel(prices_panel), date)
        if self._mom_secondary is None:
            return primary.reindex(symbols)

        secondary = self._row_at(
            self._mom_secondary.compute_panel(prices_panel), date
        )
        z1 = self._zscore(primary).fillna(0.0)
        z2 = self._zscore(secondary).fillna(0.0)
        combined = (z1 + z2) / 2.0
        # 标记两边都 NaN 的 symbol
        all_nan_mask = primary.isna() & secondary.isna()
        combined[all_nan_mask] = np.nan
        return combined.reindex(symbols)

    @staticmethod
    def _row_at(panel_wide: pd.DataFrame, date: pd.Timestamp) -> pd.Series:
        """从 wide DataFrame 中按 `date` 取一行；不存在则取 <= date 的最后一行。"""
        if panel_wide.empty:
            return pd.Series(dtype=float)
        if date in panel_wide.index:
            return panel_wide.loc[date]
        candidates = panel_wide.loc[:date]
        if candidates.empty:
            return pd.Series(np.nan, index=panel_wide.columns)
        return candidates.iloc[-1]

    @staticmethod
    def _zscore(s: pd.Series) -> pd.Series:
        x = s.astype(float)
        valid = x.dropna()
        if len(valid) < 2:
            return pd.Series(np.nan, index=s.index)
        std = valid.std()
        if std == 0 or pd.isna(std):
            return pd.Series(0.0, index=s.index)
        return (x - valid.mean()) / std

    def _tilt_weights(self, z: pd.Series) -> pd.Series:
        """`w_raw = 1/N + alpha * z / N` → clip → normalize（带迭代再分配）.

        简单的一次 clip + 归一化在极端 z 下会失真（被 clip 后归一化又跑出边界）。
        这里用经典的「水位线」迭代：
          每轮把当前 free 资产按比例缩放到 sum=remaining；
          检查超出 [w_min, w_max] 的，钉死在边界、移出 free 集合；
          直到没有新违规或 free 为空。
        """
        n = len(z)
        eps = 1e-12
        # 先按可行区间 [w_min, w_max] 做基本可行性检查：
        if self.w_min * n > 1.0 + eps or self.w_max * n < 1.0 - eps:
            raise ValueError(
                f"w_min*N={self.w_min*n} 与 w_max*N={self.w_max*n} 与归一化和=1 矛盾"
            )

        raw = 1.0 / n + (self.alpha * z) / n
        # 起步先 clip 一次（让初始 free_w 不会出现负数等极端值）
        w = raw.clip(lower=self.w_min, upper=self.w_max).astype(float)

        fixed: dict[str, float] = {}
        symbols = list(z.index)
        for _ in range(2 * n + 2):
            free = [s for s in symbols if s not in fixed]
            remaining = 1.0 - sum(fixed.values())
            if not free:
                # 已全部被钉死：检验 sum 是否=1，否则按比例校正（应不会发生，因为
                # 上面有可行性断言）
                total_fixed = sum(fixed.values())
                if abs(total_fixed - 1.0) > 1e-9 and total_fixed > 0:
                    factor = 1.0 / total_fixed
                    fixed = {s: v * factor for s, v in fixed.items()}
                break

            free_w = w.loc[free].astype(float)
            total = float(free_w.sum())
            if total <= eps:
                free_w = pd.Series(remaining / len(free), index=free)
            else:
                free_w = free_w * (remaining / total)

            # 找新违规：取「最严重」的那个边界先钉，避免一轮把所有都钉超
            over = free_w[free_w > self.w_max + eps]
            under = free_w[free_w < self.w_min - eps]
            if over.empty and under.empty:
                # 收敛
                out = pd.Series(dtype=float)
                if fixed:
                    out = pd.concat([out, pd.Series(fixed, dtype=float)])
                out = pd.concat([out, free_w])
                return out.reindex(symbols).astype(float)

            # 优先处理上限（下限引发的「填满」更温和）
            if not over.empty:
                worst = over.idxmax()
                fixed[worst] = self.w_max
            else:
                worst = under.idxmin()
                fixed[worst] = self.w_min
            # 把 w 中的对应位置更新为边界（影响下一轮 free_w 取值）
            w.loc[worst] = fixed[worst]

        # 兜底：未收敛 → 等权
        eq = 1.0 / n
        return pd.Series(eq, index=symbols)
