"""Strategy 2 V2 validation script.

入口：

1. ``smoke()`` — 合成 OHLCV 跑通 DCA 三态 / vol-adaptive band / cooldown / NAV 恒等。
2. ``backtest_real(since, until)`` — 真实数据回测，产出 v2 vs v1 vs 510300 BH 对比。
3. CLI 包装。

运行：
    python summaries/S2_cn_etf_dca_swing/v2/validate.py smoke
    python summaries/S2_cn_etf_dca_swing/v2/validate.py real --since 2020-01-01 --until 2024-12-31
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# 注意新目录结构：v2/validate.py → parents[3] 才是 repo root
ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _load_v2_module():
    import importlib.util

    target = SRC / "strategy_lib" / "strategies" / "cn_etf_dca_swing_v2.py"
    spec = importlib.util.spec_from_file_location("_dca_swing_v2_module", target)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 {target}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_v1_module():
    import importlib.util

    target = SRC / "strategy_lib" / "strategies" / "cn_etf_dca_swing.py"
    spec = importlib.util.spec_from_file_location("_dca_swing_v1_module", target)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 {target}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


try:
    from strategy_lib.strategies.cn_etf_dca_swing_v2 import (  # noqa: E402
        DCASwingV2Strategy,
        DEFAULT_CASH_SYMBOL,
        DEFAULT_RISK_SYMBOLS,
    )
except ModuleNotFoundError:
    _mod = _load_v2_module()
    DCASwingV2Strategy = _mod.DCASwingV2Strategy
    DEFAULT_CASH_SYMBOL = _mod.DEFAULT_CASH_SYMBOL
    DEFAULT_RISK_SYMBOLS = _mod.DEFAULT_RISK_SYMBOLS

try:
    from strategy_lib.strategies.cn_etf_dca_swing import DCASwingStrategy  # noqa: E402
except ModuleNotFoundError:
    _v1mod = _load_v1_module()
    DCASwingStrategy = _v1mod.DCASwingStrategy


# ---------------------------------------------------------------------------
# 合成数据（与 v1 同 generator，便于结构对齐）
# ---------------------------------------------------------------------------


def make_synthetic_panel(
    *,
    start: str = "2020-01-02",
    n_days: int = 252 * 2,
    seed: int = 42,
) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start=start, periods=n_days, freq="B", name="timestamp")

    panel: dict[str, pd.DataFrame] = {}

    cash_close = 1.0 * np.exp(np.arange(n_days) * (np.log(1.02) / 252))
    cash_df = pd.DataFrame(
        {
            "open": cash_close,
            "high": cash_close * 1.0001,
            "low": cash_close * 0.9999,
            "close": cash_close,
            "volume": np.full(n_days, 1e8),
        },
        index=idx,
    )
    panel[DEFAULT_CASH_SYMBOL] = cash_df

    drifts = np.array([0.10, 0.05, 0.15, -0.02, 0.08, 0.03])
    vols = np.array([0.20, 0.22, 0.30, 0.28, 0.25, 0.18])
    base_price = 100.0

    for s, mu, sigma in zip(DEFAULT_RISK_SYMBOLS, drifts, vols, strict=True):
        daily_mu = mu / 252
        daily_sigma = sigma / np.sqrt(252)
        rets = rng.normal(daily_mu, daily_sigma, size=n_days)
        close = base_price * np.exp(np.cumsum(rets))
        open_ = close * (1 + rng.normal(0, 0.002, size=n_days))
        high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.005, size=n_days)))
        low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.005, size=n_days)))
        vol = rng.uniform(1e6, 5e6, size=n_days)
        panel[s] = pd.DataFrame(
            {"open": open_, "high": high, "low": low, "close": close, "volume": vol},
            index=idx,
        )

    return panel


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------


def smoke() -> dict:
    panel = make_synthetic_panel()
    strat = DCASwingV2Strategy(
        initial_cash=100_000.0,
        monthly_dca_amount=5_000.0,
        adjust_ratio=0.50,
        cooldown_days=5,
    )
    result = strat.simulate(panel)

    n_months = result.holdings.index.to_period("M").nunique()
    n_dca_buys = result.diagnostics["n_dca_buy_orders"]
    expected_per_month = len(strat.risk_symbols)
    # NORMAL 和 BOOST 都会产生 6 笔 dca_buy；OFF 产生 0 笔
    n_modes_active = (
        result.diagnostics["n_dca_normal"] + result.diagnostics["n_dca_boost"]
    )
    expected_buys = n_modes_active * expected_per_month
    assert n_dca_buys == expected_buys, (
        f"DCA 买入笔数 {n_dca_buys} 与活跃模式数 {n_modes_active}×6={expected_buys} 不匹配"
    )

    # NAV 恒等
    last_holdings = result.holdings.iloc[-1]
    last_close = pd.DataFrame({s: panel[s]["close"] for s in panel}).iloc[-1]
    recompute_nav = float((last_holdings * last_close).sum())
    assert abs(recompute_nav - result.nav.iloc[-1]) / result.nav.iloc[-1] < 1e-9, (
        f"NAV 重算不一致: {recompute_nav} vs {result.nav.iloc[-1]}"
    )

    # cooldown 检查
    swing_orders = result.orders[
        result.orders["kind"].isin(["swing_buy", "swing_sell"])
    ].copy()
    if not swing_orders.empty:
        swing_orders["date"] = pd.to_datetime(swing_orders["date"])
        for s, grp in swing_orders.groupby("symbol"):
            dates = grp["date"].sort_values().reset_index(drop=True)
            gaps = dates.diff().dt.days.dropna()
            if len(gaps):
                assert gaps.min() >= 5, f"cooldown 失效 {s}: min gap = {gaps.min()}"

    # 起始全在货基
    first_w = result.weights.iloc[0]
    assert first_w[DEFAULT_CASH_SYMBOL] > 0.99, (
        f"初始未把 init_cash 全部买入货基: {first_w[DEFAULT_CASH_SYMBOL]}"
    )

    # band 范围检查
    band = result.band_t.iloc[strat.vol_lookback:]
    if len(band) > 0:
        assert band.min() >= strat.vol_band_min - 1e-9, (
            f"band_t 下穿 min: {band.min()} < {strat.vol_band_min}"
        )
        assert band.max() <= strat.vol_band_max + 1e-9, (
            f"band_t 上穿 max: {band.max()} > {strat.vol_band_max}"
        )

    # DCA 三态非全部为 0（除非 risk_target 在 5 年内一直被 v1 模型死保住——不可能）
    total_dca_decisions = (
        result.diagnostics["n_dca_normal"]
        + result.diagnostics["n_dca_off"]
        + result.diagnostics["n_dca_boost"]
    )
    assert total_dca_decisions >= n_months - 2, (
        f"DCA 决策次数 {total_dca_decisions} 少于月数 {n_months}-2"
    )

    summary = {
        "n_days": int(result.diagnostics.get("n_days", len(result.nav))),
        "n_months": int(n_months),
        "n_dca_buy_orders": int(n_dca_buys),
        "n_dca_normal": result.diagnostics["n_dca_normal"],
        "n_dca_off": result.diagnostics["n_dca_off"],
        "n_dca_boost": result.diagnostics["n_dca_boost"],
        "n_swing_buy": result.diagnostics["n_swing_buy"],
        "n_swing_sell": result.diagnostics["n_swing_sell"],
        "init_cash": strat.initial_cash,
        "final_nav": float(result.nav.iloc[-1]),
        "final_risk_weight": float(result.diagnostics["final_risk_weight"]),
        "final_cash_weight": float(result.diagnostics["final_cash_weight"]),
        "band_mean": result.diagnostics["band_mean"],
        "band_min": result.diagnostics["band_min"],
        "band_max": result.diagnostics["band_max"],
        "metrics": result.metrics,
    }
    return summary


# ---------------------------------------------------------------------------
# 真实数据
# ---------------------------------------------------------------------------


def _load_panel(since: str, until: str, symbols: tuple[str, ...]) -> dict[str, pd.DataFrame]:
    from strategy_lib.data import get_loader

    loader = get_loader("cn_etf")
    panel: dict[str, pd.DataFrame] = {}
    for s in symbols:
        df = loader.load(symbol=s, timeframe="1d", since=since, until=until)
        if df.index.tz is not None:
            df = df.tz_convert("UTC").tz_localize(None)
        panel[s] = df
    return panel


def _benchmark_510300(panel: dict[str, pd.DataFrame], init_cash: float, fees: float,
                      slippage: float, index: pd.DatetimeIndex) -> pd.Series:
    bm = panel["510300"].reindex(index)
    first_open = float(bm["open"].iloc[0])
    buy_price = first_open * (1 + slippage)
    cash_after_fee = init_cash * (1 - fees)
    shares = cash_after_fee / buy_price
    nav = shares * bm["close"]
    nav.name = "bh_510300"
    return nav


def _annual_returns(nav: pd.Series) -> pd.Series:
    yearly = nav.groupby(nav.index.year).agg(["first", "last"])
    return (yearly["last"] / yearly["first"] - 1).rename("annual_return")


def _max_drawdown_series(nav: pd.Series) -> pd.Series:
    return nav / nav.cummax() - 1


def _turnover_annual(orders: pd.DataFrame, nav: pd.Series) -> float:
    if orders.empty:
        return 0.0
    df = orders[orders["kind"] != "init_buy"].copy()
    df["notional"] = (df["size"].abs() * df["price"]).astype(float)
    total = float(df["notional"].sum())
    avg_nav = float(nav.mean())
    n_years = max((nav.index[-1] - nav.index[0]).days / 365.25, 1e-9)
    if avg_nav <= 0:
        return 0.0
    return total / avg_nav / n_years


def _info_ratio(strategy_nav: pd.Series, bm_nav: pd.Series) -> tuple[float, float, float]:
    s = strategy_nav.pct_change().dropna()
    b = bm_nav.pct_change().reindex(s.index).fillna(0.0)
    excess = s - b
    if excess.std(ddof=0) == 0:
        return 0.0, float("nan"), 0.0
    te = float(excess.std(ddof=0) * np.sqrt(252))
    alpha = float(excess.mean() * 252)
    ir = alpha / te if te > 0 else float("nan")
    return alpha, ir, te


# ---------------------------------------------------------------------------
# Plotting — v2 vs v1 vs BH
# ---------------------------------------------------------------------------


def _plot_artifacts(
    v2_result,
    v1_result,
    bm_nav: pd.Series,
    strat_v2: DCASwingV2Strategy,
    out_dir: Path,
) -> None:
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)

    nav_v2 = v2_result.nav
    nav_v1 = v1_result.nav

    # 1) equity curve
    fig, ax = plt.subplots(figsize=(11, 5))
    (nav_v2 / nav_v2.iloc[0]).plot(ax=ax, label="S2 v2 (DCA-priority + vol-adapt)",
                                    color="#2ca02c", lw=1.7)
    (nav_v1 / nav_v1.iloc[0]).plot(ax=ax, label="S2 v1 (baseline)",
                                    color="#1f77b4", lw=1.4, alpha=0.85)
    (bm_nav / bm_nav.iloc[0]).plot(ax=ax, label="510300 BH",
                                    color="#d62728", lw=1.2, alpha=0.85)
    ax.axhline(1.0, color="gray", lw=0.6, ls=":")
    ax.set_title("Equity curve — S2 v2 vs v1 vs 510300 BH (normalized to 1.0)")
    ax.set_ylabel("Normalized NAV")
    ax.legend(loc="upper left")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "equity_curve.png", dpi=140)
    plt.close(fig)

    # 2) drawdown
    fig, ax = plt.subplots(figsize=(11, 4.5))
    dd_v2 = _max_drawdown_series(nav_v2)
    dd_v1 = _max_drawdown_series(nav_v1)
    dd_bh = _max_drawdown_series(bm_nav)
    ax.fill_between(dd_v2.index, dd_v2.values, 0, color="#2ca02c", alpha=0.40, label="S2 v2")
    ax.plot(dd_v1.index, dd_v1.values, color="#1f77b4", lw=1.0, alpha=0.9, label="S2 v1")
    ax.plot(dd_bh.index, dd_bh.values, color="#d62728", lw=1.0, alpha=0.85, label="510300 BH")
    ax.set_title("Drawdown — S2 v2 vs v1 vs 510300 BH")
    ax.set_ylabel("Drawdown")
    ax.legend(loc="lower left")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "drawdown.png", dpi=140)
    plt.close(fig)

    # 3) swing events on risk-pool weight (v2)
    weights = v2_result.weights
    orders = v2_result.orders
    risk_w = weights[list(strat_v2.risk_symbols)].sum(axis=1)
    fig, ax = plt.subplots(figsize=(11, 5))
    risk_w.plot(ax=ax, color="#2ca02c", lw=1.2, label="Risk-pool weight (sum)")
    target = strat_v2.risk_target_weight
    ax.axhline(target, color="black", lw=0.8, ls="--", label=f"target {target:.0%}")
    ax.axhline(target * (1 + strat_v2.dca_band_high), color="#ff7f0e", lw=0.6, ls=":",
               label=f"DCA OFF threshold {target*(1+strat_v2.dca_band_high):.0%}")
    ax.axhline(target * (1 - strat_v2.dca_band_low), color="#1f77b4", lw=0.6, ls=":",
               label=f"DCA BOOST threshold {target*(1-strat_v2.dca_band_low):.0%}")
    if not orders.empty:
        sells = orders[orders["kind"] == "swing_sell"]
        buys = orders[orders["kind"] == "swing_buy"]
        if not sells.empty:
            d = pd.to_datetime(sells["date"]).values
            yvals = risk_w.reindex(d).values
            ax.scatter(d, yvals, s=22, marker="v", color="#d62728",
                       label=f"high-sell ({len(sells)})", zorder=5)
        if not buys.empty:
            d = pd.to_datetime(buys["date"]).values
            yvals = risk_w.reindex(d).values
            ax.scatter(d, yvals, s=22, marker="^", color="#2ca02c",
                       label=f"low-buy ({len(buys)})", zorder=5)
    ax.set_title("Swing events — V2 (risk-pool weight + DCA OFF/BOOST thresholds)")
    ax.set_ylabel("Risk weight")
    ax.legend(loc="best", fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "swing_events.png", dpi=140)
    plt.close(fig)

    # 4) risk weight band — V2 actual + dynamic band_t
    fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True,
                             gridspec_kw={"height_ratios": [3, 1]})
    ax = axes[0]
    # 用 per-symbol band 区间需要每只 ETF 单独画——这里画风险池总权重 + DCA 三态阈值
    ax.fill_between(
        risk_w.index,
        target * (1 - strat_v2.dca_band_low),
        target * (1 + strat_v2.dca_band_high),
        color="#2ca02c", alpha=0.13,
        label=f"DCA neutral zone (±{strat_v2.dca_band_high:.0%})",
    )
    risk_w.plot(ax=ax, color="#2ca02c", lw=1.2, label="V2 actual risk weight")
    ax.axhline(target, color="black", lw=0.8, ls="--", label=f"target {target:.0%}")
    ax.set_title("V2 risk-asset weight trajectory + DCA neutral zone")
    ax.set_ylabel("Weight")
    ax.legend(loc="best", fontsize=9)
    ax.grid(alpha=0.3)

    # 下半幅：band_t 动态阈值
    ax2 = axes[1]
    band_t = v2_result.band_t
    band_t.plot(ax=ax2, color="#9467bd", lw=1.0, label="band_t (vol-adaptive)")
    ax2.axhline(strat_v2.vol_band_min, color="gray", lw=0.5, ls=":")
    ax2.axhline(strat_v2.vol_band_max, color="gray", lw=0.5, ls=":")
    ax2.set_title("Vol-adaptive swing band_t over time")
    ax2.set_ylabel("band_t")
    ax2.legend(loc="best", fontsize=9)
    ax2.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "risk_weight_band.png", dpi=140)
    plt.close(fig)


# ---------------------------------------------------------------------------
# 真实回测主入口
# ---------------------------------------------------------------------------


def backtest_real(since: str, until: str) -> dict:
    strat_v2 = DCASwingV2Strategy()  # 默认参数即 v2 配置
    strat_v1 = DCASwingStrategy()    # 默认参数即 v1 baseline

    panel = _load_panel(since, until, strat_v2.all_symbols)
    result_v2 = strat_v2.run(panel)
    result_v1 = strat_v1.run(panel)

    nav_v2 = result_v2.nav
    nav_v1 = result_v1.nav
    bm_nav = _benchmark_510300(panel, strat_v2.initial_cash, strat_v2.fees,
                               strat_v2.slippage, nav_v2.index)

    # v2 metrics
    metrics_v2 = result_v2.metrics
    metrics_v1 = result_v1.metrics
    metrics_bh = DCASwingV2Strategy._compute_metrics(bm_nav)

    alpha_v2, ir_v2, te_v2 = _info_ratio(nav_v2, bm_nav)
    alpha_v1, ir_v1, te_v1 = _info_ratio(nav_v1, bm_nav)

    excess_v2 = float(nav_v2.iloc[-1] / nav_v2.iloc[0] - bm_nav.iloc[-1] / bm_nav.iloc[0])
    excess_v1 = float(nav_v1.iloc[-1] / nav_v1.iloc[0] - bm_nav.iloc[-1] / bm_nav.iloc[0])

    turnover_v2 = _turnover_annual(result_v2.orders, nav_v2)
    turnover_v1 = _turnover_annual(result_v1.orders, nav_v1)

    yearly_v2 = _annual_returns(nav_v2)
    yearly_v1 = _annual_returns(nav_v1)
    yearly_bh = _annual_returns(bm_nav)

    # swing 事件统计
    o_v2 = result_v2.orders
    n_buy_v2 = int((o_v2["kind"] == "swing_buy").sum())
    n_sell_v2 = int((o_v2["kind"] == "swing_sell").sum())
    o_v1 = result_v1.orders
    n_buy_v1 = int((o_v1["kind"] == "swing_buy").sum())
    n_sell_v1 = int((o_v1["kind"] == "swing_sell").sum())

    # 出图
    out_dir = Path(__file__).resolve().parent / "artifacts"
    _plot_artifacts(result_v2, result_v1, bm_nav, strat_v2, out_dir)

    # dump csv
    nav_df = pd.DataFrame({"v2": nav_v2, "v1": nav_v1, "bh_510300": bm_nav})
    nav_df.to_csv(out_dir / "nav_series.csv")
    result_v2.orders.to_csv(out_dir / "orders.csv", index=False)
    result_v2.weights.to_csv(out_dir / "weights.csv")
    if result_v2.band_t is not None:
        result_v2.band_t.to_csv(out_dir / "band_t.csv")
    if result_v2.dca_modes is not None:
        result_v2.dca_modes.to_csv(out_dir / "dca_modes.csv", index=False)

    summary = {
        "since": since,
        "until": until,
        "n_days": int(len(nav_v2)),
        "init_cash": strat_v2.initial_cash,
        "v2": {
            "final_nav": float(nav_v2.iloc[-1]),
            "metrics": metrics_v2,
            "alpha_annual": alpha_v2,
            "info_ratio": ir_v2,
            "tracking_error_annual": te_v2,
            "excess_total": excess_v2,
            "turnover_annual": turnover_v2,
            "annual_returns": {int(y): float(v) for y, v in yearly_v2.items()},
            "swing": {
                "n_swing_buy": n_buy_v2,
                "n_swing_sell": n_sell_v2,
                "buy_sell_ratio": (n_sell_v2 / n_buy_v2) if n_buy_v2 > 0 else float("inf"),
            },
            "diagnostics": result_v2.diagnostics,
        },
        "v1": {
            "final_nav": float(nav_v1.iloc[-1]),
            "metrics": metrics_v1,
            "alpha_annual": alpha_v1,
            "info_ratio": ir_v1,
            "tracking_error_annual": te_v1,
            "excess_total": excess_v1,
            "turnover_annual": turnover_v1,
            "annual_returns": {int(y): float(v) for y, v in yearly_v1.items()},
            "swing": {
                "n_swing_buy": n_buy_v1,
                "n_swing_sell": n_sell_v1,
                "buy_sell_ratio": (n_sell_v1 / n_buy_v1) if n_buy_v1 > 0 else float("inf"),
            },
        },
        "bh": {
            "final_nav": float(bm_nav.iloc[-1]),
            "metrics": metrics_bh,
            "annual_returns": {int(y): float(v) for y, v in yearly_bh.items()},
        },
    }

    with open(out_dir / "real_backtest_summary.json", "w") as fh:
        json.dump(summary, fh, indent=2, default=str)
    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _main() -> int:
    parser = argparse.ArgumentParser(description="Strategy 2 V2 validate")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("smoke", help="合成数据 smoke test")
    real = sub.add_parser("real", help="真实数据回测（v2 vs v1 vs BH）")
    real.add_argument("--since", default="2020-01-01")
    real.add_argument("--until", default="2024-12-31")
    args = parser.parse_args()

    if args.cmd == "smoke":
        out = smoke()
        print("=== V2 smoke test passed ===")
        for k, v in out.items():
            if k == "metrics":
                print("  metrics:")
                for mk, mv in v.items():
                    print(f"    {mk}: {mv}")
            else:
                print(f"  {k}: {v}")
        return 0

    if args.cmd == "real":
        out = backtest_real(args.since, args.until)
        print("=== V2 real backtest done ===")
        print(f"  window: {out['since']} -> {out['until']}, n_days={out['n_days']}")
        print(f"  init_cash: {out['init_cash']:,.0f}")
        v2 = out["v2"]
        v1 = out["v1"]
        bh = out["bh"]
        print("  --- V2 ---")
        print(f"    final NAV: {v2['final_nav']:,.2f}")
        print(f"    CAGR: {v2['metrics']['annual_return']:+.4f}")
        print(f"    Sharpe: {v2['metrics']['sharpe']:.4f}")
        print(f"    MaxDD: {v2['metrics']['max_drawdown']:.4f}")
        print(f"    alpha (annual): {v2['alpha_annual']:+.4f}, IR: {v2['info_ratio']:.3f}")
        print(f"    turnover (annual): {v2['turnover_annual']:.4f}")
        print(f"    swing buy/sell: {v2['swing']['n_swing_buy']} / {v2['swing']['n_swing_sell']} (ratio={v2['swing']['buy_sell_ratio']:.2f}:1)")
        d = v2["diagnostics"]
        print(f"    DCA NORMAL/OFF/BOOST: {d['n_dca_normal']} / {d['n_dca_off']} / {d['n_dca_boost']}")
        print(f"    band_t mean/min/max: {d['band_mean']:.4f} / {d['band_min']:.4f} / {d['band_max']:.4f}")
        print("  --- V1 ---")
        print(f"    final NAV: {v1['final_nav']:,.2f}")
        print(f"    CAGR: {v1['metrics']['annual_return']:+.4f}")
        print(f"    Sharpe: {v1['metrics']['sharpe']:.4f}")
        print(f"    MaxDD: {v1['metrics']['max_drawdown']:.4f}")
        print(f"    swing buy/sell: {v1['swing']['n_swing_buy']} / {v1['swing']['n_swing_sell']} (ratio={v1['swing']['buy_sell_ratio']:.2f}:1)")
        print("  --- BH 510300 ---")
        print(f"    final NAV: {bh['final_nav']:,.2f}")
        print(f"    CAGR: {bh['metrics']['annual_return']:+.4f}")
        print("  Annual breakdown (V2 / V1 / BH):")
        for y in sorted(v2["annual_returns"]):
            v2y = v2["annual_returns"][y]
            v1y = v1["annual_returns"].get(y, float("nan"))
            bhy = bh["annual_returns"].get(y, float("nan"))
            print(f"    {y}: v2={v2y:+.4f}  v1={v1y:+.4f}  bh={bhy:+.4f}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(_main())
