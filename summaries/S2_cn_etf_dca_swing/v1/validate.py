"""Strategy 2 validation script.

三个入口：

1. ``smoke()`` — 合成 OHLCV 数据跑 simulate，验证恒等式 / cooldown / DCA 频次。
2. ``backtest_real(since, until)`` — 真实数据回测，产出绩效 + 与 510300 BH 对比 +
   绘图保存到 ``artifacts/``。
3. ``main_real_with_plots`` — CLI 包装。

运行：
    python summaries/cn_etf_dca_swing/validate.py smoke
    python summaries/cn_etf_dca_swing/validate.py real --since 2020-01-01 --until 2024-12-31
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# 让脚本能 import strategy_lib（仓库根 / src 没装到 site-packages 的兜底）
ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _load_strategy_module():
    """直接加载 strategies/cn_etf_dca_swing.py，绕过 strategy_lib/__init__.py
    的重依赖（loguru / vectorbt / akshare 等）。这样 smoke test 不依赖这些库。
    """
    import importlib.util

    target = SRC / "strategy_lib" / "strategies" / "cn_etf_dca_swing.py"
    spec = importlib.util.spec_from_file_location(
        "_dca_swing_module", target
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 {target}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


try:
    from strategy_lib.strategies.cn_etf_dca_swing import (  # noqa: E402
        DEFAULT_CASH_SYMBOL,
        DEFAULT_RISK_SYMBOLS,
        DCASwingStrategy,
    )
except ModuleNotFoundError:
    # smoke test 不依赖完整 strategy_lib（loguru/vectorbt/akshare 可能没装）
    _mod = _load_strategy_module()
    DEFAULT_CASH_SYMBOL = _mod.DEFAULT_CASH_SYMBOL
    DEFAULT_RISK_SYMBOLS = _mod.DEFAULT_RISK_SYMBOLS
    DCASwingStrategy = _mod.DCASwingStrategy


# ---------------------------------------------------------------------------
# 合成数据
# ---------------------------------------------------------------------------


def make_synthetic_panel(
    *,
    start: str = "2020-01-02",
    n_days: int = 252 * 2,  # 2 年
    seed: int = 42,
) -> dict[str, pd.DataFrame]:
    """生成 1 货基 + 6 ETF 的合成 OHLCV，方便 smoke test。

    - 货基 511990：年化 2% 线性增长，几乎无波动
    - 风险 ETF：几何布朗运动，drift/vol 不同，制造权重偏离触发再平衡
    """
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start=start, periods=n_days, freq="B", name="timestamp")

    panel: dict[str, pd.DataFrame] = {}

    # 货基：年化 2%，日波动 ~0
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

    # 风险 ETF：drift 在 [-5%, 15%] 年化、vol 在 [15%, 35%] 年化
    drifts = np.array([0.10, 0.05, 0.15, -0.02, 0.08, 0.03])
    vols = np.array([0.20, 0.22, 0.30, 0.28, 0.25, 0.18])
    base_price = 100.0

    for s, mu, sigma in zip(DEFAULT_RISK_SYMBOLS, drifts, vols, strict=True):
        # 几何布朗
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
    """合成数据下的健全性检查。"""
    panel = make_synthetic_panel()
    strat = DCASwingStrategy(
        initial_cash=100_000.0,
        monthly_dca_amount=5_000.0,
        rel_band=0.20,
        adjust_ratio=0.50,
        cooldown_days=5,
    )
    result = strat.simulate(panel)

    # ---- 断言 1：月度 DCA 触发次数 ≈ 月份数 ----
    n_months = result.holdings.index.to_period("M").nunique()
    n_dca_buys = result.diagnostics["n_dca_events"]  # 6 笔 / 月（每只一笔）
    expected_dca_buys_per_month = len(strat.risk_symbols)
    assert n_dca_buys >= expected_dca_buys_per_month * (n_months - 2), (
        f"DCA 次数异常: {n_dca_buys}, 月数 {n_months}"
    )

    # ---- 断言 2：现金 + 风险 ≈ NAV ----
    last_holdings = result.holdings.iloc[-1]
    last_close = pd.DataFrame({s: panel[s]["close"] for s in panel}).iloc[-1]
    recompute_nav = float((last_holdings * last_close).sum())
    assert abs(recompute_nav - result.nav.iloc[-1]) / result.nav.iloc[-1] < 1e-9, (
        f"NAV 重算不一致: {recompute_nav} vs {result.nav.iloc[-1]}"
    )

    # ---- 断言 3：cooldown 拦截 ----
    swing_orders = result.orders[
        result.orders["kind"].isin(["swing_buy", "swing_sell"])
    ].copy()
    if not swing_orders.empty:
        swing_orders["date"] = pd.to_datetime(swing_orders["date"])
        for s, grp in swing_orders.groupby("symbol"):
            dates = grp["date"].sort_values().reset_index(drop=True)
            gaps = dates.diff().dt.days.dropna()
            if len(gaps):
                # cooldown 5 个交易日 ≈ 至少 5 个自然日（不严格，但应该 > 4）
                assert gaps.min() >= 5, (
                    f"cooldown 失效 {s}: min gap = {gaps.min()} days"
                )

    # ---- 断言 4：起始持仓 ≈ 全在货基 ----
    first_weights = result.weights.iloc[0]
    assert first_weights[DEFAULT_CASH_SYMBOL] > 0.99, (
        f"初始未把 init_cash 全部买入货基: {first_weights[DEFAULT_CASH_SYMBOL]}"
    )

    # ---- 断言 5：终态权重应接近目标（在 cooldown 失效后被重新拉到附近）----
    final_risk_w = result.diagnostics["final_risk_weight"]
    # 由于 DCA 持续买入，风险权重最终会偏向更高，但不应该 > 100%
    assert 0.0 < final_risk_w < 1.01, f"终态风险权重异常: {final_risk_w}"

    summary = {
        "n_days": int(result.diagnostics.get("n_days", len(result.nav))),
        "n_months": int(n_months),
        "n_dca_buy_orders": int(n_dca_buys),
        "n_swing_buy": int(result.diagnostics["n_swing_buy"]),
        "n_swing_sell": int(result.diagnostics["n_swing_sell"]),
        "init_cash": strat.initial_cash,
        "final_nav": float(result.nav.iloc[-1]),
        "final_risk_weight": float(final_risk_w),
        "final_cash_weight": float(result.diagnostics["final_cash_weight"]),
        "metrics": result.metrics,
    }
    return summary


# ---------------------------------------------------------------------------
# 真实数据入口
# ---------------------------------------------------------------------------


def _load_panel(since: str, until: str, strat: DCASwingStrategy) -> dict[str, pd.DataFrame]:
    """从缓存加载 7 只 ETF 的 OHLCV，去掉时区方便和 strategy 内部对齐。"""
    from strategy_lib.data import get_loader  # noqa: WPS433

    loader = get_loader("cn_etf")
    panel: dict[str, pd.DataFrame] = {}
    for s in strat.all_symbols:
        df = loader.load(symbol=s, timeframe="1d", since=since, until=until)
        # 去时区：策略内部用 naive index 比较月初；strict 对齐
        if df.index.tz is not None:
            df = df.tz_convert("UTC").tz_localize(None)
        panel[s] = df
    return panel


def _benchmark_510300(panel: dict[str, pd.DataFrame], strat: DCASwingStrategy,
                     index: pd.DatetimeIndex) -> pd.Series:
    """510300 买入持有：T0 把 init_cash 全部按 open + slippage 买入，之后每日按 close 估值。

    成本与策略一致：fees + slippage。
    """
    bm = panel["510300"].reindex(index)
    first_open = float(bm["open"].iloc[0])
    buy_price = first_open * (1 + strat.slippage)
    # 一次买入扣一笔 fee
    cash_after_fee = strat.initial_cash * (1 - strat.fees)
    shares = cash_after_fee / buy_price
    nav = shares * bm["close"]
    nav.name = "bh_510300"
    return nav


def _annual_returns(nav: pd.Series) -> pd.Series:
    """按自然年聚合的总收益。"""
    yearly = nav.groupby(nav.index.year).agg(["first", "last"])
    return (yearly["last"] / yearly["first"] - 1).rename("annual_return")


def _max_drawdown_series(nav: pd.Series) -> pd.Series:
    return nav / nav.cummax() - 1


def _turnover_annual(orders: pd.DataFrame, nav: pd.Series, strat: DCASwingStrategy) -> float:
    """年化换手率：成交额 / 平均 NAV / 年数。

    DCA 与 swing 都计入；init_buy 不计（属于建仓）。
    """
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
    """返回 (alpha 年化, IR, 跟踪误差年化)。"""
    s = strategy_nav.pct_change().dropna()
    b = bm_nav.pct_change().reindex(s.index).fillna(0.0)
    excess = s - b
    if excess.std(ddof=0) == 0:
        return 0.0, float("nan"), 0.0
    te = float(excess.std(ddof=0) * np.sqrt(252))
    alpha = float(excess.mean() * 252)
    ir = alpha / te if te > 0 else float("nan")
    return alpha, ir, te


def _swing_event_stats(orders: pd.DataFrame, weights: pd.DataFrame,
                       strat: DCASwingStrategy) -> dict:
    """S2 特有指标：高抛/低吸次数、平均触发偏离、cooldown 命中率。"""
    if orders.empty:
        return {}
    swings = orders[orders["kind"].isin(["swing_buy", "swing_sell"])].copy()
    n_buy = int((swings["kind"] == "swing_buy").sum())
    n_sell = int((swings["kind"] == "swing_sell").sum())

    # 平均触发偏离：触发当日 T-1 close 的权重 vs 目标
    target = strat.per_risk_weight
    triggers_dev: list[float] = []
    if not swings.empty:
        # orders 里 date 是 T+1 成交日；触发判定在 T 收盘 → T 是 date 的前一交易日。
        # 简化：用成交日前一日的权重当作触发权重
        idx = weights.index
        for _, row in swings.iterrows():
            d = pd.to_datetime(row["date"])
            pos = idx.get_indexer([d])[0]
            if pos > 0:
                w = weights.iloc[pos - 1][row["symbol"]]
                triggers_dev.append(abs(w / target - 1.0))
    avg_dev = float(np.mean(triggers_dev)) if triggers_dev else float("nan")

    # cooldown 命中率：理论上每日扫描，超阈值的次数 vs 实际触发次数
    cooldown_metric = _cooldown_hit_rate(weights, swings, strat)

    return {
        "n_swing_buy": n_buy,
        "n_swing_sell": n_sell,
        "n_swing_total": n_buy + n_sell,
        "avg_trigger_deviation": avg_dev,
        "cooldown_hit_rate": cooldown_metric,
    }


def _cooldown_hit_rate(weights: pd.DataFrame, swings: pd.DataFrame,
                       strat: DCASwingStrategy) -> float:
    """近似 cooldown 命中率：
    每日扫描超阈值的「想触发」事件数；实际触发数 / 想触发数 = 「未被 cooldown 拦下的比例」。
    返回 1 - 该比例 = cooldown 命中率（被 cooldown 拦下的比例）。
    """
    target = strat.per_risk_weight
    upper = target * (1 + strat.rel_band)
    lower = target * (1 - strat.rel_band)
    risk = list(strat.risk_symbols)
    rel = weights[risk]
    # 超阈值次数（每日每只独立计）
    over = ((rel > upper) | ((rel < lower) & (rel > 0))).sum().sum()
    actual = len(swings)
    if over <= 0:
        return float("nan")
    return float(1.0 - actual / over)


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------


def _plot_artifacts(result, bm_nav: pd.Series, strat: DCASwingStrategy,
                    out_dir: Path) -> None:
    import matplotlib.pyplot as plt
    out_dir.mkdir(parents=True, exist_ok=True)

    nav = result.nav
    weights = result.weights
    orders = result.orders

    # 1) equity curve
    fig, ax = plt.subplots(figsize=(11, 5))
    (nav / nav.iloc[0]).plot(ax=ax, label="S2 (DCA + swing)", color="#1f77b4", lw=1.6)
    (bm_nav / bm_nav.iloc[0]).plot(ax=ax, label="510300 BH", color="#d62728", lw=1.4, alpha=0.85)
    ax.axhline(1.0, color="gray", lw=0.6, ls=":")
    ax.set_title("Equity curve — S2 vs 510300 BH (normalized to 1.0)")
    ax.set_ylabel("Normalized NAV")
    ax.legend(loc="upper left")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "equity_curve.png", dpi=140)
    plt.close(fig)

    # 2) drawdown
    fig, ax = plt.subplots(figsize=(11, 4))
    s2_dd = _max_drawdown_series(nav)
    bm_dd = _max_drawdown_series(bm_nav)
    ax.fill_between(s2_dd.index, s2_dd.values, 0, color="#1f77b4", alpha=0.45, label="S2")
    ax.plot(bm_dd.index, bm_dd.values, color="#d62728", lw=1.0, alpha=0.85, label="510300 BH")
    ax.set_title("Drawdown — S2 vs 510300 BH")
    ax.set_ylabel("Drawdown")
    ax.legend(loc="lower left")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "drawdown.png", dpi=140)
    plt.close(fig)

    # 3) swing events overlay on risk-pool weight
    risk_w = weights[list(strat.risk_symbols)].sum(axis=1)
    fig, ax = plt.subplots(figsize=(11, 5))
    risk_w.plot(ax=ax, color="#1f77b4", lw=1.2, label="Risk-pool weight (sum)")
    target = strat.risk_target_weight
    ax.axhline(target, color="black", lw=0.8, ls="--", label=f"target {target:.0%}")
    ax.axhline(target * (1 + strat.rel_band), color="#d62728", lw=0.6, ls=":",
               label=f"upper {target*(1+strat.rel_band):.0%}")
    ax.axhline(target * (1 - strat.rel_band), color="#2ca02c", lw=0.6, ls=":",
               label=f"lower {target*(1-strat.rel_band):.0%}")
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
    ax.set_title("Swing events overlaid on risk-pool weight")
    ax.set_ylabel("Risk weight")
    ax.legend(loc="best", fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "swing_events.png", dpi=140)
    plt.close(fig)

    # 4) risk weight band — 实际轨迹 + 阈值带
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.fill_between(risk_w.index,
                    target * (1 - strat.rel_band),
                    target * (1 + strat.rel_band),
                    color="#1f77b4", alpha=0.13,
                    label=f"target band ±{strat.rel_band:.0%}")
    risk_w.plot(ax=ax, color="#1f77b4", lw=1.2, label="actual risk weight")
    ax.axhline(target, color="black", lw=0.8, ls="--", label=f"target {target:.0%}")
    ax.set_title("Risk-asset weight: actual trajectory vs target band")
    ax.set_ylabel("Weight")
    ax.legend(loc="best", fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "risk_weight_band.png", dpi=140)
    plt.close(fig)


# ---------------------------------------------------------------------------


def backtest_real(since: str, until: str) -> dict:
    """真实数据回测入口。

    1. 从缓存（或 akshare）加载 7 只 ETF
    2. 跑 simulate / run
    3. 算与 510300 BH 的对比指标
    4. 出图保存到 ``artifacts/``
    5. 返回 summary dict（CLI 会打印 + 落 json）
    """
    strat = DCASwingStrategy()  # 默认参数即共享基线
    panel = _load_panel(since, until, strat)
    result = strat.run(panel)

    nav = result.nav
    bm_nav = _benchmark_510300(panel, strat, nav.index)

    # 核心绩效
    metrics = result.metrics
    bm_metrics = DCASwingStrategy._compute_metrics(bm_nav)

    # alpha / IR / TE
    alpha, ir, te = _info_ratio(nav, bm_nav)
    excess_total = float(nav.iloc[-1] / nav.iloc[0] - bm_nav.iloc[-1] / bm_nav.iloc[0])

    # 换手率
    turnover = _turnover_annual(result.orders, nav, strat)

    # 分年度
    s2_yearly = _annual_returns(nav)
    bm_yearly = _annual_returns(bm_nav)

    # S2 特有事件统计
    swing_stats = _swing_event_stats(result.orders, result.weights, strat)

    # 出图
    out_dir = Path(__file__).resolve().parent / "artifacts"
    _plot_artifacts(result, bm_nav, strat, out_dir)

    # 把核心数据 dump 一份 csv，便于复盘
    nav_df = pd.DataFrame({"s2": nav, "bh_510300": bm_nav})
    nav_df.to_csv(out_dir / "nav_series.csv")
    result.orders.to_csv(out_dir / "orders.csv", index=False)
    result.weights.to_csv(out_dir / "weights.csv")

    summary = {
        "since": since,
        "until": until,
        "n_days": int(len(nav)),
        "init_cash": strat.initial_cash,
        "final_nav": float(nav.iloc[-1]),
        "bh_final_nav": float(bm_nav.iloc[-1]),
        "metrics": metrics,
        "bh_metrics": bm_metrics,
        "alpha_annual": alpha,
        "info_ratio": ir,
        "tracking_error_annual": te,
        "excess_total_return": excess_total,
        "turnover_annual": turnover,
        "annual_returns": {int(y): float(v) for y, v in s2_yearly.items()},
        "bh_annual_returns": {int(y): float(v) for y, v in bm_yearly.items()},
        "swing_stats": swing_stats,
        "diagnostics": result.diagnostics,
        "n_orders": int(len(result.orders)),
        "vbt_portfolio_built": result.portfolio is not None,
    }
    # dump json
    with open(out_dir / "real_backtest_summary.json", "w") as fh:
        json.dump(summary, fh, indent=2, default=str)
    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _main() -> int:
    parser = argparse.ArgumentParser(description="Strategy 2 validate")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("smoke", help="合成数据 smoke test")
    real = sub.add_parser("real", help="真实数据回测")
    real.add_argument("--since", default="2020-01-01")
    real.add_argument("--until", default="2024-12-31")
    args = parser.parse_args()

    if args.cmd == "smoke":
        out = smoke()
        print("=== smoke test passed ===")
        for k, v in out.items():
            if k == "metrics":
                print(f"  metrics:")
                for mk, mv in v.items():
                    print(f"    {mk}: {mv}")
            else:
                print(f"  {k}: {v}")
        return 0
    if args.cmd == "real":
        out = backtest_real(args.since, args.until)
        print("=== real backtest done ===")
        print(f"  window: {out['since']} -> {out['until']}, n_days={out['n_days']}")
        print(f"  init_cash: {out['init_cash']:,.0f}")
        print(f"  S2 final NAV: {out['final_nav']:,.2f}")
        print(f"  BH final NAV: {out['bh_final_nav']:,.2f}")
        print(f"  excess (total): {out['excess_total_return']:+.2%}")
        print("  S2 metrics:")
        for k, v in out["metrics"].items():
            print(f"    {k}: {v}")
        print("  510300 BH metrics:")
        for k, v in out["bh_metrics"].items():
            print(f"    {k}: {v}")
        print(f"  alpha (annual): {out['alpha_annual']:+.2%}")
        print(f"  info ratio: {out['info_ratio']:.3f}")
        print(f"  tracking error (annual): {out['tracking_error_annual']:.2%}")
        print(f"  turnover (annual): {out['turnover_annual']:.2%}")
        print("  swing stats:")
        for k, v in out["swing_stats"].items():
            print(f"    {k}: {v}")
        print("  annual returns (S2 / BH):")
        for y in sorted(out["annual_returns"]):
            s2 = out["annual_returns"][y]
            bh = out["bh_annual_returns"].get(y, float("nan"))
            print(f"    {y}: {s2:+.2%}  /  {bh:+.2%}")
        print(f"  vbt portfolio built: {out['vbt_portfolio_built']}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(_main())
