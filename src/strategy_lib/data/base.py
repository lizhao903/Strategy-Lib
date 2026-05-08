"""数据 Loader 的抽象基类，封装 parquet 缓存、列名规范化、并发拉取。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import pandas as pd

from strategy_lib.utils.logging import logger
from strategy_lib.utils.paths import RAW_DIR

OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]


class Market(str, Enum):
    CRYPTO = "crypto"
    CN_STOCK = "cn_stock"
    HK_STOCK = "hk_stock"
    CN_ETF = "cn_etf"
    US_STOCK = "us_stock"


@dataclass
class FetchSpec:
    symbol: str
    timeframe: str = "1d"
    since: str | None = None  # ISO date, e.g. "2020-01-01"
    until: str | None = None


class BaseDataLoader(ABC):
    """市场无关的 OHLCV 加载器接口。子类只需实现 `_fetch_one`。"""

    market: Market

    def __init__(self, *, cache: bool = True, refresh: bool = False) -> None:
        self.cache = cache
        self.refresh = refresh

    # ----- 公共 API -----

    def load(
        self,
        symbol: str,
        timeframe: str = "1d",
        since: str | None = None,
        until: str | None = None,
    ) -> pd.DataFrame:
        """加载单个 symbol 的 OHLCV。优先读缓存，缺失才拉取。"""
        spec = FetchSpec(symbol=symbol, timeframe=timeframe, since=since, until=until)
        cache_path = self._cache_path(spec)

        if self.cache and not self.refresh and cache_path.exists():
            logger.debug(f"cache hit: {cache_path.name}")
            df = pd.read_parquet(cache_path)
        else:
            logger.info(f"fetching {self.market.value}:{symbol} {timeframe} since={since}")
            df = self._fetch_one(spec)
            df = self._normalize(df)
            if self.cache:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                df.to_parquet(cache_path)

        return self._slice(df, since=since, until=until)

    def load_many(
        self,
        symbols: list[str],
        timeframe: str = "1d",
        since: str | None = None,
        until: str | None = None,
        max_workers: int = 4,
    ) -> dict[str, pd.DataFrame]:
        """并发加载多个 symbol。返回 dict。"""
        out: dict[str, pd.DataFrame] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            fut_to_sym = {
                ex.submit(self.load, s, timeframe, since, until): s for s in symbols
            }
            for fut, sym in fut_to_sym.items():
                try:
                    out[sym] = fut.result()
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"failed {sym}: {e}")
        return out

    # ----- 子类实现 -----

    @abstractmethod
    def _fetch_one(self, spec: FetchSpec) -> pd.DataFrame:
        """从外部数据源拉单个 symbol 的原始数据。返回 DataFrame，列名/索引在 _normalize 里规范化。"""

    # ----- 内部 -----

    def _cache_path(self, spec: FetchSpec) -> Path:
        safe_sym = spec.symbol.replace("/", "_").replace(":", "_")
        return RAW_DIR / self.market.value / f"{safe_sym}_{spec.timeframe}.parquet"

    @staticmethod
    def _normalize(df: pd.DataFrame) -> pd.DataFrame:
        """规范化为标准 OHLCV：索引为 UTC DatetimeIndex(name=timestamp)，列名小写。"""
        df = df.copy()
        # 列名小写
        df.columns = [str(c).lower() for c in df.columns]
        # 找到时间列
        if not isinstance(df.index, pd.DatetimeIndex):
            for col in ("timestamp", "date", "datetime", "time"):
                if col in df.columns:
                    df = df.set_index(col)
                    break
        df.index = pd.to_datetime(df.index, utc=True)
        df.index.name = "timestamp"
        # 只保留标准列（多余列丢弃）
        missing = [c for c in OHLCV_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(f"missing columns after normalize: {missing}")
        df = df[OHLCV_COLUMNS].astype("float64")
        df = df[~df.index.duplicated(keep="last")].sort_index()
        return df

    @staticmethod
    def _slice(df: pd.DataFrame, since: str | None, until: str | None) -> pd.DataFrame:
        if since:
            df = df.loc[df.index >= pd.Timestamp(since, tz="UTC")]
        if until:
            df = df.loc[df.index <= pd.Timestamp(until, tz="UTC")]
        return df
