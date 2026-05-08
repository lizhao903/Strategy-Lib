"""美股 / 美股 ETF 数据：yfinance。"""

from __future__ import annotations

import pandas as pd

from strategy_lib.data.base import BaseDataLoader, FetchSpec, Market

_TF_MAP = {"1d": "1d", "1h": "1h", "1m": "1m", "1wk": "1wk"}


class USStockLoader(BaseDataLoader):
    market = Market.US_STOCK

    def _fetch_one(self, spec: FetchSpec) -> pd.DataFrame:
        import yfinance as yf

        interval = _TF_MAP.get(spec.timeframe, spec.timeframe)
        df = yf.download(
            tickers=spec.symbol,
            start=spec.since,
            end=spec.until,
            interval=interval,
            auto_adjust=True,   # 复权
            progress=False,
            threads=False,
        )
        if df.empty:
            raise ValueError(f"yfinance returned empty for {spec.symbol}")
        # yfinance 多列时是 MultiIndex，单 ticker 也可能。统一拍平
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.reset_index().rename(columns={"Date": "timestamp", "Datetime": "timestamp"})
        return df
