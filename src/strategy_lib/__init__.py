"""Strategy-Lib: 多市场量化策略研究库."""

__version__ = "0.1.0"

from strategy_lib.data import get_loader
from strategy_lib.factors.base import Factor
from strategy_lib.universes import Universe, get_universe

__all__ = ["Factor", "Universe", "__version__", "get_loader", "get_universe"]
