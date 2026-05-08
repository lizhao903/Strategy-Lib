"""Validation entry for MomentumTiltStrategy (Strategy 4).

Sub-commands
------------
- ``smoke`` (default): synthetic-panel sanity check; **no real data, no S3 import**.
  Used to validate `target_weights` math (sum=1, bounds, momentum direction,
  fallbacks) without pulling akshare/vectorbt heavy deps.
- ``real``:  full real-data backtest 2020-01-01 ~ 2024-12-31 over the V1 6-ETF
  pool. Compares against:
    * 510300 buy-and-hold (absolute benchmark)
    * S3 ``EqualRebalanceStrategy`` with the **same** ``rebalance_period`` (the
      key like-for-like to isolate the momentum tilt's contribution).
  Saves equity / drawdown / weight-evolution / tilt-strength PNGs to
  ``summaries/cn_etf_momentum_tilt/artifacts/`` and prints a metrics table.

Run:
    python summaries/cn_etf_momentum_tilt/validate.py smoke
    python summaries/cn_etf_momentum_tilt/validate.py real
    python summaries/cn_etf_momentum_tilt/validate.py real --since 2020-01-01 --until 2024-12-31
    python summaries/cn_etf_momentum_tilt/validate.py sweep    # alpha & lookback grid
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
import types
from abc import ABC, abstractmethod
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Smoke path (kept self-contained — no real strategy_lib import).
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
ARTIFACTS = Path(__file__).resolve().parent / "artifacts"


def _smoke_main() -> int:
    """Synthetic-panel smoke test (the original v1 implementation)."""

    def _load(mod_name: str, file_path: Path) -> types.ModuleType:
        spec = importlib.util.spec_from_file_location(mod_name, file_path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
        return mod

    def _ensure_pkg(mod_name: str) -> None:
        if mod_name not in sys.modules:
            m = types.ModuleType(mod_name)
            m.__path__ = []  # type: ignore[attr-defined]
            sys.modules[mod_name] = m

    _ensure_pkg("strategy_lib")
    _ensure_pkg("strategy_lib.factors")
    _ensure_pkg("strategy_lib.strategies")

    _load(
        "strategy_lib.factors.base",
        SRC / "strategy_lib" / "factors" / "base.py",
    )
    _load(
        "strategy_lib.factors.momentum",
        SRC / "strategy_lib" / "factors" / "momentum.py",
    )

    _stub_mod_name = "strategy_lib.strategies.cn_etf_equal_rebalance"
    if _stub_mod_name not in sys.modules:
        stub = types.ModuleType(_stub_mod_name)

        class EqualRebalanceStrategy(ABC):
            def __init__(self, *args, **kwargs) -> None:
                self.symbols = kwargs.get("symbols")
                self.rebalance = kwargs.get("rebalance", 20)

            @abstractmethod
            def target_weights(self, date, prices_panel):  # pragma: no cover
                ...

        stub.EqualRebalanceStrategy = EqualRebalanceStrategy
        sys.modules[_stub_mod_name] = stub

    mt_mod = _load(
        "strategy_lib.strategies.cn_etf_momentum_tilt",
        SRC / "strategy_lib" / "strategies" / "cn_etf_momentum_tilt.py",
    )
    MomentumTiltStrategy = mt_mod.MomentumTiltStrategy

    def make_panel(seed: int = 42, n_days: int = 250) -> dict[str, pd.DataFrame]:
        rng = np.random.default_rng(seed)
        symbols = ["510300", "510500", "159915", "512100", "512880", "512170"]
        drifts = np.linspace(-0.0010, 0.0020, len(symbols))
        idx = pd.date_range("2023-01-01", periods=n_days, freq="B", name="timestamp")
        panel: dict[str, pd.DataFrame] = {}
        for sym, mu in zip(symbols, drifts, strict=True):
            rets = rng.normal(mu, 0.015, size=n_days)
            close = 100 * np.exp(np.cumsum(rets))
            df = pd.DataFrame(
                {
                    "open": close * (1 + rng.normal(0, 0.002, size=n_days)),
                    "high": close * (1 + np.abs(rng.normal(0, 0.004, size=n_days))),
                    "low": close * (1 - np.abs(rng.normal(0, 0.004, size=n_days))),
                    "close": close,
                    "volume": rng.uniform(1e6, 5e6, size=n_days),
                },
                index=idx,
            )
            panel[sym] = df
        return panel

    def assert_close(actual: float, expected: float, tol: float = 1e-9, msg: str = "") -> None:
        assert abs(actual - expected) <= tol, f"{msg}: {actual} vs {expected}"

    panel = make_panel()
    date = panel["510300"].index[-1]

    strat = MomentumTiltStrategy()
    w = strat.target_weights(date, panel)
    print(f"[case1] default alpha=1.0  weights @ {date.date()}:")
    for s, v in sorted(w.items(), key=lambda kv: -kv[1]):
        print(f"   {s}: {v:.4f}")
    s_sum = sum(w.values())
    s_min = min(w.values())
    s_max = max(w.values())
    print(f"   sum={s_sum:.6f}  min={s_min:.4f}  max={s_max:.4f}")
    assert_close(s_sum, 1.0, tol=1e-6, msg="case1 sum != 1")
    assert s_min >= 0.05 - 1e-9, f"case1 below w_min: {s_min}"
    assert s_max <= 0.40 + 1e-9, f"case1 above w_max: {s_max}"
    assert w["512170"] > w["510300"], "动量方向不符：高 drift 资产权重 <= 低 drift"

    strat0 = MomentumTiltStrategy(alpha=0.0)
    w0 = strat0.target_weights(date, panel)
    eq = 1.0 / len(panel)
    print(f"[case2] alpha=0  expect equal weight {eq:.4f}")
    for v in w0.values():
        assert_close(v, eq, tol=1e-9, msg="case2 不等权")
    assert_close(sum(w0.values()), 1.0, tol=1e-9, msg="case2 sum != 1")

    strat_hi = MomentumTiltStrategy(alpha=10.0)
    w_hi = strat_hi.target_weights(date, panel)
    print("[case3] alpha=10  weights:")
    for s, v in sorted(w_hi.items(), key=lambda kv: -kv[1]):
        print(f"   {s}: {v:.4f}")
    assert_close(sum(w_hi.values()), 1.0, tol=1e-6, msg="case3 sum != 1")
    assert min(w_hi.values()) >= 0.05 - 1e-9
    assert max(w_hi.values()) <= 0.40 + 1e-9
    assert abs(w_hi["512170"] - 0.40) < 1e-6, "case3 top-drift 应该饱和到 w_max"

    strat2 = MomentumTiltStrategy(lookback=20, secondary_lookback=60, alpha=1.0)
    w2 = strat2.target_weights(date, panel)
    s_sum2 = sum(w2.values())
    print(f"[case4] secondary_lookback=60  sum={s_sum2:.6f} max={max(w2.values()):.4f} min={min(w2.values()):.4f}")
    assert_close(s_sum2, 1.0, tol=1e-6, msg="case4 sum != 1")

    sparse_panel = {s: df.iloc[:5].copy() for s, df in panel.items()}
    early_date = sparse_panel["510300"].index[-1]
    strat_sparse = MomentumTiltStrategy(lookback=20, alpha=1.0)
    w_sparse = strat_sparse.target_weights(early_date, sparse_panel)
    print(f"[case5] sparse data  weights: {w_sparse}")
    eq = 1.0 / len(sparse_panel)
    for v in w_sparse.values():
        assert_close(v, eq, tol=1e-9, msg="case5 应降级为等权")

    one_panel = {"510300": panel["510300"]}
    w_one = MomentumTiltStrategy().target_weights(date, one_panel)
    assert w_one == {"510300": 1.0}, f"case6 unexpected: {w_one}"

    w_empty = MomentumTiltStrategy().target_weights(date, {})
    assert w_empty == {}, f"case7 unexpected: {w_empty}"

    print("\nALL SMOKE TESTS PASSED")
    return 0


# ---------------------------------------------------------------------------
# Real-data backtest.
# ---------------------------------------------------------------------------
DEFAULT_SYMBOLS = ["510300", "510500", "159915", "512100", "512880", "512170"]
TRADING_DAYS = 252


def _annualized_metrics(returns: pd.Series, freq: int = TRADING_DAYS) -> dict:
    """Compute CAGR / Sharpe / vol / MaxDD / Calmar from a daily return series."""
    r = returns.dropna()
    if r.empty:
        return {"cagr": np.nan, "vol": np.nan, "sharpe": np.nan, "max_dd": np.nan, "calmar": np.nan}
    n = len(r)
    cum = (1 + r).cumprod()
    total = float(cum.iloc[-1] - 1)
    cagr = (1 + total) ** (freq / n) - 1
    vol = float(r.std() * np.sqrt(freq))
    sharpe = float(r.mean() / r.std() * np.sqrt(freq)) if r.std() > 0 else np.nan
    drawdown = cum / cum.cummax() - 1
    max_dd = float(drawdown.min())
    calmar = cagr / abs(max_dd) if max_dd < 0 else np.nan
    return {
        "cagr": float(cagr),
        "vol": vol,
        "sharpe": sharpe,
        "max_dd": max_dd,
        "calmar": calmar,
        "total_return": total,
        "final_value_factor": float(cum.iloc[-1]),
    }


def _yearly_returns(returns: pd.Series) -> pd.Series:
    return (1 + returns).groupby(returns.index.year).prod() - 1


def _info_ratio(strat_ret: pd.Series, base_ret: pd.Series, freq: int = TRADING_DAYS) -> dict:
    """Information ratio + tracking error + t-stat of excess returns."""
    diff = (strat_ret - base_ret).dropna()
    if diff.empty:
        return {"ir": np.nan, "te": np.nan, "alpha_ann": np.nan, "t_stat": np.nan, "n": 0}
    mu = diff.mean()
    sd = diff.std()
    n = len(diff)
    te = float(sd * np.sqrt(freq))
    ir = float(mu / sd * np.sqrt(freq)) if sd > 0 else np.nan
    alpha_ann = float(mu * freq)
    t_stat = float(mu / (sd / np.sqrt(n))) if sd > 0 else np.nan
    return {"ir": ir, "te": te, "alpha_ann": alpha_ann, "t_stat": t_stat, "n": int(n)}


def _portfolio_returns(pf) -> pd.Series:
    """Daily return series of a vectorbt portfolio (handles grouped/single)."""
    val = pf.value()
    if isinstance(val, pd.DataFrame):
        # grouped → one column
        if val.shape[1] == 1:
            val = val.iloc[:, 0]
        else:
            val = val.sum(axis=1)
    ret = val.pct_change().fillna(0.0)
    ret.name = "ret"
    return ret


def _bh_510300(panel: dict[str, pd.DataFrame], init_cash: float):
    import vectorbt as vbt

    close = panel["510300"]["close"]
    return vbt.Portfolio.from_holding(
        close, init_cash=init_cash, fees=0.00005, slippage=0.0005, freq="1D"
    )


def _print_table(rows: list[dict], cols: list[str], title: str = "") -> None:
    if title:
        print(f"\n=== {title} ===")
    widths = {c: max(len(c), max((len(str(r.get(c, ""))) for r in rows), default=0)) for c in cols}
    line = "  ".join(c.ljust(widths[c]) for c in cols)
    print(line)
    print("  ".join("-" * widths[c] for c in cols))
    for r in rows:
        print("  ".join(str(r.get(c, "")).ljust(widths[c]) for c in cols))


def _fmt(v, pct: bool = False, digits: int = 4) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    if pct:
        return f"{v * 100:.2f}%"
    return f"{v:.{digits}f}"


def run_real(
    since: str = "2020-01-01",
    until: str = "2024-12-31",
    symbols: list[str] | None = None,
    rebalance_period: int = 20,
    lookback: int = 20,
    alpha: float = 1.0,
    w_min: float = 0.05,
    w_max: float = 0.40,
    init_cash: float = 100_000,
    save_plots: bool = True,
):
    """Real-data backtest. Returns a dict with everything for sweep/printing."""
    from strategy_lib.data import get_loader
    from strategy_lib.strategies.cn_etf_equal_rebalance import EqualRebalanceStrategy
    from strategy_lib.strategies.cn_etf_momentum_tilt import MomentumTiltStrategy

    syms = symbols or DEFAULT_SYMBOLS
    panel = get_loader("cn_etf").load_many(syms, since=since, until=until)
    missing = [s for s in syms if s not in panel]
    if missing:
        raise RuntimeError(f"data load failed for: {missing}")

    # Strategy 4: momentum tilt
    strat = MomentumTiltStrategy(
        symbols=syms,
        rebalance_period=rebalance_period,
        lookback=lookback,
        alpha=alpha,
        w_min=w_min,
        w_max=w_max,
    )
    res4 = strat.run(panel, init_cash=init_cash)

    # Strategy 3: equal rebalance baseline (same period)
    strat3 = EqualRebalanceStrategy(symbols=syms, rebalance_period=rebalance_period)
    res3 = strat3.run(panel, init_cash=init_cash)

    # 510300 BH absolute benchmark
    pf_bh = _bh_510300(panel, init_cash)

    r4 = _portfolio_returns(res4.portfolio)
    r3 = _portfolio_returns(res3.portfolio)
    r_bh = _portfolio_returns(pf_bh)

    # Align indices
    common = r4.index.intersection(r3.index).intersection(r_bh.index)
    r4 = r4.loc[common]
    r3 = r3.loc[common]
    r_bh = r_bh.loc[common]

    m4 = _annualized_metrics(r4)
    m3 = _annualized_metrics(r3)
    m_bh = _annualized_metrics(r_bh)

    vs_s3 = _info_ratio(r4, r3)
    vs_bh = _info_ratio(r4, r_bh)

    yearly = pd.DataFrame(
        {
            "S4 momentum_tilt": _yearly_returns(r4),
            "S3 equal_rebal": _yearly_returns(r3),
            "510300 BH": _yearly_returns(r_bh),
        }
    )
    yearly["S4 - S3"] = yearly["S4 momentum_tilt"] - yearly["S3 equal_rebal"]
    yearly["S4 - BH"] = yearly["S4 momentum_tilt"] - yearly["510300 BH"]

    # Turnover (annualized one-way)
    weights_actual = res4.target_weights.ffill().fillna(0.0)
    weights_actual_3 = res3.target_weights.ffill().fillna(0.0)
    # Approximate turnover at each rebalance: sum |Δw| / 2
    def _annual_turnover(weights_df: pd.DataFrame, rebal_dates) -> float:
        if len(rebal_dates) < 2:
            return float("nan")
        wd = weights_df.loc[rebal_dates].fillna(0.0)
        diffs = wd.diff().abs().sum(axis=1) / 2  # one-way fraction
        years = (wd.index[-1] - wd.index[0]).days / 365.25
        if years <= 0:
            return float("nan")
        return float(diffs.sum() / years)

    turn4 = _annual_turnover(weights_actual, res4.rebalance_dates)
    turn3 = _annual_turnover(weights_actual_3, res3.rebalance_dates)

    # Active weight magnitude
    if not res4.target_weights.dropna(how="all").empty:
        rebal_w = res4.target_weights.dropna(how="all")
        n = len(syms)
        active = (rebal_w - 1.0 / n).abs().mean(axis=1)
        mean_active_w = float(active.mean())
    else:
        mean_active_w = float("nan")

    out = {
        "panel": panel,
        "res4": res4,
        "res3": res3,
        "pf_bh": pf_bh,
        "returns": {"s4": r4, "s3": r3, "bh": r_bh},
        "metrics": {"s4": m4, "s3": m3, "bh": m_bh, "vs_s3": vs_s3, "vs_bh": vs_bh},
        "yearly": yearly,
        "turnover": {"s4": turn4, "s3": turn3},
        "mean_active_w": mean_active_w,
        "config": {
            "since": since,
            "until": until,
            "rebalance_period": rebalance_period,
            "lookback": lookback,
            "alpha": alpha,
            "w_min": w_min,
            "w_max": w_max,
            "init_cash": init_cash,
        },
    }

    if save_plots:
        _save_plots(out)

    return out


def _save_plots(out: dict) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    r4 = out["returns"]["s4"]
    r3 = out["returns"]["s3"]
    r_bh = out["returns"]["bh"]

    # 1) Equity curve
    fig, ax = plt.subplots(figsize=(11, 5))
    nav4 = (1 + r4).cumprod()
    nav3 = (1 + r3).cumprod()
    nav_bh = (1 + r_bh).cumprod()
    ax.plot(nav4.index, nav4.values, label="S4 momentum_tilt", linewidth=1.6, color="#1f77b4")
    ax.plot(nav3.index, nav3.values, label="S3 equal_rebal", linewidth=1.4, color="#2ca02c", alpha=0.85)
    ax.plot(nav_bh.index, nav_bh.values, label="510300 BH", linewidth=1.2, color="#d62728", alpha=0.75)
    ax.set_title("Equity Curve  (start=1.0)")
    ax.set_ylabel("NAV")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(ARTIFACTS / "equity_curve.png", dpi=130)
    plt.close(fig)

    # 2) Drawdown
    fig, ax = plt.subplots(figsize=(11, 4))
    for r, label, color in [
        (r4, "S4 momentum_tilt", "#1f77b4"),
        (r3, "S3 equal_rebal", "#2ca02c"),
        (r_bh, "510300 BH", "#d62728"),
    ]:
        cum = (1 + r).cumprod()
        dd = cum / cum.cummax() - 1
        ax.plot(dd.index, dd.values, label=label, linewidth=1.2, color=color, alpha=0.85)
    ax.set_title("Drawdown")
    ax.set_ylabel("Drawdown")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(ARTIFACTS / "drawdown.png", dpi=130)
    plt.close(fig)

    # 3) Weight evolution (stacked area, ffill held weights)
    res4 = out["res4"]
    syms = list(res4.target_weights.columns)
    w_held = res4.target_weights.ffill().fillna(0.0)
    fig, ax = plt.subplots(figsize=(11, 5))
    colors = plt.get_cmap("tab10").colors[: len(syms)]
    ax.stackplot(w_held.index, w_held.T.values, labels=syms, colors=colors, alpha=0.85)
    ax.set_ylim(0, 1)
    ax.set_title("Weight Evolution — S4 momentum_tilt (held weights)")
    ax.set_ylabel("Weight")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.08), ncol=len(syms), fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(ARTIFACTS / "weight_evolution.png", dpi=130)
    plt.close(fig)

    # 4) Tilt strength: distribution of momentum z-scores at rebalance dates
    #    + actual deviation of weight from 1/N
    rebal_w = res4.target_weights.dropna(how="all")
    n = len(syms)
    deviations = (rebal_w - 1.0 / n).values.flatten()

    # recompute z-scores per rebalance date for diagnostics
    from strategy_lib.strategies.cn_etf_momentum_tilt import MomentumTiltStrategy

    cfg = out["config"]
    diag = MomentumTiltStrategy(
        symbols=syms,
        rebalance_period=cfg["rebalance_period"],
        lookback=cfg["lookback"],
        alpha=cfg["alpha"],
        w_min=cfg["w_min"],
        w_max=cfg["w_max"],
    )
    panel = out["panel"]
    z_rows = []
    for d in rebal_w.index:
        scores = diag._momentum_scores(pd.Timestamp(d), panel)
        z = diag._zscore(scores).fillna(0.0)
        z_rows.append(z.reindex(syms).values)
    z_arr = np.asarray(z_rows).flatten()

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))
    axes[0].hist(z_arr, bins=30, color="#1f77b4", alpha=0.85, edgecolor="white")
    axes[0].axvline(0, color="black", linewidth=0.8)
    axes[0].set_title(f"Momentum z-score distribution\n(n={len(z_arr)} rebal-asset obs)")
    axes[0].set_xlabel("z-score")
    axes[0].grid(alpha=0.3)

    axes[1].hist(deviations, bins=30, color="#ff7f0e", alpha=0.85, edgecolor="white")
    axes[1].axvline(0, color="black", linewidth=0.8)
    axes[1].set_title(
        f"Active weight deviation w_i − 1/N\nmean|Δw| = {out['mean_active_w']:.4f}"
    )
    axes[1].set_xlabel("w − 1/N")
    axes[1].grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(ARTIFACTS / "tilt_strength.png", dpi=130)
    plt.close(fig)


def print_real_summary(out: dict) -> None:
    cfg = out["config"]
    m = out["metrics"]
    print(
        f"\nConfig: since={cfg['since']} until={cfg['until']} rebal={cfg['rebalance_period']}"
        f" lookback={cfg['lookback']} alpha={cfg['alpha']} w_min={cfg['w_min']} w_max={cfg['w_max']}"
    )
    rows = [
        {
            "strategy": "S4 momentum_tilt",
            "final_NAV": _fmt(m["s4"]["final_value_factor"]),
            "total_ret": _fmt(m["s4"]["total_return"], pct=True),
            "CAGR": _fmt(m["s4"]["cagr"], pct=True),
            "Vol": _fmt(m["s4"]["vol"], pct=True),
            "Sharpe": _fmt(m["s4"]["sharpe"]),
            "MaxDD": _fmt(m["s4"]["max_dd"], pct=True),
            "Calmar": _fmt(m["s4"]["calmar"]),
            "Turnover/yr": _fmt(out["turnover"]["s4"], pct=True),
        },
        {
            "strategy": "S3 equal_rebal",
            "final_NAV": _fmt(m["s3"]["final_value_factor"]),
            "total_ret": _fmt(m["s3"]["total_return"], pct=True),
            "CAGR": _fmt(m["s3"]["cagr"], pct=True),
            "Vol": _fmt(m["s3"]["vol"], pct=True),
            "Sharpe": _fmt(m["s3"]["sharpe"]),
            "MaxDD": _fmt(m["s3"]["max_dd"], pct=True),
            "Calmar": _fmt(m["s3"]["calmar"]),
            "Turnover/yr": _fmt(out["turnover"]["s3"], pct=True),
        },
        {
            "strategy": "510300 BH",
            "final_NAV": _fmt(m["bh"]["final_value_factor"]),
            "total_ret": _fmt(m["bh"]["total_return"], pct=True),
            "CAGR": _fmt(m["bh"]["cagr"], pct=True),
            "Vol": _fmt(m["bh"]["vol"], pct=True),
            "Sharpe": _fmt(m["bh"]["sharpe"]),
            "MaxDD": _fmt(m["bh"]["max_dd"], pct=True),
            "Calmar": _fmt(m["bh"]["calmar"]),
            "Turnover/yr": "—",
        },
    ]
    _print_table(
        rows,
        ["strategy", "final_NAV", "total_ret", "CAGR", "Vol", "Sharpe", "MaxDD", "Calmar", "Turnover/yr"],
        title="Performance",
    )

    vs_s3 = m["vs_s3"]
    vs_bh = m["vs_bh"]
    print("\n=== vs S3 equal_rebal (factor effectiveness) ===")
    print(
        f"  alpha_ann (excess CAGR proxy) = {_fmt(vs_s3['alpha_ann'], pct=True)}"
        f"  IR = {_fmt(vs_s3['ir'])}  TE = {_fmt(vs_s3['te'], pct=True)}"
        f"  t-stat = {_fmt(vs_s3['t_stat'])}  n = {vs_s3['n']}"
    )
    print("\n=== vs 510300 BH (absolute benchmark) ===")
    print(
        f"  alpha_ann = {_fmt(vs_bh['alpha_ann'], pct=True)}"
        f"  IR = {_fmt(vs_bh['ir'])}  TE = {_fmt(vs_bh['te'], pct=True)}"
        f"  t-stat = {_fmt(vs_bh['t_stat'])}  n = {vs_bh['n']}"
    )

    print("\n=== Yearly returns ===")
    pd_opts = pd.option_context("display.float_format", lambda x: f"{x*100:6.2f}%")
    with pd_opts:
        print(out["yearly"].to_string())

    print(f"\nMean active weight |Δw| = {out['mean_active_w']:.4f}")


def run_alpha_sweep(
    since: str = "2020-01-01",
    until: str = "2024-12-31",
    alphas: tuple[float, ...] = (0.0, 0.5, 1.0, 2.0, 5.0),
    lookback: int = 20,
    rebalance_period: int = 20,
) -> pd.DataFrame:
    rows = []
    base_out = None
    for a in alphas:
        out = run_real(
            since=since,
            until=until,
            rebalance_period=rebalance_period,
            lookback=lookback,
            alpha=a,
            save_plots=False,
        )
        if base_out is None:
            base_out = out
        m = out["metrics"]["s4"]
        ir = out["metrics"]["vs_s3"]
        rows.append(
            {
                "alpha": a,
                "CAGR": m["cagr"],
                "Vol": m["vol"],
                "Sharpe": m["sharpe"],
                "MaxDD": m["max_dd"],
                "Calmar": m["calmar"],
                "TotalRet": m["total_return"],
                "vs_S3_alpha_ann": ir["alpha_ann"],
                "vs_S3_IR": ir["ir"],
                "vs_S3_TE": ir["te"],
                "vs_S3_t": ir["t_stat"],
                "Turnover/yr": out["turnover"]["s4"],
                "mean_|Δw|": out["mean_active_w"],
            }
        )
    df = pd.DataFrame(rows)
    return df


def run_lookback_sweep(
    since: str = "2020-01-01",
    until: str = "2024-12-31",
    lookbacks: tuple[int, ...] = (10, 20, 60),
    alpha: float = 1.0,
    rebalance_period: int = 20,
) -> pd.DataFrame:
    rows = []
    for lb in lookbacks:
        out = run_real(
            since=since,
            until=until,
            rebalance_period=rebalance_period,
            lookback=lb,
            alpha=alpha,
            save_plots=False,
        )
        m = out["metrics"]["s4"]
        ir = out["metrics"]["vs_s3"]
        rows.append(
            {
                "lookback": lb,
                "CAGR": m["cagr"],
                "Sharpe": m["sharpe"],
                "MaxDD": m["max_dd"],
                "vs_S3_alpha_ann": ir["alpha_ann"],
                "vs_S3_IR": ir["ir"],
                "vs_S3_t": ir["t_stat"],
                "mean_|Δw|": out["mean_active_w"],
            }
        )
    return pd.DataFrame(rows)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=False)

    sub.add_parser("smoke", help="synthetic-panel smoke test (default)")

    p_real = sub.add_parser("real", help="real-data backtest")
    p_real.add_argument("--since", default="2020-01-01")
    p_real.add_argument("--until", default="2024-12-31")
    p_real.add_argument("--rebalance", type=int, default=20)
    p_real.add_argument("--lookback", type=int, default=20)
    p_real.add_argument("--alpha", type=float, default=1.0)
    p_real.add_argument("--w-min", type=float, default=0.05)
    p_real.add_argument("--w-max", type=float, default=0.40)
    p_real.add_argument("--no-plots", action="store_true")

    p_sweep = sub.add_parser("sweep", help="alpha + lookback sensitivity (no plots, prints tables)")
    p_sweep.add_argument("--since", default="2020-01-01")
    p_sweep.add_argument("--until", default="2024-12-31")

    args = p.parse_args(argv)
    if args.cmd in (None, "smoke"):
        return _smoke_main()
    if args.cmd == "real":
        out = run_real(
            since=args.since,
            until=args.until,
            rebalance_period=args.rebalance,
            lookback=args.lookback,
            alpha=args.alpha,
            w_min=args.w_min,
            w_max=args.w_max,
            save_plots=not args.no_plots,
        )
        print_real_summary(out)
        return 0
    if args.cmd == "sweep":
        print("\n=== alpha sensitivity (lookback=20, rebal=20) ===")
        df_a = run_alpha_sweep(since=args.since, until=args.until)
        with pd.option_context(
            "display.float_format", lambda x: f"{x:.4f}", "display.width", 160
        ):
            print(df_a.to_string(index=False))

        print("\n=== lookback sensitivity (alpha=1.0, rebal=20) ===")
        df_l = run_lookback_sweep(since=args.since, until=args.until)
        with pd.option_context(
            "display.float_format", lambda x: f"{x:.4f}", "display.width", 160
        ):
            print(df_l.to_string(index=False))
        # Persist sweep tables alongside artifacts for reference
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        df_a.to_csv(ARTIFACTS / "alpha_sweep.csv", index=False)
        df_l.to_csv(ARTIFACTS / "lookback_sweep.csv", index=False)
        print(f"\n(sweep tables saved to {ARTIFACTS})")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
