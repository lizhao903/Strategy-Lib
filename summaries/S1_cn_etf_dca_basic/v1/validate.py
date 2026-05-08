"""验证脚本：基础 DCA (cn_etf_dca_basic)。

用法
----
1) Smoke test（合成数据，零依赖）:
       python summaries/cn_etf_dca_basic/validate.py --smoke

2) 真实数据回测（需 akshare + 网络）:
       python summaries/cn_etf_dca_basic/validate.py

输出
----
- 关键指标到 stdout
- 真实回测时绘图保存到 summaries/cn_etf_dca_basic/artifacts/
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 让脚本在仓库根目录下直接运行
ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

ARTIFACTS = Path(__file__).resolve().parent / "artifacts"


# ---------------------------------------------------------------- smoke test


def make_synth_panel(seed: int = 42, n_days: int = 250) -> dict:
    """合成 7 个 symbol（cash + 6 risk）的 OHLCV panel，与 tests/conftest.py 风格一致。"""
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(seed)
    idx = pd.date_range("2023-01-02", periods=n_days, freq="B", tz="UTC", name="timestamp")
    panel = {}

    # 货币 ETF：极低波动，缓慢上涨（年化 ~2%）
    cash_rets = rng.normal(0.00008, 0.0002, size=n_days)
    cash_close = 100 * np.exp(np.cumsum(cash_rets))
    panel["511990"] = pd.DataFrame(
        {
            "open": cash_close, "high": cash_close * 1.0001,
            "low": cash_close * 0.9999, "close": cash_close,
            "volume": rng.uniform(1e5, 5e5, size=n_days),
        },
        index=idx,
    )

    # 风险 ETF：日波动 ~2%，年化漂移 8%
    risk_syms = ["510300", "510500", "159915", "512100", "512880", "512170"]
    for i, sym in enumerate(risk_syms):
        sub_rng = np.random.default_rng(seed + i + 1)
        rets = sub_rng.normal(0.0003, 0.018, size=n_days)
        close = 5.0 * np.exp(np.cumsum(rets))
        high = close * (1 + np.abs(sub_rng.normal(0, 0.005, size=n_days)))
        low = close * (1 - np.abs(sub_rng.normal(0, 0.005, size=n_days)))
        open_ = close * (1 + sub_rng.normal(0, 0.003, size=n_days))
        panel[sym] = pd.DataFrame(
            {"open": open_, "high": high, "low": low, "close": close,
             "volume": sub_rng.uniform(1e6, 5e6, size=n_days)},
            index=idx,
        )
    return panel


def run_smoke() -> dict:
    """合成数据 smoke test：策略实例化 + run()，断言指标 dict 结构。"""
    from strategy_lib.strategies.cn_etf_dca_basic import DCABasicStrategy

    panel = make_synth_panel()
    strat = DCABasicStrategy()
    result = strat.run(panel, init_cash=100_000)

    metrics = result.metrics
    assert isinstance(metrics, dict), f"metrics 应为 dict，实际 {type(metrics)}"
    for k in ("total_return", "cagr", "sharpe", "max_drawdown", "annual_turnover", "n_trades"):
        assert k in metrics, f"metrics 缺少键 {k}"

    assert result.equity.iloc[0] > 0, "起始净值应 > 0"
    assert result.equity.notna().all(), "净值不应有 NaN"
    assert len(result.holdings.columns) == 6, "应持有 6 只风险 ETF"
    # 至少触发了 ~12 次 DCA（一年合成数据）
    assert result.metrics["n_trades"] > 0, "DCA 应至少产生 1 次交易"

    print("=" * 60)
    print("[SMOKE TEST PASSED] cn_etf_dca_basic")
    print("=" * 60)
    print(f"days simulated     : {len(result.equity)}")
    print(f"first equity       : {result.equity.iloc[0]:>12,.2f}")
    print(f"final equity       : {result.equity.iloc[-1]:>12,.2f}")
    print(f"final cash share   : {result.weights['__cash__'].iloc[-1]:>12.2%}")
    print(f"n DCA trades       : {result.metrics['n_trades']:>12d}")
    print("--- metrics ---")
    for k, v in result.metrics.items():
        print(f"  {k:<18}: {v}")
    return metrics


# ---------------------------------------------------------------- real backtest


def _ann_metrics(equity, init_cash: float = 100_000, ann_factor: float = 252.0):
    """简易年化指标助手：CAGR / vol / Sharpe / MaxDD / Calmar。"""
    import numpy as np

    rets = equity.pct_change().fillna(0.0)
    n = len(equity)
    years = max(n / ann_factor, 1e-9)
    cagr = float((equity.iloc[-1] / init_cash) ** (1 / years) - 1.0)
    ann_vol = float(rets.std(ddof=0) * np.sqrt(ann_factor))
    sharpe = (
        float(rets.mean() / rets.std(ddof=0) * np.sqrt(ann_factor))
        if rets.std(ddof=0) > 0
        else float("nan")
    )
    cummax = equity.cummax()
    dd = equity / cummax - 1.0
    max_dd = float(dd.min())
    calmar = float(cagr / abs(max_dd)) if max_dd < 0 else float("nan")
    return {
        "cagr": cagr,
        "ann_vol": ann_vol,
        "sharpe": sharpe,
        "max_drawdown": max_dd,
        "calmar": calmar,
        "drawdown_series": dd,
    }


def _yearly_returns(equity, init_cash: float = 100_000):
    """按自然年返回 dict[year -> return]。第一年从 init_cash 起算。"""
    import pandas as pd

    yearly_last = equity.resample("YE").last()
    yearly_first = equity.resample("YE").first()
    out = {}
    prev = init_cash
    for ts, last in yearly_last.items():
        # 用上一年末（或初始）作为起点更稳；这里用 init_cash + 链式
        first = yearly_first.loc[ts]
        # 第一年特殊处理：从 init_cash 起算
        if ts.year == yearly_last.index[0].year:
            ret = float(last / init_cash - 1.0)
        else:
            ret = float(last / prev - 1.0)
        out[ts.year] = ret
        prev = last
    return out


def run_real() -> dict:
    """真实数据回测：通过 strategy_lib.data.get_loader('cn_etf') 拉 akshare 行情（命中本地 parquet 缓存）。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd

    from strategy_lib.data import get_loader
    from strategy_lib.strategies.cn_etf_dca_basic import (
        DCABasicStrategy,
        DEFAULT_CASH_SYMBOL,
        DEFAULT_RISK_POOL,
    )

    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    since = "2020-01-01"
    until = "2024-12-31"
    benchmark_sym = "510300"
    init_cash = 100_000.0

    loader = get_loader("cn_etf")
    symbols = [DEFAULT_CASH_SYMBOL] + list(DEFAULT_RISK_POOL)
    panel = loader.load_many(symbols, timeframe="1d", since=since, until=until)

    missing = [s for s in symbols if s not in panel]
    if missing:
        raise RuntimeError(f"akshare 加载失败的 symbol：{missing}")

    # loader 返回 tz-aware (UTC) 索引；DCABasicStrategy.run 内部用 tz-naive Timestamp 做切片，
    # 会触发 tz mismatch。这里在 panel 层面把索引转为 tz-naive，并保证 since/until 切片已应用。
    sliced_panel: dict[str, pd.DataFrame] = {}
    for sym, df in panel.items():
        df = df.copy()
        if df.index.tz is not None:
            df.index = df.index.tz_convert(None)
        df = df.loc[(df.index >= pd.Timestamp(since)) & (df.index <= pd.Timestamp(until))]
        sliced_panel[sym] = df

    strat = DCABasicStrategy()
    result = strat.run(
        sliced_panel,
        init_cash=init_cash,
        fees=0.00005,
        slippage=0.0005,
    )

    # —— 基准：510300 买入持有，初始 100k，按收盘价等额买入 ——
    bench_close = sliced_panel[benchmark_sym]["close"].copy()
    # 对齐到策略 equity 的索引
    bench_close = bench_close.reindex(result.equity.index).ffill()
    bench_equity = init_cash * bench_close / bench_close.iloc[0]
    bench_equity.name = "bench_equity"

    # —— 指标 ——
    strat_m = result.metrics
    bench_m = _ann_metrics(bench_equity, init_cash=init_cash)

    # 跟踪 / 信息比率
    strat_rets = result.equity.pct_change().fillna(0.0)
    bench_rets = bench_equity.pct_change().fillna(0.0)
    excess = strat_rets - bench_rets
    tracking_error = float(excess.std(ddof=0) * np.sqrt(252.0))
    info_ratio = (
        float(excess.mean() / excess.std(ddof=0) * np.sqrt(252.0))
        if excess.std(ddof=0) > 0
        else float("nan")
    )
    excess_total = float(result.equity.iloc[-1] / init_cash - bench_equity.iloc[-1] / init_cash)

    # —— 输出指标 ——
    print("=" * 60)
    print("[REAL BACKTEST] cn_etf_dca_basic | 2020-01-01 ~ 2024-12-31")
    print("=" * 60)
    for k, v in strat_m.items():
        print(f"  strat.{k:<18}: {v}")
    print()
    for k, v in bench_m.items():
        if k == "drawdown_series":
            continue
        print(f"  bench.{k:<18}: {v}")
    print()
    print(f"  excess_total_return : {excess_total:.4f}")
    print(f"  information_ratio   : {info_ratio:.4f}")
    print(f"  tracking_error      : {tracking_error:.4f}")

    # 分年度收益
    strat_yearly = _yearly_returns(result.equity, init_cash=init_cash)
    bench_yearly = _yearly_returns(bench_equity, init_cash=init_cash)
    print("\n  分年度收益（strat | bench | diff）:")
    for y in sorted(strat_yearly):
        s = strat_yearly[y]
        b = bench_yearly.get(y, float("nan"))
        print(f"    {y}: {s:>+8.2%} | {b:>+8.2%} | {s - b:>+8.2%}")

    # —— 绘图 1：equity curve ——
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(result.equity.index, result.equity.values, label="DCA basic", linewidth=1.5)
    ax.plot(bench_equity.index, bench_equity.values, label=f"BH {benchmark_sym}",
            linewidth=1.0, alpha=0.85)
    ax.axhline(init_cash, color="gray", linestyle=":", linewidth=0.8, alpha=0.6)
    ax.set_title("cn_etf_dca_basic vs 510300 BH (init=100k, 2020-01-01 ~ 2024-12-31)")
    ax.set_ylabel("Equity (RMB)")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(ARTIFACTS / "equity_curve.png", dpi=120)
    plt.close(fig)

    # —— 绘图 2：drawdown ——
    strat_dd = result.equity / result.equity.cummax() - 1.0
    bench_dd = bench_m["drawdown_series"]
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.fill_between(strat_dd.index, strat_dd.values, 0, alpha=0.4, label="DCA basic")
    ax.plot(bench_dd.index, bench_dd.values, label=f"BH {benchmark_sym}",
            linewidth=1.0, color="firebrick", alpha=0.8)
    ax.set_title("Drawdown: cn_etf_dca_basic vs 510300 BH")
    ax.set_ylabel("Drawdown")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(ARTIFACTS / "drawdown.png", dpi=120)
    plt.close(fig)

    # —— 绘图 3：cash_vs_risk ——
    cash_share = result.weights["__cash__"].clip(lower=0, upper=1)
    risk_share = (1.0 - cash_share).clip(lower=0, upper=1)
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.fill_between(cash_share.index, 0, cash_share.values,
                    color="#4f8ad6", alpha=0.7, label="Cash (511990)")
    ax.fill_between(cash_share.index, cash_share.values, cash_share.values + risk_share.values,
                    color="#e07b5a", alpha=0.7, label="Risk pool (6 ETFs)")
    ax.set_title("Cash vs Risk allocation over time")
    ax.set_ylabel("Share of NAV")
    ax.set_ylim(0, 1)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="center left")
    fig.tight_layout()
    fig.savefig(ARTIFACTS / "cash_vs_risk.png", dpi=120)
    plt.close(fig)

    # —— 绘图 4（保留旧的）：weights stack ——
    fig, ax = plt.subplots(figsize=(11, 5))
    w = result.weights.copy()
    cols = [c for c in w.columns if c != "__cash__"] + ["__cash__"]
    ax.stackplot(w.index, *[w[c].values for c in cols], labels=cols)
    ax.set_title("Position weights over time")
    ax.set_ylim(0, 1)
    ax.legend(loc="lower left", ncol=4, fontsize=8)
    fig.tight_layout()
    fig.savefig(ARTIFACTS / "weights_stack.png", dpi=120)
    plt.close(fig)

    print(f"\nArtifacts saved to: {ARTIFACTS}")

    return {
        "strat": strat_m,
        "bench": {k: v for k, v in bench_m.items() if k != "drawdown_series"},
        "excess_total_return": excess_total,
        "information_ratio": info_ratio,
        "tracking_error": tracking_error,
        "strat_yearly": strat_yearly,
        "bench_yearly": bench_yearly,
        "final_strat_nav": float(result.equity.iloc[-1]),
        "final_bench_nav": float(bench_equity.iloc[-1]),
    }


# ---------------------------------------------------------------- entry


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--smoke", action="store_true", help="只跑合成数据 smoke test")
    args = p.parse_args()

    if args.smoke:
        run_smoke()
        return 0

    # 默认：先跑 smoke 再跑真实
    run_smoke()
    print()
    run_real()
    return 0


if __name__ == "__main__":
    sys.exit(main())
