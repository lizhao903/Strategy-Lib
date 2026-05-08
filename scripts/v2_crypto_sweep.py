"""V2 Crypto sweep — 4 策略 × 5 crypto universe 网格 + NO_SOL ablation.

跑法：
    cd /Volumes/ai/github/Strategy-Lib && source .venv/bin/activate
    python scripts/v2_crypto_sweep.py

产物：
    results/v2_crypto_sweep_<ts>.csv
    stdout: 4 个 pivot 矩阵（Sharpe / NAV / MaxDD / CAGR）
    + NO_SOL vs TOP_5 对比

注意：sweep 自动检测 universe.market == 'crypto' 用 365 天年化。
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
    CRYPTO_BTC_ETH_2,
    CRYPTO_TOP_3,
    CRYPTO_TOP_5,
    CRYPTO_TOP_5_NO_SOL,
    CRYPTO_TOP_10,
)
from strategy_lib.utils.paths import RESULTS_DIR  # noqa: E402


def main() -> int:
    print("=" * 70)
    print("V2 Crypto Sweep — 4 strategies × 5 universes (含 NO_SOL ablation)")
    print("窗口: 2021-01-01 ~ 2024-12-31, 100k USDT, fees+slip 各 10bp, 年化 365")
    print("=" * 70)

    strategies = {
        "S3 equal_rebal": s3_equal_rebalance,
        "S4v2 momentum_tilt": s4v2_momentum_tilt,
        "S5v2 trend_tilt": s5v2_trend_tilt,
        "S7v2 ma_filter": s7v2_market_ma_filter,
    }

    universes = [
        CRYPTO_BTC_ETH_2,       # 2 标的极简
        CRYPTO_TOP_3,           # 含 SOL
        CRYPTO_TOP_5_NO_SOL,    # 4 标的，剔除 SOL（关键 ablation）
        CRYPTO_TOP_5,           # V2-S1 默认
        CRYPTO_TOP_10,          # 加 alt
    ]

    df = sweep(
        strategies=strategies,
        universes=universes,
        since="2021-01-01",
        until="2024-12-31",
        init_cash=100_000,
        fees=0.001,        # crypto 10 bp
        slippage=0.001,    # crypto 10 bp
        verbose=True,
    )

    # 保存原始结果
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"v2_crypto_sweep_{ts}.csv"
    df.to_csv(out_path, index=False)
    print(f"\n[saved] {out_path}")

    # Pivot 矩阵展示
    universe_order = [u.name for u in universes]

    print("\n" + "=" * 70)
    print("Sharpe 矩阵（行=策略，列=universe）")
    print("=" * 70)
    if "sharpe" in df.columns:
        print(df.pivot(index="strategy", columns="universe", values="sharpe")
              .reindex(columns=universe_order).round(3).to_string())

    print("\n" + "=" * 70)
    print("Final NAV (100k USDT 起) 矩阵")
    print("=" * 70)
    if "final_nav_100k" in df.columns:
        nav = df.pivot(index="strategy", columns="universe", values="final_nav_100k")
        print((nav.reindex(columns=universe_order) / 1000).round(1).to_string())

    print("\n" + "=" * 70)
    print("CAGR 矩阵 (%)")
    print("=" * 70)
    if "cagr" in df.columns:
        cagr = df.pivot(index="strategy", columns="universe", values="cagr")
        print((cagr.reindex(columns=universe_order) * 100).round(2).to_string())

    print("\n" + "=" * 70)
    print("MaxDD 矩阵 (%)")
    print("=" * 70)
    if "max_dd" in df.columns:
        dd = df.pivot(index="strategy", columns="universe", values="max_dd")
        print((dd.reindex(columns=universe_order) * 100).round(1).to_string())

    # NO_SOL ablation 专项
    print("\n" + "=" * 70)
    print("【关键 ablation】SOL 贡献的边际 alpha")
    print("=" * 70)
    for strat_name in strategies:
        try:
            row_top5 = df[(df["strategy"] == strat_name) & (df["universe"] == "crypto_top_5")].iloc[0]
            row_no_sol = df[(df["strategy"] == strat_name) & (df["universe"] == "crypto_top_5_no_sol")].iloc[0]
            cagr_diff = (row_top5["cagr"] - row_no_sol["cagr"]) * 100
            nav_diff = row_top5["final_nav_100k"] - row_no_sol["final_nav_100k"]
            sharpe_diff = row_top5["sharpe"] - row_no_sol["sharpe"]
            print(f"  {strat_name}:")
            print(f"    TOP_5: CAGR {row_top5['cagr']*100:+.2f}% / Sharpe {row_top5['sharpe']:.3f} / NAV {row_top5['final_nav_100k']/1000:.1f}k")
            print(f"    NO_SOL: CAGR {row_no_sol['cagr']*100:+.2f}% / Sharpe {row_no_sol['sharpe']:.3f} / NAV {row_no_sol['final_nav_100k']/1000:.1f}k")
            print(f"    Δ (SOL 贡献): CAGR {cagr_diff:+.2f} pct / Sharpe {sharpe_diff:+.3f} / NAV {nav_diff/1000:+.1f}k")
        except Exception as e:  # noqa: BLE001
            print(f"  {strat_name}: ablation 计算失败 {e}")

    if "error" in df.columns and df["error"].notna().any():
        print("\n[errors]")
        print(df[df["error"].notna()][["strategy", "universe", "error"]].to_string(index=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())
