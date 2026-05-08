"""V2-S3 (S12) `crypto_trend_tilt` 真实数据回测 + ablation.

跑法：
    cd /Volumes/ai/github/Strategy-Lib && source .venv/bin/activate
    python summaries/S12_crypto_trend_tilt/v1/validate.py

产物（artifacts/）：
    - real_backtest_summary.json
    - equity_curve.png / drawdown.png / yearly_returns.{csv,png}
    - vol_high_sweep.csv          vol_high ∈ {0.30, 0.50, 0.80, 1.00}
    - vol_haircut_ablation.csv    haircut ∈ {0.5, 1.0}（关/开 vol filter）
    - universe_ablation.csv       TOP_5 / TOP_10 / NO_SOL
    - calmar_comparison.csv       V2-S1 / V2-S2 / V2-S4 vs V2-S3 Calmar
    - position_timeline.csv       平均仓位时序（每月）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

ARTIFACTS = Path(__file__).resolve().parent / "artifacts"
ARTIFACTS.mkdir(exist_ok=True)

from strategy_lib.strategies.cn_etf_trend_tilt_v2 import TrendTiltV2Strategy  # noqa: E402
from strategy_lib.strategies.cn_etf_equal_rebalance import EqualRebalanceStrategy  # noqa: E402
from strategy_lib.universes import (  # noqa: E402
    CRYPTO_TOP_5,
    CRYPTO_TOP_10,
    CRYPTO_TOP_5_NO_SOL,
)

SINCE_FETCH = "2020-09-01"
SINCE_PERF = "2021-01-01"
UNTIL = "2024-12-31"
INIT_CASH = 100_000
FEES = 0.001
SLIPPAGE = 0.001
TDPY = 365


def calc_crypto_metrics(nav: pd.Series, label: str = "") -> dict:
    nav = nav.dropna()
    if len(nav) < 5:
        return {"label": label, "error": "nav too short"}
    nav_norm = nav / nav.iloc[0]
    daily_ret = nav_norm.pct_change().dropna()
    n_days = len(nav_norm)
    n_years = n_days / TDPY
    final_norm = float(nav_norm.iloc[-1])
    cagr = final_norm ** (1 / n_years) - 1 if n_years > 0 else float("nan")
    vol_ann = float(daily_ret.std() * np.sqrt(TDPY))
    sharpe = (
        float(daily_ret.mean() / daily_ret.std() * np.sqrt(TDPY))
        if daily_ret.std() > 0 else float("nan")
    )
    cummax = nav_norm.cummax()
    max_dd = float((nav_norm / cummax - 1).min())
    calmar = cagr / abs(max_dd) if max_dd < 0 else float("nan")
    yearly = (
        nav_norm.groupby(nav_norm.index.year)
        .apply(lambda s: s.iloc[-1] / s.iloc[0] - 1 if len(s) > 1 else 0)
        .to_dict()
    )
    return {
        "label": label,
        "n_days": int(n_days),
        "final_nav_100k": float(final_norm * INIT_CASH),
        "cagr": cagr,
        "vol_ann": vol_ann,
        "sharpe": sharpe,
        "max_dd": max_dd,
        "calmar": calmar,
        "yearly": {int(k): float(v) for k, v in yearly.items()},
    }


def extract_nav(result) -> pd.Series:
    pf = result.portfolio
    val = pf.value() if callable(getattr(pf, "value", None)) else pf.value
    if hasattr(val, "to_series"):
        try:
            val = val.to_series()
        except Exception:  # noqa: BLE001
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


def run_trend(panel, symbols, *, vol_high=0.30, vol_haircut=0.5):
    strat = TrendTiltV2Strategy(
        symbols=list(symbols),
        rebalance_period=20,
        vol_high=vol_high,
        vol_haircut=vol_haircut,
    )
    return strat.run(panel, init_cash=INIT_CASH, fees=FEES, slippage=SLIPPAGE)


def run_equal(panel, symbols):
    strat = EqualRebalanceStrategy(symbols=list(symbols), rebalance_period=20)
    return strat.run(panel, init_cash=INIT_CASH, fees=FEES, slippage=SLIPPAGE)


def plot_equity(navs, path):
    fig, ax = plt.subplots(figsize=(13, 6))
    style = {
        "V2-S3 trend tilt": ("#9467bd", 2.5, "-"),
        "V2-S1 equal": ("#d62728", 1.6, "--"),
        "BTC/USDT BH": ("#ff7f0e", 1.2, ":"),
    }
    for k, s in navs.items():
        c, lw, ls = style.get(k, ("#888", 1.0, "-"))
        ax.plot(s.index, s.values, label=k, color=c, lw=lw, linestyle=ls)
    ax.set_title("V2-S3 trend_tilt vs V2-S1 vs BTC BH (2021-2024)")
    ax.set_ylabel("Normalized NAV")
    ax.set_yscale("log")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def plot_drawdown(navs, path):
    fig, ax = plt.subplots(figsize=(13, 5))
    for k, s in navs.items():
        dd = s / s.cummax() - 1
        ax.plot(s.index, dd.values, label=k, lw=1.2)
    ax.axhline(0, color="black", lw=0.5)
    if navs:
        s = next(iter(navs.values()))
        ax.axvspan(
            pd.Timestamp("2022-01-01", tz=s.index.tz),
            pd.Timestamp("2022-12-31", tz=s.index.tz),
            alpha=0.10, color="red",
        )
    ax.set_title("Drawdown 2022 LUNA/FTX highlighted")
    ax.set_ylabel("Drawdown")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def main() -> int:
    print("=" * 72)
    print("V2-S3 (S12) crypto_trend_tilt 真实数据回测 + ablation")
    print(f"  窗口: {SINCE_PERF} ~ {UNTIL}, 初始 {INIT_CASH:,} USDT")
    print(f"  fees={FEES * 1e4:.0f}bp, slippage={SLIPPAGE * 1e4:.0f}bp, ann={TDPY}")
    print("=" * 72)

    print("\n[1/8] 加载 CRYPTO_TOP_5 panel ...")
    panel_top5 = CRYPTO_TOP_5.load_panel(since=SINCE_FETCH, until=UNTIL, include_cash=False)

    # ----- 主回测 V1 默认参数 -----
    print("\n[2/8] V2-S3 主回测（TOP_5, V1 默认 vol_high=0.30 vol_haircut=0.5）...")
    res_t = run_trend(panel_top5, CRYPTO_TOP_5.symbols, vol_high=0.30, vol_haircut=0.5)
    nav_t = trim_to_perf(extract_nav(res_t))
    m_t = calc_crypto_metrics(nav_t, "V2-S3 trend tilt (TOP_5, V1 default)")
    print(f"  V2-S3 主: NAV {m_t['final_nav_100k']/1000:.1f}k / "
          f"CAGR {m_t['cagr']*100:+.2f}% / Sharpe {m_t['sharpe']:.3f} / "
          f"MaxDD {m_t['max_dd']*100:.1f}% / Vol {m_t['vol_ann']*100:.1f}% / Calmar {m_t['calmar']:.2f}")

    # ----- V2-S1 等权对照 -----
    print("\n[3/8] V2-S1 等权对照（TOP_5）...")
    res_eq = run_equal(panel_top5, CRYPTO_TOP_5.symbols)
    nav_eq = trim_to_perf(extract_nav(res_eq))
    m_eq = calc_crypto_metrics(nav_eq, "V2-S1 equal (TOP_5)")
    print(f"  V2-S1: NAV {m_eq['final_nav_100k']/1000:.1f}k / "
          f"CAGR {m_eq['cagr']*100:+.2f}% / Sharpe {m_eq['sharpe']:.3f} / "
          f"MaxDD {m_eq['max_dd']*100:.1f}% / Calmar {m_eq['calmar']:.2f}")

    # ----- BTC BH -----
    btc = panel_top5["BTC/USDT"]["close"]
    btc = btc[(btc.index >= pd.Timestamp(SINCE_PERF, tz=btc.index.tz))
              & (btc.index <= pd.Timestamp(UNTIL, tz=btc.index.tz))]
    nav_btc = btc / btc.iloc[0] * INIT_CASH
    m_btc = calc_crypto_metrics(nav_btc, "BTC/USDT BH")
    print(f"  BTC BH: NAV {m_btc['final_nav_100k']/1000:.1f}k / "
          f"CAGR {m_btc['cagr']*100:+.2f}% / Sharpe {m_btc['sharpe']:.3f}")

    # ----- vol_high sweep -----
    print("\n[4/8] vol_high sweep [0.30, 0.50, 0.80, 1.00] ...")
    vh_rows = []
    for vh in (0.30, 0.50, 0.80, 1.00):
        res = run_trend(panel_top5, CRYPTO_TOP_5.symbols, vol_high=vh, vol_haircut=0.5)
        nav = trim_to_perf(extract_nav(res))
        m = calc_crypto_metrics(nav, f"vol_high={vh}")
        print(f"  vol_high={vh}: NAV {m['final_nav_100k']/1000:.1f}k / "
              f"CAGR {m['cagr']*100:+.2f}% / Sharpe {m['sharpe']:.3f} / "
              f"MaxDD {m['max_dd']*100:.1f}% / Calmar {m['calmar']:.2f}")
        vh_rows.append({
            "vol_high": vh,
            "final_nav_100k": m["final_nav_100k"],
            "cagr_pct": m["cagr"] * 100,
            "sharpe": m["sharpe"],
            "max_dd_pct": m["max_dd"] * 100,
            "vol_ann_pct": m["vol_ann"] * 100,
            "calmar": m["calmar"],
        })
    pd.DataFrame(vh_rows).to_csv(ARTIFACTS / "vol_high_sweep.csv", index=False)

    # ----- vol_haircut ablation -----
    print("\n[5/8] vol_haircut ablation [0.5, 1.0] ...")
    hc_rows = []
    for hc in (0.5, 1.0):
        res = run_trend(panel_top5, CRYPTO_TOP_5.symbols, vol_high=0.30, vol_haircut=hc)
        nav = trim_to_perf(extract_nav(res))
        m = calc_crypto_metrics(nav, f"haircut={hc}")
        print(f"  vol_haircut={hc}: NAV {m['final_nav_100k']/1000:.1f}k / "
              f"CAGR {m['cagr']*100:+.2f}% / Sharpe {m['sharpe']:.3f} / "
              f"MaxDD {m['max_dd']*100:.1f}%")
        hc_rows.append({
            "vol_haircut": hc,
            "final_nav_100k": m["final_nav_100k"],
            "cagr_pct": m["cagr"] * 100,
            "sharpe": m["sharpe"],
            "max_dd_pct": m["max_dd"] * 100,
            "vol_ann_pct": m["vol_ann"] * 100,
        })
    pd.DataFrame(hc_rows).to_csv(ARTIFACTS / "vol_haircut_ablation.csv", index=False)

    # ----- Universe ablation -----
    print("\n[6/8] Universe ablation: TOP_5 / TOP_10 / NO_SOL ...")
    abl_rows = []
    for u in (CRYPTO_TOP_5, CRYPTO_TOP_10, CRYPTO_TOP_5_NO_SOL):
        try:
            u_panel = u.load_panel(since=SINCE_FETCH, until=UNTIL, include_cash=False)
            res = run_trend(u_panel, u.symbols, vol_high=0.30, vol_haircut=0.5)
            nav = trim_to_perf(extract_nav(res))
            m = calc_crypto_metrics(nav, f"trend_{u.name}")
            res_e = run_equal(u_panel, u.symbols)
            nav_e = trim_to_perf(extract_nav(res_e))
            me = calc_crypto_metrics(nav_e, f"equal_{u.name}")
            print(f"  {u.name} (n={len(u)}): trend NAV {m['final_nav_100k']/1000:.1f}k / "
                  f"Sharpe {m['sharpe']:.3f} / MaxDD {m['max_dd']*100:.1f}% / Calmar {m['calmar']:.2f} | "
                  f"equal Sharpe {me['sharpe']:.3f} MaxDD {me['max_dd']*100:.1f}%")
            abl_rows.append({
                "universe": u.name,
                "n_symbols": len(u),
                "trend_nav_100k": m["final_nav_100k"],
                "trend_cagr_pct": m["cagr"] * 100,
                "trend_sharpe": m["sharpe"],
                "trend_max_dd_pct": m["max_dd"] * 100,
                "trend_calmar": m["calmar"],
                "equal_sharpe": me["sharpe"],
                "equal_max_dd_pct": me["max_dd"] * 100,
                "equal_calmar": me["calmar"],
                "calmar_lift_pct": (m["calmar"] - me["calmar"]) / abs(me["calmar"]) * 100 if me["calmar"] else None,
            })
        except Exception as e:  # noqa: BLE001
            print(f"  {u.name}: FAILED {type(e).__name__}: {e}")
            abl_rows.append({"universe": u.name, "error": str(e)})
    pd.DataFrame(abl_rows).to_csv(ARTIFACTS / "universe_ablation.csv", index=False)

    # ----- Calmar 比较表（V2-S1 vs V2-S3 各 universe） -----
    print("\n[7/8] Calmar vs V2-S1（risk-adjusted return 真实度量）...")
    calmar_rows = []
    for r in abl_rows:
        if "error" in r:
            continue
        calmar_rows.append({
            "universe": r["universe"],
            "v2_s1_calmar": r["equal_calmar"],
            "v2_s3_calmar": r["trend_calmar"],
            "calmar_lift_abs": r["trend_calmar"] - r["equal_calmar"],
        })
    pd.DataFrame(calmar_rows).to_csv(ARTIFACTS / "calmar_comparison.csv", index=False)

    # ----- 仓位时序（用 result.target_weights 的 row_sum） -----
    print("\n[8/8] 仓位时序 + 绘图 + summary ...")
    weights = res_t.target_weights
    pos_sum = weights.sum(axis=1)
    pos_sum = pos_sum[(pos_sum.index >= pd.Timestamp(SINCE_PERF, tz=pos_sum.index.tz))
                       & (pos_sum.index <= pd.Timestamp(UNTIL, tz=pos_sum.index.tz))]
    pos_monthly = pos_sum.resample("ME").mean()
    pos_monthly.to_csv(ARTIFACTS / "position_timeline.csv", header=["risky_weight_sum"])
    print(f"  平均仓位（risky weight sum）：mean={pos_sum.mean():.3f}, "
          f"median={pos_sum.median():.3f}, max={pos_sum.max():.3f}")

    plot_equity({
        "V2-S3 trend tilt": nav_t,
        "V2-S1 equal": nav_eq,
        "BTC/USDT BH": nav_btc,
    }, ARTIFACTS / "equity_curve.png")
    plot_drawdown({
        "V2-S3 trend": nav_t,
        "V2-S1 equal": nav_eq,
        "BTC BH": nav_btc,
    }, ARTIFACTS / "drawdown.png")

    years = sorted(m_t["yearly"].keys())
    pd.DataFrame({
        "year": years,
        "v2s3_trend_pct": [m_t["yearly"].get(y, 0) * 100 for y in years],
        "v2s1_eq_pct":    [m_eq["yearly"].get(y, 0) * 100 for y in years],
        "btc_bh_pct":     [m_btc["yearly"].get(y, 0) * 100 for y in years],
    }).to_csv(ARTIFACTS / "yearly_returns.csv", index=False)

    summary = {
        "config": {
            "since": SINCE_PERF, "until": UNTIL,
            "init_cash_usdt": INIT_CASH,
            "fees_bp": FEES * 1e4, "slippage_bp": SLIPPAGE * 1e4,
            "trading_days_per_year": TDPY,
            "rebalance_period": 20,
            "vol_high_default": 0.30,
            "vol_haircut_default": 0.5,
            "universe_main": "CRYPTO_TOP_5",
        },
        "v2_s3_main": m_t,
        "v2_s1_baseline": m_eq,
        "btc_bh_benchmark": m_btc,
        "alpha_v2s3_vs_v2s1_pct_per_yr": (m_t["cagr"] - m_eq["cagr"]) * 100,
        "alpha_v2s3_vs_btc_bh_pct_per_yr": (m_t["cagr"] - m_btc["cagr"]) * 100,
        "calmar_lift_v2s3_vs_v2s1": m_t["calmar"] - m_eq["calmar"],
        "vol_high_sweep": vh_rows,
        "vol_haircut_ablation": hc_rows,
        "universe_ablation": abl_rows,
        "avg_position_pct": float(pos_sum.mean() * 100),
        "median_position_pct": float(pos_sum.median() * 100),
    }
    with open(ARTIFACTS / "real_backtest_summary.json", "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
    print(f"  saved 2 plots + 5 csv + 1 json to {ARTIFACTS}")

    print("\n" + "=" * 72)
    print(f"V2-S3 vs V2-S1 CAGR alpha = {(m_t['cagr'] - m_eq['cagr']) * 100:+.2f}%/yr")
    print(f"V2-S3 Calmar = {m_t['calmar']:.2f} vs V2-S1 Calmar = {m_eq['calmar']:.2f} "
          f"(lift {m_t['calmar'] - m_eq['calmar']:+.2f})")
    print(f"V2-S3 平均仓位 = {pos_sum.mean()*100:.1f}% (vs V2-S1 ~100%)")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
