"""Pytest 共享 fixture：合成 OHLCV 数据，避免测试依赖外部数据源。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def synth_ohlcv() -> pd.DataFrame:
    """单 asset 合成 OHLCV，250 个交易日，几何布朗运动。"""
    rng = np.random.default_rng(42)
    n = 250
    rets = rng.normal(0.0005, 0.02, size=n)
    close = 100 * np.exp(np.cumsum(rets))
    high = close * (1 + np.abs(rng.normal(0, 0.005, size=n)))
    low = close * (1 - np.abs(rng.normal(0, 0.005, size=n)))
    open_ = close * (1 + rng.normal(0, 0.003, size=n))
    volume = rng.uniform(1e6, 5e6, size=n)
    idx = pd.date_range("2023-01-01", periods=n, freq="D", tz="UTC", name="timestamp")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


@pytest.fixture
def synth_panel(synth_ohlcv) -> dict[str, pd.DataFrame]:
    """多 asset：复用 synth_ohlcv 加随机扰动制造 5 个 symbol。"""
    rng = np.random.default_rng(7)
    panel = {}
    for i in range(5):
        df = synth_ohlcv.copy()
        bump = 1 + rng.normal(0, 0.001, size=len(df)).cumsum()
        for c in ("open", "high", "low", "close"):
            df[c] = df[c] * bump
        panel[f"SYM{i}"] = df
    return panel
