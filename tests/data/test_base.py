"""数据层基础测试：normalize / 缓存路径生成。不接外部 API。"""

from __future__ import annotations

import pandas as pd
import pytest

from strategy_lib.data.base import BaseDataLoader, FetchSpec, Market


class _FakeLoader(BaseDataLoader):
    market = Market.CRYPTO

    def _fetch_one(self, spec: FetchSpec) -> pd.DataFrame:
        idx = pd.date_range("2024-01-01", periods=10, freq="D", tz="UTC")
        return pd.DataFrame(
            {
                "Open": range(10),
                "High": range(10),
                "Low": range(10),
                "Close": range(10),
                "Volume": range(10),
            },
            index=idx,
        )


def test_normalize_lowercases_columns():
    fl = _FakeLoader(cache=False)
    df = fl._fetch_one(FetchSpec("X"))
    out = fl._normalize(df)
    assert list(out.columns) == ["open", "high", "low", "close", "volume"]
    assert out.index.name == "timestamp"


def test_normalize_raises_on_missing_columns():
    fl = _FakeLoader(cache=False)
    bad = pd.DataFrame({"open": [1], "high": [1]}, index=pd.DatetimeIndex(["2024-01-01"], tz="UTC"))
    with pytest.raises(ValueError, match="missing columns"):
        fl._normalize(bad)


def test_cache_path_safe_for_slash_symbols(tmp_path, monkeypatch):
    fl = _FakeLoader(cache=False)
    p = fl._cache_path(FetchSpec("BTC/USDT", "1d"))
    assert "BTC_USDT" in p.name
    assert p.suffix == ".parquet"


def test_load_uses_cache_after_first_fetch(tmp_path, monkeypatch):
    from strategy_lib.utils import paths

    monkeypatch.setattr(paths, "RAW_DIR", tmp_path)
    monkeypatch.setattr("strategy_lib.data.base.RAW_DIR", tmp_path)

    fl = _FakeLoader(cache=True)
    df1 = fl.load("X", "1d")
    # 第二次：拉取被替换为 raise，确保走缓存
    monkeypatch.setattr(fl, "_fetch_one", lambda s: (_ for _ in ()).throw(AssertionError("应走缓存")))
    df2 = fl.load("X", "1d")
    pd.testing.assert_frame_equal(df1, df2)
