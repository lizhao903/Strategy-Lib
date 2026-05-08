"""Validation runner for EqualRebalanceStrategy (Strategy 3, Benchmark Suite V1).

Two subcommands:
  - ``smoke``：合成数据 panel 上的契约测试（不依赖 vectorbt / 真实数据）
  - ``real`` ：真实数据回测（2020-01-01 ~ 2024-12-31，6 只 V1 基线 ETF）

Smoke 子命令验证：
  1. EqualRebalanceStrategy 可正常实例化
  2. build_target_weight_panel 在触发日产生 1/n 等权（和=1，非负）
  3. drift_threshold 模式可正确减少触发次数
  4. **target_weights 钩子可被子类覆盖**（S4/S5 契约）
  5. 子类返回未归一权重时基类会自动重归一化

Real 子命令：
  - 用 ``data.get_loader('cn_etf')`` 拉 6 只 ETF（均已预缓存）
  - 跑 EqualRebalanceStrategy.run() 得到 portfolio + metrics
  - 单独 load 510300 buy-and-hold 同窗口同成本作为 benchmark
  - 跑 rebalance_period 敏感性（5/10/20/60）
  - 出图到 artifacts/

CLI 用法：
    python validate.py smoke
    python validate.py real --since 2020-01-01 --until 2024-12-31
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

# 直接加载 cn_etf_equal_rebalance.py 模块（绕过 strategy_lib 包的 __init__，
# 后者会 import loguru 等可选依赖；smoke test 不需要它们）。
ROOT = Path(__file__).resolve().parents[3]
ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
MODULE_PATH = ROOT / "src" / "strategy_lib" / "strategies" / "cn_etf_equal_rebalance.py"
_spec = importlib.util.spec_from_file_location("cn_etf_equal_rebalance", MODULE_PATH)
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
sys.modules["cn_etf_equal_rebalance"] = _module  # Python 3.13 dataclass 需要这一步
_spec.loader.exec_module(_module)
EqualRebalanceStrategy = _module.EqualRebalanceStrategy

# V1 基线常量 ----------------------------------------------------------------
def _setup_cjk_font() -> None:
    """让 matplotlib 能渲染中文图例（macOS 默认走 Hiragino Sans GB）。"""
    try:
        import matplotlib

        matplotlib.rcParams["font.sans-serif"] = [
            "Hiragino Sans GB",
            "PingFang HK",
            "Heiti TC",
            "STHeiti",
            "Arial Unicode MS",
            "DejaVu Sans",
        ]
        matplotlib.rcParams["axes.unicode_minus"] = False
    except Exception:  # noqa: BLE001
        pass


RISK_SYMBOLS: list[str] = ["510300", "510500", "159915", "512100", "512880", "512170"]
SYMBOL_NAMES: dict[str, str] = {
    "510300": "沪深300",
    "510500": "中证500",
    "159915": "创业板",
    "512100": "中证1000",
    "512880": "证券",
    "512170": "医疗",
}
INIT_CASH: float = 100_000.0
FEES: float = 0.00005
SLIPPAGE: float = 0.0005
BENCHMARK_SYMBOL: str = "510300"


# =============================================================================
# Smoke tests
# =============================================================================


def make_synth_panel(symbols: list[str], n_days: int = 250, seed: int = 42) -> dict[str, pd.DataFrame]:
    """为给定 symbol 生成合成 OHLCV panel（共享日历）。"""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2023-01-02", periods=n_days, freq="B", tz="UTC", name="timestamp")
    panel: dict[str, pd.DataFrame] = {}
    for i, sym in enumerate(symbols):
        rets = rng.normal(0.0005, 0.015, size=n_days) + 0.0002 * i  # 给每个 symbol 一点漂移差异
        close = 100.0 * np.exp(np.cumsum(rets))
        high = close * (1 + np.abs(rng.normal(0, 0.005, size=n_days)))
        low = close * (1 - np.abs(rng.normal(0, 0.005, size=n_days)))
        open_ = close * (1 + rng.normal(0, 0.003, size=n_days))
        volume = rng.uniform(1e6, 5e6, size=n_days)
        panel[sym] = pd.DataFrame(
            {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
            index=idx,
        )
    return panel


def _check(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)
    print(f"  PASS  {msg}")


def test_basic_equal_weight_panel() -> None:
    print("\n[1] basic equal-weight target panel")
    strat = EqualRebalanceStrategy(rebalance_period=20)
    panel = make_synth_panel(list(strat.symbols))

    weights_df, triggered = strat.build_target_weight_panel(panel)

    _check(weights_df.shape[1] == 6, "6 symbols in weights_df")
    triggered_rows = weights_df.loc[triggered]
    _check(np.allclose(triggered_rows.values, 1 / 6), "每个触发日权重 = 1/6")
    _check(np.allclose(triggered_rows.sum(axis=1), 1.0), "触发日权重和 = 1.0")
    _check((triggered_rows >= 0).all().all(), "权重非负")
    non_triggered = weights_df.drop(triggered)
    _check(non_triggered.isna().all().all(), "非触发日权重为 NaN")
    expected = (250 // 20) + (1 if 250 % 20 else 0)
    _check(len(triggered) == expected, f"触发次数 = {len(triggered)} (期望 {expected})")


def test_drift_threshold_reduces_triggers() -> None:
    print("\n[2] drift_threshold 减少触发次数")
    panel = make_synth_panel(list(EqualRebalanceStrategy.DEFAULT_SYMBOLS))

    base = EqualRebalanceStrategy(rebalance_period=20, drift_threshold=None)
    drift = EqualRebalanceStrategy(rebalance_period=20, drift_threshold=0.05)

    _, base_trig = base.build_target_weight_panel(panel)
    _, drift_trig = drift.build_target_weight_panel(panel)

    _check(len(drift_trig) >= 1, "drift 模式至少触发 1 次（初始建仓）")
    _check(len(drift_trig) <= len(base_trig), "drift 模式触发次数 <= 纯日历")


def test_subclass_override_target_weights() -> None:
    """**核心测试：S4/S5 契约**——子类覆盖 target_weights 应被父类正确消费。"""
    print("\n[3] subclass override target_weights (S4/S5 契约)")

    class TiltedStrategy(EqualRebalanceStrategy):
        def target_weights(self, date, prices_panel):  # noqa: D401, ARG002
            n = len(self.symbols)
            heavy = self.symbols[0]
            tilt: dict[str, float] = {heavy: 0.5}
            other = 0.5 / (n - 1)
            for s in self.symbols[1:]:
                tilt[s] = other
            return tilt

    strat = TiltedStrategy(rebalance_period=20)
    panel = make_synth_panel(list(strat.symbols))

    weights_df, triggered = strat.build_target_weight_panel(panel)
    row = weights_df.loc[triggered[0]]

    _check(abs(row[strat.symbols[0]] - 0.5) < 1e-9, "覆盖后 heavy symbol 权重 = 0.5")
    _check(abs(row.drop(strat.symbols[0]).iloc[0] - 0.5 / 5) < 1e-9, "其余 symbol 权重 = 0.1")
    _check(abs(row.sum() - 1.0) < 1e-9, "覆盖后权重和 = 1.0")


def test_subclass_unnormalized_weights_get_renormalized() -> None:
    print("\n[4] 未归一权重自动重归一化")

    class UnnormalizedStrategy(EqualRebalanceStrategy):
        def target_weights(self, date, prices_panel):  # noqa: ARG002
            return {s: 1.0 for s in self.symbols}

    strat = UnnormalizedStrategy(rebalance_period=20)
    panel = make_synth_panel(list(strat.symbols))
    weights_df, triggered = strat.build_target_weight_panel(panel)
    row = weights_df.loc[triggered[0]]
    _check(abs(row.sum() - 1.0) < 1e-9, "重归一化后和 = 1.0")
    _check(np.allclose(row.values, 1 / 6), "重归一化后等权")


def test_subclass_negative_weights_raise() -> None:
    print("\n[5] 负权重报错")

    class ShortingStrategy(EqualRebalanceStrategy):
        def target_weights(self, date, prices_panel):  # noqa: ARG002
            w = {s: 1.0 / len(self.symbols) for s in self.symbols}
            w[self.symbols[0]] = -0.1
            return w

    strat = ShortingStrategy()
    panel = make_synth_panel(list(strat.symbols))
    try:
        strat.build_target_weight_panel(panel)
    except ValueError as e:
        _check("负值" in str(e) or "负" in str(e), "raises ValueError 提示负值")
        return
    raise AssertionError("应当抛出 ValueError")


def run_smoke() -> int:
    tests = [
        test_basic_equal_weight_panel,
        test_drift_threshold_reduces_triggers,
        test_subclass_override_target_weights,
        test_subclass_unnormalized_weights_get_renormalized,
        test_subclass_negative_weights_raise,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception:  # noqa: BLE001
            failed += 1
            print(f"  FAIL  {t.__name__}")
            traceback.print_exc()
    print(f"\n{'=' * 60}\n{len(tests) - failed}/{len(tests)} passed")
    return 0 if failed == 0 else 1


# =============================================================================
# Real-data backtest helpers
# =============================================================================


def _load_panel(symbols: list[str], since: str, until: str) -> dict[str, pd.DataFrame]:
    """通过 strategy_lib.data.get_loader 加载 6 只 ETF（命中本地 parquet 缓存）。"""
    # 确保 src/ 在 sys.path（包根 strategy_lib 在 src/ 下）
    src = ROOT / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    from strategy_lib.data import get_loader

    loader = get_loader("cn_etf")
    panel = loader.load_many(symbols, since=since, until=until)
    missing = [s for s in symbols if s not in panel or panel[s].empty]
    if missing:
        raise RuntimeError(f"missing data for symbols: {missing}")
    return panel


def _benchmark_buy_hold(
    benchmark_close: pd.Series,
    *,
    init_cash: float = INIT_CASH,
    fees: float = FEES,
    slippage: float = SLIPPAGE,
):
    """单 asset buy-and-hold portfolio（用与策略一致的费率）。"""
    import vectorbt as vbt

    size = pd.Series(np.nan, index=benchmark_close.index, dtype="float64")
    size.iloc[0] = 1.0  # 第一天满仓买入并持有
    pf = vbt.Portfolio.from_orders(
        close=benchmark_close,
        size=size,
        size_type="targetpercent",
        init_cash=init_cash,
        fees=fees,
        slippage=slippage,
        freq="1D",
    )
    return pf


def _annualized_turnover(pf, *, init_cash: float = INIT_CASH) -> float:
    """估算年化换手率：sum(|order notional|) / mean(value) / years。

    注意：这是双边换手（买+卖）。S3 等权再平衡的换手率通常每次再平衡 ~10-20%
    总名义价值变动，年化下来一般在 50-200% 之间。
    """
    orders = pf.orders.records_readable
    if len(orders) == 0:
        return 0.0
    # records_readable 在不同 vbt 版本字段名略有差异，这里统一保护取数
    cols = {c.lower(): c for c in orders.columns}
    size_col = cols.get("size")
    price_col = cols.get("price")
    if size_col is None or price_col is None:
        # fallback：直接用 records 字段
        size_col, price_col = "Size", "Price"
    notional = (orders[size_col].astype(float) * orders[price_col].astype(float)).abs().sum()

    value = pf.value()
    mean_value = float(value.mean()) if hasattr(value, "mean") else float(value)
    if mean_value <= 0:
        mean_value = init_cash
    n_days = len(pf.value())
    years = max(n_days / 252.0, 1e-9)
    # 双边除以 2 以得到单边等价（行业惯例）
    return notional / mean_value / years / 2.0


def _safe_scalar(x) -> float:
    """vectorbt 在 group_by 模式下可能返回 0-d Series；统一变成 float。"""
    try:
        return float(x)
    except (TypeError, ValueError):
        return float(np.asarray(x).item())


def _portfolio_summary(pf, *, init_cash: float = INIT_CASH) -> dict:
    """提取关键绩效指标。"""
    value = pf.value()
    if isinstance(value, pd.DataFrame):
        value = value.sum(axis=1)
    final_value = float(value.iloc[-1])
    total_return = final_value / init_cash - 1.0
    n_days = len(value)
    years = max(n_days / 252.0, 1e-9)
    cagr = (final_value / init_cash) ** (1 / years) - 1.0
    rets = value.pct_change().dropna()
    vol = float(rets.std() * np.sqrt(252.0)) if len(rets) > 1 else float("nan")
    sharpe = _safe_scalar(pf.sharpe_ratio())
    max_dd = _safe_scalar(pf.max_drawdown())
    calmar = cagr / abs(max_dd) if max_dd not in (0.0, None) and not np.isnan(max_dd) else float("nan")
    turnover = _annualized_turnover(pf, init_cash=init_cash)
    return {
        "final_value": final_value,
        "total_return": total_return,
        "cagr": cagr,
        "vol": vol,
        "sharpe": sharpe,
        "max_drawdown": max_dd,
        "calmar": calmar,
        "annual_turnover": turnover,
    }


def _yearly_returns(value: pd.Series) -> pd.Series:
    """按年度计算收益率（基于 portfolio value 序列的首末）。"""
    if isinstance(value, pd.DataFrame):
        value = value.sum(axis=1)
    df = value.copy()
    df.index = pd.to_datetime(df.index)
    out: dict[int, float] = {}
    for year, group in df.groupby(df.index.year):
        if len(group) < 2:
            continue
        out[int(year)] = float(group.iloc[-1] / group.iloc[0] - 1.0)
    return pd.Series(out, name="yearly_return")


def _excess_metrics(strat_value: pd.Series, bench_value: pd.Series) -> dict:
    """超额收益 / 信息比率 / 跟踪误差。"""
    if isinstance(strat_value, pd.DataFrame):
        strat_value = strat_value.sum(axis=1)
    if isinstance(bench_value, pd.DataFrame):
        bench_value = bench_value.sum(axis=1)
    s = strat_value.pct_change().dropna()
    b = bench_value.pct_change().dropna()
    aligned = pd.concat([s.rename("s"), b.rename("b")], axis=1).dropna()
    excess = aligned["s"] - aligned["b"]
    if excess.std() == 0 or len(excess) < 2:
        ir = float("nan")
    else:
        ir = float(excess.mean() / excess.std() * np.sqrt(252.0))
    te = float(excess.std() * np.sqrt(252.0)) if len(excess) > 1 else float("nan")
    cum_excess = float((1 + aligned["s"]).prod() - (1 + aligned["b"]).prod())
    return {"alpha_total": cum_excess, "info_ratio": ir, "tracking_error": te}


# =============================================================================
# Plotting
# =============================================================================


def _plot_equity_curve(
    strat_value: pd.Series,
    bench_value: pd.Series,
    out_path: Path,
) -> None:
    import matplotlib.pyplot as plt

    if isinstance(strat_value, pd.DataFrame):
        strat_value = strat_value.sum(axis=1)
    if isinstance(bench_value, pd.DataFrame):
        bench_value = bench_value.sum(axis=1)
    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.plot(strat_value.index, strat_value.values, label="S3 EqualRebalance (period=20)", lw=1.6, color="#d6604d")
    ax.plot(bench_value.index, bench_value.values, label="510300 Buy & Hold", lw=1.4, color="#4393c3", linestyle="--")
    ax.set_title("Strategy 3 vs 510300 BH — Equity Curve")
    ax.set_xlabel("Date")
    ax.set_ylabel("Portfolio Value (RMB)")
    ax.grid(alpha=0.3)
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)


def _plot_drawdown(
    strat_value: pd.Series,
    bench_value: pd.Series,
    out_path: Path,
) -> None:
    import matplotlib.pyplot as plt

    if isinstance(strat_value, pd.DataFrame):
        strat_value = strat_value.sum(axis=1)
    if isinstance(bench_value, pd.DataFrame):
        bench_value = bench_value.sum(axis=1)

    def _dd(v: pd.Series) -> pd.Series:
        peak = v.cummax()
        return v / peak - 1.0

    s_dd = _dd(strat_value)
    b_dd = _dd(bench_value)
    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.fill_between(s_dd.index, s_dd.values, 0, color="#d6604d", alpha=0.35, label="S3 drawdown")
    ax.plot(b_dd.index, b_dd.values, color="#4393c3", lw=1.2, label="510300 BH drawdown")
    ax.set_title("Drawdown — S3 vs 510300 BH")
    ax.set_ylabel("Drawdown")
    ax.grid(alpha=0.3)
    ax.legend(loc="lower left")
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)


def _plot_rebalance_dates(
    rebalance_dates: pd.DatetimeIndex,
    pre_post_drift: list[tuple[pd.Timestamp, pd.Series, pd.Series]],
    symbols: list[str],
    out_path: Path,
) -> None:
    """两栏：上 - 再平衡日期分布；下 - 每次 rebalance 前后权重偏离条形图。"""
    import matplotlib.pyplot as plt

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7.5), gridspec_kw={"height_ratios": [1, 2]})

    # 上：日期分布（作为 rug + 月度直方）
    ax1.vlines(rebalance_dates, 0, 1, color="#d6604d", lw=1)
    ax1.set_yticks([])
    ax1.set_title(f"Rebalance Dates (n={len(rebalance_dates)})")
    ax1.set_xlim(rebalance_dates.min(), rebalance_dates.max())
    ax1.grid(axis="x", alpha=0.3)

    # 下：每次 rebalance 前的实际权重 - 目标 (1/n) 偏离
    if pre_post_drift:
        # 取一段中间窗口（避免初始建仓没有"前"），最多展示 12 次再平衡
        sample = pre_post_drift[1:13] if len(pre_post_drift) > 1 else pre_post_drift
        n_groups = len(sample)
        bar_width = 0.8 / max(len(symbols), 1)
        x_base = np.arange(n_groups)
        colors = plt.cm.tab10(np.linspace(0, 1, len(symbols)))
        for i, sym in enumerate(symbols):
            drifts = [float(pre[sym] - 1.0 / len(symbols)) for _, pre, _ in sample]
            ax2.bar(
                x_base + i * bar_width,
                drifts,
                width=bar_width,
                label=f"{sym} {SYMBOL_NAMES.get(sym, '')}",
                color=colors[i],
            )
        ax2.set_xticks(x_base + bar_width * (len(symbols) - 1) / 2)
        ax2.set_xticklabels(
            [pd.Timestamp(t).strftime("%Y-%m") for t, _, _ in sample],
            rotation=45,
            ha="right",
        )
        ax2.axhline(0.0, color="black", lw=0.8)
        ax2.set_title("Pre-rebalance weight drift from 1/6 (sample of mid-period rebalances)")
        ax2.set_ylabel("actual w - 1/6")
        ax2.legend(ncol=3, fontsize=8, loc="best")
        ax2.grid(axis="y", alpha=0.3)
    else:
        ax2.text(0.5, 0.5, "no rebalance drift data", ha="center", transform=ax2.transAxes)

    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)


def _plot_weight_drift_heatmap(
    actual_weights_df: pd.DataFrame,
    out_path: Path,
) -> None:
    """6 只 ETF 的权重时间序列热图（持仓占组合总价值的比例）。"""
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(13, 4.5))
    # 行：symbol；列：日期。下采样到 ~250 个时间点避免太密。
    df = actual_weights_df.copy()
    if len(df) > 252 * 5:
        step = max(1, len(df) // (252 * 2))
        df = df.iloc[::step]
    mat = df.T.values
    # 自适应色阶：S3 等权下偏离很小，把 vmax 收紧到 actual max + 一点 padding
    vmax = float(np.nanmax(mat))
    vmin = float(np.nanmin(mat))
    # 居中在 1/n 附近，使颜色对比凸显偏离
    n_assets = mat.shape[0]
    target = 1.0 / n_assets if n_assets > 0 else 0.167
    half = max(vmax - target, target - vmin, 0.02)
    im = ax.imshow(
        mat,
        aspect="auto",
        cmap="RdYlBu_r",
        vmin=max(0.0, target - half),
        vmax=target + half,
        extent=[0, len(df), len(df.columns), 0],
    )
    ax.set_yticks(np.arange(len(df.columns)) + 0.5)
    ax.set_yticklabels([f"{s} {SYMBOL_NAMES.get(s, '')}" for s in df.columns])
    # 横轴选 ~6 个均匀刻度
    n_ticks = 6
    tick_pos = np.linspace(0, len(df) - 1, n_ticks).astype(int)
    ax.set_xticks(tick_pos)
    ax.set_xticklabels([df.index[i].strftime("%Y-%m") for i in tick_pos])
    ax.set_title("Actual weight heatmap (each row = ETF, color = portfolio share)")
    cbar = fig.colorbar(im, ax=ax, shrink=0.85)
    cbar.set_label("weight")
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)


def _actual_weights_from_pf(pf, symbols: list[str]) -> pd.DataFrame:
    """从 vbt Portfolio 提取每个 asset 的资产价值占比时间序列。"""
    asset_value = pf.asset_value(group_by=False)  # DataFrame [date, symbol]
    if isinstance(asset_value, pd.Series):
        asset_value = asset_value.to_frame()
    # 列序对齐到我们想要的 symbols
    asset_value = asset_value.reindex(columns=symbols)
    total = asset_value.sum(axis=1).replace(0, np.nan)
    weights = asset_value.div(total, axis=0).fillna(0.0)
    return weights


# =============================================================================
# Real-data run
# =============================================================================


def run_real(
    since: str = "2020-01-01",
    until: str = "2024-12-31",
    rebalance_period: int = 20,
    sensitivity_periods: tuple[int, ...] = (5, 10, 20, 60),
) -> dict:
    """真实数据回测主入口。

    返回：
        dict, 包含主结果指标 / benchmark 指标 / 敏感性表 / 分年度收益。
    """
    _setup_cjk_font()
    print(f"\n[real] backtest window: {since} ~ {until}")
    print(f"[real] symbols: {RISK_SYMBOLS}")
    print(f"[real] rebalance_period: {rebalance_period} (sensitivity: {sensitivity_periods})")
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 加载数据
    panel = _load_panel(RISK_SYMBOLS, since=since, until=until)
    for s, df in panel.items():
        print(f"  loaded {s}: {df.index.min().date()} ~ {df.index.max().date()}, n={len(df)}")
    bench = _load_panel([BENCHMARK_SYMBOL], since=since, until=until)[BENCHMARK_SYMBOL]

    # 2. 主策略：rebalance_period=20
    strat = EqualRebalanceStrategy(symbols=RISK_SYMBOLS, rebalance_period=rebalance_period)
    result = strat.run(panel, init_cash=INIT_CASH, fees=FEES, slippage=SLIPPAGE)
    pf = result.portfolio
    weights_df = result.target_weights
    rebalance_dates = result.rebalance_dates
    print(f"[real] strategy: {len(rebalance_dates)} rebalances over {len(weights_df)} days")

    # 3. Benchmark：510300 BH（对齐到策略交易日历）
    bench_close = bench["close"].reindex(weights_df.index).ffill().dropna()
    bench_pf = _benchmark_buy_hold(bench_close)

    # 4. 指标
    main_metrics = _portfolio_summary(pf)
    bench_metrics = _portfolio_summary(bench_pf)
    excess = _excess_metrics(pf.value(), bench_pf.value())
    yearly_strat = _yearly_returns(pf.value())
    yearly_bench = _yearly_returns(bench_pf.value())

    print("\n[real] === Main result (rebalance_period=20) ===")
    for k, v in main_metrics.items():
        print(f"  {k:>18s}: {v:.4f}" if isinstance(v, float) else f"  {k:>18s}: {v}")
    print("\n[real] === Benchmark 510300 BH ===")
    for k, v in bench_metrics.items():
        print(f"  {k:>18s}: {v:.4f}" if isinstance(v, float) else f"  {k:>18s}: {v}")
    print("\n[real] === Excess vs benchmark ===")
    for k, v in excess.items():
        print(f"  {k:>18s}: {v:.4f}" if isinstance(v, float) else f"  {k:>18s}: {v}")

    # 5. 敏感性扫描
    sens_rows: list[dict] = []
    sens_pfs: dict[int, object] = {}
    for p in sensitivity_periods:
        s_strat = EqualRebalanceStrategy(symbols=RISK_SYMBOLS, rebalance_period=p)
        s_res = s_strat.run(panel, init_cash=INIT_CASH, fees=FEES, slippage=SLIPPAGE)
        s_metrics = _portfolio_summary(s_res.portfolio)
        s_metrics["rebalance_period"] = p
        s_metrics["n_rebalances"] = len(s_res.rebalance_dates)
        sens_rows.append(s_metrics)
        sens_pfs[p] = s_res.portfolio
    sens_df = pd.DataFrame(sens_rows).set_index("rebalance_period")
    sens_df = sens_df[
        ["n_rebalances", "final_value", "cagr", "sharpe", "max_drawdown", "annual_turnover"]
    ]
    print("\n[real] === Rebalance period sensitivity ===")
    print(sens_df.round(4).to_string())

    # 6. 写 CSV：分年度 + 敏感性
    yearly_df = pd.concat(
        [yearly_strat.rename("S3_period20"), yearly_bench.rename("BH_510300")],
        axis=1,
    ).round(4)
    yearly_df.to_csv(ARTIFACTS_DIR / "yearly_returns.csv")
    sens_df.round(6).to_csv(ARTIFACTS_DIR / "rebalance_period_sensitivity.csv")
    print(f"\n[real] yearly returns:\n{yearly_df.to_string()}")

    # 7. 绘图
    _plot_equity_curve(pf.value(), bench_pf.value(), ARTIFACTS_DIR / "equity_curve.png")
    _plot_drawdown(pf.value(), bench_pf.value(), ARTIFACTS_DIR / "drawdown.png")

    # 收集每次 rebalance 前后的实际权重
    actual_weights = _actual_weights_from_pf(pf, RISK_SYMBOLS)
    pre_post_drift: list[tuple[pd.Timestamp, pd.Series, pd.Series]] = []
    for d in rebalance_dates:
        # "pre" = 当日开盘前（即前一交易日收盘时的权重）；"post" = 当日（再平衡后）
        if d not in actual_weights.index:
            continue
        pos = actual_weights.index.get_loc(d)
        if pos == 0:
            continue
        pre = actual_weights.iloc[pos - 1]
        post = actual_weights.iloc[pos]
        pre_post_drift.append((d, pre, post))
    _plot_rebalance_dates(
        rebalance_dates, pre_post_drift, RISK_SYMBOLS, ARTIFACTS_DIR / "rebalance_dates.png"
    )
    _plot_weight_drift_heatmap(actual_weights, ARTIFACTS_DIR / "weight_drift_heatmap.png")

    print(f"\n[real] artifacts written to: {ARTIFACTS_DIR}")
    for f in sorted(ARTIFACTS_DIR.iterdir()):
        print(f"  - {f.name}")

    return {
        "main_metrics": main_metrics,
        "bench_metrics": bench_metrics,
        "excess": excess,
        "yearly": yearly_df,
        "sensitivity": sens_df,
        "rebalance_dates": rebalance_dates,
    }


# =============================================================================
# CLI
# =============================================================================


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Validate Strategy 3 (cn_etf_equal_rebalance).")
    sub = p.add_subparsers(dest="cmd", required=False)
    sub.add_parser("smoke", help="run synthetic-data contract tests (no vectorbt needed)")
    p_real = sub.add_parser("real", help="run real-data backtest (2020-2024)")
    p_real.add_argument("--since", default="2020-01-01")
    p_real.add_argument("--until", default="2024-12-31")
    p_real.add_argument("--rebalance-period", type=int, default=20)
    p_real.add_argument(
        "--sensitivity",
        default="5,10,20,60",
        help="comma-separated rebalance_period values for the sensitivity sweep",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.cmd is None or args.cmd == "smoke":
        return run_smoke()
    if args.cmd == "real":
        periods = tuple(int(x) for x in args.sensitivity.split(",") if x.strip())
        run_real(
            since=args.since,
            until=args.until,
            rebalance_period=args.rebalance_period,
            sensitivity_periods=periods,
        )
        return 0
    parser.error(f"unknown subcommand: {args.cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
