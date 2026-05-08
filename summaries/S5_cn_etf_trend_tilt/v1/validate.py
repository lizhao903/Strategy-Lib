"""Validation for cn_etf_trend_tilt — Smoke + Real-data backtest.

入口:
    PYTHONPATH=src python summaries/cn_etf_trend_tilt/validate.py            # 默认: smoke
    PYTHONPATH=src python summaries/cn_etf_trend_tilt/validate.py real       # 真实数据回测
    PYTHONPATH=src python summaries/cn_etf_trend_tilt/validate.py all        # smoke + real

Smoke 测试场景：
1. 暖机期：lookback 不足 → 全空仓
2. 全部多头排列：所有 ETF 都强趋势 → 接近等权
3. 一半多头一半空头：空头 ETF 权重为 0
4. 全空头：返回空 dict（全空仓）
5. compute_trend_scores 数学一致性：score ∈ [-2, +2]

Real-data 回测：
- 2020-01-01 ~ 2024-12-31，2019-07-01 起暖机
- 6 只 ETF：510300/510500/159915/512100/512880/512170
- 对比基线：510300 BH、S3 等权再平衡、S4 动量倾斜
- cutoff 敏感性：{0.0, 0.3, 0.5}
- 输出：artifacts/*.png + 控制台绩效表
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd

# 让 src 进入 import 路径
ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"


# ---------------------------------------------------------------------------
# 在没装 loguru 的纯净环境也能跑：注入一个最小 stub
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
# Stub 父类：在 S3 还没合并时占位
# ---------------------------------------------------------------------------
def _install_stub_parent_if_missing() -> bool:
    import importlib

    try:
        importlib.import_module("strategy_lib.strategies.cn_etf_equal_rebalance")
        return False
    except ModuleNotFoundError:
        pass

    stub_mod = types.ModuleType("strategy_lib.strategies.cn_etf_equal_rebalance")

    class EqualRebalanceStrategy:
        """Stub for S3。提供本测试需要的最小接口。"""

        def __init__(
            self,
            symbols=None,
            rebalance_period: int = 20,
            drift_threshold=None,
            **kwargs,
        ) -> None:
            self.symbols = list(symbols) if symbols else []
            self.rebalance_period = rebalance_period
            self.drift_threshold = drift_threshold
            for k, v in kwargs.items():
                setattr(self, k, v)

        def target_weights(self, date, prices_panel):
            n = len(prices_panel)
            if n == 0:
                return {}
            return {sym: 1.0 / n for sym in prices_panel}

    stub_mod.EqualRebalanceStrategy = EqualRebalanceStrategy
    sys.modules["strategy_lib.strategies.cn_etf_equal_rebalance"] = stub_mod
    return True


# ---------------------------------------------------------------------------
# 合成数据生成（smoke）
# ---------------------------------------------------------------------------
def synth_ohlcv(
    n_days: int = 250,
    start_price: float = 100.0,
    drift: float = 0.0,
    vol: float = 0.015,
    seed: int = 0,
) -> pd.DataFrame:
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


def synth_deterministic(
    n_days: int = 400,
    start_price: float = 100.0,
    drift: float = 0.0,
) -> pd.DataFrame:
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


def make_panel(directions: dict[str, float], n_days: int = 250) -> dict[str, pd.DataFrame]:
    panel = {}
    for i, (sym, drift) in enumerate(directions.items()):
        panel[sym] = synth_ohlcv(n_days=n_days, drift=drift, seed=i)
    return panel


# ---------------------------------------------------------------------------
# Smoke Tests
# ---------------------------------------------------------------------------
def test_factors_independent():
    from strategy_lib.factors.trend import DonchianPosition, MABullishScore

    df = synth_ohlcv(n_days=300, drift=0.001, seed=0)

    ma_factor = MABullishScore(short=20, mid=60, long=120)
    s = ma_factor.compute(df)
    assert s.iloc[:119].isna().all(), "MA120 暖机期前必须 NaN"
    assert s.dropna().between(-3, 3).all(), "MA 得分必须在 [-3,3]"

    dc_factor = DonchianPosition(lookback=120)
    p = dc_factor.compute(df)
    assert p.iloc[:119].isna().all(), "Donchian 暖机期前必须 NaN"
    assert p.dropna().between(0, 1).all(), "Donchian 位置必须在 [0,1]"

    print("[ok] test_factors_independent")


def test_warmup_returns_empty():
    from strategy_lib.strategies.cn_etf_trend_tilt import TrendTiltStrategy

    panel = make_panel({"A": 0.001, "B": 0.0, "C": -0.001}, n_days=50)
    strat = TrendTiltStrategy(symbols=list(panel))
    weights = strat.target_weights(panel["A"].index[-1], panel)
    assert weights == {}, f"暖机期应该全空仓，得到 {weights}"
    print("[ok] test_warmup_returns_empty")


def test_all_uptrend_near_equal_weight():
    from strategy_lib.strategies.cn_etf_trend_tilt import TrendTiltStrategy

    n = 400
    panel = {f"S{i}": synth_deterministic(n_days=n, drift=0.001) for i in range(6)}
    strat = TrendTiltStrategy(symbols=list(panel))
    weights = strat.target_weights(panel["S0"].index[-1], panel)
    assert len(weights) == 6, f"全上行时应每个都有权重，得到 {weights}"
    total = sum(weights.values())
    assert abs(total - 1.0) < 1e-9, f"权重和应为 1，得到 {total}"
    for sym, w in weights.items():
        assert abs(w - 1 / 6) < 1e-9, f"{sym} 应为 1/6，得到 {w}"
    print(f"[ok] test_all_uptrend_near_equal_weight  weights_sum={total:.6f}")


def test_mixed_trends_filters_negatives():
    from strategy_lib.strategies.cn_etf_trend_tilt import TrendTiltStrategy

    n = 400
    panel = {
        "UP1": synth_deterministic(n_days=n, drift=0.001),
        "UP2": synth_deterministic(n_days=n, drift=0.001),
        "UP3": synth_deterministic(n_days=n, drift=0.001),
        "DN1": synth_deterministic(n_days=n, drift=-0.001),
        "DN2": synth_deterministic(n_days=n, drift=-0.001),
        "DN3": synth_deterministic(n_days=n, drift=-0.001),
    }
    strat = TrendTiltStrategy(symbols=list(panel))
    weights = strat.target_weights(panel["UP1"].index[-1], panel)

    for dn in ("DN1", "DN2", "DN3"):
        assert dn not in weights or weights[dn] == 0, f"{dn} 应被过滤，得到 {weights.get(dn)}"
    total = sum(weights.values())
    assert abs(total - 1.0) < 1e-9, f"上行 ETF 权重和应为 1，得到 {total}"
    print(f"[ok] test_mixed_trends_filters_negatives  weights={weights}")


def test_all_downtrend_returns_empty():
    from strategy_lib.strategies.cn_etf_trend_tilt import TrendTiltStrategy

    n = 400
    panel = {f"D{i}": synth_deterministic(n_days=n, drift=-0.001) for i in range(6)}
    strat = TrendTiltStrategy(symbols=list(panel))
    weights = strat.target_weights(panel["D0"].index[-1], panel)
    assert weights == {}, f"全下行应空仓，得到 {weights}"
    print("[ok] test_all_downtrend_returns_empty")


def test_validate_weights_allows_subunit_sum():
    from strategy_lib.strategies.cn_etf_trend_tilt import TrendTiltStrategy

    strat = TrendTiltStrategy(symbols=["A", "B", "C"])
    out = strat._validate_weights({"A": 0.4, "B": 0.2})
    assert out == {"A": 0.4, "B": 0.2, "C": 0.0}, out

    out = strat._validate_weights({})
    assert out == {"A": 0.0, "B": 0.0, "C": 0.0}, out

    try:
        strat._validate_weights({"A": -0.1})
        raise AssertionError("应抛出负值错误")
    except ValueError:
        pass
    print("[ok] test_validate_weights_allows_subunit_sum")


def test_compute_trend_scores_range():
    from strategy_lib.strategies.cn_etf_trend_tilt import TrendTiltStrategy

    n = 400
    panel = {
        "UP": synth_deterministic(n_days=n, drift=0.001),
        "DOWN": synth_deterministic(n_days=n, drift=-0.001),
    }
    strat = TrendTiltStrategy(symbols=list(panel))
    scores = strat.compute_trend_scores(panel["UP"].index[-1], panel)
    valid = scores.dropna()
    assert valid.between(-2, 2).all(), f"trend_score 必须 ∈ [-2, +2]，得到 {scores}"
    assert scores["UP"] > scores["DOWN"], f"上行 > 下行，得到 {scores}"
    assert abs(scores["UP"] - 2.0) < 0.05, f"无噪声上行 score 应 ~ 2.0，得到 {scores['UP']}"
    assert abs(scores["DOWN"] - (-2.0)) < 0.05, f"无噪声下行 score 应 ~ -2.0，得到 {scores['DOWN']}"
    print(f"[ok] test_compute_trend_scores_range  scores={scores.to_dict()}")


def test_lookahead_bias():
    from strategy_lib.strategies.cn_etf_trend_tilt import TrendTiltStrategy

    n = 250
    panel_full = {
        "X": synth_deterministic(n_days=n, drift=0.001),
        "Y": synth_deterministic(n_days=n, drift=-0.001),
    }
    cutoff_date = panel_full["X"].index[150]

    panel_trunc = {sym: df.loc[df.index <= cutoff_date].copy() for sym, df in panel_full.items()}

    strat = TrendTiltStrategy(symbols=list(panel_full))
    scores_full = strat.compute_trend_scores(cutoff_date, panel_full)
    scores_trunc = strat.compute_trend_scores(cutoff_date, panel_trunc)

    for sym in scores_full.index:
        a, b = scores_full[sym], scores_trunc[sym]
        if pd.isna(a) and pd.isna(b):
            continue
        assert abs(a - b) < 1e-9, f"{sym}: lookahead bias! full={a} trunc={b}"
    print("[ok] test_lookahead_bias")


def run_smoke() -> None:
    used_stub = _install_stub_parent_if_missing()
    print(f"[setup] using stub parent: {used_stub}")
    print(f"[setup] using loguru stub: {_INSTALLED_LOGURU_STUB}")

    test_factors_independent()
    test_warmup_returns_empty()
    test_all_uptrend_near_equal_weight()
    test_mixed_trends_filters_negatives()
    test_all_downtrend_returns_empty()
    test_validate_weights_allows_subunit_sum()
    test_compute_trend_scores_range()
    test_lookahead_bias()

    print("\nSMOKE OK — 趋势倾斜逻辑独立验证通过\n")


# ---------------------------------------------------------------------------
# Real-data backtest helpers
# ---------------------------------------------------------------------------
def _equity_metrics(equity: pd.Series, freq_per_year: int = 252) -> dict:
    """从净值序列计算 CAGR / Sharpe / MaxDD / Calmar。"""
    equity = equity.dropna()
    if len(equity) < 2:
        return {"cagr": np.nan, "sharpe": np.nan, "max_dd": np.nan, "calmar": np.nan, "total_return": np.nan, "vol": np.nan}
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


def _yearly_returns(equity: pd.Series) -> pd.Series:
    """按自然年度切片计算收益率。"""
    equity = equity.dropna()
    annual = equity.resample("YE").last()
    annual = pd.concat([equity.iloc[[0]], annual])
    annual = annual[~annual.index.duplicated(keep="last")].sort_index()
    return annual.pct_change().dropna()


def _drawdown_series(equity: pd.Series) -> pd.Series:
    return equity / equity.cummax() - 1


def _format_metrics_row(name: str, m: dict) -> str:
    return (
        f"  {name:<28s}  total={m['total_return']*100:>7.2f}%  "
        f"CAGR={m['cagr']*100:>6.2f}%  Sharpe={m['sharpe']:>5.2f}  "
        f"Vol={m['vol']*100:>5.2f}%  MaxDD={m['max_dd']*100:>7.2f}%  Calmar={m['calmar']:>5.2f}"
    )


def _benchmark_buyhold(panel: dict[str, pd.DataFrame], symbol: str, since: pd.Timestamp,
                       until: pd.Timestamp, init_cash: float = 100_000) -> pd.Series:
    """510300 买入持有等价净值（不计成本，纯做基准）。"""
    df = panel[symbol]
    close = df["close"].loc[since:until]
    nav = close / close.iloc[0] * init_cash
    return nav.rename("510300_BH")


def _slice_equity(equity: pd.Series, since: pd.Timestamp, until: pd.Timestamp) -> pd.Series:
    """从（含暖机的）equity 中取 [since, until]，并把起点重置到 init_cash 比例。

    保留绝对净值绝对值（在样本期开头 = since 当天的实际净值）—— 因为暖机期 S5 全空仓，
    现金仍 = init_cash，没产生收益，所以可以直接切片不重置。
    """
    return equity.loc[since:until]


def _cash_ratio_series(pf, since: pd.Timestamp, until: pd.Timestamp) -> pd.Series:
    """从 vbt Portfolio 拿每日现金占比 = cash / value。"""
    cash = pf.cash()
    value = pf.value()
    if isinstance(cash, pd.DataFrame):
        cash = cash.iloc[:, 0]
    if isinstance(value, pd.DataFrame):
        value = value.iloc[:, 0]
    ratio = cash / value
    return ratio.loc[since:until]


def _make_artifacts_dir():
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


def _plot_equity_curve(curves: dict[str, pd.Series], path: Path, title: str = "Equity Curves") -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(11, 6))
    for name, s in curves.items():
        if s is None or s.empty:
            continue
        ax.plot(s.index, s.values, label=name, lw=1.5)
    ax.set_title(title)
    ax.set_xlabel("date")
    ax.set_ylabel("equity (RMB)")
    ax.grid(alpha=0.3)
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _plot_drawdown(curves: dict[str, pd.Series], path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(11, 5))
    for name, s in curves.items():
        if s is None or s.empty:
            continue
        dd = _drawdown_series(s)
        ax.fill_between(dd.index, dd.values, 0, alpha=0.25, label=name)
        ax.plot(dd.index, dd.values, lw=1.0)
    ax.set_title("Drawdowns")
    ax.set_xlabel("date")
    ax.set_ylabel("drawdown")
    ax.grid(alpha=0.3)
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _plot_cash_ratio(cash_ratio: pd.Series, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(cash_ratio.index, cash_ratio.values, lw=1.2, color="tab:orange")
    ax.fill_between(cash_ratio.index, cash_ratio.values, 0, alpha=0.25, color="tab:orange")
    ax.set_title("S5 cash ratio (1 = 全空仓)")
    ax.set_ylim(0, 1.05)
    ax.set_xlabel("date")
    ax.set_ylabel("cash / equity")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _plot_regime_overlay(bh_nav: pd.Series, cash_ratio: pd.Series, path: Path,
                         full_cash_threshold: float = 0.99) -> None:
    """在 510300 BH 净值上叠加 S5「全空仓」（cash_ratio >= 阈值）灰色背景."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(bh_nav.index, bh_nav.values, lw=1.5, color="tab:blue", label="510300 BH")

    # 标记 S5 全空仓段
    is_full_cash = (cash_ratio >= full_cash_threshold).reindex(bh_nav.index, method="ffill").fillna(False)
    if is_full_cash.any():
        ymin, ymax = ax.get_ylim()
        ax.fill_between(
            bh_nav.index, ymin, ymax,
            where=is_full_cash.values,
            color="grey", alpha=0.25,
            label="S5 全空仓 (cash≥99%)",
        )
        ax.set_ylim(ymin, ymax)

    ax.set_title("S5 全空仓段叠加 510300 BH 净值")
    ax.set_xlabel("date")
    ax.set_ylabel("510300 BH equity")
    ax.grid(alpha=0.3)
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Real backtest
# ---------------------------------------------------------------------------
def run_real(
    since: str = "2020-01-01",
    until: str = "2024-12-31",
    warmup_since: str = "2019-07-01",
    init_cash: float = 100_000,
    fees: float = 0.00005,
    slippage: float = 0.0005,
) -> dict:
    """跑 S5 真实数据回测，对比 S3 / 510300 BH / S4，输出绩效表 + artifacts。"""
    from strategy_lib.data import get_loader
    from strategy_lib.strategies.cn_etf_trend_tilt import TrendTiltStrategy
    from strategy_lib.strategies.cn_etf_equal_rebalance import EqualRebalanceStrategy
    try:
        from strategy_lib.strategies.cn_etf_momentum_tilt import MomentumTiltStrategy
        _has_s4 = True
    except Exception as e:
        print(f"[warn] S4 import failed: {e}")
        _has_s4 = False

    print("=" * 80)
    print("Real-data Backtest — Strategy 5 (cn_etf_trend_tilt)")
    print("=" * 80)
    print(f"sample window: {since} ~ {until}, warmup since {warmup_since}")
    print(f"init_cash={init_cash}, fees={fees}, slippage={slippage}")

    symbols = ['510300', '510500', '159915', '512100', '512880', '512170']
    loader = get_loader('cn_etf')
    panel = loader.load_many(symbols, since=warmup_since, until=until)
    print(f"\nLoaded panel: {list(panel.keys())}")
    for s in symbols:
        df = panel[s]
        print(f"  {s}: {df.shape[0]} rows, {df.index[0].date()} ~ {df.index[-1].date()}")

    # 统计区间边界（对齐到 panel 索引）
    common_idx = None
    for s in symbols:
        idx = panel[s].index
        common_idx = idx if common_idx is None else common_idx.intersection(idx)
    assert common_idx is not None
    common_idx = common_idx.sort_values()

    since_ts = pd.Timestamp(since, tz="UTC")
    until_ts = pd.Timestamp(until, tz="UTC")
    sample_idx = common_idx[(common_idx >= since_ts) & (common_idx <= until_ts)]
    print(f"\nsample bars (post-warmup): {len(sample_idx)}, "
          f"{sample_idx[0].date()} ~ {sample_idx[-1].date()}")

    # ---- S5 默认参数 ----
    print("\n[1/4] Running S5 (cutoff=0.0) ...")
    s5 = TrendTiltStrategy(
        symbols=symbols, rebalance_period=20,
        ma_short=20, ma_mid=60, ma_long=120,
        donchian_lookback=120, cutoff=0.0,
    )
    s5_res = s5.run(panel, init_cash=init_cash, fees=fees, slippage=slippage)
    s5_equity_full = s5_res.portfolio.value()
    if isinstance(s5_equity_full, pd.DataFrame):
        s5_equity_full = s5_equity_full.iloc[:, 0]
    s5_equity = _slice_equity(s5_equity_full, since_ts, until_ts).rename("S5_trend_tilt")

    s5_cash_ratio = _cash_ratio_series(s5_res.portfolio, since_ts, until_ts)
    s5_full_cash_days = int((s5_cash_ratio >= 0.99).sum())
    s5_partial_cash_days = int((s5_cash_ratio >= 0.50).sum())
    s5_total_days = len(s5_cash_ratio)
    cash_days_ratio = s5_full_cash_days / s5_total_days if s5_total_days else 0.0
    print(f"  S5 done: trigger_count={len(s5_res.rebalance_dates)}, "
          f"full_cash_days={s5_full_cash_days}/{s5_total_days} "
          f"(ratio={cash_days_ratio:.3f})")

    # ---- S3 等权 ----
    print("[2/4] Running S3 (equal rebalance) ...")
    s3 = EqualRebalanceStrategy(symbols=symbols, rebalance_period=20)
    s3_res = s3.run(panel, init_cash=init_cash, fees=fees, slippage=slippage)
    s3_equity_full = s3_res.portfolio.value()
    if isinstance(s3_equity_full, pd.DataFrame):
        s3_equity_full = s3_equity_full.iloc[:, 0]
    s3_equity = _slice_equity(s3_equity_full, since_ts, until_ts).rename("S3_equal")

    # ---- 510300 BH ----
    print("[3/4] Building 510300 BH benchmark ...")
    bh_full = panel['510300']['close'] / panel['510300']['close'].iloc[0] * init_cash
    bh_equity = bh_full.loc[since_ts:until_ts]
    # rebase: 让样本期起点 = init_cash
    bh_equity = (bh_equity / bh_equity.iloc[0] * init_cash).rename("510300_BH")

    # ---- S4 动量倾斜（可选） ----
    s4_equity = None
    if _has_s4:
        print("[4/4] Running S4 (momentum tilt) ...")
        try:
            s4 = MomentumTiltStrategy(symbols=symbols, rebalance_period=20)
            s4_res = s4.run(panel, init_cash=init_cash, fees=fees, slippage=slippage)
            s4_equity_full = s4_res.portfolio.value()
            if isinstance(s4_equity_full, pd.DataFrame):
                s4_equity_full = s4_equity_full.iloc[:, 0]
            s4_equity = _slice_equity(s4_equity_full, since_ts, until_ts).rename("S4_momentum")
        except Exception as e:
            print(f"  S4 run failed: {e}")
            s4_equity = None

    # ---- 整理样本期内的净值（对齐起点 = init_cash） ----
    def _rebase(s: pd.Series) -> pd.Series:
        if s is None or s.empty:
            return s
        return s / s.iloc[0] * init_cash

    curves = {
        "S5_trend_tilt": _rebase(s5_equity),
        "S3_equal": _rebase(s3_equity),
        "510300_BH": _rebase(bh_equity),
    }
    if s4_equity is not None:
        curves["S4_momentum"] = _rebase(s4_equity)

    # ---- 绩效表 ----
    print("\n--- 主绩效表 (样本期 [%s, %s], 起始净值=%.0f) ---" %
          (sample_idx[0].date(), sample_idx[-1].date(), init_cash))
    metrics_table = {}
    for name, s in curves.items():
        m = _equity_metrics(s)
        metrics_table[name] = m
        print(_format_metrics_row(name, m))

    # ---- 分年度收益 ----
    print("\n--- 分年度收益 ---")
    yearly = pd.DataFrame({name: _yearly_returns(s) for name, s in curves.items()})
    yearly.index = yearly.index.year
    print(yearly.round(4).to_string())

    # ---- S5 vs 基准 alpha ----
    rets_s5 = curves["S5_trend_tilt"].pct_change().dropna()
    rets_bh = curves["510300_BH"].pct_change().dropna()
    rets_s3 = curves["S3_equal"].pct_change().dropna()
    common = rets_s5.index.intersection(rets_bh.index)
    excess_vs_bh = rets_s5.loc[common] - rets_bh.loc[common]
    common3 = rets_s5.index.intersection(rets_s3.index)
    excess_vs_s3 = rets_s5.loc[common3] - rets_s3.loc[common3]

    def _ir(excess: pd.Series) -> dict:
        if excess.empty or excess.std() == 0:
            return {"alpha_ann": np.nan, "te_ann": np.nan, "ir": np.nan}
        return {
            "alpha_ann": float(excess.mean() * 252),
            "te_ann": float(excess.std() * np.sqrt(252)),
            "ir": float(excess.mean() / excess.std() * np.sqrt(252)),
        }

    ir_bh = _ir(excess_vs_bh)
    ir_s3 = _ir(excess_vs_s3)
    print(f"\nS5 vs 510300 BH: alpha_ann={ir_bh['alpha_ann']*100:.2f}%, "
          f"te={ir_bh['te_ann']*100:.2f}%, IR={ir_bh['ir']:.3f}")
    print(f"S5 vs S3 equal : alpha_ann={ir_s3['alpha_ann']*100:.2f}%, "
          f"te={ir_s3['te_ann']*100:.2f}%, IR={ir_s3['ir']:.3f}")

    # ---- S5 特有：空仓与 BH 跌幅相关性 ----
    is_full_cash = (s5_cash_ratio >= 0.99).astype(int).reindex(rets_bh.index, method="ffill").fillna(0)
    bh_neg_day = (rets_bh < 0).astype(int)
    if is_full_cash.var() > 0 and bh_neg_day.var() > 0:
        cash_neg_corr = float(np.corrcoef(is_full_cash.values, bh_neg_day.values)[0, 1])
    else:
        cash_neg_corr = float("nan")
    # 空仓时段的 BH 平均日收益
    bh_during_cash = rets_bh.loc[is_full_cash.astype(bool)]
    bh_avg_ret_during_cash = float(bh_during_cash.mean()) if len(bh_during_cash) else float("nan")
    bh_avg_ret_overall = float(rets_bh.mean())
    print(f"\nS5 特有：")
    print(f"  cash_days_ratio (>=99%空仓 / 总天数): {cash_days_ratio:.3f}")
    print(f"  半空仓+ (>=50%) 天数: {s5_partial_cash_days} / {s5_total_days} = "
          f"{s5_partial_cash_days/s5_total_days:.3f}")
    print(f"  全空仓段与 510300 BH '当日下跌' 相关性: {cash_neg_corr:.3f}")
    print(f"  全空仓时 510300 平均日收益: {bh_avg_ret_during_cash*100:.4f}% "
          f"(整体均值 {bh_avg_ret_overall*100:.4f}%)")

    # ---- artifacts ----
    _make_artifacts_dir()
    _plot_equity_curve(curves, ARTIFACTS_DIR / "equity_curve.png",
                       title=f"Equity Curves {since} ~ {until}")
    _plot_drawdown(curves, ARTIFACTS_DIR / "drawdown.png")
    _plot_cash_ratio(s5_cash_ratio, ARTIFACTS_DIR / "cash_ratio.png")
    _plot_regime_overlay(curves["510300_BH"], s5_cash_ratio,
                         ARTIFACTS_DIR / "regime_overlay.png")
    print(f"\nArtifacts saved to: {ARTIFACTS_DIR}")

    # ---- cutoff 敏感性 ----
    print("\n--- cutoff 敏感性 ---")
    sens_rows = []
    for cutoff in (0.0, 0.3, 0.5):
        strat_c = TrendTiltStrategy(
            symbols=symbols, rebalance_period=20,
            ma_short=20, ma_mid=60, ma_long=120,
            donchian_lookback=120, cutoff=cutoff,
        )
        res_c = strat_c.run(panel, init_cash=init_cash, fees=fees, slippage=slippage)
        eq_full = res_c.portfolio.value()
        if isinstance(eq_full, pd.DataFrame):
            eq_full = eq_full.iloc[:, 0]
        eq = _rebase(_slice_equity(eq_full, since_ts, until_ts))
        m = _equity_metrics(eq)
        cr = _cash_ratio_series(res_c.portfolio, since_ts, until_ts)
        full_cash_ratio = float((cr >= 0.99).mean()) if len(cr) else float("nan")
        sens_rows.append({
            "cutoff": cutoff,
            "total_return": m["total_return"],
            "cagr": m["cagr"],
            "sharpe": m["sharpe"],
            "max_dd": m["max_dd"],
            "calmar": m["calmar"],
            "cash_days_ratio": full_cash_ratio,
        })
        print(f"  cutoff={cutoff:.1f}: total={m['total_return']*100:>7.2f}%  "
              f"CAGR={m['cagr']*100:>5.2f}%  Sharpe={m['sharpe']:>5.2f}  "
              f"MaxDD={m['max_dd']*100:>7.2f}%  Calmar={m['calmar']:>5.2f}  "
              f"cash_days_ratio={full_cash_ratio:.3f}")
    sens_df = pd.DataFrame(sens_rows)

    # 返回汇总，validation.md 那一节用得到
    return {
        "metrics": metrics_table,
        "yearly": yearly,
        "ir_bh": ir_bh,
        "ir_s3": ir_s3,
        "cash_days_ratio": cash_days_ratio,
        "partial_cash_days": s5_partial_cash_days,
        "total_days": s5_total_days,
        "cash_neg_corr": cash_neg_corr,
        "bh_avg_ret_during_cash": bh_avg_ret_during_cash,
        "bh_avg_ret_overall": bh_avg_ret_overall,
        "sensitivity": sens_df,
        "trigger_count": len(s5_res.rebalance_dates),
        "sample_start": str(sample_idx[0].date()),
        "sample_end": str(sample_idx[-1].date()),
        "n_bars": len(sample_idx),
    }


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------
def main(argv: list[str]) -> int:
    mode = "smoke"
    if len(argv) > 1:
        mode = argv[1].lower()

    if mode in ("smoke", "all"):
        run_smoke()
    if mode in ("real", "all"):
        run_real()

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
