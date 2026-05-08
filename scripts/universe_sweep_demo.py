"""Universe Sweep 演示：「策略 × 标的池」grid search。

跑法：
    cd /Volumes/ai/github/Strategy-Lib && source .venv/bin/activate
    python scripts/universe_sweep_demo.py

产物：
    results/universe_sweep_demo_<timestamp>.csv —— 完整长格式结果
    stdout —— Sharpe / NAV / MaxDD 三个 pivot 矩阵
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from strategy_lib.backtest import sweep  # noqa: E402
from strategy_lib.strategies.factories import (  # noqa: E402
    s3_equal_rebalance,
    s4v2_momentum_tilt,
    s5v2_trend_tilt,
    s7v2_market_ma_filter,
)
from strategy_lib.universes import (  # noqa: E402
    CN_ETF_BASE_6,
    CN_ETF_BROAD_3,
    CN_ETF_DEFENSIVE_3,
    CN_ETF_EXPANDED_11,
    CN_ETF_OVERSEAS_4,
)
from strategy_lib.utils.paths import RESULTS_DIR  # noqa: E402


def main() -> int:
    print("=" * 70)
    print("Universe Sweep Demo — 4 strategies × 4 universes")
    print("=" * 70)

    strategies = {
        "S3 equal_rebal": s3_equal_rebalance,
        "S4v2 momentum_tilt": s4v2_momentum_tilt,
        "S5v2 trend_tilt": s5v2_trend_tilt,
        "S7v2 ma_filter": s7v2_market_ma_filter,
    }

    universes = [
        CN_ETF_BROAD_3,        # 3 只宽基（最简）
        CN_ETF_BASE_6,         # V1 baseline 6 池
        CN_ETF_OVERSEAS_4,     # 海外+黄金（A股低相关）
        CN_ETF_EXPANDED_11,    # S4v2/S7v2 11 跨资产池
    ]

    df = sweep(
        strategies=strategies,
        universes=universes,
        since="2020-01-02",
        until="2024-12-31",
        init_cash=100_000,
        verbose=True,
    )

    # 保存原始结果
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"universe_sweep_demo_{ts}.csv"
    df.to_csv(out_path, index=False)
    print(f"\n[saved] {out_path}")

    print("\n" + "=" * 70)
    print("Sharpe 矩阵（行=策略，列=universe）")
    print("=" * 70)
    if "sharpe" in df.columns:
        print(df.pivot(index="strategy", columns="universe", values="sharpe").round(3).to_string())

    print("\n" + "=" * 70)
    print("Final NAV (100k 起) 矩阵")
    print("=" * 70)
    if "final_nav_100k" in df.columns:
        nav = df.pivot(index="strategy", columns="universe", values="final_nav_100k")
        print((nav / 1000).round(1).to_string())

    print("\n" + "=" * 70)
    print("MaxDD 矩阵 (%)")
    print("=" * 70)
    if "max_dd" in df.columns:
        dd = df.pivot(index="strategy", columns="universe", values="max_dd")
        print((dd * 100).round(1).to_string())

    print("\n" + "=" * 70)
    print("CAGR 矩阵 (%)")
    print("=" * 70)
    if "cagr" in df.columns:
        cagr = df.pivot(index="strategy", columns="universe", values="cagr")
        print((cagr * 100).round(2).to_string())

    # 错误汇总
    if "error" in df.columns and df["error"].notna().any():
        print("\n[errors]")
        print(df[df["error"].notna()][["strategy", "universe", "error"]].to_string(index=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())
