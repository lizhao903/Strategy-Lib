"""因子层基础测试：能正确计算、形状对齐、参数化生效。"""

from __future__ import annotations

import pytest

from strategy_lib.factors import (
    ATRRatio,
    MACDDiff,
    MomentumReturn,
    OBVMomentum,
    RSIReversal,
    RealizedVol,
    ShortTermReversal,
    VolumeRatio,
)

ALL_FACTORS = [
    (MomentumReturn, {"lookback": 20}),
    (MACDDiff, {}),
    (ShortTermReversal, {"lookback": 5}),
    (RSIReversal, {"period": 14}),
    (RealizedVol, {"lookback": 20}),
    (ATRRatio, {"period": 14}),
    (VolumeRatio, {"lookback": 20}),
    (OBVMomentum, {"lookback": 20}),
]


@pytest.mark.parametrize("factor_cls,params", ALL_FACTORS)
def test_factor_compute_shape(factor_cls, params, synth_ohlcv):
    f = factor_cls(**params)
    out = f.compute(synth_ohlcv)
    assert len(out) == len(synth_ohlcv)
    assert out.index.equals(synth_ohlcv.index)
    # 至少 80% 是有效值（除非 lookback 很大）
    valid = out.notna().mean()
    assert valid > 0.5, f"{factor_cls.__name__} 有效值过少: {valid}"


@pytest.mark.parametrize("factor_cls,params", ALL_FACTORS)
def test_factor_compute_panel(factor_cls, params, synth_panel):
    f = factor_cls(**params)
    wide = f.compute_panel(synth_panel)
    assert wide.shape[1] == len(synth_panel)
    assert set(wide.columns) == set(synth_panel.keys())


def test_momentum_param_changes_output(synth_ohlcv):
    f1 = MomentumReturn(lookback=5)
    f2 = MomentumReturn(lookback=60)
    assert not f1.compute(synth_ohlcv).equals(f2.compute(synth_ohlcv))


def test_factor_full_name_includes_params():
    f = MomentumReturn(lookback=20, skip=5)
    assert "20" in f.full_name and "5" in f.full_name and "mom_return" in f.full_name


def test_factor_direction_attribute():
    assert MomentumReturn(lookback=20).direction == 1
    assert ShortTermReversal(lookback=5).direction == -1
    assert RealizedVol(lookback=20).direction == -1
