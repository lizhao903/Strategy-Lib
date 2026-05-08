"""预定义标的池（Universe）+ 快速加载。

Universe 抽象的是「一组标的 + cash 代理 + benchmark」三件套，让策略与具体
symbol list 解耦。研究流程：
    from strategy_lib.universes import CN_ETF_EXPANDED_11
    panel = CN_ETF_EXPANDED_11.load_panel(since="2020-01-01", until="2024-12-31")
    # 然后用 strategy.run(panel, ...) 跑回测

用 ``Universe.custom(...)`` 可以一行造一个临时 universe。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


@dataclass(frozen=True)
class Universe:
    """命名标的池，含 cash/benchmark 元数据。

    Attributes
    ----------
    name : str
        Universe 名称（slug，用于日志/索引/文件名）
    symbols : tuple[str, ...]
        risky 资产列表
    market : str
        market id（cn_etf / cn_stock / hk_stock / us_stock / crypto），决定 loader
    cash_proxy : str | None
        现金等价资产（DCA / MA filter 类策略需要）。None 表示纯满仓策略不用 cash
    benchmark : str | None
        基准标的（用于计算 alpha / IR），不一定要在 symbols 里
    description : str
        简短描述（写报告时引用）
    warmup_days : int
        建议暖机天数（如 200MA 需 200 日，trend 因子需 ~120 日）
    """

    name: str
    symbols: tuple[str, ...]
    market: str
    cash_proxy: str | None = None
    benchmark: str | None = None
    description: str = ""
    warmup_days: int = 0
    extra_tags: tuple[str, ...] = field(default_factory=tuple)

    # ------------------------------------------------------------------
    # 构造助手
    # ------------------------------------------------------------------

    @classmethod
    def custom(
        cls,
        name: str,
        symbols: list[str] | tuple[str, ...],
        *,
        market: str,
        cash_proxy: str | None = None,
        benchmark: str | None = None,
        description: str = "",
        warmup_days: int = 0,
    ) -> "Universe":
        """一行造临时 universe（不入预定义清单）。"""
        return cls(
            name=name,
            symbols=tuple(symbols),
            market=market,
            cash_proxy=cash_proxy,
            benchmark=benchmark,
            description=description,
            warmup_days=warmup_days,
        )

    def with_extra(self, *symbols: str, name_suffix: str = "_plus") -> "Universe":
        """派生：在现有 symbols 末尾追加几个，新 universe 名 = 原名 + suffix。"""
        new_syms = tuple(self.symbols) + tuple(s for s in symbols if s not in self.symbols)
        return replace(self, name=self.name + name_suffix, symbols=new_syms)

    def subset(self, symbols: list[str], *, name: str | None = None) -> "Universe":
        """派生：只保留指定子集。"""
        kept = [s for s in symbols if s in self.symbols]
        if not kept:
            raise ValueError(f"subset 与 universe.symbols 无交集: {symbols}")
        return replace(self, name=name or f"{self.name}_subset", symbols=tuple(kept))

    # ------------------------------------------------------------------
    # 数据加载
    # ------------------------------------------------------------------

    @property
    def all_needed_symbols(self) -> list[str]:
        """实际加载需要的全部 symbol（含 cash 与 benchmark）。"""
        out = list(self.symbols)
        if self.cash_proxy and self.cash_proxy not in out:
            out.append(self.cash_proxy)
        if self.benchmark and self.benchmark not in out:
            out.append(self.benchmark)
        return out

    def load_panel(
        self,
        since: str | None = None,
        until: str | None = None,
        *,
        include_cash: bool = True,
        include_benchmark: bool = True,
    ) -> "dict[str, pd.DataFrame]":
        """加载本 universe 全部标的的 OHLCV panel。

        Parameters
        ----------
        since, until : ISO date 字符串
        include_cash, include_benchmark : 是否在 panel 里包含 cash / benchmark
            默认包含（策略类常需要直接访问），False 时只返 symbols
        """
        from strategy_lib.data import get_loader

        loader = get_loader(self.market)
        targets = list(self.symbols)
        if include_cash and self.cash_proxy and self.cash_proxy not in targets:
            targets.append(self.cash_proxy)
        if include_benchmark and self.benchmark and self.benchmark not in targets:
            targets.append(self.benchmark)
        return loader.load_many(targets, since=since, until=until)

    def __len__(self) -> int:
        return len(self.symbols)

    def __repr__(self) -> str:
        return (
            f"Universe(name={self.name!r}, n={len(self.symbols)}, "
            f"market={self.market!r}, cash={self.cash_proxy!r}, "
            f"benchmark={self.benchmark!r})"
        )


# =============================================================================
# 预定义 universe
# =============================================================================
# ---- A股 ETF ----

CN_ETF_BASE_6 = Universe(
    name="cn_etf_base_6",
    symbols=("510300", "510500", "159915", "512100", "512880", "512170"),
    market="cn_etf",
    cash_proxy="511990",
    benchmark="510300",
    description="V1 baseline: 6 只 A股宽基/行业 ETF（沪深300/中证500/创业板/中证1000/证券/医疗）",
    warmup_days=120,
    extra_tags=("v1_baseline",),
)

CN_ETF_EXPANDED_11 = Universe(
    name="cn_etf_expanded_11",
    symbols=(
        "510300", "510500", "159915", "512100", "512880", "512170",  # base 6
        "159920",  # 恒生 (港股)
        "518880",  # 黄金
        "513100",  # 纳指
        "513500",  # 标普500
        "511260",  # 十年国债
    ),
    market="cn_etf",
    cash_proxy="511990",
    benchmark="510300",
    description="S4v2 扩池：base 6 + 跨资产 5（港股/黄金/纳指/标普500/十年国债）",
    warmup_days=200,
    extra_tags=("v1_v2_pool", "cross_asset"),
)

CN_ETF_BROAD_3 = Universe(
    name="cn_etf_broad_3",
    symbols=("510300", "510500", "159915"),
    market="cn_etf",
    cash_proxy="511990",
    benchmark="510300",
    description="A股宽基 3 只：沪深300/中证500/创业板（最简组合）",
    warmup_days=120,
)

CN_ETF_OVERSEAS_4 = Universe(
    name="cn_etf_overseas_4",
    symbols=("159920", "513100", "513500", "518880"),
    market="cn_etf",
    cash_proxy="511990",
    benchmark="510300",
    description="海外+黄金 4 只：恒生/纳指/标普500/黄金（A股相关性低）",
    warmup_days=120,
)

CN_ETF_DEFENSIVE_3 = Universe(
    name="cn_etf_defensive_3",
    symbols=("511260", "518880", "511990"),
    market="cn_etf",
    cash_proxy="511990",
    benchmark="510300",
    description="防御 3 只：十年国债/黄金/货币（避险组合）",
    warmup_days=20,
)

CN_ETF_SECTOR_3 = Universe(
    name="cn_etf_sector_3",
    symbols=("512880", "512170", "159928"),  # 证券 / 医疗 / 消费
    market="cn_etf",
    cash_proxy="511990",
    benchmark="510300",
    description="A股行业 3 只：证券/医疗/消费（行业轮动池，注意 159928 数据范围）",
    warmup_days=120,
    extra_tags=("experimental",),
)

# ---- Crypto 数字货币（V2 Suite）----
# 见 docs/benchmark_suite_v2_crypto.md 的共享基线
# 数据源：ccxt Binance；现金代理 USDT（无利息）；基准 BTC/USDT BH

CRYPTO_TOP_3 = Universe(
    name="crypto_top_3",
    symbols=("BTC/USDT", "ETH/USDT", "SOL/USDT"),
    market="crypto",
    cash_proxy="USDT",      # USDT 在 ccxt 不需 fetch_ohlcv（永远 = 1 USDT）
    benchmark="BTC/USDT",
    description="Crypto V2 baseline：三大主流（BTC/ETH/SOL）",
    warmup_days=120,
    extra_tags=("v2_crypto", "spot"),
)

CRYPTO_TOP_5 = Universe(
    name="crypto_top_5",
    symbols=("BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"),
    market="crypto",
    cash_proxy="USDT",
    benchmark="BTC/USDT",
    description="Crypto V2：头部 5 只（BTC/ETH/SOL/BNB/XRP）",
    warmup_days=120,
    extra_tags=("v2_crypto", "spot"),
)

CRYPTO_TOP_10 = Universe(
    name="crypto_top_10",
    symbols=(
        "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
        "DOGE/USDT", "ADA/USDT", "AVAX/USDT", "LINK/USDT", "DOT/USDT",
    ),
    market="crypto",
    cash_proxy="USDT",
    benchmark="BTC/USDT",
    description="Crypto V2：头部 10 只（注意部分 alt 2021 后才上市）",
    warmup_days=120,
    extra_tags=("v2_crypto", "spot"),
)

CRYPTO_BTC_ETH_2 = Universe(
    name="crypto_btc_eth_2",
    symbols=("BTC/USDT", "ETH/USDT"),
    market="crypto",
    cash_proxy="USDT",
    benchmark="BTC/USDT",
    description="Crypto V2 极简：BTC/ETH 双标（vs CN_ETF_BROAD_3 类似定位）",
    warmup_days=120,
    extra_tags=("v2_crypto", "spot"),
)

CRYPTO_TOP_5_NO_SOL = Universe(
    name="crypto_top_5_no_sol",
    symbols=("BTC/USDT", "ETH/USDT", "BNB/USDT", "XRP/USDT"),  # 4 只，剔除 SOL
    market="crypto",
    cash_proxy="USDT",
    benchmark="BTC/USDT",
    description=(
        "Crypto V2-S1 robustness 测试：从 TOP_5 剔除 SOL，验证 V2-S1 +118% CAGR alpha 是否依赖单一 100x outlier"
    ),
    warmup_days=120,
    extra_tags=("v2_crypto", "spot", "ablation"),
)

ALL_CRYPTO_UNIVERSES: tuple[Universe, ...] = (
    CRYPTO_BTC_ETH_2,
    CRYPTO_TOP_3,
    CRYPTO_TOP_5,
    CRYPTO_TOP_5_NO_SOL,
    CRYPTO_TOP_10,
)

# ---- 全部预定义 universe 的清单（方便 sweep 调用） ----

ALL_CN_ETF_UNIVERSES: tuple[Universe, ...] = (
    CN_ETF_BASE_6,
    CN_ETF_EXPANDED_11,
    CN_ETF_BROAD_3,
    CN_ETF_OVERSEAS_4,
    CN_ETF_DEFENSIVE_3,
)

# 按名称快速查找
UNIVERSE_REGISTRY: dict[str, Universe] = {
    u.name: u
    for u in ALL_CN_ETF_UNIVERSES + ALL_CRYPTO_UNIVERSES + (CN_ETF_SECTOR_3,)
}


def get_universe(name: str) -> Universe:
    """按名称取预定义 universe；未注册时报错。"""
    if name not in UNIVERSE_REGISTRY:
        raise KeyError(
            f"Unknown universe: {name!r}. registered: {sorted(UNIVERSE_REGISTRY)}"
        )
    return UNIVERSE_REGISTRY[name]


__all__ = [
    "ALL_CN_ETF_UNIVERSES",
    "ALL_CRYPTO_UNIVERSES",
    "CN_ETF_BASE_6",
    "CN_ETF_BROAD_3",
    "CN_ETF_DEFENSIVE_3",
    "CN_ETF_EXPANDED_11",
    "CN_ETF_OVERSEAS_4",
    "CN_ETF_SECTOR_3",
    "CRYPTO_BTC_ETH_2",
    "CRYPTO_TOP_3",
    "CRYPTO_TOP_5",
    "CRYPTO_TOP_5_NO_SOL",
    "CRYPTO_TOP_10",
    "UNIVERSE_REGISTRY",
    "Universe",
    "get_universe",
]
