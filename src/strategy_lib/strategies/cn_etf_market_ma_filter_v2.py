"""Strategy 7 v2 — 大盘 MA 过滤的 ship 版（lag=1 主参数 + 11 池 risky pool）。

v1 sensitivity sweep 已证：
- lag=1 是 4 档 lag 中唯一显著跑赢 S3 的（NAV 119.1k / Sharpe 0.30 / vs S3 +1.34%/yr）
- lag 越大越差（加层过滤反而损害收益），事前默认 lag=2 是错误直觉

v2 改动 = 把这两条已验证结论变成默认配置：
1. ``lag_days = 1`` 默认（v1 默认是 2）
2. 11 池 risky pool（继承 S4v2 扩池发现：73% alpha 来自池子本身）

代码本体复用 v1 的 ``MarketMAFilterStrategy``，仅改默认参数 — 避免代码重复。
v1 类作为 baseline 保留不动。
"""

from __future__ import annotations

from strategy_lib.strategies.cn_etf_market_ma_filter import (
    MarketMAFilterResult,
    MarketMAFilterStrategy,
)

# 11 池：S4v2 已验证扩池本身贡献 73% alpha
RISKY_POOL_11 = (
    "510300",  # 沪深300
    "510500",  # 中证500
    "159915",  # 创业板
    "512100",  # 中证1000
    "512880",  # 证券
    "512170",  # 医疗
    "159920",  # 恒生 ETF（港股代理）
    "518880",  # 黄金 ETF
    "513100",  # 纳指 ETF
    "513500",  # 标普500 ETF
    "511260",  # 十年国债 ETF
)


class MarketMAFilterV2Strategy(MarketMAFilterStrategy):
    """v2: 默认 lag=1 + 11 池 risky pool。其余行为与 v1 完全一致。"""

    DEFAULT_SYMBOLS: tuple[str, ...] = RISKY_POOL_11

    def __init__(
        self,
        symbols=None,
        *,
        cash_symbol: str = "511990",
        signal_symbol: str = "510300",
        ma_length: int = 200,
        lag_days: int = 1,            # v2: 默认 1（v1 默认 2）
        weight_mode: str = "equal",
        name: str = "cn_etf_market_ma_filter_v2",
    ) -> None:
        super().__init__(
            symbols=symbols,
            cash_symbol=cash_symbol,
            signal_symbol=signal_symbol,
            ma_length=ma_length,
            lag_days=lag_days,
            weight_mode=weight_mode,
            name=name,
        )


__all__ = ["MarketMAFilterResult", "MarketMAFilterV2Strategy", "RISKY_POOL_11"]
