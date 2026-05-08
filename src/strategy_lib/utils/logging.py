"""统一日志：默认 INFO 到 stderr，可通过环境变量 STRATEGY_LIB_LOG_LEVEL 调整。"""

from __future__ import annotations

import os
import sys

from loguru import logger

logger.remove()
logger.add(
    sys.stderr,
    level=os.environ.get("STRATEGY_LIB_LOG_LEVEL", "INFO"),
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | <cyan>{name}</cyan> - {message}",
)

__all__ = ["logger"]
