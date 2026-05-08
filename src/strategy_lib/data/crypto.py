"""加密货币数据：ccxt 拉取，默认 binance。"""

from __future__ import annotations

import time

import pandas as pd

from strategy_lib.data.base import BaseDataLoader, FetchSpec, Market, OHLCV_COLUMNS
from strategy_lib.utils.logging import logger

# 稳定币 / 现金代理常量集合：load() 时合成常数 OHLCV，不走 ccxt
_CONST_CASH_SYMBOLS: frozenset[str] = frozenset({"USDT", "USDC", "BUSD", "DAI", "FDUSD"})

_TIMEFRAME_TO_FREQ: dict[str, str] = {
    "1d": "1D",
    "12h": "12h",
    "8h": "8h",
    "6h": "6h",
    "4h": "4h",
    "2h": "2h",
    "1h": "1h",
    "30m": "30min",
    "15m": "15min",
    "5m": "5min",
    "1m": "1min",
}


def _synthesize_const_ohlcv(
    symbol: str,
    timeframe: str,
    since: str | None,
    until: str | None,
) -> pd.DataFrame:
    """对稳定币合成常数 1.0 OHLCV（close=open=high=low=1.0, volume=0）。

    crypto 24/7 + 稳定币锚定 USD，对回测来说"持有 USDT 就是持有 1 USD/coin"。
    需要明确 since/until 才能生成完整索引。
    """
    if not (since and until):
        raise ValueError(
            f"合成稳定币 {symbol!r} OHLCV 需要明确 since/until（crypto 24/7 无默认日历）"
        )
    freq = _TIMEFRAME_TO_FREQ.get(timeframe)
    if freq is None:
        raise ValueError(f"未知 timeframe: {timeframe!r}")
    idx = pd.date_range(start=since, end=until, freq=freq, tz="UTC", inclusive="both")
    idx.name = "timestamp"
    df = pd.DataFrame(
        {col: (1.0 if col != "volume" else 0.0) for col in OHLCV_COLUMNS},
        index=idx,
    ).astype("float64")
    return df


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

    def load(
        self,
        symbol: str,
        timeframe: str = "1d",
        since: str | None = None,
        until: str | None = None,
    ) -> pd.DataFrame:
        """加载单个 symbol。稳定币（USDT/USDC/...）走合成路径，不走 ccxt。"""
        if symbol in _CONST_CASH_SYMBOLS:
            logger.debug(f"crypto cash synth: {symbol} {timeframe} {since}~{until}")
            return _synthesize_const_ohlcv(symbol, timeframe, since, until)
        return super().load(symbol, timeframe=timeframe, since=since, until=until)

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
