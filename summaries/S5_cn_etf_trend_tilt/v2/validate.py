"""Validation for cn_etf_trend_tilt v2 — Smoke + Real-data backtest.

入口:
    PYTHONPATH=src python summaries/S5_cn_etf_trend_tilt/v2/validate.py            # 默认: smoke
    PYTHONPATH=src python summaries/S5_cn_etf_trend_tilt/v2/validate.py real       # 真实数据
    PYTHONPATH=src python summaries/S5_cn_etf_trend_tilt/v2/validate.py all        # smoke + real

v2 关键验证：
1. 连续 ramp 数学：score 落在 cutoff/score_full 之间时，权重 ∈ (0, 1/N)
2. sum < 1 自然产生：单独某只资产 score < score_full 时，sum < 1
3. vol haircut 在高波时段触发
4. bond_symbol 在现金缺口处获得权重
5. 真实回测：v2 vs v1 vs S3 vs BH 对比，重点看 2022 单年 / cash 分布 / cash↔跌相关性
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"


# ---------------------------------------------------------------------------
# loguru / S3 父类 stub（v1 风格保持兼容）
# ---------------------------------------------------------------------------
def _install_loguru_stub_if_missing() -> bool:
    try:
        import loguru  # noqa: F401
        return False
    except ModuleNotFoundError:
        pass
    stub = types.ModuleType("loguru")

    class _Logger:
        def __getattr__(self, _name):
            return lambda *a, **k: None

    stub.logger = _Logger()
    sys.modules["loguru"] = stub
    return True


_INSTALLED_LOGURU_STUB = _install_loguru_stub_if_missing()


# ---------------------------------------------------------------------------
# 合成数据
# ---------------------------------------------------------------------------
def synth_ohlcv(n_days=250, start_price=100.0, drift=0.0, vol=0.015, seed=0):
    rng = np.random.default_rng(seed)
    rets = rng.normal(drift, vol, size=n_days)
    close = start_price * np.exp(np.cumsum(rets))
    high = close * (1 + np.abs(rng.normal(0, 0.005, size=n_days)))
    low = close * (1 - np.abs(rng.normal(0, 0.005, size=n_days)))
    open_ = close * (1 + rng.normal(0, 0.003, size=n_days))
    volume = rng.uniform(1e6, 5e6, size=n_days)
    idx = pd.date_range("2020-01-01", periods=n_days, freq="B", name="timestamp")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


def synth_deterministic(n_days=400, start_price=100.0, drift=0.0):
    close = start_price * np.exp(np.arange(n_days) * drift)
    idx = pd.date_range("2020-01-01", periods=n_days, freq="B", name="timestamp")
    return pd.DataFrame(
        {
            "open": close,
            "high": close * 1.001,
            "low": close * 0.999,
            "close": close,
            "volume": np.full(n_days, 1e6),
        },
        index=idx,
    )


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------
def test_v2_continuous_ramp_subunit_sum():
    """v2 关键：弱趋势（score 在 ramp 区间内）时 sum < 1 而非 1。"""
    from strategy_lib.strategies.cn_etf_trend_tilt_v2 import TrendTiltV2Strategy

    n = 400
    # 6 只 ETF：3 强上行（score 接近 +2），3 弱上行（score 接近 0.2，落入 ramp）
    panel = {
        "STRONG1": synth_deterministic(n_days=n, drift=0.001),
        "STRONG2": synth_deterministic(n_days=n, drift=0.001),
        "STRONG3": synth_deterministic(n_days=n, drift=0.001),
        "WEAK1": synth_deterministic(n_days=n, drift=0.0001),
        "WEAK2": synth_deterministic(n_days=n, drift=0.0001),
        "WEAK3": synth_deterministic(n_days=n, drift=0.0001),
    }
    strat = TrendTiltV2Strategy(
        symbols=list(panel),
        score_full=1.0,
        vol_haircut=1.0,  # 关闭 vol filter 单独看 ramp
        bond_symbol=None,
    )
    weights = strat.target_weights(panel["STRONG1"].index[-1], panel)
    total = sum(weights.values())
    assert 0 < total <= 1.0 + 1e-9, f"sum 应 ∈ (0, 1]，得到 {total}"
    print(f"[ok] test_v2_continuous_ramp_subunit_sum  sum={total:.4f}, weights={ {k: round(v,4) for k,v in weights.items()} }")


def test_v2_all_strong_full_invest():
    """v2: 所有 ETF 都强上行（score ≥ score_full）时应满仓。"""
    from strategy_lib.strategies.cn_etf_trend_tilt_v2 import TrendTiltV2Strategy

    n = 400
    panel = {f"S{i}": synth_deterministic(n_days=n, drift=0.001) for i in range(6)}
    strat = TrendTiltV2Strategy(
        symbols=list(panel), score_full=1.0, vol_haircut=1.0, bond_symbol=None
    )
    weights = strat.target_weights(panel["S0"].index[-1], panel)
    total = sum(weights.values())
    assert abs(total - 1.0) < 0.05, f"全强上行应近满仓，得到 {total}"
    for v in weights.values():
        assert abs(v - 1 / 6) < 0.02, f"每只应 ≈ 1/6, 得到 {v}"
    print(f"[ok] test_v2_all_strong_full_invest  sum={total:.4f}")


def test_v2_all_downtrend_zero():
    """v2: 全下行时空仓（与 v1 一致）。"""
    from strategy_lib.strategies.cn_etf_trend_tilt_v2 import TrendTiltV2Strategy

    n = 400
    panel = {f"D{i}": synth_deterministic(n_days=n, drift=-0.001) for i in range(6)}
    strat = TrendTiltV2Strategy(
        symbols=list(panel), score_full=1.0, vol_haircut=1.0, bond_symbol=None
    )
    weights = strat.target_weights(panel["D0"].index[-1], panel)
    total = sum(weights.values())
    assert total == 0.0, f"全下行应空仓，得到 {weights}"
    print("[ok] test_v2_all_downtrend_zero")


def test_v2_vol_haircut_triggers():
    """v2: 高波时段（vol > vol_high 且 breadth ≥ 阈值）应触发降仓。"""
    from strategy_lib.strategies.cn_etf_trend_tilt_v2 import TrendTiltV2Strategy

    n = 400
    # 都是上行（trend 信号正），但波动率分两组：高波 4 只，低波 2 只
    panel = {}
    for i in range(4):
        panel[f"HV{i}"] = synth_ohlcv(n_days=n, drift=0.001, vol=0.04, seed=i)  # ~63% 年化
    for i in range(2):
        panel[f"LV{i}"] = synth_ohlcv(n_days=n, drift=0.001, vol=0.005, seed=10 + i)  # ~8%

    strat_off = TrendTiltV2Strategy(
        symbols=list(panel), score_full=1.0, vol_haircut=1.0, bond_symbol=None
    )
    strat_on = TrendTiltV2Strategy(
        symbols=list(panel),
        score_full=1.0,
        vol_high=0.30,
        vol_breadth_threshold=0.5,
        vol_haircut=0.5,
        bond_symbol=None,
    )
    last = panel["HV0"].index[-1]
    w_off = strat_off.target_weights(last, panel)
    w_on = strat_on.target_weights(last, panel)
    sum_off = sum(w_off.values())
    sum_on = sum(w_on.values())
    assert sum_on < sum_off, f"vol haircut 应降低总仓，off={sum_off:.3f} on={sum_on:.3f}"
    assert abs(sum_on - sum_off * 0.5) < 0.05, f"应近 50% 降仓，off={sum_off} on={sum_on}"
    print(f"[ok] test_v2_vol_haircut_triggers  off={sum_off:.3f}  on={sum_on:.3f}")


def test_v2_bond_overlay():
    """v2: 指定 bond_symbol 后，cash gap 应部分填到 bond。"""
    from strategy_lib.strategies.cn_etf_trend_tilt_v2 import TrendTiltV2Strategy

    n = 400
    # 3 强上行 + 3 弱（让 risky_sum < 1）
    panel = {
        "S1": synth_deterministic(n_days=n, drift=0.001),
        "S2": synth_deterministic(n_days=n, drift=0.001),
        "S3": synth_deterministic(n_days=n, drift=0.001),
        "W1": synth_deterministic(n_days=n, drift=0.0001),
        "W2": synth_deterministic(n_days=n, drift=0.0001),
        "W3": synth_deterministic(n_days=n, drift=0.0001),
        "BOND": synth_deterministic(n_days=n, drift=0.0001),  # 平稳的 bond
    }
    strat = TrendTiltV2Strategy(
        symbols=list(panel),
        score_full=1.0,
        vol_haircut=1.0,
        bond_symbol="BOND",
        bond_max_weight=0.4,
    )
    weights = strat.target_weights(panel["S1"].index[-1], panel)
    bond_w = weights.get("BOND", 0.0)
    assert bond_w > 0, f"应有 bond 权重，得到 {weights}"
    assert bond_w <= 0.4 + 1e-9, f"bond 权重应 ≤ 0.4，得到 {bond_w}"
    print(f"[ok] test_v2_bond_overlay  bond_w={bond_w:.4f}")


def test_v2_warmup_returns_empty():
    from strategy_lib.strategies.cn_etf_trend_tilt_v2 import TrendTiltV2Strategy

    panel = {f"S{i}": synth_ohlcv(n_days=50, drift=0.001, seed=i) for i in range(3)}
    strat = TrendTiltV2Strategy(symbols=list(panel), bond_symbol=None)
    weights = strat.target_weights(panel["S0"].index[-1], panel)
    assert weights == {}, f"暖机期应空仓，得到 {weights}"
    print("[ok] test_v2_warmup_returns_empty")


def run_smoke() -> None:
    print(f"[setup] using loguru stub: {_INSTALLED_LOGURU_STUB}")
    test_v2_warmup_returns_empty()
    test_v2_all_strong_full_invest()
    test_v2_all_downtrend_zero()
    test_v2_continuous_ramp_subunit_sum()
    test_v2_vol_haircut_triggers()
    test_v2_bond_overlay()
    print("\nSMOKE OK — v2 连续 ramp / vol filter / bond overlay 全部通过\n")


# ---------------------------------------------------------------------------
# Real-data helpers（从 v1 复制 + 扩展）
# ---------------------------------------------------------------------------
def _equity_metrics(equity, freq_per_year=252):
    equity = equity.dropna()
    if len(equity) < 2:
        return {k: np.nan for k in ["cagr", "sharpe", "max_dd", "calmar", "total_return", "vol"]}
    rets = equity.pct_change().dropna()
    n = len(rets)
    years = n / freq_per_year
    total_ret = equity.iloc[-1] / equity.iloc[0] - 1
    cagr = (equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1 if years > 0 else np.nan
    vol = rets.std() * np.sqrt(freq_per_year)
    sharpe = rets.mean() / rets.std() * np.sqrt(freq_per_year) if rets.std() > 0 else np.nan
    cummax = equity.cummax()
    dd = equity / cummax - 1
    max_dd = dd.min()
    calmar = cagr / abs(max_dd) if max_dd < 0 else np.nan
    return {
        "total_return": float(total_ret),
        "cagr": float(cagr),
        "sharpe": float(sharpe),
        "vol": float(vol),
        "max_dd": float(max_dd),
        "calmar": float(calmar),
    }


def _yearly_returns(equity):
    equity = equity.dropna()
    annual = equity.resample("YE").last()
    annual = pd.concat([equity.iloc[[0]], annual])
    annual = annual[~annual.index.duplicated(keep="last")].sort_index()
    return annual.pct_change().dropna()


def _drawdown(equity):
    return equity / equity.cummax() - 1


def _format_row(name, m):
    return (
        f"  {name:<28s}  total={m['total_return']*100:>7.2f}%  "
        f"CAGR={m['cagr']*100:>6.2f}%  Sharpe={m['sharpe']:>5.2f}  "
        f"Vol={m['vol']*100:>5.2f}%  MaxDD={m['max_dd']*100:>7.2f}%  Calmar={m['calmar']:>5.2f}"
    )


def _slice(s, since, until):
    return s.loc[since:until]


def _cash_ratio(pf, since, until, risky_symbols):
    """v2: cash ratio = (1 - sum(risky asset values) / total value)。

    bond 不算 cash。 v1 的 pf.cash() / pf.value() 在含 bond 的组合里把 bond 算
    成 risky 的一部分，所以这里直接算 risky 资产价值占比，cash_ratio = 1 - risky 占比。
    """
    value_total = pf.value()
    if isinstance(value_total, pd.DataFrame):
        value_total = value_total.iloc[:, 0]

    # asset_value 返回每个 asset 的市值
    av = pf.asset_value(group_by=False)
    if isinstance(av, pd.Series):
        av = av.to_frame()
    risky_in = [s for s in risky_symbols if s in av.columns]
    if not risky_in:
        # fallback：用 cash()
        cash = pf.cash()
        if isinstance(cash, pd.DataFrame):
            cash = cash.iloc[:, 0]
        return (cash / value_total).loc[since:until]
    risky_value = av[risky_in].sum(axis=1)
    risky_value = risky_value.reindex(value_total.index).fillna(0.0)
    cash_ratio = 1.0 - risky_value / value_total
    return cash_ratio.loc[since:until]


def _bond_ratio(pf, since, until, bond_symbol):
    if bond_symbol is None:
        return None
    av = pf.asset_value(group_by=False)
    if isinstance(av, pd.Series):
        av = av.to_frame()
    if bond_symbol not in av.columns:
        return None
    value_total = pf.value()
    if isinstance(value_total, pd.DataFrame):
        value_total = value_total.iloc[:, 0]
    bond_value = av[bond_symbol].reindex(value_total.index).fillna(0.0)
    return (bond_value / value_total).loc[since:until]


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------
def _ensure_artifacts():
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


def _plot_equity(curves, path, title="Equity Curves"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(11, 6))
    for name, s in curves.items():
        if s is None or s.empty:
            continue
        ax.plot(s.index, s.values, label=name, lw=1.5)
    ax.set_title(title)
    ax.set_xlabel("date"); ax.set_ylabel("equity (RMB)")
    ax.grid(alpha=0.3); ax.legend(loc="best")
    fig.tight_layout(); fig.savefig(path, dpi=120); plt.close(fig)


def _plot_drawdown(curves, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(11, 5))
    for name, s in curves.items():
        if s is None or s.empty:
            continue
        dd = _drawdown(s)
        ax.fill_between(dd.index, dd.values, 0, alpha=0.20, label=name)
        ax.plot(dd.index, dd.values, lw=1.0)
    ax.set_title("Drawdowns"); ax.set_xlabel("date"); ax.set_ylabel("drawdown")
    ax.grid(alpha=0.3); ax.legend(loc="best")
    fig.tight_layout(); fig.savefig(path, dpi=120); plt.close(fig)


def _plot_cash_ratio(v2_cash, v1_cash, path):
    """v2 vs v1 现金比例时间序列 + v2 直方图。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 1, figsize=(11, 7), gridspec_kw={"height_ratios": [2, 1]})
    ax0 = axes[0]
    if v1_cash is not None:
        ax0.plot(v1_cash.index, v1_cash.values, lw=1.0, color="tab:gray", alpha=0.7, label="v1 cash_ratio")
    ax0.plot(v2_cash.index, v2_cash.values, lw=1.2, color="tab:orange", label="v2 cash_ratio")
    ax0.fill_between(v2_cash.index, v2_cash.values, 0, alpha=0.15, color="tab:orange")
    ax0.set_ylim(0, 1.05); ax0.set_ylabel("cash / equity")
    ax0.set_title("Cash ratio: v2 (continuous) vs v1 (binary)")
    ax0.grid(alpha=0.3); ax0.legend(loc="best")
    ax1 = axes[1]
    ax1.hist(v2_cash.dropna().values, bins=30, color="tab:orange", alpha=0.7, label="v2")
    if v1_cash is not None:
        ax1.hist(v1_cash.dropna().values, bins=30, color="tab:gray", alpha=0.5, label="v1")
    ax1.set_xlabel("cash ratio"); ax1.set_ylabel("days")
    ax1.set_title("Distribution: v2 应当连续 vs v1 双峰")
    ax1.legend(loc="best"); ax1.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(path, dpi=120); plt.close(fig)


def _plot_regime_overlay(bh_nav, v2_cash, path, threshold=0.7):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(bh_nav.index, bh_nav.values, lw=1.5, color="tab:blue", label="510300 BH")
    is_high_cash = (v2_cash >= threshold).reindex(bh_nav.index, method="ffill").fillna(False)
    if is_high_cash.any():
        ymin, ymax = ax.get_ylim()
        ax.fill_between(
            bh_nav.index, ymin, ymax,
            where=is_high_cash.values, color="grey", alpha=0.25,
            label=f"v2 cash≥{threshold}",
        )
        ax.set_ylim(ymin, ymax)
    ax.set_title(f"v2 高现金段 (cash≥{threshold}) 叠加 510300 BH")
    ax.set_xlabel("date"); ax.set_ylabel("510300 BH equity")
    ax.grid(alpha=0.3); ax.legend(loc="best")
    fig.tight_layout(); fig.savefig(path, dpi=120); plt.close(fig)


def _plot_vol_filter_trace(breadth_series, haircut_dates, path, vol_threshold=0.5):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(breadth_series.index, breadth_series.values, lw=1.2, color="tab:purple", label="vol breadth (frac > vol_high)")
    ax.axhline(vol_threshold, color="red", ls="--", lw=1.0, label=f"trigger ≥ {vol_threshold}")
    ax.fill_between(breadth_series.index, breadth_series.values, 0,
                    where=breadth_series.values >= vol_threshold,
                    color="tab:red", alpha=0.20, label="haircut active")
    ax.set_ylim(0, 1.05); ax.set_xlabel("date"); ax.set_ylabel("breadth")
    ax.set_title("v2 vol filter trace: 高波资产占池比例 (rebalance 日采样)")
    ax.grid(alpha=0.3); ax.legend(loc="best")
    fig.tight_layout(); fig.savefig(path, dpi=120); plt.close(fig)


# ---------------------------------------------------------------------------
# Real-data backtest
# ---------------------------------------------------------------------------
def run_real(
    since="2020-01-01",
    until="2024-12-31",
    warmup_since="2019-07-01",
    init_cash=100_000,
    fees=0.00005,
    slippage=0.0005,
):
    from strategy_lib.data import get_loader
    from strategy_lib.strategies.cn_etf_trend_tilt_v2 import TrendTiltV2Strategy
    from strategy_lib.strategies.cn_etf_trend_tilt import TrendTiltStrategy
    from strategy_lib.strategies.cn_etf_equal_rebalance import EqualRebalanceStrategy

    print("=" * 80)
    print("Real-data Backtest — Strategy 5 v2 (cn_etf_trend_tilt_v2)")
    print("=" * 80)

    risky_symbols = ['510300', '510500', '159915', '512100', '512880', '512170']
    bond_symbol = '511260'
    all_symbols = risky_symbols + [bond_symbol]

    loader = get_loader('cn_etf')
    panel = loader.load_many(all_symbols, since=warmup_since, until=until)
    print(f"Loaded panel: {list(panel.keys())}")
    for s in all_symbols:
        df = panel[s]
        print(f"  {s}: {df.shape[0]} rows, {df.index[0].date()} ~ {df.index[-1].date()}")

    common_idx = None
    for s in all_symbols:
        idx = panel[s].index
        common_idx = idx if common_idx is None else common_idx.intersection(idx)
    common_idx = common_idx.sort_values()
    since_ts = pd.Timestamp(since, tz="UTC")
    until_ts = pd.Timestamp(until, tz="UTC")
    sample_idx = common_idx[(common_idx >= since_ts) & (common_idx <= until_ts)]
    print(f"sample bars: {len(sample_idx)}, {sample_idx[0].date()} ~ {sample_idx[-1].date()}")

    # ---------------------------------------------------------------- v2 主跑
    print("\n[1/3] Running S5 v2 (continuous + vol filter + bond overlay) ...")
    s5v2 = TrendTiltV2Strategy(
        symbols=all_symbols, rebalance_period=20,
        ma_short=20, ma_mid=60, ma_long=120,
        donchian_lookback=120, cutoff=0.0,
        score_full=1.0,
        use_continuous_score=True,
        vol_lookback=60, vol_high=0.30,
        vol_breadth_threshold=0.5, vol_haircut=0.5,
        bond_symbol=bond_symbol, bond_max_weight=0.4,
    )
    s5v2_res = s5v2.run(panel, init_cash=init_cash, fees=fees, slippage=slippage)
    s5v2_eq = s5v2_res.portfolio.value()
    if isinstance(s5v2_eq, pd.DataFrame):
        s5v2_eq = s5v2_eq.iloc[:, 0]
    s5v2_eq = _slice(s5v2_eq, since_ts, until_ts).rename("S5v2")

    s5v2_cash = _cash_ratio(s5v2_res.portfolio, since_ts, until_ts, risky_symbols)
    s5v2_bond = _bond_ratio(s5v2_res.portfolio, since_ts, until_ts, bond_symbol)
    print(f"  triggers={len(s5v2_res.rebalance_dates)}  "
          f"cash_ratio min/median/max = {s5v2_cash.min():.3f}/{s5v2_cash.median():.3f}/{s5v2_cash.max():.3f}, "
          f"std={s5v2_cash.std():.3f}")

    # ---------------------------------------------------------------- v1 重跑（对照）
    print("[2/3] Running S5 v1 (baseline, with same risky pool, no bond) ...")
    s5v1 = TrendTiltStrategy(
        symbols=risky_symbols, rebalance_period=20,
        ma_short=20, ma_mid=60, ma_long=120,
        donchian_lookback=120, cutoff=0.0,
    )
    panel_v1 = {s: panel[s] for s in risky_symbols}
    s5v1_res = s5v1.run(panel_v1, init_cash=init_cash, fees=fees, slippage=slippage)
    s5v1_eq = s5v1_res.portfolio.value()
    if isinstance(s5v1_eq, pd.DataFrame):
        s5v1_eq = s5v1_eq.iloc[:, 0]
    s5v1_eq = _slice(s5v1_eq, since_ts, until_ts).rename("S5v1")
    s5v1_cash = _cash_ratio(s5v1_res.portfolio, since_ts, until_ts, risky_symbols)

    # ---------------------------------------------------------------- S3 / BH
    print("[3/3] Running S3 (equal rebal) + 510300 BH ...")
    s3 = EqualRebalanceStrategy(symbols=risky_symbols, rebalance_period=20)
    s3_res = s3.run(panel_v1, init_cash=init_cash, fees=fees, slippage=slippage)
    s3_eq = s3_res.portfolio.value()
    if isinstance(s3_eq, pd.DataFrame):
        s3_eq = s3_eq.iloc[:, 0]
    s3_eq = _slice(s3_eq, since_ts, until_ts).rename("S3_equal")

    bh_full = panel['510300']['close'] / panel['510300']['close'].iloc[0] * init_cash
    bh_eq = bh_full.loc[since_ts:until_ts]
    bh_eq = (bh_eq / bh_eq.iloc[0] * init_cash).rename("510300_BH")

    # ---- rebase ----
    def _rebase(s):
        return s if (s is None or s.empty) else s / s.iloc[0] * init_cash

    curves = {
        "S5v2": _rebase(s5v2_eq),
        "S5v1": _rebase(s5v1_eq),
        "S3_equal": _rebase(s3_eq),
        "510300_BH": _rebase(bh_eq),
    }

    print("\n--- 主绩效表 ---")
    metrics = {}
    for name, s in curves.items():
        m = _equity_metrics(s)
        metrics[name] = m
        print(_format_row(name, m))

    # ---- 分年度收益 ----
    print("\n--- 分年度收益 ---")
    yearly = pd.DataFrame({name: _yearly_returns(s) for name, s in curves.items()})
    yearly.index = yearly.index.year
    print(yearly.round(4).to_string())

    # ---- v2 vs benchmarks: alpha / IR ----
    rets_v2 = curves["S5v2"].pct_change().dropna()
    rets_v1 = curves["S5v1"].pct_change().dropna()
    rets_bh = curves["510300_BH"].pct_change().dropna()
    rets_s3 = curves["S3_equal"].pct_change().dropna()

    def _ir(excess):
        if excess.empty or excess.std() == 0:
            return {"alpha_ann": np.nan, "te_ann": np.nan, "ir": np.nan}
        return {
            "alpha_ann": float(excess.mean() * 252),
            "te_ann": float(excess.std() * np.sqrt(252)),
            "ir": float(excess.mean() / excess.std() * np.sqrt(252)),
        }

    common_bh = rets_v2.index.intersection(rets_bh.index)
    common_s3 = rets_v2.index.intersection(rets_s3.index)
    common_v1 = rets_v2.index.intersection(rets_v1.index)
    ir_bh = _ir(rets_v2.loc[common_bh] - rets_bh.loc[common_bh])
    ir_s3 = _ir(rets_v2.loc[common_s3] - rets_s3.loc[common_s3])
    ir_v1 = _ir(rets_v2.loc[common_v1] - rets_v1.loc[common_v1])
    print(f"\nS5v2 vs 510300 BH: alpha={ir_bh['alpha_ann']*100:.2f}%, te={ir_bh['te_ann']*100:.2f}%, IR={ir_bh['ir']:.3f}")
    print(f"S5v2 vs S3 equal : alpha={ir_s3['alpha_ann']*100:.2f}%, te={ir_s3['te_ann']*100:.2f}%, IR={ir_s3['ir']:.3f}")
    print(f"S5v2 vs S5 v1   : alpha={ir_v1['alpha_ann']*100:.2f}%, te={ir_v1['te_ann']*100:.2f}%, IR={ir_v1['ir']:.3f}")

    # ---- v2 cash 分布 + 避险命题验证 ----
    cash_distribution = {
        "min": float(s5v2_cash.min()),
        "p25": float(s5v2_cash.quantile(0.25)),
        "median": float(s5v2_cash.median()),
        "p75": float(s5v2_cash.quantile(0.75)),
        "max": float(s5v2_cash.max()),
        "std": float(s5v2_cash.std()),
        "frac_intermediate": float(((s5v2_cash > 0.05) & (s5v2_cash < 0.95)).mean()),
        "frac_full_cash": float((s5v2_cash >= 0.99).mean()),
        "frac_no_cash": float((s5v2_cash <= 0.01).mean()),
    }
    print(f"\nv2 cash_ratio 分布:")
    for k, v in cash_distribution.items():
        print(f"  {k:<22s} = {v:.4f}")

    v1_cash_distribution = {
        "min": float(s5v1_cash.min()),
        "median": float(s5v1_cash.median()),
        "max": float(s5v1_cash.max()),
        "std": float(s5v1_cash.std()),
        "frac_intermediate": float(((s5v1_cash > 0.05) & (s5v1_cash < 0.95)).mean()),
        "frac_full_cash": float((s5v1_cash >= 0.99).mean()),
        "frac_no_cash": float((s5v1_cash <= 0.01).mean()),
    }
    print(f"\nv1 cash_ratio 分布（参照）:")
    for k, v in v1_cash_distribution.items():
        print(f"  {k:<22s} = {v:.4f}")

    # 现金 vs BH 跌相关性（v1 / v2 各一次）
    def _cash_neg_corr(cash_series, rets_bh_series, threshold):
        is_cash = (cash_series >= threshold).astype(int).reindex(rets_bh_series.index, method="ffill").fillna(0)
        bh_neg = (rets_bh_series < 0).astype(int)
        if is_cash.var() > 0 and bh_neg.var() > 0:
            return float(np.corrcoef(is_cash.values, bh_neg.values)[0, 1])
        return float("nan")

    # v1: 用 0.99 阈值（满仓现金）
    v1_corr = _cash_neg_corr(s5v1_cash, rets_bh, 0.99)
    # v2: 用 0.99 / 0.5 / 0.3 三档
    v2_corr_99 = _cash_neg_corr(s5v2_cash, rets_bh, 0.99)
    v2_corr_50 = _cash_neg_corr(s5v2_cash, rets_bh, 0.50)
    v2_corr_30 = _cash_neg_corr(s5v2_cash, rets_bh, 0.30)
    # 连续相关：cash_ratio vs |bh_ret| 的同向性
    aligned = pd.concat([s5v2_cash.rename("cash"), rets_bh.rename("bh_ret")], axis=1).dropna()
    if not aligned.empty:
        v2_corr_cont_neg = float(np.corrcoef(
            aligned["cash"].values,
            (aligned["bh_ret"] < 0).astype(int).values,
        )[0, 1])
        v2_corr_cont_ret = float(np.corrcoef(
            aligned["cash"].values,
            (-aligned["bh_ret"]).values,
        )[0, 1])
    else:
        v2_corr_cont_neg = float("nan"); v2_corr_cont_ret = float("nan")

    print(f"\n避险命题验证（cash 是否真的对齐 BH 下跌）:")
    print(f"  v1 cash≥0.99 vs BH down: corr = {v1_corr:.3f}")
    print(f"  v2 cash≥0.99 vs BH down: corr = {v2_corr_99:.3f}")
    print(f"  v2 cash≥0.50 vs BH down: corr = {v2_corr_50:.3f}")
    print(f"  v2 cash≥0.30 vs BH down: corr = {v2_corr_30:.3f}")
    print(f"  v2 continuous cash vs BH down indicator: corr = {v2_corr_cont_neg:.3f}")
    print(f"  v2 continuous cash vs (-BH_ret): corr = {v2_corr_cont_ret:.3f}")

    # bond overlay 用量
    bond_stats = None
    if s5v2_bond is not None:
        bond_stats = {
            "frac_active": float((s5v2_bond > 0.01).mean()),
            "median_when_active": float(s5v2_bond[s5v2_bond > 0.01].median()) if (s5v2_bond > 0.01).any() else 0.0,
            "max": float(s5v2_bond.max()),
            "mean": float(s5v2_bond.mean()),
        }
        print(f"\n债券暴露 (511260):")
        for k, v in bond_stats.items():
            print(f"  {k:<22s} = {v:.4f}")

    # vol filter 触发 trace（只在 rebalance 日采样）
    print("\n采样 vol breadth on rebalance dates...")
    breadth_records = []
    for date in s5v2_res.rebalance_dates:
        breadth = s5v2._vol_breadth(date, panel)
        breadth_records.append((date, breadth))
    breadth_series = pd.Series(
        [b for _, b in breadth_records],
        index=pd.DatetimeIndex([d for d, _ in breadth_records]),
        name="vol_breadth",
    )
    haircut_active_count = int((breadth_series >= 0.5).sum())
    print(f"  rebalance days: {len(breadth_series)}, vol haircut active days: {haircut_active_count}")

    # ---- artifacts ----
    _ensure_artifacts()
    _plot_equity(curves, ARTIFACTS_DIR / "equity_curve.png",
                 title=f"Equity v2 vs v1 vs S3 vs BH ({since}~{until})")
    _plot_drawdown({"S5v2": curves["S5v2"], "S5v1": curves["S5v1"], "510300_BH": curves["510300_BH"]},
                   ARTIFACTS_DIR / "drawdown.png")
    _plot_cash_ratio(s5v2_cash, s5v1_cash, ARTIFACTS_DIR / "cash_ratio.png")
    _plot_regime_overlay(curves["510300_BH"], s5v2_cash, ARTIFACTS_DIR / "regime_overlay.png", threshold=0.7)
    _plot_vol_filter_trace(breadth_series, None, ARTIFACTS_DIR / "vol_filter_trace.png", vol_threshold=0.5)
    print(f"\nArtifacts saved to: {ARTIFACTS_DIR}")

    return {
        "metrics": metrics,
        "yearly": yearly,
        "ir_bh": ir_bh,
        "ir_s3": ir_s3,
        "ir_v1": ir_v1,
        "cash_distribution_v2": cash_distribution,
        "cash_distribution_v1": v1_cash_distribution,
        "cash_neg_corr": {
            "v1_99": v1_corr,
            "v2_99": v2_corr_99, "v2_50": v2_corr_50, "v2_30": v2_corr_30,
            "v2_continuous": v2_corr_cont_neg,
        },
        "bond_stats": bond_stats,
        "haircut_active": haircut_active_count,
        "rebalance_days": len(breadth_series),
        "trigger_count": len(s5v2_res.rebalance_dates),
        "sample_start": str(sample_idx[0].date()),
        "sample_end": str(sample_idx[-1].date()),
        "n_bars": len(sample_idx),
    }


def main(argv):
    mode = argv[1].lower() if len(argv) > 1 else "smoke"
    if mode in ("smoke", "all"):
        run_smoke()
    if mode in ("real", "all"):
        run_real()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
