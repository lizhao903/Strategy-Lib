"""数据层：每个市场一个 Loader，统一返回标准 OHLCV DataFrame。

DataFrame 约定：
- 索引：UTC `DatetimeIndex`（命名 `timestamp`）
- 列：`open, high, low, close, volume`（小写）
- 多 symbol 加载返回 dict[symbol -> DataFrame]
"""

from __future__ import annotations

from strategy_lib.data.base import BaseDataLoader, Market, OHLCV_COLUMNS

__all__ = ["BaseDataLoader", "Market", "OHLCV_COLUMNS", "get_loader"]


def get_loader(market: str | Market, **kwargs) -> BaseDataLoader:
    """根据市场类型返回对应的 loader 实例。

    market: "crypto" | "cn_stock" | "us_stock" | "cn_etf" | "hk_stock"
    """
    market = Market(market) if isinstance(market, str) else market

    if market is Market.CRYPTO:
        from strategy_lib.data.crypto import CryptoLoader

        return CryptoLoader(**kwargs)
    if market in (Market.CN_STOCK, Market.HK_STOCK, Market.CN_ETF):
        from strategy_lib.data.cn_stock import CNStockLoader

        return CNStockLoader(market=market, **kwargs)
    if market is Market.US_STOCK:
        from strategy_lib.data.us_stock import USStockLoader

        return USStockLoader(**kwargs)

    raise ValueError(f"Unsupported market: {market}")
