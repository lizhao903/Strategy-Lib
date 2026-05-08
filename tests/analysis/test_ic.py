"""IC 分析层测试。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from strategy_lib.analysis import (
    compute_forward_returns,
    ic_decay,
    ic_timeseries,
    quantile_cumulative_returns,
    quantile_returns,
    rank_ic_timeseries,
    summarize_factor,
)


def _synth_panel_to_wide(panel: dict[str, pd.DataFrame]) -> pd.DataFrame:
    return pd.DataFrame({s: df["close"] for s, df in panel.items()})


def test_forward_returns_shift(synth_panel):
    prices = _synth_panel_to_wide(synth_panel)
    fwd = compute_forward_returns(prices, periods=(1, 5))
    # 最后 5 期没有 5 日未来收益
    assert fwd[5].iloc[-5:].isna().all().all()


def test_ic_with_perfect_predictor(synth_panel):
    """如果因子=未来收益本身，IC 应该 ~1。"""
    prices = _synth_panel_to_wide(synth_panel)
    fwd = prices.pct_change(5).shift(-5)
    ic = ic_timeseries(fwd, fwd)  # factor == fwd_ret
    assert ic.dropna().mean() > 0.95


def test_ic_with_random_predictor(synth_panel):
    prices = _synth_panel_to_wide(synth_panel)
    fwd = prices.pct_change(5).shift(-5)
    rng = np.random.default_rng(0)
    noise = pd.DataFrame(rng.normal(size=fwd.shape), index=fwd.index, columns=fwd.columns)
    ic = ic_timeseries(noise, fwd)
    assert abs(ic.mean()) < 0.2  # 噪声 IC 应该接近 0


def test_rank_ic_robust_to_outliers(synth_panel):
    prices = _synth_panel_to_wide(synth_panel)
    fwd = prices.pct_change(5).shift(-5)
    factor = fwd.copy()
    factor.iloc[0, 0] = 1e10  # 注入极端值
    rank_ic = rank_ic_timeseries(factor, fwd)
    assert rank_ic.dropna().mean() > 0.9


def test_quantile_returns_shape(synth_panel):
    prices = _synth_panel_to_wide(synth_panel)
    fwd = prices.pct_change(5).shift(-5)
    factor = prices.pct_change(20)
    qr = quantile_returns(factor, fwd, n_groups=3)
    assert list(qr.columns) == ["Q1", "Q2", "Q3"]


def test_quantile_cumulative_includes_long_short(synth_panel):
    prices = _synth_panel_to_wide(synth_panel)
    factor = prices.pct_change(20)
    cum = quantile_cumulative_returns(factor, prices, n_groups=3, holding_period=5)
    assert "LongShort" in cum.columns


def test_ic_decay_returns_dataframe(synth_panel):
    prices = _synth_panel_to_wide(synth_panel)
    factor = prices.pct_change(20)
    decay = ic_decay(factor, prices, periods=(1, 5, 10))
    assert {"ic_mean", "icir", "rank_ic_mean"}.issubset(decay.columns)
    assert list(decay.index) == [1, 5, 10]


def test_summarize_factor_keys(synth_panel):
    prices = _synth_panel_to_wide(synth_panel)
    factor = prices.pct_change(20)
    s = summarize_factor(factor, prices, fwd_period=5)
    assert {"ic_mean", "icir", "rank_ic_mean", "n_periods"}.issubset(s.keys())
