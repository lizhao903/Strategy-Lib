"""Validate S7 v2 — lag=1 + 11 跨资产池.

跑法：
    cd /Volumes/ai/github/Strategy-Lib && source .venv/bin/activate
    python summaries/S7_cn_etf_market_ma_filter/v2/validate.py

产物（保存到本目录的 artifacts/）:
    - real_backtest_summary.json: 主结果 + 所有 ablation
    - equity_curve.png: v2 vs v1 lag=1 6池 vs S5v2 vs S4v2 vs S3 vs BH
    - drawdown.png: 同上
    - signal_overlay.png: 510300 + MA200 + ON/OFF 色块（与 v1 同）
    - ablation.csv: 4 档对照（v2, v1 lag=1 6池, v2 lag=2 11池, v1 lag=2 6池）
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

from strategy_lib.data import get_loader  # noqa: E402
from strategy_lib.strategies.cn_etf_market_ma_filter import MarketMAFilterStrategy  # noqa: E402
from strategy_lib.strategies.cn_etf_market_ma_filter_v2 import (  # noqa: E402
    MarketMAFilterV2Strategy,
    RISKY_POOL_11,
)
from strategy_lib.strategies.cn_etf_equal_rebalance import EqualRebalanceStrategy  # noqa: E402

POOL_6 = ("510300", "510500", "159915", "512100", "512880", "512170")
SINCE = "2019-07-01"  # 含 200MA 暖机
SINCE_PERF = "2020-01-02"  # 绩效统计起点
UNTIL = "2024-12-31"


def load_panel(symbols: list[str]) -> dict[str, pd.DataFrame]:
    """加载 panel，含 cash 与 signal 资产。"""
    loader = get_loader("cn_etf")
    needed = set(symbols) | {"511990", "510300"}
    panel = loader.load_many(sorted(needed), since=SINCE, until=UNTIL)
    return panel


def calc_metrics(nav: pd.Series, label: str = "") -> dict:
    """从 NAV 序列计算关键指标。"""
    nav = nav.dropna()
    daily_ret = nav.pct_change().dropna()
    n_years = len(nav) / 252
    cagr = (nav.iloc[-1] / nav.iloc[0]) ** (1 / n_years) - 1
    vol = daily_ret.std() * np.sqrt(252)
    sharpe = daily_ret.mean() / daily_ret.std() * np.sqrt(252) if daily_ret.std() > 0 else 0.0
    cummax = nav.cummax()
    max_dd = (nav / cummax - 1).min()
    # 分年度
    yearly = (
        nav.groupby(nav.index.year)
        .apply(lambda s: s.iloc[-1] / s.iloc[0] - 1 if len(s) > 1 else 0)
        .to_dict()
    )
    return {
        "label": label,
        "final_nav_100k": float(nav.iloc[-1] * 100000),
        "cagr": float(cagr),
        "vol_ann": float(vol),
        "sharpe": float(sharpe),
        "max_dd": float(max_dd),
        "yearly": {int(k): float(v) for k, v in yearly.items()},
    }


def run_strategy(strategy, panel, init_cash=100_000, trim_to_perf=True) -> pd.Series:
    """跑一个策略，返回 NAV 序列（归一化到起点 = 1）。"""
    result = strategy.run(panel, init_cash=init_cash)
    pf = result.portfolio
    nav = pf.value() if callable(getattr(pf, "value", None)) else pf.value
    if hasattr(nav, "to_series"):
        nav = nav.to_series() if callable(nav.to_series) else nav
    nav = pd.Series(nav.values if hasattr(nav, "values") else nav, index=pf.wrapper.index)
    if trim_to_perf:
        nav = nav[nav.index >= pd.Timestamp(SINCE_PERF, tz=nav.index.tz)]
    return nav / nav.iloc[0]


def run_bh_510300(panel) -> pd.Series:
    """Buy-and-hold 510300，同窗口同费率。"""
    close = panel["510300"]["close"]
    close = close[close.index >= pd.Timestamp(SINCE_PERF, tz=close.index.tz)]
    close = close[close.index <= pd.Timestamp(UNTIL, tz=close.index.tz)]
    return close / close.iloc[0]


def run_main_v2(panel) -> tuple[pd.Series, dict, MarketMAFilterV2Strategy, object]:
    """跑 v2 主配置：lag=1 + 11 池。"""
    strat = MarketMAFilterV2Strategy(symbols=list(RISKY_POOL_11))
    result = strat.run(panel, init_cash=100_000)
    pf = result.portfolio
    nav_full = pd.Series(pf.value().values, index=pf.wrapper.index)
    nav = nav_full[nav_full.index >= pd.Timestamp(SINCE_PERF, tz=nav_full.index.tz)] / 100_000
    metrics = calc_metrics(nav, "S7v2 lag=1 11池")
    # 切换次数
    sig = result.signal
    metrics["switches"] = int((sig.diff().abs() > 0.5).sum())
    metrics["on_ratio"] = float(sig.mean())
    return nav, metrics, strat, result


def run_ablations(panel) -> pd.DataFrame:
    """4 档 ablation：v2 (lag=1, 11池) / v1 lag=1 (6池) / lag=2 11池 / v1 lag=2 6池."""
    cases = [
        ("v2 lag=1 11池", MarketMAFilterV2Strategy(symbols=list(RISKY_POOL_11))),
        ("v1 lag=1 6池", MarketMAFilterStrategy(symbols=list(POOL_6), lag_days=1)),
        ("lag=2 11池", MarketMAFilterStrategy(symbols=list(RISKY_POOL_11), lag_days=2)),
        ("v1 lag=2 6池 (默认)", MarketMAFilterStrategy(symbols=list(POOL_6), lag_days=2)),
    ]
    rows = []
    for label, strat in cases:
        nav = run_strategy(strat, panel)
        m = calc_metrics(nav, label)
        m["yr_2022"] = m["yearly"].get(2022, np.nan)
        m["yr_2024"] = m["yearly"].get(2024, np.nan)
        rows.append(m)
    return pd.DataFrame(rows)


def run_baselines(panel) -> dict[str, pd.Series]:
    """跑横向对照：S3 / S4v2 / BH。"""
    out: dict[str, pd.Series] = {}
    # BH 510300
    out["BH 510300"] = run_bh_510300(panel)
    # S3 v1 6 池
    s3 = EqualRebalanceStrategy(symbols=list(POOL_6), rebalance_period=20)
    out["S3 v1 6池"] = run_strategy(s3, panel)
    # S3 with 11 pool（隐含 v3 候选 baseline）
    s3_11 = EqualRebalanceStrategy(symbols=list(RISKY_POOL_11), rebalance_period=20)
    out["S3 11池 (S4v2 隐含)"] = run_strategy(s3_11, panel)
    return out


def plot_equity(navs: dict[str, pd.Series], path: Path) -> None:
    fig, ax = plt.subplots(figsize=(13, 6))
    colors = {
        "S7 v2 lag=1 11池": ("#d62728", 2.5, "-"),
        "BH 510300": ("#7f7f7f", 1.2, "--"),
        "S3 v1 6池": ("#2ca02c", 1.2, "-"),
        "S3 11池 (S4v2 隐含)": ("#1f77b4", 1.5, "-"),
        "S7 v1 lag=2 6池": ("#ff7f0e", 1.2, ":"),
    }
    for k, s in navs.items():
        c, lw, ls = colors.get(k, ("#888", 1.0, "-"))
        ax.plot(s.index, s.values, label=k, color=c, lw=lw, linestyle=ls)
    ax.set_title("S7 v2: 大盘 MA 过滤 (lag=1 + 11 池) — 净值对比")
    ax.set_ylabel("Normalized NAV (start=1)")
    ax.set_yscale("log")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def plot_drawdown(navs: dict[str, pd.Series], path: Path) -> None:
    fig, ax = plt.subplots(figsize=(13, 5))
    for k, s in navs.items():
        dd = s / s.cummax() - 1
        ax.plot(s.index, dd.values, label=k, lw=1.2)
    ax.axhline(0, color="black", lw=0.5)
    ax.set_title("回撤对比")
    ax.set_ylabel("Drawdown")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    # 高亮 2022 段
    ax.axvspan(pd.Timestamp("2022-01-01", tz=s.index.tz),
               pd.Timestamp("2022-12-31", tz=s.index.tz),
               alpha=0.10, color="red", label="2022")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def plot_signal_overlay(panel: dict[str, pd.DataFrame], result, path: Path) -> None:
    # 先在共同 index 上对齐三个序列
    close_full = panel["510300"]["close"]
    ma200_full = close_full.rolling(200).mean()
    sig_full = result.signal
    cutoff = pd.Timestamp(SINCE_PERF, tz=close_full.index.tz)
    common = close_full.index.intersection(sig_full.index)
    common = common[common >= cutoff]
    close = close_full.loc[common]
    ma200 = ma200_full.loc[common]
    sig = sig_full.loc[common]

    fig, ax = plt.subplots(figsize=(13, 5))
    ax.plot(close.index, close.values, color="black", lw=0.8, label="510300 close")
    ax.plot(ma200.index, ma200.values, color="orange", lw=1.5, label="MA200")
    on_mask = sig.values == 1
    ax.fill_between(close.index, close.min(), close.max(), where=on_mask,
                    alpha=0.10, color="green", label="ON")
    ax.fill_between(close.index, close.min(), close.max(), where=~on_mask,
                    alpha=0.10, color="red", label="OFF")
    ax.set_title("510300 + MA200 + ON/OFF 信号 (S7 v2, lag=1)")
    ax.legend(loc="best", fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def main() -> int:
    print("=" * 70)
    print("S7 v2 真实数据回测：lag=1 + 11 跨资产池")
    print("=" * 70)

    print("\n[1/5] 加载 panel ...")
    panel = load_panel(list(RISKY_POOL_11))
    print(f"  loaded {len(panel)} symbols, range {panel['510300'].index.min()} ~ {panel['510300'].index.max()}")

    print("\n[2/5] 跑 v2 主配置 ...")
    nav_v2, m_v2, strat_v2, result_v2 = run_main_v2(panel)
    print(f"  v2: NAV {m_v2['final_nav_100k']/1000:.1f}k / CAGR {m_v2['cagr']*100:+.2f}% / "
          f"Sharpe {m_v2['sharpe']:.3f} / MaxDD {m_v2['max_dd']*100:.1f}% / "
          f"切换 {m_v2['switches']} / ON占比 {m_v2['on_ratio']*100:.1f}%")

    print("\n[3/5] 跑 ablation 4 档 ...")
    abl = run_ablations(panel)
    abl_simple = abl[["label", "final_nav_100k", "cagr", "sharpe", "max_dd",
                      "yr_2022", "yr_2024"]].copy()
    abl_simple["final_nav_100k"] = abl_simple["final_nav_100k"].round(0)
    abl_simple["cagr"] = (abl_simple["cagr"] * 100).round(2)
    abl_simple["sharpe"] = abl_simple["sharpe"].round(3)
    abl_simple["max_dd"] = (abl_simple["max_dd"] * 100).round(1)
    abl_simple["yr_2022"] = (abl_simple["yr_2022"] * 100).round(2)
    abl_simple["yr_2024"] = (abl_simple["yr_2024"] * 100).round(2)
    print(abl_simple.to_string(index=False))
    abl.to_csv(ARTIFACTS / "ablation.csv", index=False)

    print("\n[4/5] 跑横向对比 baselines ...")
    base_navs = run_baselines(panel)
    for k, s in base_navs.items():
        m = calc_metrics(s, k)
        print(f"  {k}: NAV {m['final_nav_100k']/1000:.1f}k / CAGR {m['cagr']*100:+.2f}% / "
              f"Sharpe {m['sharpe']:.3f} / MaxDD {m['max_dd']*100:.1f}%")

    print("\n[5/5] 绘图 ...")
    all_navs = {"S7 v2 lag=1 11池": nav_v2, **base_navs}
    # 加 v1 lag=2 6池 (默认) 作对比
    s7_v1_default = MarketMAFilterStrategy(symbols=list(POOL_6), lag_days=2)
    all_navs["S7 v1 lag=2 6池"] = run_strategy(s7_v1_default, panel)

    plot_equity(all_navs, ARTIFACTS / "equity_curve.png")
    plot_drawdown(all_navs, ARTIFACTS / "drawdown.png")
    plot_signal_overlay(panel, result_v2, ARTIFACTS / "signal_overlay.png")
    print(f"  saved 3 plots to {ARTIFACTS}")

    # JSON 摘要
    summary = {
        "v2_main": m_v2,
        "ablation": abl.to_dict(orient="records"),
        "baselines": {k: calc_metrics(s, k) for k, s in base_navs.items()},
        "config": {"lag_days": 1, "ma_length": 200, "pool_size": 11,
                   "since": SINCE_PERF, "until": UNTIL, "init_cash": 100_000},
    }
    with open(ARTIFACTS / "real_backtest_summary.json", "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 70)
    print("v2 vs v1 lag=2 6池 (S7 默认): "
          f"alpha = {(m_v2['cagr'] - 0.0164) * 100:+.2f}%/yr, "
          f"NAV diff = {m_v2['final_nav_100k']/1000 - 108.1:+.1f}k")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
