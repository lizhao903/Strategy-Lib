"""加密货币数据：ccxt 拉取，默认 binance。"""

from __future__ import annotations

import time

import pandas as pd

from strategy_lib.data.base import BaseDataLoader, FetchSpec, Market
from strategy_lib.utils.logging import logger


class CryptoLoader(BaseDataLoader):
    market = Market.CRYPTO

    def __init__(
        self,
        exchange: str = "binance",
        *,
        cache: bool = True,
        refresh: bool = False,
        rate_limit_ms: int = 200,
    ) -> None:
        super().__init__(cache=cache, refresh=refresh)
        import ccxt

        self.exchange = getattr(ccxt, exchange)({"enableRateLimit": True})
        self.rate_limit_ms = rate_limit_ms

    def _fetch_one(self, spec: FetchSpec) -> pd.DataFrame:
        since_ms = (
            int(pd.Timestamp(spec.since, tz="UTC").timestamp() * 1000) if spec.since else None
        )
        until_ms = (
            int(pd.Timestamp(spec.until, tz="UTC").timestamp() * 1000) if spec.until else None
        )

        all_rows: list[list] = []
        cursor = since_ms
        while True:
            batch = self.exchange.fetch_ohlcv(
                spec.symbol, timeframe=spec.timeframe, since=cursor, limit=1000
            )
            if not batch:
                break
            all_rows.extend(batch)
            last_ts = batch[-1][0]
            if until_ms and last_ts >= until_ms:
                break
            if len(batch) < 1000:
                break
            cursor = last_ts + 1
            time.sleep(self.rate_limit_ms / 1000)
            logger.debug(f"  fetched {len(all_rows)} bars, last={pd.Timestamp(last_ts, unit='ms')}")

        df = pd.DataFrame(
            all_rows, columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        return df
