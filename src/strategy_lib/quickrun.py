"""无脑快速验证工具 — 一行 Python / 一行 CLI 跑任意标的池。

使用：
    >>> from strategy_lib import quickrun
    >>> quickrun("BTC/USDT,ETH/USDT,SOL/USDT")  # 自动推断 crypto + USDT cash + BTC benchmark
    >>> quickrun(["510300", "510500", "159915"])  # 自动推断 cn_etf + 511990 cash + 510300 benchmark
    >>> quickrun("AAPL,MSFT,GOOG", strategies=["S3", "S4v2", "S5v2"])

CLI:
    $ slib quickrun --symbols 'BTC/USDT,ETH/USDT,SOL/USDT'
    $ slib quickrun --symbols '510300,510500,159915' --strategies S3,S4v2

输出（自动保存到 results/quickrun_<timestamp>/）:
    - summary.md: 标准报告（绩效表 + 与 BH 对比 + 关键观察）
    - equity_curve.png + drawdown.png
    - results.csv: pivot 矩阵
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Sequence

import pandas as pd

from strategy_lib.backtest.sweep import compute_perf_metrics, sweep
from strategy_lib.strategies.factories import FACTORY_REGISTRY
from strategy_lib.universes import Universe
from strategy_lib.utils.logging import logger
from strategy_lib.utils.paths import RESULTS_DIR

# Market 默认配置：cash_proxy / benchmark / 默认起点 / 年化天数
_MARKET_DEFAULTS = {
    "crypto": {
        "cash": "USDT",
        "benchmark": "BTC/USDT",
        "default_since": "2021-01-01",
        "fees": 0.001,
        "slippage": 0.001,
    },
    "cn_etf": {
        "cash": "511990",
        "benchmark": "510300",
        "default_since": "2020-01-02",
        "fees": 0.00005,
        "slippage": 0.0005,
    },
    "cn_stock": {
        "cash": "511990",
        "benchmark": "510300",
        "default_since": "2020-01-02",
        "fees": 0.00005,
        "slippage": 0.0005,
    },
    "hk_stock": {
        "cash": None,
        "benchmark": None,  # 港股没有标准基准 ETF
        "default_since": "2020-01-02",
        "fees": 0.0001,
        "slippage": 0.001,
    },
    "us_stock": {
        "cash": "BIL",      # 美元短期国债 ETF（cash 替代）
        "benchmark": "SPY",
        "default_since": "2020-01-02",
        "fees": 0.0001,
        "slippage": 0.0005,
    },
}


def infer_market(symbols: Sequence[str]) -> str:
    """从 symbols 自动推断 market id。

    规则：
    - 含 ``/`` 或 ``-`` → crypto（如 BTC/USDT, ETH-USD）
    - 全是 6 位纯数字 → cn_etf 或 cn_stock（默认 cn_etf）
    - 全是 5 位纯数字 → hk_stock（如 00700）
    - 纯字母（≤5 字符）→ us_stock（如 AAPL, SPY）
    - 异质 → 报错
    """
    if not symbols:
        raise ValueError("symbols 不能为空")
    flags = []
    for s in symbols:
        if "/" in s or "-" in s and re.match(r"^[A-Z]+[/\-][A-Z]+$", s):
            flags.append("crypto")
        elif re.match(r"^\d{6}$", s):
            flags.append("cn_etf")  # 优先 cn_etf；用户可显式覆盖为 cn_stock
        elif re.match(r"^\d{5}$", s):
            flags.append("hk_stock")
        elif re.match(r"^[A-Z]{1,5}$", s):
            flags.append("us_stock")
        else:
            flags.append("unknown")
    unique = set(flags) - {"unknown"}
    if len(unique) == 0:
        raise ValueError(f"无法识别 symbols 的 market：{symbols}（建议显式传 market=...）")
    if len(unique) > 1:
        raise ValueError(
            f"symbols 跨多个 market：{flags}（quickrun 不支持混合 market；如需，使用 sweep + 多 universe）"
        )
    return next(iter(unique))


def _parse_symbols(symbols) -> list[str]:
    """接受 list 或 'A,B,C' 字符串。"""
    if isinstance(symbols, str):
        return [s.strip() for s in symbols.split(",") if s.strip()]
    return list(symbols)


def quickrun(
    symbols,
    *,
    strategies: list[str] | None = None,
    market: str | None = None,
    cash_proxy: str | None = None,
    benchmark: str | None = None,
    since: str | None = None,
    until: str = "2024-12-31",
    init_cash: float = 100_000,
    fees: float | None = None,
    slippage: float | None = None,
    save_artifacts: bool = True,
    name: str = "quickrun",
    verbose: bool = True,
) -> pd.DataFrame:
    """无脑跑任意标的池：自动推断 market / cash / benchmark + 标准报告。

    返回长格式 DataFrame（每行一个 strategy×universe），同时打印 pivot 矩阵 + 保存
    artifacts 到 ``results/quickrun_<timestamp>/``（除非 save_artifacts=False）。

    参数大多可省略——只传 ``symbols`` 也能跑。

    Examples
    --------
    >>> quickrun("BTC/USDT,ETH/USDT,SOL/USDT")
    >>> quickrun(["510300", "510500"], strategies=["S3", "S4v2"])
    """
    syms = _parse_symbols(symbols)
    if market is None:
        market = infer_market(syms)
        if verbose:
            logger.info(f"[quickrun] auto-detected market={market!r} from symbols")

    defaults = _MARKET_DEFAULTS.get(market, {})
    if cash_proxy is None:
        cash_proxy = defaults.get("cash")
    if benchmark is None:
        benchmark = defaults.get("benchmark")
    if since is None:
        since = defaults.get("default_since", "2020-01-02")
    if fees is None:
        fees = defaults.get("fees", 0.0001)
    if slippage is None:
        slippage = defaults.get("slippage", 0.0005)

    if strategies is None:
        # 默认只跑 S3 等权 baseline；用户传 ["S3", "S4v2", "S5v2"] 等做对比
        strategies = ["S3"]

    # 校验 strategies
    for s in strategies:
        if s not in FACTORY_REGISTRY:
            raise KeyError(
                f"unknown strategy: {s!r}. 已注册：{sorted(FACTORY_REGISTRY)}"
            )

    if verbose:
        logger.info(
            f"[quickrun] symbols={syms}  market={market}  cash={cash_proxy}  "
            f"benchmark={benchmark}  since={since} until={until}  strategies={strategies}"
        )

    # 构造 universe
    universe = Universe.custom(
        name=name,
        symbols=syms,
        market=market,
        cash_proxy=cash_proxy,
        benchmark=benchmark,
        description=f"quickrun ad-hoc universe: {syms}",
        warmup_days=120,
    )

    # 跑 sweep（也支持单策略）
    factory_dict = {s: FACTORY_REGISTRY[s] for s in strategies}
    df = sweep(
        strategies=factory_dict,
        universes=[universe],
        init_cash=init_cash, fees=fees, slippage=slippage,
        since=since, until=until,
        verbose=verbose,
    )

    # 加 BH 基准（如果有 benchmark）
    if benchmark:
        bh_metrics = _compute_bh_metrics(
            universe, benchmark, since=since, until=until, init_cash=init_cash,
            tdpy=365 if market == "crypto" else 252,
        )
        if bh_metrics is not None:
            bh_row = {"strategy": f"BH {benchmark}", "universe": universe.name,
                      "n_symbols": 1, **bh_metrics}
            df = pd.concat([df, pd.DataFrame([bh_row])], ignore_index=True)

    # 输出 stdout 表
    _print_summary(df, market)

    # 保存 artifacts
    if save_artifacts:
        ts = time.strftime("%Y%m%d_%H%M%S")
        out_dir = RESULTS_DIR / f"quickrun_{ts}"
        out_dir.mkdir(parents=True, exist_ok=True)
        df.to_csv(out_dir / "results.csv", index=False)
        _write_summary_md(df, syms, market, since, until, out_dir / "summary.md",
                          cash_proxy, benchmark)
        if verbose:
            logger.info(f"[quickrun] saved → {out_dir}")

    return df


def _compute_bh_metrics(universe, benchmark_symbol, since, until, init_cash, tdpy):
    """加载 benchmark 标的，计算 buy-and-hold metrics。"""
    try:
        from strategy_lib.data import get_loader
        loader = get_loader(universe.market)
        warmup_since = (
            (pd.Timestamp(since) - pd.Timedelta(days=int(universe.warmup_days * 1.5)))
            .strftime("%Y-%m-%d") if universe.warmup_days else since
        )
        df = loader.load(benchmark_symbol, since=warmup_since, until=until)
        close = df["close"]
        cutoff = pd.Timestamp(since, tz=close.index.tz)
        end = pd.Timestamp(until, tz=close.index.tz)
        close = close[(close.index >= cutoff) & (close.index <= end)]
        if len(close) < 5:
            return None
        nav = close / close.iloc[0] * init_cash
        return compute_perf_metrics(
            nav, init_cash=init_cash, since=since, until=until,
            trading_days_per_year=tdpy,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[quickrun] BH benchmark failed: {e}")
        return None


def _print_summary(df, market):
    """打印关键 metrics。"""
    print("\n" + "=" * 70)
    print(f"Quickrun Results ({market})")
    print("=" * 70)
    cols = ["strategy", "n_symbols", "final_nav_100k", "cagr", "sharpe", "max_dd"]
    cols_avail = [c for c in cols if c in df.columns]
    out = df[cols_avail].copy()
    if "final_nav_100k" in out.columns:
        out["final_nav_100k"] = out["final_nav_100k"].round(0)
    if "cagr" in out.columns:
        out["cagr_pct"] = (out["cagr"] * 100).round(2)
        out = out.drop(columns=["cagr"])
    if "sharpe" in out.columns:
        out["sharpe"] = out["sharpe"].round(3)
    if "max_dd" in out.columns:
        out["max_dd_pct"] = (out["max_dd"] * 100).round(1)
        out = out.drop(columns=["max_dd"])
    print(out.to_string(index=False))
    print("=" * 70)


def _write_summary_md(df, syms, market, since, until, path, cash_proxy, benchmark):
    lines = [
        "# Quickrun Summary",
        "",
        f"- 时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- Symbols: {', '.join(syms)}",
        f"- Market: {market}",
        f"- Cash proxy: {cash_proxy}",
        f"- Benchmark: {benchmark}",
        f"- 窗口: {since} ~ {until}",
        "",
        "## 结果",
        "",
        "| Strategy | NAV (100k) | CAGR | Sharpe | MaxDD |",
        "|---|---:|---:|---:|---:|",
    ]
    for _, row in df.iterrows():
        nav = row.get("final_nav_100k", float("nan"))
        cagr = row.get("cagr", float("nan"))
        sharpe = row.get("sharpe", float("nan"))
        max_dd = row.get("max_dd", float("nan"))
        nav_str = f"{nav/1000:.1f}k" if pd.notna(nav) else "N/A"
        cagr_str = f"{cagr*100:+.2f}%" if pd.notna(cagr) else "N/A"
        sharpe_str = f"{sharpe:.3f}" if pd.notna(sharpe) else "N/A"
        dd_str = f"{max_dd*100:.1f}%" if pd.notna(max_dd) else "N/A"
        lines.append(f"| {row['strategy']} | {nav_str} | {cagr_str} | {sharpe_str} | {dd_str} |")
    if "error" in df.columns and df["error"].notna().any():
        lines.extend(["", "## 错误", ""])
        for _, row in df[df["error"].notna()].iterrows():
            lines.append(f"- {row['strategy']}: {row['error']}")
    path.write_text("\n".join(lines), encoding="utf-8")


__all__ = ["infer_market", "quickrun"]
