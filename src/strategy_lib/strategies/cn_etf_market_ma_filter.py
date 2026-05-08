"""Strategy 7 — A股 ETF 大盘 MA 过滤 (Benchmark Suite V1).

**单一大盘信号 + 二元仓位**：
- 每日检查信号资产（默认 510300 沪深300）的收盘价 vs 长周期 MA（默认 200 日）
- 信号 ON（close > MA，连续 lag_days 日满足）：满仓 risky pool（默认 S3 等权 6 ETF）
- 信号 OFF：全部转入现金等价资产（默认 511990 货币基金）
- 切换在信号变化的次日开盘成交（vbt close 成交 + shift(1) 防 lookahead）

设计参考 Mebane Faber (2007) GTAA 的简化版（单资产二元过滤）。

与 S5 (`cn_etf_trend_tilt`) 的本质区别
--------------------------------------
- S5：6 个 ETF 各自跑 trend score，加权倾斜（信息冗余 + 假突破频繁）
- S7：1 个市场代理（510300）决定全局 ON/OFF（信号更稳、切换更少）

V1 baseline 已验证 vectorbt `from_orders + targetpercent + cash_sharing` 兼容
sum<1 与 11 资产（S4v2/S5v2）。本策略复用同一回测引擎。

不强求继承 ``EqualRebalanceStrategy``：S7 的权重生成逻辑（基于市场代理信号
全局切换）与 S3 的「按再平衡日历产生权重」结构差异较大，独立实现更清晰。
但内部使用与 S3 完全一致的 ``vbt.Portfolio.from_orders`` 调用模式。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd


@dataclass
class MarketMAFilterResult:
    """S7 回测结果。"""

    portfolio: object  # vectorbt Portfolio
    target_weights: pd.DataFrame  # index=date, columns=symbol；逐日权重（不是 NaN，每日更新）
    signal: pd.Series  # index=date, value ∈ {0, 1}；最终采用的 (lagged + filtered) 信号
    raw_signal: pd.Series  # index=date, value ∈ {0, 1}；过滤前的原始信号 (close > MA)
    switch_dates: pd.DatetimeIndex  # 实际发生 ON↔OFF 切换的日期
    metrics: dict


class MarketMAFilterStrategy:
    """大盘 MA 过滤的二元 risk-on/off 策略。

    Parameters
    ----------
    symbols
        Risk-on 时持仓的 risky 资产池。默认与 V1 baseline 6 池一致。
    cash_symbol
        Risk-off 时全仓持有的现金等价资产。默认 ``511990``（货币基金）。
    signal_symbol
        信号资产。默认 ``510300``（沪深300）。**不要求**包含在 ``symbols`` 内
        （即信号资产可以与持仓资产分离），但通常会包含。
    ma_length
        MA 长度（交易日）。默认 200。
    lag_days
        滞后过滤天数：原始信号需要连续 ``lag_days`` 日同向才触发实际切换。
        默认 2（连续 2 天 close > MA 才进场，连续 2 天 close ≤ MA 才离场）。
        设为 1 即等价于"无滞后过滤"。
    weight_mode
        Risk-on 时的权重分配方式。
        - ``"equal"``（默认）：6 ETF 等权 1/6
        - ``"signal_only"``：仅持有 signal_symbol 100%（用于测试纯 timing 效果）
    name
        策略名（日志/标识）。
    """

    DEFAULT_SYMBOLS: tuple[str, ...] = (
        "510300",  # 沪深300
        "510500",  # 中证500
        "159915",  # 创业板
        "512100",  # 中证1000
        "512880",  # 证券
        "512170",  # 医疗
    )

    def __init__(
        self,
        symbols: Sequence[str] | None = None,
        *,
        cash_symbol: str = "511990",
        signal_symbol: str = "510300",
        ma_length: int = 200,
        lag_days: int = 2,
        weight_mode: str = "equal",
        name: str = "cn_etf_market_ma_filter",
    ) -> None:
        if ma_length < 2:
            raise ValueError("ma_length 必须 >= 2")
        if lag_days < 1:
            raise ValueError("lag_days 必须 >= 1（=1 表示无滞后过滤）")
        if weight_mode not in ("equal", "signal_only"):
            raise ValueError(f"weight_mode 必须是 'equal' 或 'signal_only'，得到 {weight_mode}")
        self.symbols: list[str] = list(symbols) if symbols is not None else list(self.DEFAULT_SYMBOLS)
        self.cash_symbol = cash_symbol
        self.signal_symbol = signal_symbol
        self.ma_length = ma_length
        self.lag_days = lag_days
        self.weight_mode = weight_mode
        self.name = name

    # ------------------------------------------------------------------
    # 信号生成
    # ------------------------------------------------------------------
    def _compute_raw_signal(self, signal_close: pd.Series) -> pd.Series:
        """原始 ON/OFF 信号：close > MA(N) → 1, else 0。

        在 MA 暖机期内（前 ma_length-1 天），信号置 0（保守视为 risk-off）。
        """
        ma = signal_close.rolling(self.ma_length).mean()
        sig = (signal_close > ma).astype(int)
        # 暖机期：MA 为 NaN 时强制 0
        sig = sig.where(ma.notna(), 0).astype(int)
        return sig.rename("raw_signal")

    def _apply_lag_filter(self, raw: pd.Series) -> pd.Series:
        """滞后过滤：连续 lag_days 日同向才切换状态。

        实现：每天的"当前状态"= 该日是否处于「上个 ``lag_days`` 日全部为新状态」的窗口。
        具体：
        - 如果连续 lag_days 天 raw == 1，则 filtered = 1
        - 如果连续 lag_days 天 raw == 0，则 filtered = 0
        - 否则保持上一日 filtered（粘滞）

        lag_days = 1 时退化为 filtered == raw。
        """
        if self.lag_days == 1:
            return raw.copy().rename("signal")

        n = self.lag_days
        # 滚动窗口求和：== n 表示连续 n 天都是 1，== 0 表示连续 n 天都是 0
        rolled = raw.rolling(n).sum()
        out = pd.Series(np.nan, index=raw.index)
        # 初始状态默认 0（risk-off）
        last = 0
        rolled_arr = rolled.values
        out_arr = np.empty(len(raw), dtype=float)
        for i, r in enumerate(rolled_arr):
            if np.isnan(r):
                # 暖机期内（< n-1 天）保持 last
                out_arr[i] = last
                continue
            if r == n:  # 连续 n 天 1
                last = 1
            elif r == 0:  # 连续 n 天 0
                last = 0
            # 否则 last 不变（粘滞）
            out_arr[i] = last
        return pd.Series(out_arr, index=raw.index, name="signal").astype(int)

    def build_signal(
        self,
        panel: dict[str, pd.DataFrame],
    ) -> tuple[pd.Series, pd.Series]:
        """生成 (raw_signal, lag-filtered signal)。

        Returns
        -------
        raw_signal : pd.Series, dtype=int, 0/1
        signal     : pd.Series, dtype=int, 0/1（最终用于权重分配）
        """
        if self.signal_symbol not in panel:
            raise KeyError(f"panel 缺少 signal_symbol: {self.signal_symbol}")
        signal_close = panel[self.signal_symbol]["close"]
        raw = self._compute_raw_signal(signal_close)
        sig = self._apply_lag_filter(raw)
        return raw, sig

    # ------------------------------------------------------------------
    # 权重生成
    # ------------------------------------------------------------------
    def _all_assets(self) -> list[str]:
        """全部资产 = risky symbols + cash_symbol（去重保序）。"""
        seen = set()
        out: list[str] = []
        for s in list(self.symbols) + [self.cash_symbol]:
            if s not in seen:
                seen.add(s)
                out.append(s)
        return out

    def _risk_on_weights(self) -> dict[str, float]:
        """Risk-on 时的目标权重 dict（不含 cash_symbol）。"""
        if self.weight_mode == "equal":
            n = len(self.symbols)
            return {s: 1.0 / n for s in self.symbols}
        elif self.weight_mode == "signal_only":
            return {self.signal_symbol: 1.0}
        else:  # pragma: no cover
            raise ValueError(self.weight_mode)

    def build_target_weight_panel(
        self,
        panel: dict[str, pd.DataFrame],
        signal: pd.Series,
    ) -> pd.DataFrame:
        """逐日权重 DataFrame。

        - 信号 ON 日：risky pool 等权（cash_symbol 权重 = 0）
        - 信号 OFF 日：cash_symbol 权重 = 1（risky pool 全 0）

        所有资产对齐到共同的交易日历交集。
        """
        all_syms = self._all_assets()
        common_idx: pd.DatetimeIndex | None = None
        for s in all_syms:
            if s not in panel:
                raise KeyError(f"panel 缺少 symbol: {s}")
            idx = panel[s].index
            common_idx = idx if common_idx is None else common_idx.intersection(idx)
        assert common_idx is not None
        common_idx = common_idx.sort_values()

        sig_aligned = signal.reindex(common_idx).fillna(0).astype(int)

        weights = pd.DataFrame(0.0, index=common_idx, columns=all_syms, dtype="float64")

        on_w = self._risk_on_weights()
        # ON 日：填 risky pool 权重
        on_mask = (sig_aligned == 1).values
        for s, w in on_w.items():
            if s in weights.columns:
                weights.loc[on_mask, s] = w
        # OFF 日：cash_symbol = 1
        off_mask = (sig_aligned == 0).values
        weights.loc[off_mask, self.cash_symbol] = 1.0

        return weights

    # ------------------------------------------------------------------
    # 主回测入口
    # ------------------------------------------------------------------
    def run(
        self,
        panel: dict[str, pd.DataFrame],
        *,
        init_cash: float = 100_000,
        fees: float = 0.00005,
        slippage: float = 0.0005,
        signal_lag: int = 1,
    ) -> MarketMAFilterResult:
        """执行回测。

        Parameters
        ----------
        panel
            ``dict[symbol -> OHLCV DataFrame]``。必须包含 ``signal_symbol``、
            全部 ``self.symbols`` 与 ``cash_symbol``。
        init_cash, fees, slippage
            V1 共享基线：100k / 万 0.5 佣金 / 万 5 滑点。
        signal_lag
            权重 shift 天数。默认 1：t 日生成的信号在 t+1 日成交（避免 lookahead）。
            设为 0 即同 bar 成交（不推荐；用于消融测试）。
        """
        import vectorbt as vbt

        raw_sig, sig = self.build_signal(panel)
        weights = self.build_target_weight_panel(panel, sig)

        # shift(signal_lag): 让 t 日生成的信号在 t+signal_lag 日成交
        if signal_lag > 0:
            weights_traded = weights.shift(signal_lag).fillna(0.0)
            # 头 signal_lag 行（NaN→0）此时 cash_symbol 也是 0 → 表示首根 bar 完全空仓
            # 但我们希望第一根 bar 默认 risk-off（cash 100%），手动设置：
            for i in range(min(signal_lag, len(weights_traded))):
                weights_traded.iloc[i] = 0.0
                if self.cash_symbol in weights_traded.columns:
                    weights_traded.iloc[i, weights_traded.columns.get_loc(self.cash_symbol)] = 1.0
        else:
            weights_traded = weights.copy()

        all_syms = self._all_assets()
        close = pd.DataFrame(
            {s: panel[s]["close"] for s in all_syms}
        ).reindex(weights.index)

        # vectorbt 调用：sum<=1 兼容；用 cash_sharing 共享资金池
        pf = vbt.Portfolio.from_orders(
            close=close,
            size=weights_traded,
            size_type="targetpercent",
            init_cash=init_cash,
            fees=fees,
            slippage=slippage,
            group_by=True,
            cash_sharing=True,
            call_seq="auto",
            freq="1D",
        )

        # 切换日期：filtered signal 跳变的日期
        sig_aligned = sig.reindex(weights.index).fillna(0).astype(int)
        switches = sig_aligned.diff().fillna(0)
        switch_dates = pd.DatetimeIndex(weights.index[switches != 0])

        try:
            from strategy_lib.backtest.metrics import portfolio_metrics
            metrics = portfolio_metrics(pf)
        except Exception:
            metrics = {}

        return MarketMAFilterResult(
            portfolio=pf,
            target_weights=weights_traded,
            signal=sig_aligned,
            raw_signal=raw_sig.reindex(weights.index).fillna(0).astype(int),
            switch_dates=switch_dates,
            metrics=metrics,
        )


__all__ = ["MarketMAFilterStrategy", "MarketMAFilterResult"]
