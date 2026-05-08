"""V2-S4 (S10) `crypto_momentum_tilt` 真实数据回测 + ablation.

跑法：
    cd /Volumes/ai/github/Strategy-Lib && source .venv/bin/activate
    python summaries/S10_crypto_momentum_tilt/v1/validate.py

产物（保存到 artifacts/）：
    - real_backtest_summary.json   主结果 + 与 V2-S1 对比 + ablation
    - equity_curve.png              V2-S4 vs V2-S1 vs BTC BH（log y）
    - drawdown.png                  三者回撤
    - lookback_sweep.csv            lookback ∈ {60, 120, 240} 上的指标
    - signal_sweep.csv              raw vs vol_adj 对比
    - universe_ablation.csv         TOP_5 / TOP_10 / NO_SOL 三档
    - yearly_returns.csv + .png     分年度收益

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

from strategy_lib.strategies.cn_etf_equal_rebalance import EqualRebalanceStrategy  # noqa: E402
from strategy_lib.strategies.cn_etf_momentum_tilt_v2 import MomentumTiltV2Strategy  # noqa: E402
from strategy_lib.universes import (  # noqa: E402
    CRYPTO_TOP_5,
    CRYPTO_TOP_5_NO_SOL,
    CRYPTO_TOP_10,
)

# V2 共享基线（与 S9 完全一致）
SINCE_FETCH = "2020-09-01"
SINCE_PERF = "2021-01-01"
UNTIL = "2024-12-31"
INIT_CASH = 100_000          # USDT
FEES = 0.001                 # 10 bp
SLIPPAGE = 0.001             # 10 bp
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


def run_momentum(panel, symbols, *, lookback=120, skip=5, signal="raw", alpha=1.0):
    strat = MomentumTiltV2Strategy(
        symbols=list(symbols),
        rebalance_period=20,
        lookback=lookback,
        skip=skip,
        signal=signal,
        alpha=alpha,
    )
    return strat.run(panel, init_cash=INIT_CASH, fees=FEES, slippage=SLIPPAGE)


def run_equal(panel, symbols):
    strat = EqualRebalanceStrategy(symbols=list(symbols), rebalance_period=20)
    return strat.run(panel, init_cash=INIT_CASH, fees=FEES, slippage=SLIPPAGE)


def plot_equity(navs: dict[str, pd.Series], path: Path) -> None:
    fig, ax = plt.subplots(figsize=(13, 6))
    style = {
        "V2-S4 momentum tilt (TOP_5)": ("#2ca02c", 2.5, "-"),
        "V2-S1 equal (TOP_5)":         ("#d62728", 1.8, "--"),
        "BTC/USDT BH":                 ("#ff7f0e", 1.2, ":"),
    }
    for k, s in navs.items():
        c, lw, ls = style.get(k, ("#888", 1.0, "-"))
        ax.plot(s.index, s.values, label=k, color=c, lw=lw, linestyle=ls)
    ax.set_title("V2-S4 momentum_tilt vs V2-S1 equal vs BTC BH (2021-01 ~ 2024-12)")
    ax.set_ylabel("Normalized NAV (start=1)")
    ax.set_yscale("log")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def plot_drawdown(navs: dict[str, pd.Series], path: Path) -> None:
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
    ax.set_title("回撤对比：momentum vs equal vs BTC（2022 LUNA/FTX 高亮）")
    ax.set_ylabel("Drawdown")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def plot_yearly(metrics_mom, metrics_eq, metrics_bh, path):
    years = sorted(metrics_mom["yearly"].keys())
    mom = [metrics_mom["yearly"].get(y, 0) * 100 for y in years]
    eq = [metrics_eq["yearly"].get(y, 0) * 100 for y in years]
    bh = [metrics_bh["yearly"].get(y, 0) * 100 for y in years]
    x = np.arange(len(years))
    w = 0.27
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.bar(x - w, mom, w, label="V2-S4 momentum", color="#2ca02c")
    ax.bar(x,     eq,  w, label="V2-S1 equal", color="#d62728")
    ax.bar(x + w, bh,  w, label="BTC BH", color="#ff7f0e")
    ax.axhline(0, color="black", lw=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels([str(y) for y in years])
    ax.set_ylabel("Yearly Return (%)")
    ax.set_title("V2-S4 vs V2-S1 vs BTC BH 分年度")
    ax.legend()
    ax.grid(True, alpha=0.3, axis="y")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def main() -> int:
    print("=" * 72)
    print("V2-S4 (S10) crypto_momentum_tilt 真实数据回测 + ablation")
    print(f"  窗口: {SINCE_PERF} ~ {UNTIL}, 初始 {INIT_CASH:,} USDT")
    print(f"  fees={FEES * 1e4:.0f}bp, slippage={SLIPPAGE * 1e4:.0f}bp, ann={TDPY}")
    print("=" * 72)

    print("\n[1/7] 加载 CRYPTO_TOP_5 panel ...")
    panel_top5 = CRYPTO_TOP_5.load_panel(since=SINCE_FETCH, until=UNTIL, include_cash=False)
    for sym, df in panel_top5.items():
        print(f"  {sym}: {len(df)} bars, {df.index.min().date()} ~ {df.index.max().date()}")

    # ----- 主回测：V2-S4 默认参数 -----
    print("\n[2/7] V2-S4 主回测（TOP_5, lookback=120, skip=5, signal=raw, alpha=1）...")
    res_mom = run_momentum(panel_top5, CRYPTO_TOP_5.symbols)
    nav_mom = trim_to_perf(extract_nav(res_mom))
    m_mom = calc_crypto_metrics(nav_mom, "V2-S4 momentum tilt (TOP_5)")
    print(f"  V2-S4 主: NAV {m_mom['final_nav_100k']/1000:.1f}k / "
          f"CAGR {m_mom['cagr']*100:+.2f}% / Sharpe {m_mom['sharpe']:.3f} / "
          f"MaxDD {m_mom['max_dd']*100:.1f}% / Vol {m_mom['vol_ann']*100:.1f}%")

    # ----- V2-S1 等权对照 -----
    print("\n[3/7] V2-S1 等权对照（TOP_5）...")
    res_eq = run_equal(panel_top5, CRYPTO_TOP_5.symbols)
    nav_eq = trim_to_perf(extract_nav(res_eq))
    m_eq = calc_crypto_metrics(nav_eq, "V2-S1 equal (TOP_5)")
    print(f"  V2-S1: NAV {m_eq['final_nav_100k']/1000:.1f}k / "
          f"CAGR {m_eq['cagr']*100:+.2f}% / Sharpe {m_eq['sharpe']:.3f} / "
          f"MaxDD {m_eq['max_dd']*100:.1f}%")

    # ----- BTC BH benchmark -----
    btc = panel_top5["BTC/USDT"]["close"]
    btc = btc[(btc.index >= pd.Timestamp(SINCE_PERF, tz=btc.index.tz))
              & (btc.index <= pd.Timestamp(UNTIL, tz=btc.index.tz))]
    nav_btc = btc / btc.iloc[0] * INIT_CASH
    m_btc = calc_crypto_metrics(nav_btc, "BTC/USDT BH")
    print(f"  BTC BH: NAV {m_btc['final_nav_100k']/1000:.1f}k / "
          f"CAGR {m_btc['cagr']*100:+.2f}% / Sharpe {m_btc['sharpe']:.3f}")

    # ----- lookback sweep -----
    print("\n[4/7] Lookback sweep [60, 120, 240] ...")
    lb_rows = []
    for lb in (60, 120, 240):
        res = run_momentum(panel_top5, CRYPTO_TOP_5.symbols, lookback=lb)
        nav = trim_to_perf(extract_nav(res))
        m = calc_crypto_metrics(nav, f"lookback={lb}")
        print(f"  lookback={lb}: NAV {m['final_nav_100k']/1000:.1f}k / "
              f"CAGR {m['cagr']*100:+.2f}% / Sharpe {m['sharpe']:.3f}")
        lb_rows.append({
            "lookback": lb,
            "final_nav_100k": m["final_nav_100k"],
            "cagr_pct": m["cagr"] * 100,
            "sharpe": m["sharpe"],
            "max_dd_pct": m["max_dd"] * 100,
            "vol_ann_pct": m["vol_ann"] * 100,
        })
    pd.DataFrame(lb_rows).to_csv(ARTIFACTS / "lookback_sweep.csv", index=False)

    # ----- signal sweep raw vs vol_adj -----
    print("\n[5/7] Signal sweep (raw vs vol_adj) ...")
    sig_rows = []
    for sig in ("raw", "vol_adj"):
        res = run_momentum(panel_top5, CRYPTO_TOP_5.symbols, signal=sig)
        nav = trim_to_perf(extract_nav(res))
        m = calc_crypto_metrics(nav, f"signal={sig}")
        print(f"  signal={sig}: NAV {m['final_nav_100k']/1000:.1f}k / "
              f"CAGR {m['cagr']*100:+.2f}% / Sharpe {m['sharpe']:.3f}")
        sig_rows.append({
            "signal": sig,
            "final_nav_100k": m["final_nav_100k"],
            "cagr_pct": m["cagr"] * 100,
            "sharpe": m["sharpe"],
            "max_dd_pct": m["max_dd"] * 100,
            "vol_ann_pct": m["vol_ann"] * 100,
        })
    pd.DataFrame(sig_rows).to_csv(ARTIFACTS / "signal_sweep.csv", index=False)

    # ----- universe ablation：TOP_5 / TOP_10 / NO_SOL -----
    print("\n[6/7] Universe ablation: TOP_5 / TOP_10 / NO_SOL ...")
    abl_rows = []
    for u in (CRYPTO_TOP_5, CRYPTO_TOP_10, CRYPTO_TOP_5_NO_SOL):
        try:
            u_panel = u.load_panel(since=SINCE_FETCH, until=UNTIL, include_cash=False)
            res_m = run_momentum(u_panel, u.symbols)
            nav_m = trim_to_perf(extract_nav(res_m))
            mu = calc_crypto_metrics(nav_m, f"momentum_{u.name}")
            res_e = run_equal(u_panel, u.symbols)
            nav_e = trim_to_perf(extract_nav(res_e))
            me = calc_crypto_metrics(nav_e, f"equal_{u.name}")
            print(f"  {u.name} (n={len(u)}): "
                  f"momentum NAV {mu['final_nav_100k']/1000:.1f}k Sharpe {mu['sharpe']:.3f} | "
                  f"equal NAV {me['final_nav_100k']/1000:.1f}k Sharpe {me['sharpe']:.3f} | "
                  f"alpha CAGR {(mu['cagr']-me['cagr'])*100:+.2f}pp")
            abl_rows.append({
                "universe": u.name,
                "n_symbols": len(u),
                "momentum_nav_100k": mu["final_nav_100k"],
                "momentum_cagr_pct": mu["cagr"] * 100,
                "momentum_sharpe": mu["sharpe"],
                "momentum_max_dd_pct": mu["max_dd"] * 100,
                "equal_nav_100k": me["final_nav_100k"],
                "equal_cagr_pct": me["cagr"] * 100,
                "equal_sharpe": me["sharpe"],
                "alpha_cagr_pp": (mu["cagr"] - me["cagr"]) * 100,
                "alpha_sharpe": mu["sharpe"] - me["sharpe"],
            })
        except Exception as e:  # noqa: BLE001
            print(f"  {u.name}: FAILED {type(e).__name__}: {e}")
            abl_rows.append({"universe": u.name, "error": str(e)})
    pd.DataFrame(abl_rows).to_csv(ARTIFACTS / "universe_ablation.csv", index=False)

    # ----- 绘图 + 写汇总 -----
    print("\n[7/7] 绘图 + summary ...")
    plot_equity({
        "V2-S4 momentum tilt (TOP_5)": nav_mom,
        "V2-S1 equal (TOP_5)": nav_eq,
        "BTC/USDT BH": nav_btc,
    }, ARTIFACTS / "equity_curve.png")
    plot_drawdown({
        "V2-S4 momentum": nav_mom,
        "V2-S1 equal": nav_eq,
        "BTC BH": nav_btc,
    }, ARTIFACTS / "drawdown.png")
    plot_yearly(m_mom, m_eq, m_btc, ARTIFACTS / "yearly_returns.png")

    # yearly csv
    years = sorted(m_mom["yearly"].keys())
    pd.DataFrame({
        "year": years,
        "v2s4_mom_pct": [m_mom["yearly"].get(y, 0) * 100 for y in years],
        "v2s1_eq_pct":  [m_eq["yearly"].get(y, 0) * 100 for y in years],
        "btc_bh_pct":   [m_btc["yearly"].get(y, 0) * 100 for y in years],
    }).to_csv(ARTIFACTS / "yearly_returns.csv", index=False)

    summary = {
        "config": {
            "since": SINCE_PERF, "until": UNTIL,
            "init_cash_usdt": INIT_CASH,
            "fees_bp": FEES * 1e4, "slippage_bp": SLIPPAGE * 1e4,
            "trading_days_per_year": TDPY,
            "rebalance_period": 20,
            "lookback": 120, "skip": 5, "alpha": 1.0,
            "signal": "raw",
            "universe_main": "CRYPTO_TOP_5",
        },
        "v2_s4_main": m_mom,
        "v2_s1_equal_baseline": m_eq,
        "btc_bh_benchmark": m_btc,
        "alpha_v2s4_vs_v2s1_pct_per_yr": (m_mom["cagr"] - m_eq["cagr"]) * 100,
        "alpha_v2s4_vs_btc_bh_pct_per_yr": (m_mom["cagr"] - m_btc["cagr"]) * 100,
        "lookback_sweep": lb_rows,
        "signal_sweep": sig_rows,
        "universe_ablation": abl_rows,
    }
    with open(ARTIFACTS / "real_backtest_summary.json", "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
    print(f"  saved 3 plots + 4 csv + 1 json to {ARTIFACTS}")

    print("\n" + "=" * 72)
    print(f"V2-S4 vs V2-S1 alpha = {(m_mom['cagr'] - m_eq['cagr']) * 100:+.2f}%/yr (信号贡献)")
    print(f"V2-S4 vs BTC BH alpha = {(m_mom['cagr'] - m_btc['cagr']) * 100:+.2f}%/yr (整体)")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
