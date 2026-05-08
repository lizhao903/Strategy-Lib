"""中国股票市场数据：A股、港股、ETF。底层 akshare（免费、无需 token）。"""

from __future__ import annotations

import pandas as pd

from strategy_lib.data.base import BaseDataLoader, FetchSpec, Market

# akshare 列名 -> 标准列名
_RENAME = {
    "日期": "timestamp",
    "开盘": "open",
    "最高": "high",
    "最低": "low",
    "收盘": "close",
    "成交量": "volume",
}


class CNStockLoader(BaseDataLoader):
    """A股 / 港股 / A股 ETF 统一 loader。

    symbol 约定：
    - A股：6位代码，如 "600519"
    - A股 ETF：6位代码，如 "510300"
    - 港股：5位代码，如 "00700"
    """

    def __init__(
        self,
        market: Market = Market.CN_STOCK,
        *,
        adjust: str = "qfq",  # 前复权
        cache: bool = True,
        refresh: bool = False,
    ) -> None:
        super().__init__(cache=cache, refresh=refresh)
        if market not in (Market.CN_STOCK, Market.HK_STOCK, Market.CN_ETF):
            raise ValueError(f"CNStockLoader does not support {market}")
        self.market = market
        self.adjust = adjust

    def _fetch_one(self, spec: FetchSpec) -> pd.DataFrame:
        import akshare as ak

        if spec.timeframe != "1d":
            raise NotImplementedError("CN market: 当前仅支持 daily（1d），分钟数据后续接入")

        start = (spec.since or "2010-01-01").replace("-", "")
        end = (spec.until or pd.Timestamp.utcnow().strftime("%Y-%m-%d")).replace("-", "")

        if self.market is Market.CN_STOCK:
            df = ak.stock_zh_a_hist(
                symbol=spec.symbol, period="daily", start_date=start, end_date=end,
                adjust=self.adjust,
            )
        elif self.market is Market.CN_ETF:
            df = ak.fund_etf_hist_em(
                symbol=spec.symbol, period="daily", start_date=start, end_date=end,
                adjust=self.adjust,
            )
        elif self.market is Market.HK_STOCK:
            df = ak.stock_hk_hist(
                symbol=spec.symbol, period="daily", start_date=start, end_date=end,
                adjust=self.adjust,
            )
        else:  # pragma: no cover
            raise AssertionError

        df = df.rename(columns=_RENAME)
        return df
