from strategy_lib.strategies.base import BaseStrategy, StrategyResult
from strategy_lib.strategies.factor_strategy import (
    CrossSectionalRankStrategy,
    SingleAssetThresholdStrategy,
)

# Benchmark Suite V1 — 见 docs/benchmark_suite_v1.md
from strategy_lib.strategies.cn_etf_dca_basic import DCABasicStrategy, DCAResult
from strategy_lib.strategies.cn_etf_dca_swing import DCASwingResult, DCASwingStrategy
from strategy_lib.strategies.cn_etf_equal_rebalance import (
    EqualRebalanceResult,
    EqualRebalanceStrategy,
)
from strategy_lib.strategies.cn_etf_momentum_tilt import MomentumTiltStrategy
from strategy_lib.strategies.cn_etf_trend_tilt import TrendTiltStrategy

# v2 versions (Benchmark Suite V1 改进)
from strategy_lib.strategies.cn_etf_dca_swing_v2 import DCASwingV2Result, DCASwingV2Strategy
from strategy_lib.strategies.cn_etf_momentum_tilt_v2 import MomentumTiltV2Strategy
from strategy_lib.strategies.cn_etf_trend_tilt_v2 import TrendTiltV2Strategy

# S6 / S7 — Benchmark Suite V1 扩展（基于 V1 v2 的诊断派生的新框架策略）
from strategy_lib.strategies.cn_etf_value_averaging import (
    ValueAveragingResult,
    ValueAveragingStrategy,
)
from strategy_lib.strategies.cn_etf_market_ma_filter import (
    MarketMAFilterResult,
    MarketMAFilterStrategy,
)
from strategy_lib.strategies.cn_etf_market_ma_filter_v2 import (
    MarketMAFilterV2Strategy,
    RISKY_POOL_11,
)

__all__ = [
    "BaseStrategy",
    "CrossSectionalRankStrategy",
    "DCABasicStrategy",
    "DCAResult",
    "DCASwingResult",
    "DCASwingStrategy",
    "DCASwingV2Result",
    "DCASwingV2Strategy",
    "EqualRebalanceResult",
    "EqualRebalanceStrategy",
    "MarketMAFilterResult",
    "MarketMAFilterStrategy",
    "MarketMAFilterV2Strategy",
    "RISKY_POOL_11",
    "MomentumTiltStrategy",
    "MomentumTiltV2Strategy",
    "SingleAssetThresholdStrategy",
    "StrategyResult",
    "TrendTiltStrategy",
    "TrendTiltV2Strategy",
    "ValueAveragingResult",
    "ValueAveragingStrategy",
]
