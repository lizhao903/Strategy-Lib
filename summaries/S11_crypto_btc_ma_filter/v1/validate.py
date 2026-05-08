"""V2-S2 (S11) `crypto_btc_ma_filter` 真实数据回测 + ablation.

跑法：
    cd /Volumes/ai/github/Strategy-Lib && source .venv/bin/activate
    python summaries/S11_crypto_btc_ma_filter/v1/validate.py

产物（artifacts/）：
    - real_backtest_summary.json
    - equity_curve.png / drawdown.png / yearly_returns.{csv,png}
    - ma_length_sweep.csv          MA ∈ {50, 100, 200}
    - universe_ablation.csv        TOP_5 vs TOP_10 risky
    - weight_mode_ablation.csv     equal vs signal_only
    - signal_timeline.csv          ON/OFF 切换时间分布

注意：crypto 24/7，年化用 365 天。
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

from strategy_lib.strategies.cn_etf_market_ma_filter_v2 import MarketMAFilterV2Strategy  # noqa: E402
from strategy_lib.strategies.cn_etf_equal_rebalance import EqualRebalanceStrategy  # noqa: E402
from strategy_lib.universes import CRYPTO_TOP_5, CRYPTO_TOP_10  # noqa: E402

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


def run_ma(panel, universe, *, ma_length=200, lag_days=1, weight_mode="equal"):
    strat = MarketMAFilterV2Strategy(
        symbols=list(universe.symbols),
        cash_symbol=universe.cash_proxy,
        signal_symbol=universe.benchmark,
        ma_length=ma_length,
        lag_days=lag_days,
        weight_mode=weight_mode,
    )
    return strat.run(panel, init_cash=INIT_CASH, fees=FEES, slippage=SLIPPAGE)


def run_equal(panel, symbols):
    strat = EqualRebalanceStrategy(symbols=list(symbols), rebalance_period=20)
    return strat.run(panel, init_cash=INIT_CASH, fees=FEES, slippage=SLIPPAGE)


def plot_equity(navs, path):
    fig, ax = plt.subplots(figsize=(13, 6))
    style = {
        "V2-S2 BTC MA filter": ("#1f77b4", 2.5, "-"),
        "V2-S1 equal": ("#d62728", 1.8, "--"),
        "BTC/USDT BH": ("#ff7f0e", 1.2, ":"),
    }
    for k, s in navs.items():
        c, lw, ls = style.get(k, ("#888", 1.0, "-"))
        ax.plot(s.index, s.values, label=k, color=c, lw=lw, linestyle=ls)
    ax.set_title("V2-S2 BTC MA filter vs V2-S1 vs BTC BH (2021-2024)")
    ax.set_ylabel("Normalized NAV (start=1)")
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


def plot_yearly(metrics_ma, metrics_eq, metrics_bh, path):
    years = sorted(metrics_ma["yearly"].keys())
    ma = [metrics_ma["yearly"].get(y, 0) * 100 for y in years]
    eq = [metrics_eq["yearly"].get(y, 0) * 100 for y in years]
    bh = [metrics_bh["yearly"].get(y, 0) * 100 for y in years]
    x = np.arange(len(years))
    w = 0.27
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.bar(x - w, ma, w, label="V2-S2 MA filter", color="#1f77b4")
    ax.bar(x,     eq, w, label="V2-S1 equal", color="#d62728")
    ax.bar(x + w, bh, w, label="BTC BH", color="#ff7f0e")
    ax.axhline(0, color="black", lw=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels([str(y) for y in years])
    ax.set_ylabel("Yearly Return (%)")
    ax.set_title("V2-S2 vs V2-S1 vs BTC BH yearly")
    ax.legend()
    ax.grid(True, alpha=0.3, axis="y")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def main() -> int:
    print("=" * 72)
    print("V2-S2 (S11) crypto_btc_ma_filter 真实数据回测 + ablation")
    print(f"  窗口: {SINCE_PERF} ~ {UNTIL}, 初始 {INIT_CASH:,} USDT")
    print(f"  fees={FEES * 1e4:.0f}bp, slippage={SLIPPAGE * 1e4:.0f}bp, ann={TDPY}")
    print("=" * 72)

    print("\n[1/7] 加载 CRYPTO_TOP_5 panel + USDT ...")
    panel_top5 = CRYPTO_TOP_5.load_panel(since=SINCE_FETCH, until=UNTIL, include_cash=True)
    for sym, df in panel_top5.items():
        print(f"  {sym}: {len(df)} bars")

    # ----- 主回测 -----
    print("\n[2/7] V2-S2 主回测（TOP_5, MA200, lag=1, weight=equal）...")
    res_ma = run_ma(panel_top5, CRYPTO_TOP_5, ma_length=200, lag_days=1, weight_mode="equal")
    nav_ma = trim_to_perf(extract_nav(res_ma))
    m_ma = calc_crypto_metrics(nav_ma, "V2-S2 BTC MA filter (TOP_5, MA200)")
    n_on = int((res_ma.signal == 1).sum())
    n_off = int((res_ma.signal == 0).sum())
    print(f"  V2-S2 主: NAV {m_ma['final_nav_100k']/1000:.1f}k / "
          f"CAGR {m_ma['cagr']*100:+.2f}% / Sharpe {m_ma['sharpe']:.3f} / "
          f"MaxDD {m_ma['max_dd']*100:.1f}% / Vol {m_ma['vol_ann']*100:.1f}%")
    print(f"  ON/OFF: ON={n_on}d ({n_on/(n_on+n_off)*100:.1f}%) / OFF={n_off}d / switches={len(res_ma.switch_dates)}")

    # ----- V2-S1 等权对照 -----
    print("\n[3/7] V2-S1 等权对照（TOP_5）...")
    res_eq = run_equal(panel_top5, CRYPTO_TOP_5.symbols)
    nav_eq = trim_to_perf(extract_nav(res_eq))
    m_eq = calc_crypto_metrics(nav_eq, "V2-S1 equal (TOP_5)")
    print(f"  V2-S1: NAV {m_eq['final_nav_100k']/1000:.1f}k / "
          f"CAGR {m_eq['cagr']*100:+.2f}% / Sharpe {m_eq['sharpe']:.3f} / "
          f"MaxDD {m_eq['max_dd']*100:.1f}%")

    # ----- BTC BH -----
    btc = panel_top5["BTC/USDT"]["close"]
    btc = btc[(btc.index >= pd.Timestamp(SINCE_PERF, tz=btc.index.tz))
              & (btc.index <= pd.Timestamp(UNTIL, tz=btc.index.tz))]
    nav_btc = btc / btc.iloc[0] * INIT_CASH
    m_btc = calc_crypto_metrics(nav_btc, "BTC/USDT BH")
    print(f"  BTC BH: NAV {m_btc['final_nav_100k']/1000:.1f}k / "
          f"CAGR {m_btc['cagr']*100:+.2f}% / Sharpe {m_btc['sharpe']:.3f}")

    # ----- MA length sweep -----
    print("\n[4/7] MA length sweep [50, 100, 200] ...")
    ma_rows = []
    for ma_len in (50, 100, 200):
        res = run_ma(panel_top5, CRYPTO_TOP_5, ma_length=ma_len, lag_days=1, weight_mode="equal")
        nav = trim_to_perf(extract_nav(res))
        m = calc_crypto_metrics(nav, f"MA={ma_len}")
        sig = res.signal
        n_on_y = int((sig == 1).sum())
        n_total = int(len(sig))
        n_sw = len(res.switch_dates)
        print(f"  MA={ma_len}: NAV {m['final_nav_100k']/1000:.1f}k / "
              f"CAGR {m['cagr']*100:+.2f}% / Sharpe {m['sharpe']:.3f} / "
              f"MaxDD {m['max_dd']*100:.1f}% / ON {n_on_y/n_total*100:.0f}% / sw {n_sw}")
        ma_rows.append({
            "ma_length": ma_len,
            "final_nav_100k": m["final_nav_100k"],
            "cagr_pct": m["cagr"] * 100,
            "sharpe": m["sharpe"],
            "max_dd_pct": m["max_dd"] * 100,
            "vol_ann_pct": m["vol_ann"] * 100,
            "calmar": m["calmar"],
            "on_pct": n_on_y / n_total * 100,
            "n_switches": n_sw,
        })
    pd.DataFrame(ma_rows).to_csv(ARTIFACTS / "ma_length_sweep.csv", index=False)

    # ----- 池 ablation: TOP_5 vs TOP_10 -----
    print("\n[5/7] Universe ablation: TOP_5 vs TOP_10 (risky) ...")
    abl_rows = []
    for u in (CRYPTO_TOP_5, CRYPTO_TOP_10):
        try:
            u_panel = u.load_panel(since=SINCE_FETCH, until=UNTIL, include_cash=True)
            res = run_ma(u_panel, u, ma_length=200, lag_days=1, weight_mode="equal")
            nav = trim_to_perf(extract_nav(res))
            m = calc_crypto_metrics(nav, f"ma_filter_{u.name}")
            print(f"  {u.name} (n={len(u)}): NAV {m['final_nav_100k']/1000:.1f}k / "
                  f"CAGR {m['cagr']*100:+.2f}% / Sharpe {m['sharpe']:.3f} / MaxDD {m['max_dd']*100:.1f}%")
            abl_rows.append({
                "universe": u.name,
                "n_symbols": len(u),
                "final_nav_100k": m["final_nav_100k"],
                "cagr_pct": m["cagr"] * 100,
                "sharpe": m["sharpe"],
                "max_dd_pct": m["max_dd"] * 100,
                "vol_ann_pct": m["vol_ann"] * 100,
                "calmar": m["calmar"],
            })
        except Exception as e:  # noqa: BLE001
            print(f"  {u.name}: FAILED {type(e).__name__}: {e}")
            abl_rows.append({"universe": u.name, "error": str(e)})
    pd.DataFrame(abl_rows).to_csv(ARTIFACTS / "universe_ablation.csv", index=False)

    # ----- weight_mode ablation: equal vs signal_only -----
    print("\n[6/7] Weight mode ablation: equal vs signal_only ...")
    wm_rows = []
    for wm in ("equal", "signal_only"):
        res = run_ma(panel_top5, CRYPTO_TOP_5, ma_length=200, lag_days=1, weight_mode=wm)
        nav = trim_to_perf(extract_nav(res))
        m = calc_crypto_metrics(nav, f"weight_mode={wm}")
        print(f"  weight_mode={wm}: NAV {m['final_nav_100k']/1000:.1f}k / "
              f"CAGR {m['cagr']*100:+.2f}% / Sharpe {m['sharpe']:.3f}")
        wm_rows.append({
            "weight_mode": wm,
            "final_nav_100k": m["final_nav_100k"],
            "cagr_pct": m["cagr"] * 100,
            "sharpe": m["sharpe"],
            "max_dd_pct": m["max_dd"] * 100,
        })
    pd.DataFrame(wm_rows).to_csv(ARTIFACTS / "weight_mode_ablation.csv", index=False)

    # ----- ON/OFF 时间线 -----
    sig = res_ma.signal
    sig_perf = sig[(sig.index >= pd.Timestamp(SINCE_PERF, tz=sig.index.tz))
                    & (sig.index <= pd.Timestamp(UNTIL, tz=sig.index.tz))]
    sig_yearly = sig_perf.groupby(sig_perf.index.year).agg(
        on_pct=lambda s: (s == 1).mean() * 100,
        n_days=lambda s: len(s),
    )
    sig_yearly.to_csv(ARTIFACTS / "signal_timeline.csv")
    print(f"\n  signal_timeline:\n{sig_yearly}")

    # ----- 绘图 + 写汇总 -----
    print("\n[7/7] 绘图 + summary ...")
    plot_equity({
        "V2-S2 BTC MA filter": nav_ma,
        "V2-S1 equal": nav_eq,
        "BTC/USDT BH": nav_btc,
    }, ARTIFACTS / "equity_curve.png")
    plot_drawdown({
        "V2-S2 MA filter": nav_ma,
        "V2-S1 equal": nav_eq,
        "BTC BH": nav_btc,
    }, ARTIFACTS / "drawdown.png")
    plot_yearly(m_ma, m_eq, m_btc, ARTIFACTS / "yearly_returns.png")

    years = sorted(m_ma["yearly"].keys())
    pd.DataFrame({
        "year": years,
        "v2s2_ma_pct": [m_ma["yearly"].get(y, 0) * 100 for y in years],
        "v2s1_eq_pct": [m_eq["yearly"].get(y, 0) * 100 for y in years],
        "btc_bh_pct":  [m_btc["yearly"].get(y, 0) * 100 for y in years],
    }).to_csv(ARTIFACTS / "yearly_returns.csv", index=False)

    summary = {
        "config": {
            "since": SINCE_PERF, "until": UNTIL,
            "init_cash_usdt": INIT_CASH,
            "fees_bp": FEES * 1e4, "slippage_bp": SLIPPAGE * 1e4,
            "trading_days_per_year": TDPY,
            "ma_length": 200, "lag_days": 1, "weight_mode": "equal",
            "signal_symbol": "BTC/USDT",
            "universe_main": "CRYPTO_TOP_5",
        },
        "v2_s2_main": m_ma,
        "v2_s1_baseline": m_eq,
        "btc_bh_benchmark": m_btc,
        "alpha_v2s2_vs_v2s1_pct_per_yr": (m_ma["cagr"] - m_eq["cagr"]) * 100,
        "alpha_v2s2_vs_btc_bh_pct_per_yr": (m_ma["cagr"] - m_btc["cagr"]) * 100,
        "ma_length_sweep": ma_rows,
        "universe_ablation": abl_rows,
        "weight_mode_ablation": wm_rows,
        "signal_timeline_pct": sig_yearly.to_dict(),
        "n_switches_main": len(res_ma.switch_dates),
        "on_pct_main": n_on / (n_on + n_off) * 100,
    }
    with open(ARTIFACTS / "real_backtest_summary.json", "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
    print(f"  saved 3 plots + 5 csv + 1 json to {ARTIFACTS}")

    print("\n" + "=" * 72)
    print(f"V2-S2 vs V2-S1 alpha = {(m_ma['cagr'] - m_eq['cagr']) * 100:+.2f}%/yr")
    print(f"V2-S2 vs BTC BH alpha = {(m_ma['cagr'] - m_btc['cagr']) * 100:+.2f}%/yr")
    print(f"V2-S2 MaxDD vs V2-S1 = {m_ma['max_dd']*100:+.2f}% vs {m_eq['max_dd']*100:+.2f}%")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
