"""Strategy × Universe sweep 工具。

典型用法：
    from strategy_lib.backtest import sweep
    from strategy_lib.strategies.factories import s3_equal_rebalance, s4v2_momentum_tilt
    from strategy_lib.universes import CN_ETF_BASE_6, CN_ETF_EXPANDED_11

    df = sweep(
        strategies={"S3": s3_equal_rebalance, "S4v2": s4v2_momentum_tilt},
        universes=[CN_ETF_BASE_6, CN_ETF_EXPANDED_11],
        since="2020-01-02", until="2024-12-31",
    )
    print(df)  # 长格式：每行 (strategy, universe, 指标...)
    print(df.pivot(index="strategy", columns="universe", values="sharpe"))

输出 DataFrame 列：
    strategy, universe, n_symbols, final_nav_100k, cagr, vol_ann, sharpe,
    max_dd, calmar, yr_2020..yr_2024, error (异常时), n_days
"""

from __future__ import annotations

import time
from typing import Callable

import numpy as np
import pandas as pd

from strategy_lib.universes import Universe
from strategy_lib.utils.logging import logger


# -----------------------------------------------------------------------------
# 单次回测 + 标准化指标
# -----------------------------------------------------------------------------

def _extract_nav_series(portfolio) -> pd.Series:
    """从 vbt Portfolio 取 NAV 时间序列（标量化）。"""
    val = portfolio.value() if callable(getattr(portfolio, "value", None)) else portfolio.value
    if hasattr(val, "to_series"):
        try:
            val = val.to_series()
        except Exception:  # noqa: BLE001
            pass
    if isinstance(val, pd.DataFrame):
        # 多列就取第一列（cash_sharing=True 时通常是单列）
        val = val.iloc[:, 0]
    return pd.Series(
        val.values if hasattr(val, "values") else val,
        index=portfolio.wrapper.index,
    )


def _nav_from_result(result) -> pd.Series:
    """从策略 Result 对象提取 NAV（兼容 vbt Portfolio 与自包含 result.equity）。"""
    if hasattr(result, "equity") and result.equity is not None:
        equity = result.equity
        if isinstance(equity, pd.DataFrame):
            equity = equity.iloc[:, 0]
        return pd.Series(equity.values, index=equity.index)
    if hasattr(result, "portfolio") and result.portfolio is not None:
        return _extract_nav_series(result.portfolio)
    raise AttributeError(f"无法从 {type(result).__name__} 提取 NAV")


def compute_perf_metrics(
    nav: pd.Series,
    *,
    init_cash: float = 100_000,
    since: str | pd.Timestamp | None = None,
    until: str | pd.Timestamp | None = None,
    trading_days_per_year: int = 252,
) -> dict:
    """从 NAV 时间序列算标准绩效指标。

    自动剪到 [since, until] 区间，归一化到起点 = init_cash。
    返回字段：final_nav_100k, cagr, vol_ann, sharpe, max_dd, calmar, yr_YYYY..., n_days.

    ``trading_days_per_year``: 252 适合 A 股 / 美股 / ETF；365 适合 crypto 24/7。
    """
    nav = nav.dropna()
    if len(nav) < 5:
        return {"error": "nav too short"}
    tz = nav.index.tz
    if since is not None:
        nav = nav[nav.index >= pd.Timestamp(since, tz=tz)]
    if until is not None:
        nav = nav[nav.index <= pd.Timestamp(until, tz=tz)]
    if len(nav) < 5:
        return {"error": "nav too short after slice"}

    nav_norm = nav / nav.iloc[0]  # 归一化到起点 = 1
    daily_ret = nav_norm.pct_change().dropna()
    n_days = len(nav_norm)
    n_years = n_days / trading_days_per_year

    final_norm = float(nav_norm.iloc[-1])
    cagr = final_norm ** (1 / n_years) - 1 if n_years > 0 else float("nan")
    vol_ann = (
        float(daily_ret.std() * np.sqrt(trading_days_per_year))
        if len(daily_ret) > 0 else float("nan")
    )
    sharpe = (
        float(daily_ret.mean() / daily_ret.std() * np.sqrt(trading_days_per_year))
        if daily_ret.std() > 0
        else float("nan")
    )
    cummax = nav_norm.cummax()
    max_dd = float((nav_norm / cummax - 1).min())
    calmar = cagr / abs(max_dd) if max_dd < 0 else float("nan")

    out: dict = {
        "n_days": int(n_days),
        "final_nav_100k": float(final_norm * init_cash),
        "cagr": float(cagr),
        "vol_ann": vol_ann,
        "sharpe": sharpe,
        "max_dd": max_dd,
        "calmar": calmar,
    }
    # 年度收益
    yearly = (
        nav_norm.groupby(nav_norm.index.year)
        .apply(lambda s: s.iloc[-1] / s.iloc[0] - 1 if len(s) > 1 else 0)
    )
    for year, ret in yearly.items():
        out[f"yr_{year}"] = float(ret)
    return out


def run_on_universe(
    factory: Callable[[Universe], object],
    universe: Universe,
    *,
    init_cash: float = 100_000,
    fees: float = 0.00005,
    slippage: float = 0.0005,
    since: str = "2020-01-02",
    until: str = "2024-12-31",
    panel: dict | None = None,
    factory_overrides: dict | None = None,
    run_overrides: dict | None = None,
) -> dict:
    """在单个 universe 上跑单个策略 factory。返回标准指标 dict。

    panel 可以预加载传入避免重复 IO；warmup 起点会自动比 since 早 universe.warmup_days。
    """
    factory_overrides = factory_overrides or {}
    run_overrides = run_overrides or {}

    # warmup
    warmup_since = (
        (pd.Timestamp(since) - pd.Timedelta(days=int(universe.warmup_days * 1.5)))
        .strftime("%Y-%m-%d")
        if universe.warmup_days
        else since
    )

    if panel is None:
        panel = universe.load_panel(since=warmup_since, until=until)

    strategy = factory(universe, **factory_overrides)

    # 不同策略的 run() 签名不同；优先传完整三参，失败则降级
    run_kwargs = dict(init_cash=init_cash, fees=fees, slippage=slippage)
    run_kwargs.update(run_overrides)
    try:
        result = strategy.run(panel, **run_kwargs)
    except TypeError:
        # 某些策略（如 DCA swing v1）run() 只接受 panel
        result = strategy.run(panel)

    nav = _nav_from_result(result)
    # 按 universe.market 自动选年化天数：crypto 24/7 用 365，其他用 252
    tdpy = 365 if universe.market == "crypto" else 252
    return compute_perf_metrics(
        nav, init_cash=init_cash, since=since, until=until,
        trading_days_per_year=tdpy,
    )


# -----------------------------------------------------------------------------
# Sweep
# -----------------------------------------------------------------------------

def sweep(
    strategies: dict[str, Callable[[Universe], object]] | list[Callable[[Universe], object]],
    universes: list[Universe],
    *,
    init_cash: float = 100_000,
    fees: float = 0.00005,
    slippage: float = 0.0005,
    since: str = "2020-01-02",
    until: str = "2024-12-31",
    factory_overrides: dict[str, dict] | None = None,
    catch_errors: bool = True,
    verbose: bool = True,
) -> pd.DataFrame:
    """在「策略 × universe」grid 上跑回测。

    Parameters
    ----------
    strategies : dict[name, factory] | list[factory]
        list 形式自动用 factory.__name__ 作为名字
    universes : list[Universe]
    factory_overrides : 按策略名定制参数覆盖（如 {"S4v2": {"alpha": 0.5}}）

    Returns
    -------
    pd.DataFrame
        长格式，每行 (strategy, universe, 各指标)。错误用 ``error`` 列记录、其他列 NaN
    """
    if isinstance(strategies, list):
        strategies = {fn.__name__: fn for fn in strategies}
    factory_overrides = factory_overrides or {}

    # 预加载每个 universe 的 panel（避免 N×M 次重复 IO）
    panels: dict[str, dict] = {}
    for u in universes:
        warmup_since = (
            (pd.Timestamp(since) - pd.Timedelta(days=int(u.warmup_days * 1.5)))
            .strftime("%Y-%m-%d") if u.warmup_days else since
        )
        if verbose:
            logger.info(f"loading panel for {u.name} ({len(u)} symbols, warmup since {warmup_since})")
        panels[u.name] = u.load_panel(since=warmup_since, until=until)

    rows = []
    for sname, factory in strategies.items():
        for u in universes:
            t0 = time.time()
            row: dict = {"strategy": sname, "universe": u.name, "n_symbols": len(u)}
            try:
                metrics = run_on_universe(
                    factory, u,
                    init_cash=init_cash, fees=fees, slippage=slippage,
                    since=since, until=until, panel=panels[u.name],
                    factory_overrides=factory_overrides.get(sname, {}),
                )
                row.update(metrics)
                if verbose:
                    logger.info(
                        f"  {sname} on {u.name}: NAV {metrics.get('final_nav_100k', float('nan'))/1000:.1f}k "
                        f"/ CAGR {metrics.get('cagr', 0)*100:+.2f}% / Sharpe {metrics.get('sharpe', 0):.3f} "
                        f"/ MaxDD {metrics.get('max_dd', 0)*100:.1f}% [{time.time()-t0:.1f}s]"
                    )
            except Exception as e:  # noqa: BLE001
                if catch_errors:
                    row["error"] = f"{type(e).__name__}: {e}"
                    if verbose:
                        logger.warning(f"  {sname} on {u.name} FAILED: {row['error']}")
                else:
                    raise
            rows.append(row)

    return pd.DataFrame(rows)


__all__ = ["compute_perf_metrics", "run_on_universe", "sweep"]
