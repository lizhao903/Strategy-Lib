"""策略工厂函数：把 ``Universe`` 一键转换成对应策略实例。

每个策略对 symbols / cash / benchmark 的接收字段名不一样（DCA 类用
``cash_symbol`` + ``risk_symbols``，等权类用 ``symbols``，MA filter 还要
``signal_symbol``）。本模块封装这层适配，让 sweep 调用方写
``factory(universe)`` 就拿到可跑的策略实例。

约定：每个 factory 接收 ``(universe: Universe, **overrides)`` 参数，
``overrides`` 用于覆盖默认参数（如 lookback / α）做参数 sweep。
"""

from __future__ import annotations

from typing import Callable, Protocol

from strategy_lib.strategies.cn_etf_dca_basic import DCABasicStrategy
from strategy_lib.strategies.cn_etf_dca_swing import DCASwingStrategy
from strategy_lib.strategies.cn_etf_dca_swing_v2 import DCASwingV2Strategy
from strategy_lib.strategies.cn_etf_equal_rebalance import EqualRebalanceStrategy
from strategy_lib.strategies.cn_etf_market_ma_filter import MarketMAFilterStrategy
from strategy_lib.strategies.cn_etf_market_ma_filter_v2 import MarketMAFilterV2Strategy
from strategy_lib.strategies.cn_etf_momentum_tilt import MomentumTiltStrategy
from strategy_lib.strategies.cn_etf_momentum_tilt_v2 import MomentumTiltV2Strategy
from strategy_lib.strategies.cn_etf_trend_tilt import TrendTiltStrategy
from strategy_lib.strategies.cn_etf_trend_tilt_v2 import TrendTiltV2Strategy
from strategy_lib.strategies.cn_etf_value_averaging import ValueAveragingStrategy
from strategy_lib.universes import Universe


class StrategyFactory(Protocol):
    """factory 接口：给一个 universe，返回一个可 .run(panel) 的策略实例。"""

    def __call__(self, universe: Universe, **overrides) -> object: ...


# -----------------------------------------------------------------------------
# DCA 类（用 cash_symbol + risk_symbols 接收）
# -----------------------------------------------------------------------------

def s1_dca_basic(universe: Universe, **overrides) -> DCABasicStrategy:
    """S1 DCA basic. 需要 universe.cash_proxy。"""
    if not universe.cash_proxy:
        raise ValueError("S1 需要 universe.cash_proxy（货币基金等价物）")
    return DCABasicStrategy(
        cash_symbol=universe.cash_proxy,
        risk_symbols=tuple(universe.symbols),
        **overrides,
    )


def s2_dca_swing(universe: Universe, **overrides) -> DCASwingStrategy:
    """S2 v1 DCA swing."""
    if not universe.cash_proxy:
        raise ValueError("S2 需要 universe.cash_proxy")
    return DCASwingStrategy(
        cash_symbol=universe.cash_proxy,
        risk_symbols=tuple(universe.symbols),
        **overrides,
    )


def s2v2_dca_swing(universe: Universe, **overrides) -> DCASwingV2Strategy:
    """S2 v2 DCA swing."""
    if not universe.cash_proxy:
        raise ValueError("S2v2 需要 universe.cash_proxy")
    return DCASwingV2Strategy(
        cash_symbol=universe.cash_proxy,
        risk_symbols=tuple(universe.symbols),
        **overrides,
    )


def s6_value_averaging(universe: Universe, **overrides) -> ValueAveragingStrategy:
    """S6 价值平均法。"""
    if not universe.cash_proxy:
        raise ValueError("S6 需要 universe.cash_proxy")
    return ValueAveragingStrategy(
        cash_symbol=universe.cash_proxy,
        risk_symbols=tuple(universe.symbols),
        **overrides,
    )


# -----------------------------------------------------------------------------
# 等权类 / 因子倾斜类（用 symbols 接收，无现金）
# -----------------------------------------------------------------------------

def s3_equal_rebalance(universe: Universe, **overrides) -> EqualRebalanceStrategy:
    """S3 等权 + 定时再平衡。**无现金缓冲**，universe.cash_proxy 被忽略。"""
    return EqualRebalanceStrategy(symbols=list(universe.symbols), **overrides)


def s4_momentum_tilt(universe: Universe, **overrides) -> MomentumTiltStrategy:
    """S4 v1 动量倾斜。"""
    return MomentumTiltStrategy(symbols=list(universe.symbols), **overrides)


def s4v2_momentum_tilt(universe: Universe, **overrides) -> MomentumTiltV2Strategy:
    """S4 v2 动量倾斜（11 池 + 长 lookback + shift(1) + vol_adj 默认）。"""
    return MomentumTiltV2Strategy(symbols=list(universe.symbols), **overrides)


def s5_trend_tilt(universe: Universe, **overrides) -> TrendTiltStrategy:
    """S5 v1 趋势倾斜。"""
    return TrendTiltStrategy(symbols=list(universe.symbols), **overrides)


def s5v2_trend_tilt(universe: Universe, **overrides) -> TrendTiltV2Strategy:
    """S5 v2 连续趋势 + vol filter + bond overlay."""
    return TrendTiltV2Strategy(symbols=list(universe.symbols), **overrides)


# -----------------------------------------------------------------------------
# MA filter 类（除 symbols 外还要 cash 和 signal_symbol）
# -----------------------------------------------------------------------------

def s7_market_ma_filter(universe: Universe, **overrides) -> MarketMAFilterStrategy:
    """S7 v1 大盘 MA 过滤。signal_symbol 默认取 universe.benchmark。"""
    if not universe.cash_proxy:
        raise ValueError("S7 需要 universe.cash_proxy")
    if not universe.benchmark:
        raise ValueError("S7 需要 universe.benchmark（信号资产）")
    return MarketMAFilterStrategy(
        symbols=list(universe.symbols),
        cash_symbol=universe.cash_proxy,
        signal_symbol=universe.benchmark,
        **overrides,
    )


def s7v2_market_ma_filter(universe: Universe, **overrides) -> MarketMAFilterV2Strategy:
    """S7 v2 大盘 MA 过滤（lag=1 + 11 池默认）。"""
    if not universe.cash_proxy:
        raise ValueError("S7v2 需要 universe.cash_proxy")
    if not universe.benchmark:
        raise ValueError("S7v2 需要 universe.benchmark")
    return MarketMAFilterV2Strategy(
        symbols=list(universe.symbols),
        cash_symbol=universe.cash_proxy,
        signal_symbol=universe.benchmark,
        **overrides,
    )


# -----------------------------------------------------------------------------
# 默认注册表（按 slug 查找）
# -----------------------------------------------------------------------------

FACTORY_REGISTRY: dict[str, Callable[..., object]] = {
    "S1": s1_dca_basic,
    "S2": s2_dca_swing,
    "S2v2": s2v2_dca_swing,
    "S3": s3_equal_rebalance,
    "S4": s4_momentum_tilt,
    "S4v2": s4v2_momentum_tilt,
    "S5": s5_trend_tilt,
    "S5v2": s5v2_trend_tilt,
    "S6": s6_value_averaging,
    "S7": s7_market_ma_filter,
    "S7v2": s7v2_market_ma_filter,
}


def get_factory(name: str) -> Callable[..., object]:
    """按名称取 factory（如 'S3'、'S4v2'）。"""
    if name not in FACTORY_REGISTRY:
        raise KeyError(f"Unknown strategy: {name!r}. registered: {sorted(FACTORY_REGISTRY)}")
    return FACTORY_REGISTRY[name]


__all__ = [
    "FACTORY_REGISTRY",
    "StrategyFactory",
    "get_factory",
    "s1_dca_basic",
    "s2_dca_swing",
    "s2v2_dca_swing",
    "s3_equal_rebalance",
    "s4_momentum_tilt",
    "s4v2_momentum_tilt",
    "s5_trend_tilt",
    "s5v2_trend_tilt",
    "s6_value_averaging",
    "s7_market_ma_filter",
    "s7v2_market_ma_filter",
]
