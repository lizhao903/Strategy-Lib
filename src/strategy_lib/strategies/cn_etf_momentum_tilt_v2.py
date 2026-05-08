"""Strategy 4 v2 — A股 ETF 等权 + 动量倾斜（v2 改进版）。

v1 在 6 只 A股宽基/行业 ETF 池上 5α × 3lookback 共 8 次实验全部 IR 为负，
方向稳定 → 不是参数问题，是「6 ETF 横截面分散度太低」+「20 日动量被 A股
短期反转盖过」+「未明确 shift(1)」三重叠加。

v2 针对这些问题做出 4 项改进：

1. **扩池（最关键）**：6 → 11 标的，加入跨资产 5 类 CN-listed ETF：
   - 159920 恒生ETF（港股代理）
   - 518880 黄金ETF（商品/避险）
   - 513100 纳指ETF（美股科技）
   - 513500 标普500ETF（美股宽基）
   - 511260 十年国债ETF（利率/防御）
   动机：横截面 σ↑、相关性↓ → z-score 信息密度上升。
2. **显式 shift(1)**：``target_weights`` 内用 ``df.index < date`` 严格小于切片。
   保证 rebalance 日**只用前一日及更早**的数据，杜绝 same-bar 偷看。
3. **更长 lookback + skip**：默认 ``lookback=120, skip=5``（季度趋势 +
   跳过近 1 周短期反转）。
4. **可选 vol-adjusted**：``signal="vol_adj"`` 时把动量除以 60 日波动率，
   防止扩池后高波动资产（如纳指/创业板）长期主导。

本类仅覆盖 ``target_weights`` 钩子，其它逻辑（再平衡日历、from_orders、
权重校验）完全沿用 S3 父类 ``EqualRebalanceStrategy``。
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

import numpy as np
import pandas as pd

from strategy_lib.factors.momentum import MomentumReturn, VolAdjustedMomentum
from strategy_lib.strategies.cn_etf_equal_rebalance import EqualRebalanceStrategy


class MomentumTiltV2Strategy(EqualRebalanceStrategy):
    """v2 横截面动量倾斜 + 扩池 + 严格 shift(1) + 可选 vol-adjust.

    Parameters
    ----------
    lookback : int
        动量窗口（默认 120 日，约一个季度）。
    skip : int
        跳过最近 N 日（默认 5，规避短期反转）。
    secondary_lookback : int | None
        可选二级动量 lookback（如 60）。两者各自横截面 z-score 后等权融合。
    secondary_skip : int | None
        二级动量的 skip（None → 与主一致）。
    alpha : float
        倾斜强度 raw_w = 1/N + alpha * z / N。
    w_min, w_max : float
        单资产权重上下限。
    signal : {"raw", "vol_adj"}
        动量信号类型。``"vol_adj"`` 时使用 ``VolAdjustedMomentum``（动量/波动率）。
    vol_lookback : int
        vol_adj 模式下的波动率窗口（默认 60）。
    """

    #: v2 扩池：11 只跨资产 ETF（A股宽基/行业 6 + 港股 + 黄金 + 美股 2 + 十年国债）
    DEFAULT_SYMBOLS_V2: tuple[str, ...] = (
        # A股 6 只（与 v1 一致）
        "510300",  # 沪深300
        "510500",  # 中证500
        "159915",  # 创业板
        "512100",  # 中证1000
        "512880",  # 证券
        "512170",  # 医疗
        # 跨资产 5 只（v2 新增）
        "159920",  # 恒生ETF（港股）
        "518880",  # 黄金ETF（商品/避险）
        "513100",  # 纳指ETF（美股）
        "513500",  # 标普500ETF（美股）
        "511260",  # 十年国债ETF（利率/防御）
    )

    def __init__(
        self,
        symbols: list[str] | tuple[str, ...] | None = None,
        *,
        rebalance_period: int = 20,
        drift_threshold: float | None = None,
        lookback: int = 120,
        skip: int = 5,
        secondary_lookback: int | None = None,
        secondary_skip: int | None = None,
        alpha: float = 1.0,
        w_min: float = 0.03,
        w_max: float = 0.30,
        signal: str = "raw",
        vol_lookback: int = 60,
        name: str = "cn_etf_momentum_tilt_v2",
        **kwargs: Any,
    ) -> None:
        # 扩池 default：未传 symbols 时使用 v2 11 只
        if symbols is None:
            symbols = self.DEFAULT_SYMBOLS_V2
        super().__init__(
            symbols=symbols,
            rebalance_period=rebalance_period,
            drift_threshold=drift_threshold,
            name=name,
            **kwargs,
        )

        if alpha < 0:
            raise ValueError("alpha 必须 >= 0")
        if not (0.0 <= w_min < w_max <= 1.0):
            raise ValueError("需要 0 <= w_min < w_max <= 1")
        if signal not in ("raw", "vol_adj"):
            raise ValueError(f"signal 必须是 'raw' 或 'vol_adj'，得到 {signal}")

        # 小 N 池自适应：默认 (0.03, 0.30) 是按 N=11 调过的
        # （0.03*11=0.33, 0.30*11=3.3 包住 1.0）。当 N<5 时 0.30*N<1.0 会
        # 触发 ``w_max*N<1`` 矛盾。这里在用户没有显式覆盖时按 N 自动放宽，
        # 让 crypto V2-S4 (BTC/ETH 双标 / TOP_3) 能跑通。
        n_syms = len(symbols)
        if n_syms >= 2:
            if w_max * n_syms < 1.0:
                # 让 w_max 至少能撑起单资产 100%（N=2 → 1.0；N=3 → 0.7；N=4 → 0.5）
                auto_w_max = max(w_max, 1.0 / max(n_syms - 1, 1))
                w_max = min(auto_w_max, 1.0)
            if w_min * n_syms > 1.0:
                w_min = max(0.0, 1.0 / (n_syms * 2))

        self.lookback = lookback
        self.skip = skip
        self.secondary_lookback = secondary_lookback
        self.secondary_skip = secondary_skip if secondary_skip is not None else skip
        self.alpha = alpha
        self.w_min = w_min
        self.w_max = w_max
        self.signal = signal
        self.vol_lookback = vol_lookback

        self._mom_primary = self._make_factor(lookback, skip)
        self._mom_secondary = (
            self._make_factor(secondary_lookback, self.secondary_skip)
            if secondary_lookback is not None
            else None
        )

    def _make_factor(self, lookback: int, skip: int):
        if self.signal == "vol_adj":
            return VolAdjustedMomentum(
                lookback=lookback, skip=skip, vol_lookback=self.vol_lookback
            )
        return MomentumReturn(lookback=lookback, skip=skip)

    # ------------------------------------------------------------------
    # 核心钩子
    # ------------------------------------------------------------------

    def target_weights(
        self,
        date: pd.Timestamp | _dt.date,
        prices_panel: dict[str, pd.DataFrame],
    ) -> dict[str, float]:
        """按动量倾斜生成 ``date`` 当天的目标权重。

        关键改动 vs v1：使用 ``df.index < ts`` **严格小于**切片，确保
        信号只用前一交易日及更早的数据（杜绝 same-bar lookahead）。
        """
        symbols = list(prices_panel)
        n = len(symbols)
        if n == 0:
            return {}
        if n == 1:
            return {symbols[0]: 1.0}

        ts = pd.Timestamp(date)

        # 1. 严格 shift(1) 切片：只用 < date 的数据计算因子
        sliced = self._slice_strict(prices_panel, ts)

        # 2. 计算每个 symbol 在切片末端的动量值
        scores = self._momentum_scores(sliced)

        # 3. 缺值降级
        if scores.isna().all():
            w_eq = 1.0 / n
            return {s: w_eq for s in symbols}

        # 4. 横截面 z-score（NaN 当作 0 = 中性）
        z = self._zscore(scores).fillna(0.0)

        # 5. 线性倾斜 → clip → 归一化
        weights = self._tilt_weights(z)

        return {s: float(weights.loc[s]) for s in symbols}

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _slice_strict(
        panel: dict[str, pd.DataFrame], date: pd.Timestamp
    ) -> dict[str, pd.DataFrame]:
        """对每个 symbol 取 ``index < date`` 的子表（严格小于）。

        S3 父类的下单是「rebalance 日 close 价格 + targetpercent」，
        信号必须在该日 close **之前**就已知 → 用 < 而非 <=。
        """
        out: dict[str, pd.DataFrame] = {}
        for s, df in panel.items():
            mask = df.index < date
            out[s] = df.loc[mask]
        return out

    def _momentum_scores(
        self, prices_panel: dict[str, pd.DataFrame]
    ) -> pd.Series:
        """对 panel 中的每个 symbol 取最末一行的动量得分。

        启用 secondary lookback 时，两者各自横截面 z-score 后等权平均。
        """
        symbols = list(prices_panel)
        primary = self._last_row(self._mom_primary.compute_panel(prices_panel))
        if self._mom_secondary is None:
            return primary.reindex(symbols)

        secondary = self._last_row(
            self._mom_secondary.compute_panel(prices_panel)
        )
        z1 = self._zscore(primary).fillna(0.0)
        z2 = self._zscore(secondary).fillna(0.0)
        combined = (z1 + z2) / 2.0
        all_nan_mask = primary.isna() & secondary.isna()
        combined[all_nan_mask] = np.nan
        return combined.reindex(symbols)

    @staticmethod
    def _last_row(panel_wide: pd.DataFrame) -> pd.Series:
        if panel_wide.empty:
            return pd.Series(dtype=float)
        return panel_wide.iloc[-1]

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
        """``w_raw = 1/N + alpha * z / N`` → clip → normalize（带迭代再分配）。

        与 v1 相同的 water-filling 算法，仅边界默认改为 [0.03, 0.30]
        以适配 N=11 扩池（1/N≈9.1%，对称留出更多 tilt 空间）。
        """
        n = len(z)
        eps = 1e-12
        if self.w_min * n > 1.0 + eps or self.w_max * n < 1.0 - eps:
            raise ValueError(
                f"w_min*N={self.w_min*n} 与 w_max*N={self.w_max*n} 与归一化和=1 矛盾"
            )

        raw = 1.0 / n + (self.alpha * z) / n
        w = raw.clip(lower=self.w_min, upper=self.w_max).astype(float)

        fixed: dict[str, float] = {}
        symbols = list(z.index)
        for _ in range(2 * n + 2):
            free = [s for s in symbols if s not in fixed]
            remaining = 1.0 - sum(fixed.values())
            if not free:
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

            over = free_w[free_w > self.w_max + eps]
            under = free_w[free_w < self.w_min - eps]
            if over.empty and under.empty:
                out = pd.Series(dtype=float)
                if fixed:
                    out = pd.concat([out, pd.Series(fixed, dtype=float)])
                out = pd.concat([out, free_w])
                return out.reindex(symbols).astype(float)

            if not over.empty:
                worst = over.idxmax()
                fixed[worst] = self.w_max
            else:
                worst = under.idxmin()
                fixed[worst] = self.w_min
            w.loc[worst] = fixed[worst]

        eq = 1.0 / n
        return pd.Series(eq, index=symbols)


__all__ = ["MomentumTiltV2Strategy"]
