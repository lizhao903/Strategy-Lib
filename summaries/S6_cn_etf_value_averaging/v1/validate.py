"""Strategy 6 (Value Averaging) validation script.

入口：
1. ``smoke()`` — 合成 OHLCV 跑通 VA 双向调节 / 货币池非负 / NAV 恒等
2. ``backtest_real(since, until)`` — 真实数据回测 + 对比 S1 v1 / S2 v1 / 510300 BH
3. ``sensitivity(since, until)`` — 4 档 CAGR 敏感性扫描（6%/8%/10%/12%）
4. CLI 包装

运行：
    python summaries/S6_cn_etf_value_averaging/v1/validate.py smoke
    python summaries/S6_cn_etf_value_averaging/v1/validate.py real --since 2020-01-01 --until 2024-12-31
    python summaries/S6_cn_etf_value_averaging/v1/validate.py sensitivity --since 2020-01-01 --until 2024-12-31
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# v1/validate.py → parents[3] 才是 repo root
ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _load_module(name: str, target: Path):
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, target)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 {target}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


try:
    from strategy_lib.strategies.cn_etf_value_averaging import (  # noqa: E402
        ValueAveragingStrategy,
        DEFAULT_CASH_SYMBOL,
        DEFAULT_RISK_SYMBOLS,
    )
except ModuleNotFoundError:
    _va = _load_module(
        "_value_averaging_module",
        SRC / "strategy_lib" / "strategies" / "cn_etf_value_averaging.py",
    )
    ValueAveragingStrategy = _va.ValueAveragingStrategy
    DEFAULT_CASH_SYMBOL = _va.DEFAULT_CASH_SYMBOL
    DEFAULT_RISK_SYMBOLS = _va.DEFAULT_RISK_SYMBOLS

# 加载 S1 v1 + S2 v1（用于对比表）；如果对比策略加载失败，仍可独立产 VA 结果
try:
    from strategy_lib.strategies.cn_etf_dca_basic import DCABasicStrategy  # noqa: E402
except ModuleNotFoundError:
    try:
        _s1 = _load_module(
            "_dca_basic_module",
            SRC / "strategy_lib" / "strategies" / "cn_etf_dca_basic.py",
        )
        DCABasicStrategy = _s1.DCABasicStrategy
    except Exception:
        DCABasicStrategy = None  # type: ignore

try:
    from strategy_lib.strategies.cn_etf_dca_swing import DCASwingStrategy  # noqa: E402
except ModuleNotFoundError:
    try:
        _s2 = _load_module(
            "_dca_swing_module",
            SRC / "strategy_lib" / "strategies" / "cn_etf_dca_swing.py",
        )
        DCASwingStrategy = _s2.DCASwingStrategy
    except Exception:
        DCASwingStrategy = None  # type: ignore


# ---------------------------------------------------------------------------
# 合成数据（仅 smoke 用）
# ---------------------------------------------------------------------------


def make_synthetic_panel(
    *,
    start: str = "2020-01-02",
    n_days: int = 252 * 2,
    drift_mode: str = "balanced",  # "balanced" | "down" | "up"
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

    if drift_mode == "balanced":
        drifts = np.array([0.10, 0.05, 0.15, -0.02, 0.08, 0.03])
    elif drift_mode == "down":
        drifts = np.array([-0.20, -0.15, -0.18, -0.12, -0.10, -0.08])
    elif drift_mode == "up":
        drifts = np.array([0.30, 0.25, 0.35, 0.20, 0.28, 0.22])
    else:
        raise ValueError(drift_mode)

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
    """合成数据 smoke：跑三种漂移模式，验证机制对称性 + 货币池非负 + NAV 恒等。"""

    summary: dict = {}

    # --- (1) balanced 模式 ---
    panel_bal = make_synthetic_panel(drift_mode="balanced")
    strat = ValueAveragingStrategy(initial_cash=100_000.0, cagr_target=0.08)
    res = strat.simulate(panel_bal)

    # NAV 重算恒等
    last_holdings = res.holdings.iloc[-1]
    last_close = pd.DataFrame({s: panel_bal[s]["close"] for s in panel_bal}).iloc[-1]
    recompute_nav = float((last_holdings * last_close).sum())
    assert abs(recompute_nav - res.nav.iloc[-1]) / res.nav.iloc[-1] < 1e-9, (
        f"NAV 重算不一致 (balanced): {recompute_nav} vs {res.nav.iloc[-1]}"
    )

    # 起始全在货基
    first_w = res.weights.iloc[0]
    assert first_w[DEFAULT_CASH_SYMBOL] > 0.99, (
        f"初始未把 init_cash 全部买入货基: {first_w[DEFAULT_CASH_SYMBOL]}"
    )

    # 货币池始终非负（无杠杆）
    cash_holdings = res.holdings[DEFAULT_CASH_SYMBOL]
    assert (cash_holdings >= -1e-9).all(), "货币池出现负持仓（杠杆）"

    # 至少有一些 BUY 动作（balanced 漂移下 NAV 慢于 8% target）
    n_buy = res.diagnostics["n_buy_months"]
    assert n_buy >= 5, f"balanced smoke: BUY months {n_buy} < 5"

    # cagr_target 路径单调递增
    assert res.target.iloc[-1] > res.target.iloc[0]

    summary["balanced"] = {
        "n_days": len(res.nav),
        "n_buy_months": res.diagnostics["n_buy_months"],
        "n_sell_months": res.diagnostics["n_sell_months"],
        "n_skip_months": res.diagnostics["n_skip_months"],
        "n_noop_months": res.diagnostics["n_noop_months"],
        "final_nav": float(res.nav.iloc[-1]),
        "final_target": float(res.target.iloc[-1]),
        "final_risk_weight": res.diagnostics["final_risk_weight"],
        "final_cash_weight": res.diagnostics["final_cash_weight"],
        "cash_exhausted_date": res.diagnostics["cash_exhausted_date"],
        "metrics": res.metrics,
    }

    # --- (2) down 模式：VA 应大量买入直到货币池耗尽 ---
    panel_down = make_synthetic_panel(drift_mode="down", seed=11)
    strat_down = ValueAveragingStrategy(
        initial_cash=100_000.0, cagr_target=0.08, max_buy_per_period=10_000.0
    )
    res_down = strat_down.simulate(panel_down)
    n_buy_down = res_down.diagnostics["n_buy_months"]
    n_noop_down = res_down.diagnostics["n_noop_months"]
    # 期望 BUY+NOOP 月数 >= 12（至少一年都在尝试加仓）
    assert n_buy_down + n_noop_down >= 12, (
        f"down 模式 BUY+NOOP 月数过少: {n_buy_down}+{n_noop_down}"
    )
    # 货币池耗尽期望发生
    assert res_down.diagnostics["cash_exhausted_date"] is not None, (
        "down 模式货币池未耗尽（不符合预期）"
    )
    summary["down"] = {
        "n_buy_months": n_buy_down,
        "n_noop_months": n_noop_down,
        "n_sell_months": res_down.diagnostics["n_sell_months"],
        "cash_exhausted_date": res_down.diagnostics["cash_exhausted_date"],
        "final_risk_weight": res_down.diagnostics["final_risk_weight"],
    }

    # --- (3) up 模式：VA 应有 SELL 动作 ---
    panel_up = make_synthetic_panel(drift_mode="up", seed=99)
    strat_up = ValueAveragingStrategy(initial_cash=100_000.0, cagr_target=0.08)
    res_up = strat_up.simulate(panel_up)
    n_sell_up = res_up.diagnostics["n_sell_months"]
    assert n_sell_up >= 1, f"up 模式 SELL 月数 = {n_sell_up}（不符合预期，应至少有 1 次卖出）"
    summary["up"] = {
        "n_buy_months": res_up.diagnostics["n_buy_months"],
        "n_sell_months": n_sell_up,
        "final_cash_weight": res_up.diagnostics["final_cash_weight"],
    }

    return summary


# ---------------------------------------------------------------------------
# 真实数据加载
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


def _benchmark_510300(
    panel: dict[str, pd.DataFrame],
    init_cash: float,
    fees: float,
    slippage: float,
    index: pd.DatetimeIndex,
) -> pd.Series:
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
    if orders is None or orders.empty:
        return 0.0
    df = orders[orders["kind"] != "init_buy"].copy()
    if "amount" in df.columns:
        df["notional"] = df["amount"].astype(float).abs()
    else:
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
# Plotting — VA 4 图
# ---------------------------------------------------------------------------


def _plot_artifacts(
    va_result,
    s2_result,
    s1_result,
    bm_nav: pd.Series,
    strat_va: ValueAveragingStrategy,
    out_dir: Path,
) -> None:
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)

    nav_va = va_result.nav
    target_va = va_result.target

    # 1) equity curve: S6 vs S1 vs S2 v1 vs BH（4 条线）
    fig, ax = plt.subplots(figsize=(11, 5))
    (nav_va / nav_va.iloc[0]).plot(
        ax=ax, label="S6 VA (cagr_target=8%)", color="#9467bd", lw=1.7
    )
    if s2_result is not None:
        nav_s2 = s2_result.nav
        (nav_s2 / nav_s2.iloc[0]).plot(
            ax=ax, label="S2 v1 (DCA swing)", color="#2ca02c", lw=1.3, alpha=0.85
        )
    if s1_result is not None:
        nav_s1 = s1_result.nav
        (nav_s1 / nav_s1.iloc[0]).plot(
            ax=ax, label="S1 v1 (DCA basic)", color="#1f77b4", lw=1.2, alpha=0.85
        )
    (bm_nav / bm_nav.iloc[0]).plot(
        ax=ax, label="510300 BH", color="#d62728", lw=1.2, alpha=0.85
    )
    ax.axhline(1.0, color="gray", lw=0.6, ls=":")
    ax.set_title("Equity curve — S6 (VA) vs S2 v1 vs S1 v1 vs 510300 BH (norm to 1.0)")
    ax.set_ylabel("Normalized NAV")
    ax.legend(loc="upper left")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "equity_curve.png", dpi=140)
    plt.close(fig)

    # 2) drawdown
    fig, ax = plt.subplots(figsize=(11, 4.5))
    dd_va = _max_drawdown_series(nav_va)
    dd_bh = _max_drawdown_series(bm_nav)
    ax.fill_between(dd_va.index, dd_va.values, 0, color="#9467bd", alpha=0.40, label="S6 VA")
    if s2_result is not None:
        dd_s2 = _max_drawdown_series(s2_result.nav)
        ax.plot(dd_s2.index, dd_s2.values, color="#2ca02c", lw=1.0, alpha=0.9, label="S2 v1")
    if s1_result is not None:
        dd_s1 = _max_drawdown_series(s1_result.nav)
        ax.plot(dd_s1.index, dd_s1.values, color="#1f77b4", lw=1.0, alpha=0.9, label="S1 v1")
    ax.plot(dd_bh.index, dd_bh.values, color="#d62728", lw=1.0, alpha=0.85, label="510300 BH")
    ax.set_title("Drawdown — S6 VA vs S2 v1 vs S1 v1 vs 510300 BH")
    ax.set_ylabel("Drawdown")
    ax.legend(loc="lower left")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "drawdown.png", dpi=140)
    plt.close(fig)

    # 3) target vs actual NAV（核心可视化）
    fig, ax = plt.subplots(figsize=(11, 5))
    nav_va.plot(ax=ax, color="#9467bd", lw=1.6, label="Actual NAV (S6 VA)")
    target_va.plot(
        ax=ax, color="black", lw=1.0, ls="--", label=f"Target (CAGR={strat_va.cagr_target:.0%})"
    )
    bm_nav.plot(ax=ax, color="#d62728", lw=1.0, alpha=0.8, label="510300 BH NAV")
    if va_result.cash_exhausted_date is not None:
        ax.axvline(
            va_result.cash_exhausted_date,
            color="orange",
            lw=1.0,
            ls=":",
            label=f"Cash exhausted ({va_result.cash_exhausted_date.date()})",
        )
    ax.set_title("Target vs Actual NAV — S6 Value Averaging (core visualization)")
    ax.set_ylabel("RMB")
    ax.legend(loc="best", fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "target_vs_actual.png", dpi=140)
    plt.close(fig)

    # 4) VA actions：每月 buy/sell amount 时序（条形）
    actions = va_result.actions
    fig, ax = plt.subplots(figsize=(11, 4.5))
    if actions is not None and not actions.empty:
        a = actions.copy()
        a["execute_date"] = pd.to_datetime(a["execute_date"])
        a = a.set_index("execute_date")
        # buy = 正，sell = 负
        signed = pd.Series(0.0, index=a.index)
        signed.loc[a["mode"] == "BUY"] = a.loc[a["mode"] == "BUY", "amount_actual"]
        signed.loc[a["mode"] == "SELL"] = -a.loc[a["mode"] == "SELL", "amount_actual"]
        signed.loc[a["mode"] == "BUY_NOOP"] = 0.0
        # 选用月度日期（每月一个柱）
        colors = ["#2ca02c" if v > 0 else "#d62728" if v < 0 else "#cccccc" for v in signed.values]
        ax.bar(signed.index, signed.values, width=15, color=colors, alpha=0.85)
        # NOOP 标记（货币池耗尽后想买买不到）
        noop_dates = a.index[a["mode"] == "BUY_NOOP"]
        if len(noop_dates) > 0:
            ax.scatter(
                noop_dates,
                np.zeros(len(noop_dates)),
                marker="x",
                color="orange",
                s=30,
                label=f"NOOP (cash exhausted, {len(noop_dates)})",
                zorder=5,
            )
    ax.axhline(0, color="black", lw=0.5)
    ax.set_title("VA monthly actions — green=BUY, red=SELL, orange-x=NOOP (cash exhausted)")
    ax.set_ylabel("Amount (RMB, +=buy / -=sell)")
    ax.legend(loc="best", fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "va_actions.png", dpi=140)
    plt.close(fig)

    # 5) cash vs risk weight stack（额外）
    weights = va_result.weights
    risk_w = weights[list(strat_va.risk_symbols)].sum(axis=1)
    cash_w = weights[strat_va.cash_symbol]
    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.fill_between(risk_w.index, 0, risk_w.values, color="#9467bd", alpha=0.55, label="Risk pool (sum of 6 ETFs)")
    ax.fill_between(
        risk_w.index,
        risk_w.values,
        risk_w.values + cash_w.values,
        color="#1f77b4",
        alpha=0.35,
        label="Cash pool (511990)",
    )
    if va_result.cash_exhausted_date is not None:
        ax.axvline(
            va_result.cash_exhausted_date,
            color="orange",
            lw=1.0,
            ls=":",
            label=f"Cash exhausted ({va_result.cash_exhausted_date.date()})",
        )
    ax.set_ylim(0, 1.05)
    ax.set_title("Cash vs Risk weight over time — S6 VA")
    ax.set_ylabel("Weight")
    ax.legend(loc="lower left", fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "cash_vs_risk.png", dpi=140)
    plt.close(fig)


# ---------------------------------------------------------------------------
# 真实回测主入口
# ---------------------------------------------------------------------------


def backtest_real(since: str, until: str, cagr_target: float = 0.08) -> dict:
    strat_va = ValueAveragingStrategy(cagr_target=cagr_target)
    panel = _load_panel(since, until, strat_va.all_symbols)
    res_va = strat_va.run(panel)

    # 同窗口跑 S1 v1 / S2 v1
    res_s1 = None
    if DCABasicStrategy is not None:
        try:
            res_s1 = DCABasicStrategy().run(panel)
            if hasattr(res_s1, "equity") and not hasattr(res_s1, "nav"):
                # S1 result 兼容包装：转成统一字段（部分 v1 代码用 equity）
                res_s1.nav = res_s1.equity
        except Exception as e:
            print(f"[warn] S1 v1 加载失败: {e}", file=sys.stderr)
            res_s1 = None

    res_s2 = None
    if DCASwingStrategy is not None:
        try:
            res_s2 = DCASwingStrategy().run(panel)
        except Exception as e:
            print(f"[warn] S2 v1 加载失败: {e}", file=sys.stderr)
            res_s2 = None

    nav_va = res_va.nav
    bm_nav = _benchmark_510300(
        panel, strat_va.initial_cash, strat_va.fees, strat_va.slippage, nav_va.index
    )

    metrics_va = res_va.metrics
    metrics_bh = ValueAveragingStrategy._compute_metrics(bm_nav)
    alpha_va, ir_va, te_va = _info_ratio(nav_va, bm_nav)
    excess_va = float(nav_va.iloc[-1] / nav_va.iloc[0] - bm_nav.iloc[-1] / bm_nav.iloc[0])
    turnover_va = _turnover_annual(res_va.orders, nav_va)
    yearly_va = _annual_returns(nav_va)
    yearly_bh = _annual_returns(bm_nav)

    # 出图
    out_dir = Path(__file__).resolve().parent / "artifacts"
    _plot_artifacts(res_va, res_s2, res_s1, bm_nav, strat_va, out_dir)

    # dump csv
    nav_df = pd.DataFrame({"va": nav_va, "target": res_va.target, "bh_510300": bm_nav})
    if res_s1 is not None and hasattr(res_s1, "nav"):
        nav_df["s1"] = res_s1.nav
    if res_s2 is not None:
        nav_df["s2"] = res_s2.nav
    nav_df.to_csv(out_dir / "nav_series.csv")
    res_va.orders.to_csv(out_dir / "orders.csv", index=False)
    res_va.weights.to_csv(out_dir / "weights.csv")
    if res_va.actions is not None:
        res_va.actions.to_csv(out_dir / "actions.csv", index=False)

    summary: dict = {
        "since": since,
        "until": until,
        "n_days": int(len(nav_va)),
        "init_cash": strat_va.initial_cash,
        "cagr_target": cagr_target,
        "va": {
            "final_nav": float(nav_va.iloc[-1]),
            "final_target": float(res_va.target.iloc[-1]),
            "metrics": metrics_va,
            "alpha_annual": alpha_va,
            "info_ratio": ir_va,
            "tracking_error_annual": te_va,
            "excess_total": excess_va,
            "turnover_annual": turnover_va,
            "annual_returns": {int(y): float(v) for y, v in yearly_va.items()},
            "diagnostics": res_va.diagnostics,
        },
        "bh": {
            "final_nav": float(bm_nav.iloc[-1]),
            "metrics": metrics_bh,
            "annual_returns": {int(y): float(v) for y, v in yearly_bh.items()},
        },
    }

    if res_s2 is not None:
        nav_s2 = res_s2.nav
        metrics_s2 = res_s2.metrics
        alpha_s2, ir_s2, te_s2 = _info_ratio(nav_s2, bm_nav)
        turnover_s2 = _turnover_annual(res_s2.orders, nav_s2)
        yearly_s2 = _annual_returns(nav_s2)
        o_s2 = res_s2.orders
        n_buy_s2 = int((o_s2["kind"] == "swing_buy").sum())
        n_sell_s2 = int((o_s2["kind"] == "swing_sell").sum())
        summary["s2_v1"] = {
            "final_nav": float(nav_s2.iloc[-1]),
            "metrics": metrics_s2,
            "alpha_annual": alpha_s2,
            "info_ratio": ir_s2,
            "tracking_error_annual": te_s2,
            "turnover_annual": turnover_s2,
            "annual_returns": {int(y): float(v) for y, v in yearly_s2.items()},
            "swing": {
                "n_swing_buy": n_buy_s2,
                "n_swing_sell": n_sell_s2,
                "buy_sell_ratio": (
                    n_sell_s2 / n_buy_s2 if n_buy_s2 > 0 else float("inf")
                ),
            },
        }

    if res_s1 is not None and hasattr(res_s1, "nav"):
        nav_s1 = res_s1.nav
        metrics_s1 = ValueAveragingStrategy._compute_metrics(nav_s1)
        alpha_s1, ir_s1, te_s1 = _info_ratio(nav_s1, bm_nav)
        yearly_s1 = _annual_returns(nav_s1)
        summary["s1_v1"] = {
            "final_nav": float(nav_s1.iloc[-1]),
            "metrics": metrics_s1,
            "alpha_annual": alpha_s1,
            "info_ratio": ir_s1,
            "tracking_error_annual": te_s1,
            "annual_returns": {int(y): float(v) for y, v in yearly_s1.items()},
        }

    with open(out_dir / "real_backtest_summary.json", "w") as fh:
        json.dump(summary, fh, indent=2, default=str)
    return summary


# ---------------------------------------------------------------------------
# 4 档 CAGR 敏感性
# ---------------------------------------------------------------------------


def sensitivity(since: str, until: str) -> pd.DataFrame:
    cagrs = [0.06, 0.08, 0.10, 0.12]
    rows: list[dict] = []
    panel = _load_panel(since, until, ValueAveragingStrategy().all_symbols)
    for c in cagrs:
        strat = ValueAveragingStrategy(cagr_target=c)
        res = strat.run(panel)
        bm_nav = _benchmark_510300(
            panel, strat.initial_cash, strat.fees, strat.slippage, res.nav.index
        )
        alpha, ir, te = _info_ratio(res.nav, bm_nav)
        turnover = _turnover_annual(res.orders, res.nav)
        rows.append(
            {
                "cagr_target": c,
                "final_nav": float(res.nav.iloc[-1]),
                "final_target": float(res.target.iloc[-1]),
                "cagr": res.metrics["annual_return"],
                "ann_vol": res.metrics["annual_vol"],
                "sharpe": res.metrics["sharpe"],
                "max_drawdown": res.metrics["max_drawdown"],
                "calmar": res.metrics["calmar"],
                "alpha_annual": alpha,
                "info_ratio": ir,
                "tracking_error": te,
                "turnover_annual": turnover,
                "n_buy_months": res.diagnostics["n_buy_months"],
                "n_sell_months": res.diagnostics["n_sell_months"],
                "n_skip_months": res.diagnostics["n_skip_months"],
                "n_noop_months": res.diagnostics["n_noop_months"],
                "buy_sell_ratio": res.diagnostics["buy_sell_ratio"],
                "cash_exhausted_date": res.diagnostics["cash_exhausted_date"],
                "final_cash_weight": res.diagnostics["final_cash_weight"],
                "final_risk_weight": res.diagnostics["final_risk_weight"],
            }
        )
    df = pd.DataFrame(rows)
    out_dir = Path(__file__).resolve().parent / "artifacts"
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_dir / "cagr_sensitivity.csv", index=False)
    return df


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _main() -> int:
    parser = argparse.ArgumentParser(description="Strategy 6 (Value Averaging) validate")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("smoke", help="合成数据 smoke test")
    real = sub.add_parser("real", help="真实数据回测（VA + S1 v1 + S2 v1 + BH）")
    real.add_argument("--since", default="2020-01-01")
    real.add_argument("--until", default="2024-12-31")
    real.add_argument("--cagr_target", type=float, default=0.08)
    sens = sub.add_parser("sensitivity", help="4 档 CAGR 敏感性扫描")
    sens.add_argument("--since", default="2020-01-01")
    sens.add_argument("--until", default="2024-12-31")
    args = parser.parse_args()

    if args.cmd == "smoke":
        out = smoke()
        print("=== S6 VA smoke test passed ===")
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "real":
        out = backtest_real(args.since, args.until, args.cagr_target)
        print("=== S6 VA real backtest done ===")
        print(f"  window: {out['since']} -> {out['until']}, n_days={out['n_days']}")
        print(f"  init_cash: {out['init_cash']:,.0f}; cagr_target: {out['cagr_target']:.1%}")
        va = out["va"]
        bh = out["bh"]
        print("  --- VA ---")
        print(f"    final NAV: {va['final_nav']:,.2f}")
        print(f"    final target: {va['final_target']:,.2f}")
        print(f"    CAGR: {va['metrics']['annual_return']:+.4f}")
        print(f"    Sharpe: {va['metrics']['sharpe']:.4f}")
        print(f"    MaxDD: {va['metrics']['max_drawdown']:.4f}")
        print(f"    alpha (annual): {va['alpha_annual']:+.4f}, IR: {va['info_ratio']:.3f}")
        print(f"    turnover (annual): {va['turnover_annual']:.4f}")
        d = va["diagnostics"]
        print(
            f"    months: BUY={d['n_buy_months']} SELL={d['n_sell_months']} "
            f"SKIP={d['n_skip_months']} NOOP={d['n_noop_months']}"
        )
        print(
            f"    buy/sell ratio: {d['buy_sell_ratio']:.2f}:1 "
            f"(对照 S2 v1 = 11.80:1，期望 < 3:1)"
        )
        print(f"    cash exhausted at: {d['cash_exhausted_date']}")
        if "s2_v1" in out:
            s2 = out["s2_v1"]
            print("  --- S2 v1 ---")
            print(f"    final NAV: {s2['final_nav']:,.2f}")
            print(f"    CAGR: {s2['metrics']['annual_return']:+.4f}")
            print(f"    Sharpe: {s2['metrics']['sharpe']:.4f}")
            print(f"    MaxDD: {s2['metrics']['max_drawdown']:.4f}")
            print(
                f"    swing buy/sell: {s2['swing']['n_swing_buy']}/"
                f"{s2['swing']['n_swing_sell']} (ratio={s2['swing']['buy_sell_ratio']:.2f}:1)"
            )
        if "s1_v1" in out:
            s1 = out["s1_v1"]
            print("  --- S1 v1 ---")
            print(f"    final NAV: {s1['final_nav']:,.2f}")
            print(f"    CAGR: {s1['metrics']['annual_return']:+.4f}")
            print(f"    Sharpe: {s1['metrics']['sharpe']:.4f}")
            print(f"    MaxDD: {s1['metrics']['max_drawdown']:.4f}")
        print("  --- BH 510300 ---")
        print(f"    final NAV: {bh['final_nav']:,.2f}")
        print(f"    CAGR: {bh['metrics']['annual_return']:+.4f}")
        print("  Annual breakdown (VA / BH):")
        for y in sorted(va["annual_returns"]):
            vy = va["annual_returns"][y]
            by = bh["annual_returns"].get(y, float("nan"))
            extra = ""
            if "s2_v1" in out:
                extra += f"  s2={out['s2_v1']['annual_returns'].get(y, float('nan')):+.4f}"
            if "s1_v1" in out:
                extra += f"  s1={out['s1_v1']['annual_returns'].get(y, float('nan')):+.4f}"
            print(f"    {y}: va={vy:+.4f}  bh={by:+.4f}{extra}")
        return 0

    if args.cmd == "sensitivity":
        df = sensitivity(args.since, args.until)
        print("=== S6 VA cagr_target sensitivity ===")
        cols = [
            "cagr_target",
            "final_nav",
            "cagr",
            "sharpe",
            "max_drawdown",
            "buy_sell_ratio",
            "n_noop_months",
            "cash_exhausted_date",
        ]
        with pd.option_context("display.float_format", "{:,.4f}".format):
            print(df[cols].to_string(index=False))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(_main())
