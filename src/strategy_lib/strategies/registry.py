"""yaml 配置 -> 策略实例。"""

from __future__ import annotations

from typing import Any

from strategy_lib.factors.base import Factor, registry as factor_registry
from strategy_lib.strategies.base import BaseStrategy
from strategy_lib.strategies.factor_strategy import (
    CrossSectionalRankStrategy,
    SingleAssetThresholdStrategy,
)

_STRATEGIES: dict[str, type[BaseStrategy]] = {
    "single_threshold": SingleAssetThresholdStrategy,
    "cs_rank": CrossSectionalRankStrategy,
}


def build_factors(specs: list[dict[str, Any]]) -> tuple[list[Factor], list[float]]:
    factors: list[Factor] = []
    weights: list[float] = []
    for spec in specs:
        f = factor_registry.create(spec["name"], **(spec.get("params") or {}))
        factors.append(f)
        weights.append(spec.get("weight", 1.0))
    return factors, weights


def build_strategy(config: dict[str, Any]) -> BaseStrategy:
    """从 yaml 加载的 dict 构造策略。

    config 结构：
        strategy:
          type: single_threshold | cs_rank
          factors: [{name, params, weight}, ...]
          signal: {...}     # 策略特定参数
    """
    s_cfg = config["strategy"]
    s_type = s_cfg["type"]
    cls = _STRATEGIES.get(s_type)
    if cls is None:
        raise KeyError(f"unknown strategy type: {s_type}. registered: {list(_STRATEGIES)}")

    factors, weights = build_factors(s_cfg["factors"])
    signal_kwargs = s_cfg.get("signal") or {}
    return cls(factors=factors, weights=weights, name=config.get("name", s_type), **signal_kwargs)
