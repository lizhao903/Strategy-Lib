"""因子库。每个因子是 Factor 子类，市场无关。"""

from strategy_lib.factors.base import Factor, FactorRegistry, registry
from strategy_lib.factors.momentum import MACDDiff, MomentumReturn, VolAdjustedMomentum
from strategy_lib.factors.reversal import RSIReversal, ShortTermReversal
from strategy_lib.factors.trend import DonchianPosition, MABullishContinuous, MABullishScore
from strategy_lib.factors.volatility import AnnualizedVol, ATRRatio, RealizedVol
from strategy_lib.factors.volume import OBVMomentum, VolumeRatio

__all__ = [
    "AnnualizedVol",
    "ATRRatio",
    "DonchianPosition",
    "Factor",
    "FactorRegistry",
    "MABullishContinuous",
    "MABullishScore",
    "MACDDiff",
    "MomentumReturn",
    "OBVMomentum",
    "RSIReversal",
    "RealizedVol",
    "ShortTermReversal",
    "VolAdjustedMomentum",
    "VolumeRatio",
    "registry",
]
