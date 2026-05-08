"""Validation entry for MomentumTiltV2Strategy (Strategy 4 v2).

Sub-commands
------------
- ``smoke``  : synthetic-panel + strict-shift sanity (no real data).
- ``real``   : full real-data backtest 2020-01-01 ~ 2024-12-31 over the v2
               11-ETF expanded pool. Compares against:
                 * v2 default
                 * v1 default (6-ETF, lookback=20, alpha=1, w_max=0.40)
                 * v2 on the original 6 池 (pool ablation)
                 * S3 equal-rebalance baseline (on v2 pool, like-for-like)
                 * 510300 buy-and-hold (absolute benchmark)
               Saves equity / drawdown / weight_evolution / tilt_strength /
               pool_ablation PNGs under ``./artifacts/``.
- ``sweep``  : alpha & lookback sensitivity, prints + persists CSV.

Run:
    python summaries/S4_cn_etf_momentum_tilt/v2/validate.py smoke
    python summaries/S4_cn_etf_momentum_tilt/v2/validate.py real
    python summaries/S4_cn_etf_momentum_tilt/v2/validate.py sweep
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
ARTIFACTS = Path(__file__).resolve().parent / "artifacts"

# Make `strategy_lib` importable without installing the package.
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


# -----------------------------------------------------------------------------
# v2 11-ETF default pool & v1 6-ETF original pool (для ablation)
# -----------------------------------------------------------------------------
V2_SYMBOLS = [
    "510300", "510500", "159915", "512100", "512880", "512170",
    "159920", "518880", "513100", "513500", "511260",
]
V1_SYMBOLS = ["510300", "510500", "159915", "512100", "512880", "512170"]

TRADING_DAYS = 252


# -----------------------------------------------------------------------------
# Smoke (synthetic) — verifies math + strict shift(1)
# -----------------------------------------------------------------------------
def _smoke_main() -> int:
    from strategy_lib.strategies.cn_etf_momentum_tilt_v2 import (
        MomentumTiltV2Strategy,
    )

    rng = np.random.default_rng(42)
    syms = list(MomentumTiltV2Strategy.DEFAULT_SYMBOLS_V2)
    drifts = np.linspace(-0.0010, 0.0020, len(syms))
    idx = pd.date_range("2020-01-01", periods=400, freq="B", name="timestamp")
    panel = {}
    for s, mu in zip(syms, drifts, strict=True):
        rets = rng.normal(mu, 0.015, size=len(idx))
        close = 100 * np.exp(np.cumsum(rets))
        panel[s] = pd.DataFrame(
            {
                "open": close * (1 + rng.normal(0, 0.002, size=len(idx))),
                "high": close * (1 + np.abs(rng.normal(0, 0.004, size=len(idx)))),
                "low": close * (1 - np.abs(rng.normal(0, 0.004, size=len(idx)))),
                "close": close,
                "volume": rng.uniform(1e6, 5e6, size=len(idx)),
            },
            index=idx,
        )

    date = idx[-1]

    # Case 1: default
    strat = MomentumTiltV2Strategy()
    w = strat.target_weights(date, panel)
    print(f"[case1] default lookback=120, skip=5, alpha=1, raw signal, 11 syms:")
    for s, v in sorted(w.items(), key=lambda kv: -kv[1]):
        print(f"   {s}: {v:.4f}")
    s_sum, s_min, s_max = sum(w.values()), min(w.values()), max(w.values())
    print(f"   sum={s_sum:.6f} min={s_min:.4f} max={s_max:.4f}")
    assert abs(s_sum - 1.0) < 1e-6
    assert s_min >= 0.03 - 1e-9
    assert s_max <= 0.30 + 1e-9

    # Case 2: alpha=0 → equal
    strat0 = MomentumTiltV2Strategy(alpha=0.0)
    w0 = strat0.target_weights(date, panel)
    eq = 1.0 / len(syms)
    for v in w0.values():
        assert abs(v - eq) < 1e-9
    print(f"[case2] alpha=0  -> equal {eq:.4f}  OK")

    # Case 3: vol_adj
    strat_va = MomentumTiltV2Strategy(signal="vol_adj", lookback=60, skip=5)
    w_va = strat_va.target_weights(date, panel)
    assert abs(sum(w_va.values()) - 1.0) < 1e-6
    print("[case3] vol_adj signal sum=1 OK")

    # Case 4: strict shift(1) — no row at or after `date`
    ts_mid = idx[200]
    sliced = MomentumTiltV2Strategy._slice_strict(panel, ts_mid)
    for s, df in sliced.items():
        assert df.index.max() < ts_mid
    print("[case4] strict shift(1) OK (max(idx) < date)")

    # Case 5: extreme alpha clipping
    strat_hi = MomentumTiltV2Strategy(alpha=10.0)
    w_hi = strat_hi.target_weights(date, panel)
    assert abs(sum(w_hi.values()) - 1.0) < 1e-6
    assert min(w_hi.values()) >= 0.03 - 1e-9
    assert max(w_hi.values()) <= 0.30 + 1e-9
    print(f"[case5] alpha=10 sum=1 bounds OK")

    # Case 6: data not enough → fallback equal
    sparse = {s: df.iloc[:5].copy() for s, df in panel.items()}
    early_date = sparse[syms[0]].index[-1] + pd.Timedelta(days=1)
    w_sp = MomentumTiltV2Strategy().target_weights(early_date, sparse)
    eq6 = 1.0 / len(sparse)
    for v in w_sp.values():
        assert abs(v - eq6) < 1e-9
    print("[case6] insufficient data -> fallback equal OK")

    print("\nALL SMOKE TESTS PASSED")
    return 0


# -----------------------------------------------------------------------------
# Metrics helpers (mirror v1 to keep tables comparable)
# -----------------------------------------------------------------------------
def _annualized_metrics(returns: pd.Series, freq: int = TRADING_DAYS) -> dict:
    r = returns.dropna()
    if r.empty:
        return {k: np.nan for k in
                ("cagr", "vol", "sharpe", "max_dd", "calmar", "total_return", "final_value_factor")}
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


def _info_ratio(strat_ret: pd.Series, base_ret: pd.Series, freq: int = TRADING_DAYS) -> dict:
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


def _yearly_returns(returns: pd.Series) -> pd.Series:
    return (1 + returns).groupby(returns.index.year).prod() - 1


def _portfolio_returns(pf) -> pd.Series:
    val = pf.value()
    if isinstance(val, pd.DataFrame):
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


def _annual_turnover(weights_df: pd.DataFrame, rebal_dates) -> float:
    if len(rebal_dates) < 2:
        return float("nan")
    wd = weights_df.loc[rebal_dates].fillna(0.0)
    diffs = wd.diff().abs().sum(axis=1) / 2
    years = (wd.index[-1] - wd.index[0]).days / 365.25
    if years <= 0:
        return float("nan")
    return float(diffs.sum() / years)


def _mean_active_w(weights_df: pd.DataFrame, n_assets: int) -> float:
    if weights_df.dropna(how="all").empty:
        return float("nan")
    rebal_w = weights_df.dropna(how="all").fillna(0.0)
    active = (rebal_w - 1.0 / n_assets).abs().mean(axis=1)
    return float(active.mean())


# -----------------------------------------------------------------------------
# Strategy runners
# -----------------------------------------------------------------------------
def _run_v2(
    panel: dict[str, pd.DataFrame],
    *,
    symbols: list[str],
    lookback: int,
    skip: int,
    alpha: float,
    w_min: float,
    w_max: float,
    signal: str,
    vol_lookback: int,
    rebalance_period: int,
    init_cash: float,
):
    from strategy_lib.strategies.cn_etf_momentum_tilt_v2 import (
        MomentumTiltV2Strategy,
    )
    s = MomentumTiltV2Strategy(
        symbols=symbols,
        rebalance_period=rebalance_period,
        lookback=lookback,
        skip=skip,
        alpha=alpha,
        w_min=w_min,
        w_max=w_max,
        signal=signal,
        vol_lookback=vol_lookback,
    )
    return s.run(panel, init_cash=init_cash)


def _run_v1(
    panel: dict[str, pd.DataFrame],
    *,
    symbols: list[str],
    lookback: int,
    alpha: float,
    w_min: float,
    w_max: float,
    rebalance_period: int,
    init_cash: float,
):
    from strategy_lib.strategies.cn_etf_momentum_tilt import MomentumTiltStrategy
    s = MomentumTiltStrategy(
        symbols=symbols,
        rebalance_period=rebalance_period,
        lookback=lookback,
        alpha=alpha,
        w_min=w_min,
        w_max=w_max,
    )
    return s.run(panel, init_cash=init_cash)


def _run_s3(panel, symbols, rebalance_period, init_cash):
    from strategy_lib.strategies.cn_etf_equal_rebalance import EqualRebalanceStrategy
    return EqualRebalanceStrategy(symbols=symbols, rebalance_period=rebalance_period).run(
        panel, init_cash=init_cash
    )


def run_real(
    since: str = "2020-01-01",
    until: str = "2024-12-31",
    rebalance_period: int = 20,
    # v2 defaults
    lookback: int = 120,
    skip: int = 5,
    alpha: float = 1.0,
    w_min: float = 0.03,
    w_max: float = 0.30,
    signal: str = "raw",
    vol_lookback: int = 60,
    init_cash: float = 100_000,
    save_plots: bool = True,
):
    """Run v2 default + v1 default + v2 on原池 + S3 baseline + BH。返回 dict。"""
    from strategy_lib.data import get_loader

    loader = get_loader("cn_etf")
    all_syms = sorted(set(V2_SYMBOLS) | set(V1_SYMBOLS))
    panel_full = loader.load_many(all_syms, since=since, until=until)
    missing = [s for s in all_syms if s not in panel_full]
    if missing:
        raise RuntimeError(f"data load failed for: {missing}")

    panel_v2 = {s: panel_full[s] for s in V2_SYMBOLS}
    panel_v1 = {s: panel_full[s] for s in V1_SYMBOLS}

    # 1) v2 default — expanded pool, lookback=120, skip=5, alpha=1.0, raw
    res_v2 = _run_v2(
        panel_v2,
        symbols=V2_SYMBOLS,
        lookback=lookback,
        skip=skip,
        alpha=alpha,
        w_min=w_min,
        w_max=w_max,
        signal=signal,
        vol_lookback=vol_lookback,
        rebalance_period=rebalance_period,
        init_cash=init_cash,
    )

    # 2) v1 default — original 6-ETF, lookback=20, alpha=1.0
    res_v1 = _run_v1(
        panel_v1,
        symbols=V1_SYMBOLS,
        lookback=20,
        alpha=1.0,
        w_min=0.05,
        w_max=0.40,
        rebalance_period=rebalance_period,
        init_cash=init_cash,
    )

    # 3) v2 on original 6 池 (pool ablation: same v2 params, smaller pool)
    res_v2_old_pool = _run_v2(
        panel_v1,
        symbols=V1_SYMBOLS,
        lookback=lookback,
        skip=skip,
        alpha=alpha,
        w_min=0.05,            # 6 池仍用宽松边界，避免与 N 冲突
        w_max=0.40,
        signal=signal,
        vol_lookback=vol_lookback,
        rebalance_period=rebalance_period,
        init_cash=init_cash,
    )

    # 4) S3 baseline — equal rebalance on v2 pool (like-for-like for IR)
    res_s3 = _run_s3(panel_v2, V2_SYMBOLS, rebalance_period, init_cash)

    # 4b) S3 baseline — equal rebalance on v1 pool (for v1 IR comparison)
    res_s3_old = _run_s3(panel_v1, V1_SYMBOLS, rebalance_period, init_cash)

    # 5) BH 510300
    pf_bh = _bh_510300(panel_full, init_cash)

    # Returns aligned on common index
    r_v2 = _portfolio_returns(res_v2.portfolio)
    r_v1 = _portfolio_returns(res_v1.portfolio)
    r_v2_old = _portfolio_returns(res_v2_old_pool.portfolio)
    r_s3 = _portfolio_returns(res_s3.portfolio)
    r_s3_old = _portfolio_returns(res_s3_old.portfolio)
    r_bh = _portfolio_returns(pf_bh)

    common = (r_v2.index
              .intersection(r_v1.index)
              .intersection(r_v2_old.index)
              .intersection(r_s3.index)
              .intersection(r_s3_old.index)
              .intersection(r_bh.index))
    r_v2 = r_v2.loc[common]
    r_v1 = r_v1.loc[common]
    r_v2_old = r_v2_old.loc[common]
    r_s3 = r_s3.loc[common]
    r_s3_old = r_s3_old.loc[common]
    r_bh = r_bh.loc[common]

    metrics = {
        "v2": _annualized_metrics(r_v2),
        "v1": _annualized_metrics(r_v1),
        "v2_old_pool": _annualized_metrics(r_v2_old),
        "s3": _annualized_metrics(r_s3),
        "s3_old": _annualized_metrics(r_s3_old),
        "bh": _annualized_metrics(r_bh),
        "vs_s3": _info_ratio(r_v2, r_s3),
        "vs_v1": _info_ratio(r_v2, r_v1),
        "vs_bh": _info_ratio(r_v2, r_bh),
        "v2_old_vs_s3_old": _info_ratio(r_v2_old, r_s3_old),
    }

    yearly = pd.DataFrame({
        "S4 v2 (11 pool)": _yearly_returns(r_v2),
        "S4 v1 (6 pool)": _yearly_returns(r_v1),
        "S4 v2 on old 6 pool": _yearly_returns(r_v2_old),
        "S3 equal_rebal (11 pool)": _yearly_returns(r_s3),
        "510300 BH": _yearly_returns(r_bh),
    })
    yearly["v2 - S3"] = yearly["S4 v2 (11 pool)"] - yearly["S3 equal_rebal (11 pool)"]
    yearly["v2 - v1"] = yearly["S4 v2 (11 pool)"] - yearly["S4 v1 (6 pool)"]
    yearly["v2 - BH"] = yearly["S4 v2 (11 pool)"] - yearly["510300 BH"]

    turnover = {
        "v2": _annual_turnover(res_v2.target_weights.ffill().fillna(0.0), res_v2.rebalance_dates),
        "v1": _annual_turnover(res_v1.target_weights.ffill().fillna(0.0), res_v1.rebalance_dates),
        "v2_old_pool": _annual_turnover(res_v2_old_pool.target_weights.ffill().fillna(0.0), res_v2_old_pool.rebalance_dates),
        "s3": _annual_turnover(res_s3.target_weights.ffill().fillna(0.0), res_s3.rebalance_dates),
    }

    active = {
        "v2": _mean_active_w(res_v2.target_weights, len(V2_SYMBOLS)),
        "v1": _mean_active_w(res_v1.target_weights, len(V1_SYMBOLS)),
        "v2_old_pool": _mean_active_w(res_v2_old_pool.target_weights, len(V1_SYMBOLS)),
    }

    out = {
        "panel_v2": panel_v2,
        "panel_v1": panel_v1,
        "res_v2": res_v2,
        "res_v1": res_v1,
        "res_v2_old_pool": res_v2_old_pool,
        "res_s3": res_s3,
        "res_s3_old": res_s3_old,
        "pf_bh": pf_bh,
        "returns": {
            "v2": r_v2, "v1": r_v1, "v2_old_pool": r_v2_old,
            "s3": r_s3, "s3_old": r_s3_old, "bh": r_bh,
        },
        "metrics": metrics,
        "yearly": yearly,
        "turnover": turnover,
        "active": active,
        "config": {
            "since": since, "until": until,
            "rebalance_period": rebalance_period,
            "lookback": lookback, "skip": skip,
            "alpha": alpha, "w_min": w_min, "w_max": w_max,
            "signal": signal, "vol_lookback": vol_lookback,
            "init_cash": init_cash,
        },
    }

    if save_plots:
        _save_plots(out)
    return out


# -----------------------------------------------------------------------------
# Sweeps
# -----------------------------------------------------------------------------
def run_alpha_sweep(
    since: str = "2020-01-01",
    until: str = "2024-12-31",
    alphas: tuple[float, ...] = (0.0, 0.5, 1.0, 2.0, 5.0),
    lookback: int = 120,
    skip: int = 5,
    rebalance_period: int = 20,
    signal: str = "raw",
) -> pd.DataFrame:
    from strategy_lib.data import get_loader
    panel = get_loader("cn_etf").load_many(V2_SYMBOLS, since=since, until=until)
    rows = []
    res_s3 = _run_s3(panel, V2_SYMBOLS, rebalance_period, 100_000)
    r_s3 = _portfolio_returns(res_s3.portfolio)
    for a in alphas:
        res = _run_v2(
            panel, symbols=V2_SYMBOLS,
            lookback=lookback, skip=skip, alpha=a,
            w_min=0.03, w_max=0.30,
            signal=signal, vol_lookback=60,
            rebalance_period=rebalance_period, init_cash=100_000,
        )
        r = _portfolio_returns(res.portfolio)
        common = r.index.intersection(r_s3.index)
        r_, r_s3_ = r.loc[common], r_s3.loc[common]
        m = _annualized_metrics(r_)
        ir = _info_ratio(r_, r_s3_)
        active = _mean_active_w(res.target_weights, len(V2_SYMBOLS))
        turn = _annual_turnover(res.target_weights.ffill().fillna(0.0), res.rebalance_dates)
        rows.append({
            "alpha": a,
            "CAGR": m["cagr"], "Vol": m["vol"], "Sharpe": m["sharpe"],
            "MaxDD": m["max_dd"], "Calmar": m["calmar"],
            "TotalRet": m["total_return"],
            "vs_S3_alpha_ann": ir["alpha_ann"],
            "vs_S3_IR": ir["ir"], "vs_S3_TE": ir["te"], "vs_S3_t": ir["t_stat"],
            "Turnover/yr": turn,
            "mean_|Δw|": active,
        })
    return pd.DataFrame(rows)


def run_lookback_sweep(
    since: str = "2020-01-01",
    until: str = "2024-12-31",
    lookbacks: tuple[int, ...] = (20, 60, 120, 250),
    skip: int = 5,
    alpha: float = 1.0,
    rebalance_period: int = 20,
    signal: str = "raw",
) -> pd.DataFrame:
    from strategy_lib.data import get_loader
    panel = get_loader("cn_etf").load_many(V2_SYMBOLS, since=since, until=until)
    res_s3 = _run_s3(panel, V2_SYMBOLS, rebalance_period, 100_000)
    r_s3 = _portfolio_returns(res_s3.portfolio)
    rows = []
    for lb in lookbacks:
        res = _run_v2(
            panel, symbols=V2_SYMBOLS,
            lookback=lb, skip=skip, alpha=alpha,
            w_min=0.03, w_max=0.30,
            signal=signal, vol_lookback=60,
            rebalance_period=rebalance_period, init_cash=100_000,
        )
        r = _portfolio_returns(res.portfolio)
        common = r.index.intersection(r_s3.index)
        r_, r_s3_ = r.loc[common], r_s3.loc[common]
        m = _annualized_metrics(r_)
        ir = _info_ratio(r_, r_s3_)
        rows.append({
            "lookback": lb,
            "CAGR": m["cagr"], "Sharpe": m["sharpe"],
            "MaxDD": m["max_dd"], "vs_S3_alpha_ann": ir["alpha_ann"],
            "vs_S3_IR": ir["ir"], "vs_S3_t": ir["t_stat"],
            "mean_|Δw|": _mean_active_w(res.target_weights, len(V2_SYMBOLS)),
        })
    return pd.DataFrame(rows)


def run_signal_sweep(
    since: str = "2020-01-01",
    until: str = "2024-12-31",
    rebalance_period: int = 20,
) -> pd.DataFrame:
    """Compare raw vs vol_adj signal at default lookback."""
    from strategy_lib.data import get_loader
    panel = get_loader("cn_etf").load_many(V2_SYMBOLS, since=since, until=until)
    res_s3 = _run_s3(panel, V2_SYMBOLS, rebalance_period, 100_000)
    r_s3 = _portfolio_returns(res_s3.portfolio)
    rows = []
    for sig in ("raw", "vol_adj"):
        res = _run_v2(
            panel, symbols=V2_SYMBOLS,
            lookback=120, skip=5, alpha=1.0,
            w_min=0.03, w_max=0.30,
            signal=sig, vol_lookback=60,
            rebalance_period=rebalance_period, init_cash=100_000,
        )
        r = _portfolio_returns(res.portfolio)
        common = r.index.intersection(r_s3.index)
        r_, r_s3_ = r.loc[common], r_s3.loc[common]
        m = _annualized_metrics(r_)
        ir = _info_ratio(r_, r_s3_)
        rows.append({
            "signal": sig,
            "CAGR": m["cagr"], "Sharpe": m["sharpe"], "MaxDD": m["max_dd"],
            "vs_S3_IR": ir["ir"], "vs_S3_alpha_ann": ir["alpha_ann"],
            "vs_S3_t": ir["t_stat"],
        })
    return pd.DataFrame(rows)


# -----------------------------------------------------------------------------
# Plots
# -----------------------------------------------------------------------------
def _save_plots(out: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    rs = out["returns"]

    # 1) Equity curve: v2 / v1 / S3 / BH
    fig, ax = plt.subplots(figsize=(11, 5.2))
    for key, label, color, lw in [
        ("v2", "S4 v2 (11 pool)", "#1f77b4", 1.7),
        ("v1", "S4 v1 (6 pool, lb=20)", "#ff7f0e", 1.3),
        ("s3", "S3 equal_rebal (11 pool)", "#2ca02c", 1.3),
        ("bh", "510300 BH", "#d62728", 1.1),
    ]:
        nav = (1 + rs[key]).cumprod()
        ax.plot(nav.index, nav.values, label=label, linewidth=lw, color=color, alpha=0.9)
    ax.set_title("Equity Curve  (start=1.0)")
    ax.set_ylabel("NAV")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(ARTIFACTS / "equity_curve.png", dpi=130)
    plt.close(fig)

    # 2) Drawdown
    fig, ax = plt.subplots(figsize=(11, 4))
    for key, label, color in [
        ("v2", "S4 v2", "#1f77b4"),
        ("v1", "S4 v1", "#ff7f0e"),
        ("s3", "S3 equal_rebal", "#2ca02c"),
        ("bh", "510300 BH", "#d62728"),
    ]:
        cum = (1 + rs[key]).cumprod()
        dd = cum / cum.cummax() - 1
        ax.plot(dd.index, dd.values, label=label, linewidth=1.2, color=color, alpha=0.85)
    ax.set_title("Drawdown")
    ax.set_ylabel("Drawdown")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(ARTIFACTS / "drawdown.png", dpi=130)
    plt.close(fig)

    # 3) Weight evolution (v2 11 assets, stacked area)
    res_v2 = out["res_v2"]
    syms = list(res_v2.target_weights.columns)
    w_held = res_v2.target_weights.ffill().fillna(0.0)
    fig, ax = plt.subplots(figsize=(12, 5.2))
    colors = list(plt.get_cmap("tab20").colors[: len(syms)])
    ax.stackplot(w_held.index, w_held.T.values, labels=syms, colors=colors, alpha=0.9)
    ax.set_ylim(0, 1)
    ax.set_title("Weight Evolution — S4 v2 (11 ETFs, held weights)")
    ax.set_ylabel("Weight")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.10), ncol=6, fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(ARTIFACTS / "weight_evolution.png", dpi=130)
    plt.close(fig)

    # 4) Tilt strength: v1 vs v2 z-score histograms (factor distribution)
    from strategy_lib.strategies.cn_etf_momentum_tilt import MomentumTiltStrategy
    from strategy_lib.strategies.cn_etf_momentum_tilt_v2 import (
        MomentumTiltV2Strategy,
    )

    cfg = out["config"]
    diag_v2 = MomentumTiltV2Strategy(
        symbols=V2_SYMBOLS,
        rebalance_period=cfg["rebalance_period"],
        lookback=cfg["lookback"], skip=cfg["skip"],
        alpha=cfg["alpha"], w_min=cfg["w_min"], w_max=cfg["w_max"],
        signal=cfg["signal"], vol_lookback=cfg["vol_lookback"],
    )
    diag_v1 = MomentumTiltStrategy(
        symbols=V1_SYMBOLS,
        rebalance_period=cfg["rebalance_period"],
        lookback=20, alpha=1.0, w_min=0.05, w_max=0.40,
    )

    panel_v2 = out["panel_v2"]
    panel_v1 = out["panel_v1"]
    rebal_w_v2 = out["res_v2"].target_weights.dropna(how="all")
    rebal_w_v1 = out["res_v1"].target_weights.dropna(how="all")

    z_v2_rows = []
    for d in rebal_w_v2.index:
        sliced = MomentumTiltV2Strategy._slice_strict(panel_v2, pd.Timestamp(d))
        scores = diag_v2._momentum_scores(sliced)
        z = diag_v2._zscore(scores).fillna(0.0)
        z_v2_rows.append(z.reindex(V2_SYMBOLS).values)
    z_v2 = np.asarray(z_v2_rows).flatten()

    z_v1_rows = []
    for d in rebal_w_v1.index:
        scores = diag_v1._momentum_scores(pd.Timestamp(d), panel_v1)
        z = diag_v1._zscore(scores).fillna(0.0)
        z_v1_rows.append(z.reindex(V1_SYMBOLS).values)
    z_v1 = np.asarray(z_v1_rows).flatten()

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6))
    axes[0].hist(z_v1, bins=25, color="#ff7f0e", alpha=0.7, edgecolor="white", label="v1 (lb=20, 6 pool)")
    axes[0].hist(z_v2, bins=25, color="#1f77b4", alpha=0.7, edgecolor="white", label=f"v2 (lb={cfg['lookback']}, skip={cfg['skip']}, 11 pool)")
    axes[0].axvline(0, color="black", linewidth=0.8)
    axes[0].set_title("Momentum z-score distribution: v1 vs v2")
    axes[0].set_xlabel("z-score")
    axes[0].grid(alpha=0.3)
    axes[0].legend()

    # Active weight deviation distribution
    n_v2 = len(V2_SYMBOLS); n_v1 = len(V1_SYMBOLS)
    dev_v2 = (rebal_w_v2 - 1.0 / n_v2).values.flatten()
    dev_v1 = (rebal_w_v1 - 1.0 / n_v1).values.flatten()
    axes[1].hist(dev_v1, bins=25, color="#ff7f0e", alpha=0.7, edgecolor="white",
                 label=f"v1 mean|Δw|={out['active']['v1']:.4f}")
    axes[1].hist(dev_v2, bins=25, color="#1f77b4", alpha=0.7, edgecolor="white",
                 label=f"v2 mean|Δw|={out['active']['v2']:.4f}")
    axes[1].axvline(0, color="black", linewidth=0.8)
    axes[1].set_title("Active weight deviation w_i − 1/N")
    axes[1].set_xlabel("w − 1/N")
    axes[1].grid(alpha=0.3)
    axes[1].legend()

    fig.tight_layout()
    fig.savefig(ARTIFACTS / "tilt_strength.png", dpi=130)
    plt.close(fig)

    # 5) Pool ablation — v2 on 11 pool vs v2 on 6 pool
    fig, ax = plt.subplots(figsize=(11, 5))
    nav_v2 = (1 + rs["v2"]).cumprod()
    nav_v2_old = (1 + rs["v2_old_pool"]).cumprod()
    nav_s3 = (1 + rs["s3"]).cumprod()
    nav_v1 = (1 + rs["v1"]).cumprod()
    ax.plot(nav_v2.index, nav_v2.values, label="v2 params, 11 pool (default)", color="#1f77b4", linewidth=1.7)
    ax.plot(nav_v2_old.index, nav_v2_old.values, label="v2 params, 6 pool (ablation)", color="#9467bd", linewidth=1.4)
    ax.plot(nav_v1.index, nav_v1.values, label="v1 params, 6 pool", color="#ff7f0e", linewidth=1.2, alpha=0.85)
    ax.plot(nav_s3.index, nav_s3.values, label="S3 equal, 11 pool", color="#2ca02c", linewidth=1.2, alpha=0.85)
    ax.set_title("Pool ablation: v2 params on 11 vs 6 pool")
    ax.set_ylabel("NAV (start=1)")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(ARTIFACTS / "pool_ablation.png", dpi=130)
    plt.close(fig)


# -----------------------------------------------------------------------------
# Pretty print
# -----------------------------------------------------------------------------
def _print_table(rows, cols, title=""):
    if title:
        print(f"\n=== {title} ===")
    widths = {c: max(len(c), max((len(str(r.get(c, ""))) for r in rows), default=0)) for c in cols}
    print("  ".join(c.ljust(widths[c]) for c in cols))
    print("  ".join("-" * widths[c] for c in cols))
    for r in rows:
        print("  ".join(str(r.get(c, "")).ljust(widths[c]) for c in cols))


def _fmt(v, pct=False, digits=4):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    if pct:
        return f"{v * 100:.2f}%"
    return f"{v:.{digits}f}"


def print_real_summary(out: dict) -> None:
    cfg = out["config"]
    m = out["metrics"]
    print(f"\nConfig: since={cfg['since']} until={cfg['until']} rebal={cfg['rebalance_period']}")
    print(f"        v2: lookback={cfg['lookback']} skip={cfg['skip']} alpha={cfg['alpha']} "
          f"w_min={cfg['w_min']} w_max={cfg['w_max']} signal={cfg['signal']} (vol_lb={cfg['vol_lookback']})")

    rows = []
    for key, name, n_pool in [
        ("v2", "S4 v2 (11 pool)", len(V2_SYMBOLS)),
        ("v2_old_pool", "S4 v2 on old 6 pool", len(V1_SYMBOLS)),
        ("v1", "S4 v1 (6 pool, lb=20)", len(V1_SYMBOLS)),
        ("s3", "S3 equal_rebal (11 pool)", len(V2_SYMBOLS)),
        ("s3_old", "S3 equal_rebal (6 pool)", len(V1_SYMBOLS)),
        ("bh", "510300 BH", 1),
    ]:
        mm = m[key]
        rows.append({
            "strategy": name,
            "final_NAV": _fmt(mm["final_value_factor"]),
            "total_ret": _fmt(mm["total_return"], pct=True),
            "CAGR": _fmt(mm["cagr"], pct=True),
            "Vol": _fmt(mm["vol"], pct=True),
            "Sharpe": _fmt(mm["sharpe"]),
            "MaxDD": _fmt(mm["max_dd"], pct=True),
            "Calmar": _fmt(mm["calmar"]),
        })
    _print_table(rows,
                 ["strategy", "final_NAV", "total_ret", "CAGR", "Vol", "Sharpe", "MaxDD", "Calmar"],
                 title="Performance")

    print("\n=== vs S3 equal_rebal on 11 pool (factor effectiveness) ===")
    ir = m["vs_s3"]
    print(f"  alpha_ann = {_fmt(ir['alpha_ann'], pct=True)}  IR = {_fmt(ir['ir'])}  "
          f"TE = {_fmt(ir['te'], pct=True)}  t-stat = {_fmt(ir['t_stat'])}  n = {ir['n']}")

    print("\n=== v2 vs v1 (head-to-head, different pool/params) ===")
    iv = m["vs_v1"]
    print(f"  alpha_ann = {_fmt(iv['alpha_ann'], pct=True)}  IR = {_fmt(iv['ir'])}  "
          f"TE = {_fmt(iv['te'], pct=True)}  t-stat = {_fmt(iv['t_stat'])}")

    print("\n=== Pool ablation: v2 params on 6 pool vs S3 on 6 pool ===")
    iv2 = m["v2_old_vs_s3_old"]
    print(f"  alpha_ann = {_fmt(iv2['alpha_ann'], pct=True)}  IR = {_fmt(iv2['ir'])}  "
          f"t-stat = {_fmt(iv2['t_stat'])}")

    print("\n=== vs 510300 BH (absolute benchmark) ===")
    ib = m["vs_bh"]
    print(f"  alpha_ann = {_fmt(ib['alpha_ann'], pct=True)}  IR = {_fmt(ib['ir'])}  "
          f"TE = {_fmt(ib['te'], pct=True)}  t-stat = {_fmt(ib['t_stat'])}")

    print("\n=== Yearly returns ===")
    with pd.option_context("display.float_format", lambda x: f"{x*100:6.2f}%"):
        print(out["yearly"].to_string())

    print("\n=== Active weight & turnover ===")
    print(f"  v2 mean|Δw|         = {out['active']['v2']:.4f}")
    print(f"  v1 mean|Δw|         = {out['active']['v1']:.4f}")
    print(f"  v2 (6 pool) mean|Δw|= {out['active']['v2_old_pool']:.4f}")
    print(f"  v2 turnover/yr      = {out['turnover']['v2']:.4f}")
    print(f"  v1 turnover/yr      = {out['turnover']['v1']:.4f}")
    print(f"  v2 (6 pool) turn/yr = {out['turnover']['v2_old_pool']:.4f}")


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=False)

    sub.add_parser("smoke", help="synthetic-panel smoke test (default)")

    p_real = sub.add_parser("real", help="real-data backtest")
    p_real.add_argument("--since", default="2020-01-01")
    p_real.add_argument("--until", default="2024-12-31")
    p_real.add_argument("--rebalance", type=int, default=20)
    p_real.add_argument("--lookback", type=int, default=120)
    p_real.add_argument("--skip", type=int, default=5)
    p_real.add_argument("--alpha", type=float, default=1.0)
    p_real.add_argument("--w-min", type=float, default=0.03)
    p_real.add_argument("--w-max", type=float, default=0.30)
    p_real.add_argument("--signal", default="raw", choices=["raw", "vol_adj"])
    p_real.add_argument("--vol-lookback", type=int, default=60)
    p_real.add_argument("--no-plots", action="store_true")

    p_sweep = sub.add_parser("sweep", help="alpha + lookback + signal sensitivity")
    p_sweep.add_argument("--since", default="2020-01-01")
    p_sweep.add_argument("--until", default="2024-12-31")

    args = p.parse_args(argv)
    if args.cmd in (None, "smoke"):
        return _smoke_main()

    if args.cmd == "real":
        out = run_real(
            since=args.since, until=args.until,
            rebalance_period=args.rebalance,
            lookback=args.lookback, skip=args.skip,
            alpha=args.alpha, w_min=args.w_min, w_max=args.w_max,
            signal=args.signal, vol_lookback=args.vol_lookback,
            save_plots=not args.no_plots,
        )
        print_real_summary(out)
        return 0

    if args.cmd == "sweep":
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        print("\n=== alpha sensitivity (lookback=120, skip=5, raw, 11 pool) ===")
        df_a = run_alpha_sweep(since=args.since, until=args.until)
        with pd.option_context("display.float_format", lambda x: f"{x:.4f}", "display.width", 160):
            print(df_a.to_string(index=False))

        print("\n=== lookback sensitivity (alpha=1, skip=5, raw, 11 pool) ===")
        df_l = run_lookback_sweep(since=args.since, until=args.until)
        with pd.option_context("display.float_format", lambda x: f"{x:.4f}", "display.width", 160):
            print(df_l.to_string(index=False))

        print("\n=== signal type comparison (lookback=120, alpha=1, 11 pool) ===")
        df_s = run_signal_sweep(since=args.since, until=args.until)
        with pd.option_context("display.float_format", lambda x: f"{x:.4f}", "display.width", 160):
            print(df_s.to_string(index=False))

        df_a.to_csv(ARTIFACTS / "alpha_sweep.csv", index=False)
        df_l.to_csv(ARTIFACTS / "lookback_sweep.csv", index=False)
        df_s.to_csv(ARTIFACTS / "signal_sweep.csv", index=False)
        print(f"\n(sweep tables saved to {ARTIFACTS})")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
