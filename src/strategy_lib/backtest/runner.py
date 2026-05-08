"""配置驱动的端到端回测：load yaml -> 拉数据 -> 跑策略 -> 输出指标。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from strategy_lib.data import get_loader
from strategy_lib.strategies.base import StrategyResult
from strategy_lib.strategies.registry import build_strategy
from strategy_lib.utils.logging import logger


def run_config(config_path: str | Path) -> StrategyResult:
    """跑一个 yaml 配置定义的回测。"""
    config_path = Path(config_path)
    with open(config_path) as f:
        config: dict[str, Any] = yaml.safe_load(f)

    logger.info(f"loading config: {config.get('name', config_path.stem)}")

    # 1. 数据
    u = config["universe"]
    loader = get_loader(config["market"])
    panel = loader.load_many(
        symbols=u["symbols"],
        timeframe=u.get("timeframe", "1d"),
        since=u.get("since"),
        until=u.get("until"),
    )
    if not panel:
        raise RuntimeError("no symbols loaded")

    # 2. 策略
    strategy = build_strategy(config)

    # 3. 回测
    bt_cfg = config.get("backtest") or {}
    result = strategy.run(panel, **bt_cfg)

    logger.info(f"=== {strategy.name} metrics ===")
    for k, v in result.metrics.items():
        logger.info(f"  {k}: {v:.4f}" if isinstance(v, float) else f"  {k}: {v}")

    return result
