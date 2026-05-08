"""V2-S1 (S9) `crypto_basket_equal` 真实数据回测.

跑法：
    cd /Volumes/ai/github/Strategy-Lib && source .venv/bin/activate
    python summaries/S9_crypto_basket_equal/v1/validate.py

产物（保存到本目录的 artifacts/）:
    - real_backtest_summary.json: 主结果 + 与 BTC BH 对比 + universe sweep
    - equity_curve.png: V2-S1 vs BTC BH
    - drawdown.png: 同上
    - weight_evolution.png: 5 资产权重时序堆积
    - yearly_returns.png + .csv: 分年度收益条形图
    - universe_comparison.csv: V2-S1 在 4 个 crypto universe 上的对比

注意：crypto 24/7，年化用 365 天而非 V1 的 252。
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
from strategy_lib.universes import (  # noqa: E402
    CRYPTO_BTC_ETH_2,
    CRYPTO_TOP_3,
    CRYPTO_TOP_5,
    CRYPTO_TOP_10,
)

# V2 共享基线
SINCE_FETCH = "2020-09-01"   # 含 ~4 个月暖机
SINCE_PERF = "2021-01-01"    # 绩效统计起点
UNTIL = "2024-12-31"
INIT_CASH = 100_000          # USDT
FEES = 0.001                 # 10 bp（V2 高于 V1 的 5 bp）
SLIPPAGE = 0.001             # 10 bp
TDPY = 365                   # crypto 24/7


# -----------------------------------------------------------------------------
# Metrics（crypto 适配，用 365 天年化）
# -----------------------------------------------------------------------------

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


# -----------------------------------------------------------------------------
# 图表
# -----------------------------------------------------------------------------

def plot_equity(navs: dict[str, pd.Series], path: Path) -> None:
    fig, ax = plt.subplots(figsize=(13, 6))
    colors = {
        "V2-S1 crypto basket eq": ("#d62728", 2.5, "-"),
        "BTC/USDT BH": ("#ff7f0e", 1.5, "--"),
        "ETH/USDT BH": ("#9467bd", 1.0, ":"),
    }
    for k, s in navs.items():
        c, lw, ls = colors.get(k, ("#888", 1.0, "-"))
        ax.plot(s.index, s.values, label=k, color=c, lw=lw, linestyle=ls)
    ax.set_title("V2-S1 crypto_basket_equal vs BTC BH (2021-01 ~ 2024-12)")
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
    # 高亮 2022 年（LUNA / FTX 双重崩盘）
    if len(navs) > 0:
        s = next(iter(navs.values()))
        ax.axvspan(
            pd.Timestamp("2022-01-01", tz=s.index.tz),
            pd.Timestamp("2022-12-31", tz=s.index.tz),
            alpha=0.10, color="red",
        )
    ax.set_title("回撤对比 (2022 LUNA/FTX 双崩盘高亮)")
    ax.set_ylabel("Drawdown")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def plot_weight_evolution(weights_df: pd.DataFrame, path: Path) -> None:
    weights_df = weights_df[weights_df.index >= pd.Timestamp(SINCE_PERF, tz=weights_df.index.tz)]
    fig, ax = plt.subplots(figsize=(13, 5))
    ax.stackplot(weights_df.index, weights_df.T.values,
                 labels=weights_df.columns, alpha=0.85)
    ax.set_title("V2-S1 5 资产权重时序（月度再平衡）")
    ax.set_ylabel("Weight")
    ax.set_ylim(0, 1)
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def plot_yearly(metrics_v2s1: dict, metrics_bh: dict, path: Path) -> None:
    years = sorted(metrics_v2s1["yearly"].keys())
    v2s1 = [metrics_v2s1["yearly"].get(y, 0) * 100 for y in years]
    bh = [metrics_bh["yearly"].get(y, 0) * 100 for y in years]
    x = np.arange(len(years))
    w = 0.35
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.bar(x - w / 2, v2s1, w, label="V2-S1", color="#d62728")
    ax.bar(x + w / 2, bh, w, label="BTC/USDT BH", color="#ff7f0e")
    ax.axhline(0, color="black", lw=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels([str(y) for y in years])
    ax.set_ylabel("Yearly Return (%)")
    ax.set_title("V2-S1 vs BTC BH 分年度收益")
    ax.legend()
    ax.grid(True, alpha=0.3, axis="y")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

def main() -> int:
    print("=" * 70)
    print("V2-S1 crypto_basket_equal 真实数据回测")
    print(f"  窗口: {SINCE_PERF} ~ {UNTIL}, 初始 {INIT_CASH:,} USDT")
    print(f"  fees={FEES * 1e4:.0f}bp, slippage={SLIPPAGE * 1e4:.0f}bp, ann factor={TDPY}")
    print("=" * 70)

    print("\n[1/5] 加载 CRYPTO_TOP_5 panel ...")
    panel = CRYPTO_TOP_5.load_panel(since=SINCE_FETCH, until=UNTIL, include_cash=False)
    for sym, df in panel.items():
        print(f"  {sym}: {len(df)} bars, {df.index.min().date()} ~ {df.index.max().date()}")

    print("\n[2/5] 跑 V2-S1 主回测（CRYPTO_TOP_5 等权 + 月度再平衡）...")
    strat = EqualRebalanceStrategy(symbols=list(CRYPTO_TOP_5.symbols), rebalance_period=20)
    result = strat.run(panel, init_cash=INIT_CASH, fees=FEES, slippage=SLIPPAGE)

    nav_full = extract_nav(result)
    nav_perf = trim_to_perf(nav_full)
    metrics_v2s1 = calc_crypto_metrics(nav_perf, label="V2-S1 crypto_basket_equal")
    print(f"  V2-S1: NAV {metrics_v2s1['final_nav_100k']/1000:.1f}k / "
          f"CAGR {metrics_v2s1['cagr']*100:+.2f}% / Sharpe {metrics_v2s1['sharpe']:.3f} / "
          f"MaxDD {metrics_v2s1['max_dd']*100:.1f}% / Vol {metrics_v2s1['vol_ann']*100:.1f}%")

    print("\n[3/5] 计算 BTC/USDT BH benchmark ...")
    btc_close = panel["BTC/USDT"]["close"]
    btc_close = btc_close[btc_close.index >= pd.Timestamp(SINCE_PERF, tz=btc_close.index.tz)]
    btc_close = btc_close[btc_close.index <= pd.Timestamp(UNTIL, tz=btc_close.index.tz)]
    nav_bh = btc_close / btc_close.iloc[0] * INIT_CASH
    metrics_bh = calc_crypto_metrics(nav_bh, label="BTC/USDT BH")
    print(f"  BTC BH: NAV {metrics_bh['final_nav_100k']/1000:.1f}k / "
          f"CAGR {metrics_bh['cagr']*100:+.2f}% / Sharpe {metrics_bh['sharpe']:.3f} / "
          f"MaxDD {metrics_bh['max_dd']*100:.1f}%")

    # ETH BH 作辅助参考
    eth_close = panel["ETH/USDT"]["close"]
    eth_close = eth_close[eth_close.index >= pd.Timestamp(SINCE_PERF, tz=eth_close.index.tz)]
    eth_close = eth_close[eth_close.index <= pd.Timestamp(UNTIL, tz=eth_close.index.tz)]
    nav_eth = eth_close / eth_close.iloc[0] * INIT_CASH
    metrics_eth = calc_crypto_metrics(nav_eth, label="ETH/USDT BH")
    print(f"  ETH BH: NAV {metrics_eth['final_nav_100k']/1000:.1f}k / "
          f"CAGR {metrics_eth['cagr']*100:+.2f}% / Sharpe {metrics_eth['sharpe']:.3f}")

    print("\n[4/5] Universe ablation: 等权 S3 在 4 个 crypto universe 上 ...")
    universe_rows = []
    for u in (CRYPTO_BTC_ETH_2, CRYPTO_TOP_3, CRYPTO_TOP_5, CRYPTO_TOP_10):
        try:
            u_panel = u.load_panel(since=SINCE_FETCH, until=UNTIL, include_cash=False)
            u_strat = EqualRebalanceStrategy(symbols=list(u.symbols), rebalance_period=20)
            u_result = u_strat.run(u_panel, init_cash=INIT_CASH, fees=FEES, slippage=SLIPPAGE)
            u_nav = trim_to_perf(extract_nav(u_result))
            u_metrics = calc_crypto_metrics(u_nav, label=u.name)
            print(f"  {u.name} ({len(u)}): NAV {u_metrics['final_nav_100k']/1000:.1f}k / "
                  f"CAGR {u_metrics['cagr']*100:+.2f}% / Sharpe {u_metrics['sharpe']:.3f} / "
                  f"MaxDD {u_metrics['max_dd']*100:.1f}%")
            universe_rows.append({
                "universe": u.name,
                "n_symbols": len(u),
                "final_nav_100k": u_metrics["final_nav_100k"],
                "cagr_pct": u_metrics["cagr"] * 100,
                "sharpe": u_metrics["sharpe"],
                "max_dd_pct": u_metrics["max_dd"] * 100,
                "vol_ann_pct": u_metrics["vol_ann"] * 100,
            })
        except Exception as e:  # noqa: BLE001
            print(f"  {u.name}: FAILED {type(e).__name__}: {e}")
            universe_rows.append({"universe": u.name, "error": str(e)})
    pd.DataFrame(universe_rows).to_csv(ARTIFACTS / "universe_comparison.csv", index=False)

    print("\n[5/5] 绘图 + 保存 ...")
    plot_equity(
        {"V2-S1 crypto basket eq": nav_perf, "BTC/USDT BH": nav_bh, "ETH/USDT BH": nav_eth},
        ARTIFACTS / "equity_curve.png",
    )
    plot_drawdown(
        {"V2-S1": nav_perf, "BTC BH": nav_bh, "ETH BH": nav_eth},
        ARTIFACTS / "drawdown.png",
    )
    plot_weight_evolution(result.target_weights, ARTIFACTS / "weight_evolution.png")
    plot_yearly(metrics_v2s1, metrics_bh, ARTIFACTS / "yearly_returns.png")

    yearly_df = pd.DataFrame({
        "year": sorted(metrics_v2s1["yearly"].keys()),
        "v2s1_pct": [metrics_v2s1["yearly"].get(y, 0) * 100
                     for y in sorted(metrics_v2s1["yearly"].keys())],
        "btc_bh_pct": [metrics_bh["yearly"].get(y, 0) * 100
                       for y in sorted(metrics_v2s1["yearly"].keys())],
        "eth_bh_pct": [metrics_eth["yearly"].get(y, 0) * 100
                       for y in sorted(metrics_v2s1["yearly"].keys())],
    })
    yearly_df.to_csv(ARTIFACTS / "yearly_returns.csv", index=False)

    summary = {
        "config": {
            "since": SINCE_PERF, "until": UNTIL,
            "init_cash_usdt": INIT_CASH,
            "fees_bp": FEES * 1e4, "slippage_bp": SLIPPAGE * 1e4,
            "trading_days_per_year": TDPY,
            "rebalance_period": 20,
            "universe": "CRYPTO_TOP_5",
            "symbols": list(CRYPTO_TOP_5.symbols),
        },
        "v2_s1": metrics_v2s1,
        "btc_bh": metrics_bh,
        "eth_bh": metrics_eth,
        "alpha_vs_btc_bh_pct_per_yr": (metrics_v2s1["cagr"] - metrics_bh["cagr"]) * 100,
        "universe_ablation": universe_rows,
    }
    with open(ARTIFACTS / "real_backtest_summary.json", "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
    print(f"  saved 4 plots + 2 csv + 1 json to {ARTIFACTS}")

    print("\n" + "=" * 70)
    print("Yearly returns:")
    print(yearly_df.to_string(index=False))
    print("\n" + "=" * 70)
    print(f"V2-S1 vs BTC BH alpha = {(metrics_v2s1['cagr'] - metrics_bh['cagr']) * 100:+.2f}%/yr")
    print(f"V2-S1 vs ETH BH alpha = {(metrics_v2s1['cagr'] - metrics_eth['cagr']) * 100:+.2f}%/yr")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
