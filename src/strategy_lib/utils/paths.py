"""项目路径常量。所有 IO 都通过这里集中管理。"""

from __future__ import annotations

import os
from pathlib import Path


def _find_project_root() -> Path:
    env = os.environ.get("STRATEGY_LIB_ROOT")
    if env:
        return Path(env).resolve()
    p = Path(__file__).resolve()
    for parent in [p, *p.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


PROJECT_ROOT = _find_project_root()
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
RESULTS_DIR = PROJECT_ROOT / "results"

for _d in (RAW_DIR, PROCESSED_DIR, RESULTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)
