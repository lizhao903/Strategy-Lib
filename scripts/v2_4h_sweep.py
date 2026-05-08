"""V2 Crypto 4h 频率重测 — 1d vs 4h 横向对比.

跑法：
    cd /Volumes/ai/github/Strategy-Lib && source .venv/bin/activate
    python scripts/v2_4h_sweep.py

产物：
    results/v2_4h_sweep_<ts>.csv
    stdout: 各策略 1d vs 4h 对比表 + 关键参数 sweep

测试矩阵（CRYPTO_TOP_5, 2021-01 ~ 2024-12）:
    - V2-S1 等权 (rebalance: 1d=20 / 4h=120 等月度时间)
    - V2-S2 BTC MA filter (ma_length: 1d=100 / 4h=600 等 100 天)
    - V2-S4 momentum tilt (lookback: 1d=120 / 4h=720 等 120 天)

关键问题：4h 频率是否让信号反应更快带来 alpha？
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from strategy_lib.strategies.cn_etf_equal_rebalance import EqualRebalanceStrategy  # noqa: E402
from strategy_lib.strategies.cn_etf_market_ma_filter_v2 import MarketMAFilterV2Strategy  # noqa: E402
from strategy_lib.strategies.cn_etf_momentum_tilt_v2 import MomentumTiltV2Strategy  # noqa: E402
from strategy_lib.universes import CRYPTO_TOP_5  # noqa: E402
from strategy_lib.utils.paths import RESULTS_DIR  # noqa: E402

SINCE_FETCH = "2020-09-01"
SINCE_PERF = "2021-01-01"
UNTIL = "2024-12-31"
INIT_CASH = 100_000
FEES = 0.001
SLIPPAGE = 0.001

# 365 天 × 24 / 4 = 2190 4h bars/year
TDPY_1D = 365
TDPY_4H = 365 * 6  # = 2190


def calc_metrics(nav: pd.Series, tdpy: int, label: str = "") -> dict:
    nav = nav.dropna()
    if len(nav) < 5:
        return {"label": label, "error": "nav too short"}
    nav_norm = nav / nav.iloc[0]
    daily_ret = nav_norm.pct_change().dropna()
    n_bars = len(nav_norm)
    n_years = n_bars / tdpy
    final_norm = float(nav_norm.iloc[-1])
    cagr = final_norm ** (1 / n_years) - 1 if n_years > 0 else float("nan")
    vol_ann = float(daily_ret.std() * np.sqrt(tdpy))
    sharpe = (
        float(daily_ret.mean() / daily_ret.std() * np.sqrt(tdpy))
        if daily_ret.std() > 0 else float("nan")
    )
    cummax = nav_norm.cummax()
    max_dd = float((nav_norm / cummax - 1).min())
    calmar = cagr / abs(max_dd) if max_dd < 0 else float("nan")
    return {
        "label": label,
        "n_bars": int(n_bars),
        "final_nav_100k": float(final_norm * INIT_CASH),
        "cagr_pct": cagr * 100,
        "vol_ann_pct": vol_ann * 100,
        "sharpe": sharpe,
        "max_dd_pct": max_dd * 100,
        "calmar": calmar,
    }


def extract_nav(result) -> pd.Series:
    pf = result.portfolio
    val = pf.value() if callable(getattr(pf, "value", None)) else pf.value
    if hasattr(val, "to_series"):
        try:
            val = val.to_series()
        except Exception:
            pass
    if isinstance(val, pd.DataFrame):
        val = val.iloc[:, 0]
    return pd.Series(
        val.values if hasattr(val, "values") else val,
        index=pf.wrapper.index,
    )


def trim_to_perf(nav: pd.Series) -> pd.Series:
    cutoff = pd.Timestamp(SINCE_PERF, tz=nav.index.tz)
    end = pd.Timestamp(UNTIL, tz=nav.index.tz)
    return nav[(nav.index >= cutoff) & (nav.index <= end)]


def load_panel(timeframe: str) -> dict[str, pd.DataFrame]:
    """加载 CRYPTO_TOP_5 在指定 timeframe 的 panel。"""
    from strategy_lib.data import get_loader
    loader = get_loader(CRYPTO_TOP_5.market)
    syms = list(CRYPTO_TOP_5.symbols)
    out: dict[str, pd.DataFrame] = {}
    for s in syms:
        out[s] = loader.load(s, timeframe=timeframe, since=SINCE_FETCH, until=UNTIL)
    return out


def run_strategy(strategy_name: str, panel: dict, *, tdpy: int, **params) -> dict:
    if strategy_name == "S3":
        strat = EqualRebalanceStrategy(symbols=list(CRYPTO_TOP_5.symbols), **params)
    elif strategy_name == "S4v2":
        strat = MomentumTiltV2Strategy(symbols=list(CRYPTO_TOP_5.symbols), **params)
    elif strategy_name == "S7v2":
        strat = MarketMAFilterV2Strategy(
            symbols=list(CRYPTO_TOP_5.symbols),
            cash_symbol="USDT",
            signal_symbol="BTC/USDT",
            **params,
        )
    else:
        raise ValueError(strategy_name)
    result = strat.run(panel, init_cash=INIT_CASH, fees=FEES, slippage=SLIPPAGE)
    nav = trim_to_perf(extract_nav(result))
    return calc_metrics(nav, tdpy, label=strategy_name)


def main() -> int:
    t_start = time.time()
    print("=" * 72)
    print("V2 Crypto 4h frequency sweep — 1d vs 4h on CRYPTO_TOP_5")
    print(f"  窗口: {SINCE_PERF} ~ {UNTIL}, 100k USDT, fees+slip 10bp 各")
    print(f"  TDPY: 1d={TDPY_1D}, 4h={TDPY_4H}")
    print("=" * 72)

    print("\n[1/3] 加载 1d panel ...")
    panel_1d = load_panel("1d")
    print(f"  {len(panel_1d)} symbols, BTC bars: {len(panel_1d['BTC/USDT'])}")

    print("\n[2/3] 加载 4h panel（首次拉取需 1-2 分钟）...")
    t0 = time.time()
    panel_4h = load_panel("4h")
    print(f"  {len(panel_4h)} symbols, BTC bars: {len(panel_4h['BTC/USDT'])}, took {time.time()-t0:.1f}s")
    # USDT panel for S7v2
    from strategy_lib.data import get_loader
    loader = get_loader("crypto")
    panel_4h["USDT"] = loader.load("USDT", timeframe="4h", since=SINCE_FETCH, until=UNTIL)
    panel_1d["USDT"] = loader.load("USDT", timeframe="1d", since=SINCE_FETCH, until=UNTIL)

    print("\n[3/3] 跑各策略 1d vs 4h ...")
    rows = []

    # ---- V2-S1 (S3 equal) ----
    print("\n--- V2-S1 等权 ---")
    for tf, panel, tdpy, rebal in (
        ("1d", panel_1d, TDPY_1D, 20),
        ("4h", panel_4h, TDPY_4H, 120),  # 等月度时间：6 × 20
    ):
        m = run_strategy("S3", panel, tdpy=tdpy, rebalance_period=rebal)
        m["timeframe"] = tf
        m["strategy"] = "V2-S1 equal"
        m["params"] = f"rebalance={rebal}"
        rows.append(m)
        print(f"  {tf} (rebal={rebal}): NAV {m['final_nav_100k']/1000:.1f}k / "
              f"CAGR {m['cagr_pct']:+.2f}% / Sharpe {m['sharpe']:.3f} / MaxDD {m['max_dd_pct']:.1f}% / Calmar {m['calmar']:.2f}")

    # ---- V2-S2 (S7v2 MA filter) ----
    # 1d: ma=100 (V2-S2 sweet spot), 4h: ma=600 (等 100 天) + ma=100 (等 16 天 短信号对照)
    print("\n--- V2-S2 BTC MA filter ---")
    for tf, panel, tdpy, ma_len, label_extra in (
        ("1d", panel_1d, TDPY_1D, 100, "MA=100 (sweet spot)"),
        ("4h", panel_4h, TDPY_4H, 600, "MA=600 (等 100 天)"),
        ("4h", panel_4h, TDPY_4H, 1200, "MA=1200 (等 200 天)"),
        ("4h", panel_4h, TDPY_4H, 100, "MA=100 (等 16 天 短)"),
    ):
        m = run_strategy("S7v2", panel, tdpy=tdpy, ma_length=ma_len, lag_days=1)
        m["timeframe"] = tf
        m["strategy"] = "V2-S2 MA filter"
        m["params"] = label_extra
        rows.append(m)
        print(f"  {tf} {label_extra}: NAV {m['final_nav_100k']/1000:.1f}k / "
              f"CAGR {m['cagr_pct']:+.2f}% / Sharpe {m['sharpe']:.3f} / MaxDD {m['max_dd_pct']:.1f}% / Calmar {m['calmar']:.2f}")

    # ---- V2-S4 (S4v2 momentum) ----
    print("\n--- V2-S4 momentum tilt ---")
    for tf, panel, tdpy, lookback, rebal, label_extra in (
        ("1d", panel_1d, TDPY_1D, 120, 20, "lookback=120 (V1 默认)"),
        ("4h", panel_4h, TDPY_4H, 720, 120, "lookback=720 (等 120 天)"),
        ("4h", panel_4h, TDPY_4H, 360, 60, "lookback=360 (等 60 天)"),
    ):
        try:
            m = run_strategy("S4v2", panel, tdpy=tdpy,
                             lookback=lookback, skip=5, signal="raw",
                             rebalance_period=rebal)
            m["timeframe"] = tf
            m["strategy"] = "V2-S4 momentum"
            m["params"] = label_extra
            rows.append(m)
            print(f"  {tf} {label_extra}: NAV {m['final_nav_100k']/1000:.1f}k / "
                  f"CAGR {m['cagr_pct']:+.2f}% / Sharpe {m['sharpe']:.3f} / MaxDD {m['max_dd_pct']:.1f}% / Calmar {m['calmar']:.2f}")
        except Exception as e:
            print(f"  {tf} {label_extra}: FAILED {type(e).__name__}: {e}")
            rows.append({"timeframe": tf, "strategy": "V2-S4 momentum", "params": label_extra, "error": str(e)})

    # 输出
    df = pd.DataFrame(rows)
    cols = ["strategy", "timeframe", "params", "final_nav_100k", "cagr_pct",
            "sharpe", "vol_ann_pct", "max_dd_pct", "calmar", "n_bars"]
    df = df[[c for c in cols if c in df.columns] + [c for c in df.columns if c not in cols]]
    ts = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"v2_4h_sweep_{ts}.csv"
    df.to_csv(out_path, index=False)
    print(f"\n  saved → {out_path}")

    print("\n" + "=" * 72)
    print(f"完成，总耗时 {time.time() - t_start:.1f}s")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
