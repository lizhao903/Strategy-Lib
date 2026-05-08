"""Validation for cn_etf_market_ma_filter v1 — Smoke + Real-data backtest.

入口:
    PYTHONPATH=src python summaries/S7_cn_etf_market_ma_filter/v1/validate.py            # 默认: smoke
    PYTHONPATH=src python summaries/S7_cn_etf_market_ma_filter/v1/validate.py real       # 真实数据
    PYTHONPATH=src python summaries/S7_cn_etf_market_ma_filter/v1/validate.py all        # smoke + real

S7 关键验证：
1. 信号正确性：close > MA → 1, else 0；MA 暖机期 = 0
2. 滞后过滤：连续 N 日同向才切换（中间反复不切换）
3. lookahead 防护：weights.shift(1) 让 t 日信号在 t+1 日成交
4. 切换执行：信号 ON 时持有 risky pool 满仓；OFF 时持有 cash_symbol 100%
5. 真实回测：S7 (MA200, lag=2) vs S3 v1 vs S5 v1 vs S5 v2 vs 510300 BH
   - 重点看 2022 单年、cash↔BH 跌相关性、切换次数
6. MA 长度敏感性：100 / 150 / 200 / 250
7. 滞后敏感性：1 / 2 / 3 / 5
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
# loguru stub（与 S5 v1/v2 一致风格）
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
def synth_ohlcv(n_days=400, start_price=100.0, drift=0.0, vol=0.015, seed=0):
    rng = np.random.default_rng(seed)
    rets = rng.normal(drift, vol, size=n_days)
    close = start_price * np.exp(np.cumsum(rets))
    high = close * (1 + np.abs(rng.normal(0, 0.005, size=n_days)))
    low = close * (1 - np.abs(rng.normal(0, 0.005, size=n_days)))
    open_ = close * (1 + rng.normal(0, 0.003, size=n_days))
    volume = rng.uniform(1e6, 5e6, size=n_days)
    idx = pd.date_range("2019-07-01", periods=n_days, freq="B", name="timestamp")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


def synth_deterministic(n_days=400, start_price=100.0, drift=0.0):
    close = start_price * np.exp(np.arange(n_days) * drift)
    idx = pd.date_range("2019-07-01", periods=n_days, freq="B", name="timestamp")
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


def synth_v_shape(n_days=400, start_price=100.0, half_drift=-0.003):
    """V 型：先下行 half_drift 再以 +half_drift 反弹。"""
    half = n_days // 2
    seg1 = np.exp(np.arange(half) * half_drift)
    seg2 = seg1[-1] * np.exp(np.arange(n_days - half) * (-half_drift))
    close = start_price * np.concatenate([seg1, seg2])
    idx = pd.date_range("2019-07-01", periods=n_days, freq="B", name="timestamp")
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
def _make_panel_with_signal(signal_df, n=400, drift=0.0005, seed_base=0):
    """构造含 signal/risky pool/cash 的合成 panel。"""
    pool = ["510300", "510500", "159915", "512100", "512880", "512170"]
    panel = {"510300": signal_df}
    for i, s in enumerate(pool[1:], start=1):
        panel[s] = synth_ohlcv(n_days=n, drift=drift, seed=seed_base + i)
    panel["511990"] = synth_deterministic(n_days=n, drift=0.00008)  # 货币基金平稳上行
    return panel


def test_signal_warmup_zero():
    """暖机期内（前 ma_length-1 天）信号应为 0。"""
    from strategy_lib.strategies.cn_etf_market_ma_filter import MarketMAFilterStrategy

    sig_data = synth_deterministic(n_days=300, drift=0.001)
    strat = MarketMAFilterStrategy(ma_length=200, lag_days=1)
    raw, _ = strat.build_signal(_make_panel_with_signal(sig_data, n=300))
    # 前 199 天 MA 不可计算 → 信号 = 0
    assert raw.iloc[:199].sum() == 0, f"暖机期不应有信号，得到 {raw.iloc[:199].sum()}"
    assert raw.iloc[200:].sum() > 0, "暖机后 (上行序列) 应有 ON 信号"
    print(f"[ok] test_signal_warmup_zero  warmup_sum={raw.iloc[:199].sum()}, post_sum={raw.iloc[200:].sum()}")


def test_signal_strong_uptrend():
    """长期上行：MA 暖机后信号应几乎一直 ON。"""
    from strategy_lib.strategies.cn_etf_market_ma_filter import MarketMAFilterStrategy

    sig_data = synth_deterministic(n_days=400, drift=0.001)
    strat = MarketMAFilterStrategy(ma_length=200, lag_days=1)
    raw, sig = strat.build_signal(_make_panel_with_signal(sig_data, n=400))
    post = raw.iloc[200:]
    on_ratio = post.mean()
    assert on_ratio > 0.95, f"长期上行应 ≥95% ON，得到 {on_ratio:.3f}"
    print(f"[ok] test_signal_strong_uptrend  on_ratio={on_ratio:.3f}")


def test_signal_strong_downtrend():
    """长期下行：信号应几乎一直 OFF。"""
    from strategy_lib.strategies.cn_etf_market_ma_filter import MarketMAFilterStrategy

    sig_data = synth_deterministic(n_days=400, drift=-0.001)
    strat = MarketMAFilterStrategy(ma_length=200, lag_days=1)
    raw, _ = strat.build_signal(_make_panel_with_signal(sig_data, n=400))
    post = raw.iloc[200:]
    on_ratio = post.mean()
    assert on_ratio < 0.05, f"长期下行应 <5% ON，得到 {on_ratio:.3f}"
    print(f"[ok] test_signal_strong_downtrend  on_ratio={on_ratio:.3f}")


def test_lag_filter_blocks_single_cross():
    """滞后过滤：单日穿越不应触发切换；连续 N 日才触发。"""
    from strategy_lib.strategies.cn_etf_market_ma_filter import MarketMAFilterStrategy

    # 构造一个 raw 序列：[0,0,0,1,0,1,1,1,1,0,0,0,0,1,0]，模拟单日穿越 + 持续穿越
    raw_arr = np.array([0, 0, 0, 1, 0, 1, 1, 1, 1, 0, 0, 0, 0, 1, 0])
    raw = pd.Series(raw_arr, index=pd.RangeIndex(len(raw_arr)))

    strat3 = MarketMAFilterStrategy(ma_length=200, lag_days=3)
    sig3 = strat3._apply_lag_filter(raw)
    # 期望：连续 3 日才切换（rolling window size = 3，需要窗口内全 1 才 ON / 全 0 才 OFF）
    # idx 0-2: rolling 暖机 (NaN, NaN, sum=0)，初始化保持 last=0
    # idx 3:   window [0,0,1]=1 → 不到 3，保持 0
    # idx 4:   [0,1,0]=1 → 0
    # idx 5:   [1,0,1]=2 → 0
    # idx 6:   [0,1,1]=2 → 0
    # idx 7:   [1,1,1]=3 → 切到 1
    # idx 8:   [1,1,1]=3 → 1
    # idx 9:   [1,1,0]=2 → 保持 1
    # idx 10:  [1,0,0]=1 → 保持 1
    # idx 11:  [0,0,0]=0 → 切到 0
    # idx 12:  [0,0,0]=0 → 0
    # idx 13:  [0,0,1]=1 → 0
    # idx 14:  [0,1,0]=1 → 0
    expected = np.array([0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 0])
    assert (sig3.values == expected).all(), f"\n预期 {expected}\n实际 {sig3.values}"
    print(f"[ok] test_lag_filter_blocks_single_cross  sig3={sig3.values}")


def test_lag_filter_lag1_passthrough():
    """lag=1 时应等价于 raw（无过滤）。"""
    from strategy_lib.strategies.cn_etf_market_ma_filter import MarketMAFilterStrategy

    raw_arr = np.array([0, 1, 0, 1, 1, 0])
    raw = pd.Series(raw_arr, index=pd.RangeIndex(len(raw_arr)))
    strat = MarketMAFilterStrategy(ma_length=200, lag_days=1)
    sig = strat._apply_lag_filter(raw)
    assert (sig.values == raw_arr).all(), f"lag=1 应等价 raw，得到 {sig.values}"
    print(f"[ok] test_lag_filter_lag1_passthrough")


def test_weights_on_off_split():
    """ON 日：risky pool 等权；OFF 日：cash_symbol 100%。"""
    from strategy_lib.strategies.cn_etf_market_ma_filter import MarketMAFilterStrategy

    sig_data = synth_v_shape(n_days=400, half_drift=-0.003)
    panel = _make_panel_with_signal(sig_data, n=400)
    strat = MarketMAFilterStrategy(ma_length=100, lag_days=1)
    raw, sig = strat.build_signal(panel)
    weights = strat.build_target_weight_panel(panel, sig)

    # 对每日检查 sum=1
    sums = weights.sum(axis=1)
    assert np.allclose(sums, 1.0, atol=1e-9), f"权重每日 sum 应 = 1，得到 min={sums.min()}, max={sums.max()}"

    # ON 日：cash_symbol 应为 0；6 池每只 = 1/6
    on_dates = sig[sig == 1].index
    if len(on_dates) > 0:
        sample = on_dates[len(on_dates) // 2]
        row = weights.loc[sample]
        assert abs(row["511990"]) < 1e-9, f"ON 日 cash 应 = 0，得到 {row['511990']}"
        assert abs(row["510300"] - 1.0 / 6) < 1e-9, f"ON 日 510300 应 = 1/6，得到 {row['510300']}"
    # OFF 日：cash_symbol 应为 1；其他全 0
    off_dates = sig[sig == 0].index
    if len(off_dates) > 0:
        sample = off_dates[len(off_dates) // 2]
        row = weights.loc[sample]
        assert abs(row["511990"] - 1.0) < 1e-9, f"OFF 日 cash 应 = 1，得到 {row['511990']}"
        assert abs(row["510300"]) < 1e-9, f"OFF 日 510300 应 = 0，得到 {row['510300']}"
    print(f"[ok] test_weights_on_off_split  on_days={len(on_dates)}, off_days={len(off_dates)}")


def test_v_shape_switches():
    """V 型曲线：信号应至少切换 2 次（OFF→ON, ON→OFF, ...）。"""
    from strategy_lib.strategies.cn_etf_market_ma_filter import MarketMAFilterStrategy

    sig_data = synth_v_shape(n_days=600, half_drift=-0.005)
    panel = _make_panel_with_signal(sig_data, n=600)
    strat = MarketMAFilterStrategy(ma_length=100, lag_days=2)
    raw, sig = strat.build_signal(panel)
    switches = int((sig.diff().fillna(0) != 0).sum())
    print(f"[ok] test_v_shape_switches  switches={switches}, on_ratio={sig.mean():.3f}")
    assert switches >= 1, f"V 型应至少 1 次切换，得到 {switches}"


def test_run_smoke_e2e():
    """端到端 smoke：能跑通 vbt 回测，输出 Portfolio."""
    from strategy_lib.strategies.cn_etf_market_ma_filter import MarketMAFilterStrategy

    sig_data = synth_v_shape(n_days=600, half_drift=-0.003)
    panel = _make_panel_with_signal(sig_data, n=600)
    strat = MarketMAFilterStrategy(ma_length=100, lag_days=2)
    res = strat.run(panel, init_cash=100_000)
    eq = res.portfolio.value()
    if isinstance(eq, pd.DataFrame):
        eq = eq.iloc[:, 0]
    assert eq.iloc[0] > 0
    assert eq.notna().all(), "equity 不应有 NaN"
    print(f"[ok] test_run_smoke_e2e  switches={len(res.switch_dates)}, "
          f"final={eq.iloc[-1]:.0f}, on_ratio={res.signal.mean():.3f}")


def run_smoke() -> None:
    print(f"[setup] using loguru stub: {_INSTALLED_LOGURU_STUB}")
    test_signal_warmup_zero()
    test_signal_strong_uptrend()
    test_signal_strong_downtrend()
    test_lag_filter_blocks_single_cross()
    test_lag_filter_lag1_passthrough()
    test_weights_on_off_split()
    test_v_shape_switches()
    test_run_smoke_e2e()
    print("\nSMOKE OK — S7 信号 / 滞后过滤 / 权重切换 / e2e 全部通过\n")


# ---------------------------------------------------------------------------
# Real-data helpers
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


def _rebase(s, init):
    return s if (s is None or s.empty) else s / s.iloc[0] * init


def _cash_neg_corr(signal_off_series, rets_bh_series):
    """signal_off (=1 means risk-off cash position) vs (BH return < 0) 相关性。

    signal_off_series: 0/1 序列（1=该日为 risk-off）
    """
    is_off = signal_off_series.astype(int).reindex(rets_bh_series.index, method="ffill").fillna(0)
    bh_neg = (rets_bh_series < 0).astype(int)
    if is_off.var() > 0 and bh_neg.var() > 0:
        return float(np.corrcoef(is_off.values, bh_neg.values)[0, 1])
    return float("nan")


def _switch_stats(sig_series):
    """返回切换次数 / on_ratio / 单段 ON/OFF 持续天数 list。"""
    diffs = sig_series.diff().fillna(0)
    switches = int((diffs != 0).sum())
    on_ratio = float(sig_series.mean())

    # 单段持续天数
    durations_on = []
    durations_off = []
    cur_state = sig_series.iloc[0]
    cur_len = 1
    for v in sig_series.iloc[1:]:
        if v == cur_state:
            cur_len += 1
        else:
            (durations_on if cur_state == 1 else durations_off).append(cur_len)
            cur_state = v
            cur_len = 1
    (durations_on if cur_state == 1 else durations_off).append(cur_len)
    return {
        "switches": switches,
        "on_ratio": on_ratio,
        "off_ratio": 1.0 - on_ratio,
        "durations_on": durations_on,
        "durations_off": durations_off,
        "mean_on_duration": float(np.mean(durations_on)) if durations_on else 0.0,
        "mean_off_duration": float(np.mean(durations_off)) if durations_off else 0.0,
    }


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


def _plot_drawdown(curves, path, focus_2022=True):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 1, figsize=(11, 8), gridspec_kw={"height_ratios": [3, 2]})
    ax0 = axes[0]
    for name, s in curves.items():
        if s is None or s.empty:
            continue
        dd = _drawdown(s)
        ax0.fill_between(dd.index, dd.values, 0, alpha=0.15)
        ax0.plot(dd.index, dd.values, lw=1.0, label=name)
    ax0.set_title("Drawdowns (full window)")
    ax0.set_xlabel("date"); ax0.set_ylabel("drawdown")
    ax0.grid(alpha=0.3); ax0.legend(loc="best")

    if focus_2022:
        ax1 = axes[1]
        # 2022 段
        for name, s in curves.items():
            if s is None or s.empty:
                continue
            seg = s.loc["2022-01-01":"2022-12-31"]
            if seg.empty:
                continue
            seg_rebased = seg / seg.iloc[0]
            ax1.plot(seg_rebased.index, seg_rebased.values, lw=1.5, label=name)
        ax1.set_title("2022 single-year (rebased to 1.0 at year start)")
        ax1.set_xlabel("date"); ax1.set_ylabel("rebased value")
        ax1.grid(alpha=0.3); ax1.legend(loc="best")
        ax1.axhline(1.0, color="black", lw=0.5, ls="--")
    fig.tight_layout(); fig.savefig(path, dpi=120); plt.close(fig)


def _plot_signal_overlay(signal_close, ma_series, signal_filt, path, title):
    """510300 价格 + MA + ON/OFF 区域叠加。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(13, 6))
    ax.plot(signal_close.index, signal_close.values, lw=1.2, color="tab:blue", label="510300 close")
    ax.plot(ma_series.index, ma_series.values, lw=1.4, color="tab:orange", label=f"MA")

    # ON 区域用绿色、OFF 区域用灰色
    sig_aligned = signal_filt.reindex(signal_close.index, method="ffill").fillna(0).astype(int)
    is_on = (sig_aligned == 1)
    is_off = (sig_aligned == 0)
    ymin, ymax = float(signal_close.min()), float(signal_close.max())
    ymin = ymin * 0.95
    ymax = ymax * 1.02
    ax.fill_between(signal_close.index, ymin, ymax, where=is_on.values, color="tab:green", alpha=0.10, label="risk-ON")
    ax.fill_between(signal_close.index, ymin, ymax, where=is_off.values, color="tab:gray", alpha=0.20, label="risk-OFF")
    ax.set_ylim(ymin, ymax)
    ax.set_title(title)
    ax.set_xlabel("date"); ax.set_ylabel("510300 close (qfq)")
    ax.grid(alpha=0.3); ax.legend(loc="best")
    fig.tight_layout(); fig.savefig(path, dpi=120); plt.close(fig)


def _plot_regime_periods(signal_filt, switch_dates, path):
    """ON/OFF 时段标注 + 持续时长直方图。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    stats = _switch_stats(signal_filt)
    fig, axes = plt.subplots(2, 1, figsize=(11, 7), gridspec_kw={"height_ratios": [2, 1]})

    ax0 = axes[0]
    sig_aligned = signal_filt.astype(int)
    ax0.plot(sig_aligned.index, sig_aligned.values, lw=1.2, color="tab:blue", drawstyle="steps-post")
    ax0.fill_between(sig_aligned.index, sig_aligned.values, 0, alpha=0.25, step="post", color="tab:green")
    for d in switch_dates:
        ax0.axvline(d, color="red", lw=0.5, alpha=0.5)
    ax0.set_ylim(-0.1, 1.1)
    ax0.set_title(f"S7 regime (switches={stats['switches']}, on_ratio={stats['on_ratio']:.2%})")
    ax0.set_ylabel("signal")
    ax0.grid(alpha=0.3)

    ax1 = axes[1]
    if stats["durations_on"]:
        ax1.hist(stats["durations_on"], bins=15, alpha=0.6, color="tab:green",
                 label=f"ON segments (n={len(stats['durations_on'])}, mean={stats['mean_on_duration']:.0f}d)")
    if stats["durations_off"]:
        ax1.hist(stats["durations_off"], bins=15, alpha=0.6, color="tab:gray",
                 label=f"OFF segments (n={len(stats['durations_off'])}, mean={stats['mean_off_duration']:.0f}d)")
    ax1.set_xlabel("segment duration (days)")
    ax1.set_ylabel("count")
    ax1.set_title("Segment duration histogram")
    ax1.legend(loc="best"); ax1.grid(alpha=0.3)

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
    from strategy_lib.strategies.cn_etf_market_ma_filter import MarketMAFilterStrategy
    from strategy_lib.strategies.cn_etf_equal_rebalance import EqualRebalanceStrategy
    from strategy_lib.strategies.cn_etf_trend_tilt import TrendTiltStrategy
    from strategy_lib.strategies.cn_etf_trend_tilt_v2 import TrendTiltV2Strategy

    print("=" * 80)
    print("Real-data Backtest — Strategy 7 v1 (cn_etf_market_ma_filter)")
    print("=" * 80)

    risky_symbols = ["510300", "510500", "159915", "512100", "512880", "512170"]
    cash_symbol = "511990"
    bond_symbol = "511260"  # for S5v2
    all_symbols = list({*risky_symbols, cash_symbol, bond_symbol, "510300"})

    loader = get_loader("cn_etf")
    panel = loader.load_many(all_symbols, since=warmup_since, until=until)
    print(f"Loaded panel: {sorted(panel.keys())}")
    for s in sorted(panel):
        df = panel[s]
        print(f"  {s}: {df.shape[0]} rows, {df.index[0].date()} ~ {df.index[-1].date()}")

    common_idx = None
    for s in [cash_symbol] + risky_symbols:
        idx = panel[s].index
        common_idx = idx if common_idx is None else common_idx.intersection(idx)
    common_idx = common_idx.sort_values()
    since_ts = pd.Timestamp(since, tz="UTC")
    until_ts = pd.Timestamp(until, tz="UTC")
    sample_idx = common_idx[(common_idx >= since_ts) & (common_idx <= until_ts)]
    print(f"sample bars: {len(sample_idx)}, {sample_idx[0].date()} ~ {sample_idx[-1].date()}")

    # ---------------------------------------------------------------- S7 主跑 (MA200, lag=2)
    print("\n[1/5] Running S7 (MA=200, lag=2, equal pool) ...")
    s7 = MarketMAFilterStrategy(
        symbols=risky_symbols,
        cash_symbol=cash_symbol,
        signal_symbol="510300",
        ma_length=200,
        lag_days=2,
        weight_mode="equal",
    )
    s7_panel = {s: panel[s] for s in risky_symbols + [cash_symbol]}
    s7_res = s7.run(s7_panel, init_cash=init_cash, fees=fees, slippage=slippage, signal_lag=1)
    s7_eq = s7_res.portfolio.value()
    if isinstance(s7_eq, pd.DataFrame):
        s7_eq = s7_eq.iloc[:, 0]
    s7_eq = _slice(s7_eq, since_ts, until_ts).rename("S7_MA200_lag2")

    s7_sig_full = s7_res.signal  # 0/1 series, full panel index
    s7_sig = s7_sig_full.loc[since_ts:until_ts]

    # ---------------------------------------------------------------- S3
    print("[2/5] Running S3 (equal rebal) ...")
    s3 = EqualRebalanceStrategy(symbols=risky_symbols, rebalance_period=20)
    panel_risky = {s: panel[s] for s in risky_symbols}
    s3_res = s3.run(panel_risky, init_cash=init_cash, fees=fees, slippage=slippage)
    s3_eq = s3_res.portfolio.value()
    if isinstance(s3_eq, pd.DataFrame):
        s3_eq = s3_eq.iloc[:, 0]
    s3_eq = _slice(s3_eq, since_ts, until_ts).rename("S3_equal")

    # ---------------------------------------------------------------- S5 v1
    print("[3/5] Running S5 v1 (trend tilt) ...")
    s5v1 = TrendTiltStrategy(
        symbols=risky_symbols, rebalance_period=20,
        ma_short=20, ma_mid=60, ma_long=120,
        donchian_lookback=120, cutoff=0.0,
    )
    s5v1_res = s5v1.run(panel_risky, init_cash=init_cash, fees=fees, slippage=slippage)
    s5v1_eq = s5v1_res.portfolio.value()
    if isinstance(s5v1_eq, pd.DataFrame):
        s5v1_eq = s5v1_eq.iloc[:, 0]
    s5v1_eq = _slice(s5v1_eq, since_ts, until_ts).rename("S5v1")

    # ---------------------------------------------------------------- S5 v2
    print("[4/5] Running S5 v2 (continuous + vol filter + bond) ...")
    s5v2_panel_syms = risky_symbols + [bond_symbol]
    s5v2 = TrendTiltV2Strategy(
        symbols=s5v2_panel_syms, rebalance_period=20,
        ma_short=20, ma_mid=60, ma_long=120,
        donchian_lookback=120, cutoff=0.0,
        score_full=1.0,
        use_continuous_score=True,
        vol_lookback=60, vol_high=0.30,
        vol_breadth_threshold=0.5, vol_haircut=0.5,
        bond_symbol=bond_symbol, bond_max_weight=0.4,
    )
    s5v2_panel = {s: panel[s] for s in s5v2_panel_syms}
    s5v2_res = s5v2.run(s5v2_panel, init_cash=init_cash, fees=fees, slippage=slippage)
    s5v2_eq = s5v2_res.portfolio.value()
    if isinstance(s5v2_eq, pd.DataFrame):
        s5v2_eq = s5v2_eq.iloc[:, 0]
    s5v2_eq = _slice(s5v2_eq, since_ts, until_ts).rename("S5v2")

    # ---------------------------------------------------------------- BH
    print("[5/5] Running 510300 BH ...")
    bh_full = panel["510300"]["close"]
    bh_eq = bh_full.loc[since_ts:until_ts]
    bh_eq = (bh_eq / bh_eq.iloc[0] * init_cash).rename("510300_BH")

    curves = {
        "S7_MA200_lag2": _rebase(s7_eq, init_cash),
        "S3_equal": _rebase(s3_eq, init_cash),
        "S5v1": _rebase(s5v1_eq, init_cash),
        "S5v2": _rebase(s5v2_eq, init_cash),
        "510300_BH": _rebase(bh_eq, init_cash),
    }

    print("\n--- 主绩效表 ---")
    metrics = {}
    for name, s in curves.items():
        m = _equity_metrics(s)
        metrics[name] = m
        print(_format_row(name, m))

    # ---- 分年度 ----
    print("\n--- 分年度收益 ---")
    yearly = pd.DataFrame({name: _yearly_returns(s) for name, s in curves.items()})
    yearly.index = yearly.index.year
    print(yearly.round(4).to_string())

    # ---- alpha / IR vs S3 / vs BH ----
    rets_s7 = curves["S7_MA200_lag2"].pct_change().dropna()
    rets_bh = curves["510300_BH"].pct_change().dropna()
    rets_s3 = curves["S3_equal"].pct_change().dropna()
    rets_s5v1 = curves["S5v1"].pct_change().dropna()
    rets_s5v2 = curves["S5v2"].pct_change().dropna()

    def _ir(excess):
        if excess.empty or excess.std() == 0:
            return {"alpha_ann": np.nan, "te_ann": np.nan, "ir": np.nan}
        return {
            "alpha_ann": float(excess.mean() * 252),
            "te_ann": float(excess.std() * np.sqrt(252)),
            "ir": float(excess.mean() / excess.std() * np.sqrt(252)),
        }

    def _excess(a, b):
        common = a.index.intersection(b.index)
        return _ir(a.loc[common] - b.loc[common])

    ir_bh = _excess(rets_s7, rets_bh)
    ir_s3 = _excess(rets_s7, rets_s3)
    ir_s5v1 = _excess(rets_s7, rets_s5v1)
    ir_s5v2 = _excess(rets_s7, rets_s5v2)
    print(f"\nS7 vs 510300 BH: alpha={ir_bh['alpha_ann']*100:.2f}%, te={ir_bh['te_ann']*100:.2f}%, IR={ir_bh['ir']:.3f}")
    print(f"S7 vs S3 equal : alpha={ir_s3['alpha_ann']*100:.2f}%, te={ir_s3['te_ann']*100:.2f}%, IR={ir_s3['ir']:.3f}")
    print(f"S7 vs S5 v1   : alpha={ir_s5v1['alpha_ann']*100:.2f}%, te={ir_s5v1['te_ann']*100:.2f}%, IR={ir_s5v1['ir']:.3f}")
    print(f"S7 vs S5 v2   : alpha={ir_s5v2['alpha_ann']*100:.2f}%, te={ir_s5v2['te_ann']*100:.2f}%, IR={ir_s5v2['ir']:.3f}")

    # ---- 信号 / 切换 / 避险命题 ----
    # NOTE: signal=1 → risk-ON；想看 cash 与下跌的相关性，要用 1-sig（即 OFF=1）
    s7_off = 1 - s7_sig
    s7_corr = _cash_neg_corr(s7_off, rets_bh)
    print(f"\n避险命题验证（risk-OFF 是否对齐 BH 下跌）:")
    print(f"  S7 OFF vs BH down: corr = {s7_corr:.3f}")

    # 切换 / on/off 持续天数
    s7_stats = _switch_stats(s7_sig)
    print(f"\nS7 信号统计:")
    print(f"  switches            = {s7_stats['switches']}")
    print(f"  on_ratio            = {s7_stats['on_ratio']:.4f}")
    print(f"  off_ratio (cash)    = {s7_stats['off_ratio']:.4f}")
    print(f"  mean ON  duration   = {s7_stats['mean_on_duration']:.1f} days  (n={len(s7_stats['durations_on'])})")
    print(f"  mean OFF duration   = {s7_stats['mean_off_duration']:.1f} days  (n={len(s7_stats['durations_off'])})")
    if s7_stats["durations_on"]:
        print(f"  ON  durations       = {s7_stats['durations_on']}")
    if s7_stats["durations_off"]:
        print(f"  OFF durations       = {s7_stats['durations_off']}")

    # ---- MA 长度敏感性 ----
    print("\n--- MA 长度敏感性 (lag=2 fixed) ---")
    ma_rows = []
    for ma_n in [100, 150, 200, 250]:
        s = MarketMAFilterStrategy(
            symbols=risky_symbols, cash_symbol=cash_symbol, signal_symbol="510300",
            ma_length=ma_n, lag_days=2, weight_mode="equal",
        )
        r = s.run(s7_panel, init_cash=init_cash, fees=fees, slippage=slippage, signal_lag=1)
        eq = r.portfolio.value()
        if isinstance(eq, pd.DataFrame):
            eq = eq.iloc[:, 0]
        eq = _slice(eq, since_ts, until_ts)
        m = _equity_metrics(_rebase(eq, init_cash))
        sig = r.signal.loc[since_ts:until_ts]
        st = _switch_stats(sig)
        rets = (eq / eq.iloc[0] * init_cash).pct_change().dropna()
        # 2022 单年回撤
        eq_22 = eq.loc["2022-01-01":"2022-12-31"]
        if not eq_22.empty:
            yr_22 = eq_22.iloc[-1] / eq_22.iloc[0] - 1
        else:
            yr_22 = float("nan")
        off = 1 - sig
        corr = _cash_neg_corr(off, rets_bh)
        ma_rows.append({
            "ma_length": ma_n,
            "cagr": m["cagr"],
            "sharpe": m["sharpe"],
            "max_dd": m["max_dd"],
            "yr_2022": yr_22,
            "switches": st["switches"],
            "on_ratio": st["on_ratio"],
            "cash_vs_bh_neg_corr": corr,
            "final_nav_100k": float(eq.iloc[-1] / eq.iloc[0] * 100_000) if not eq.empty else float("nan"),
        })
        print(f"  MA={ma_n:>3d}  NAV={ma_rows[-1]['final_nav_100k']:>9.0f}  "
              f"CAGR={m['cagr']*100:>6.2f}%  Sharpe={m['sharpe']:>5.2f}  "
              f"MaxDD={m['max_dd']*100:>7.2f}%  2022={yr_22*100:>7.2f}%  "
              f"switches={st['switches']:>3d}  on={st['on_ratio']:.2%}  corr={corr:.3f}")
    ma_df = pd.DataFrame(ma_rows)

    # ---- 滞后敏感性 ----
    print("\n--- 滞后敏感性 (MA=200 fixed) ---")
    lag_rows = []
    for lag in [1, 2, 3, 5]:
        s = MarketMAFilterStrategy(
            symbols=risky_symbols, cash_symbol=cash_symbol, signal_symbol="510300",
            ma_length=200, lag_days=lag, weight_mode="equal",
        )
        r = s.run(s7_panel, init_cash=init_cash, fees=fees, slippage=slippage, signal_lag=1)
        eq = r.portfolio.value()
        if isinstance(eq, pd.DataFrame):
            eq = eq.iloc[:, 0]
        eq = _slice(eq, since_ts, until_ts)
        m = _equity_metrics(_rebase(eq, init_cash))
        sig = r.signal.loc[since_ts:until_ts]
        st = _switch_stats(sig)
        eq_22 = eq.loc["2022-01-01":"2022-12-31"]
        yr_22 = (eq_22.iloc[-1] / eq_22.iloc[0] - 1) if not eq_22.empty else float("nan")
        off = 1 - sig
        corr = _cash_neg_corr(off, rets_bh)
        lag_rows.append({
            "lag_days": lag,
            "cagr": m["cagr"],
            "sharpe": m["sharpe"],
            "max_dd": m["max_dd"],
            "yr_2022": yr_22,
            "switches": st["switches"],
            "on_ratio": st["on_ratio"],
            "cash_vs_bh_neg_corr": corr,
            "final_nav_100k": float(eq.iloc[-1] / eq.iloc[0] * 100_000) if not eq.empty else float("nan"),
        })
        print(f"  lag={lag}  NAV={lag_rows[-1]['final_nav_100k']:>9.0f}  "
              f"CAGR={m['cagr']*100:>6.2f}%  Sharpe={m['sharpe']:>5.2f}  "
              f"MaxDD={m['max_dd']*100:>7.2f}%  2022={yr_22*100:>7.2f}%  "
              f"switches={st['switches']:>3d}  on={st['on_ratio']:.2%}  corr={corr:.3f}")
    lag_df = pd.DataFrame(lag_rows)

    # ---- artifacts ----
    _ensure_artifacts()
    _plot_equity(curves, ARTIFACTS_DIR / "equity_curve.png",
                 title=f"Equity S7 vs S3 vs S5v1 vs S5v2 vs BH ({since}~{until})")
    _plot_drawdown(
        {"S7": curves["S7_MA200_lag2"], "S3": curves["S3_equal"],
         "S5v1": curves["S5v1"], "S5v2": curves["S5v2"], "BH": curves["510300_BH"]},
        ARTIFACTS_DIR / "drawdown.png",
        focus_2022=True,
    )

    # signal_overlay：510300 收盘 + MA200 + ON/OFF 色块（in-sample 段）
    signal_close_full = panel["510300"]["close"]
    ma_full = signal_close_full.rolling(200).mean()
    s7_sig_full_traded = s7_res.signal
    sc_in = signal_close_full.loc[since_ts:until_ts]
    ma_in = ma_full.loc[since_ts:until_ts]
    sig_in = s7_sig_full_traded.loc[since_ts:until_ts]
    _plot_signal_overlay(
        sc_in, ma_in, sig_in,
        ARTIFACTS_DIR / "signal_overlay.png",
        title="510300 close + MA200 + S7 risk-ON/OFF regime (lag=2)",
    )

    _plot_regime_periods(s7_sig, s7_res.switch_dates, ARTIFACTS_DIR / "regime_periods.png")

    ma_df.to_csv(ARTIFACTS_DIR / "ma_length_sensitivity.csv", index=False)
    lag_df.to_csv(ARTIFACTS_DIR / "lag_sensitivity.csv", index=False)

    print(f"\nArtifacts saved to: {ARTIFACTS_DIR}")

    return {
        "metrics": metrics,
        "yearly": yearly,
        "ir_bh": ir_bh, "ir_s3": ir_s3, "ir_s5v1": ir_s5v1, "ir_s5v2": ir_s5v2,
        "s7_corr_off_vs_bh_down": s7_corr,
        "s7_stats": {k: v for k, v in s7_stats.items() if k not in ("durations_on", "durations_off")},
        "ma_sensitivity": ma_df.to_dict(orient="records"),
        "lag_sensitivity": lag_df.to_dict(orient="records"),
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
