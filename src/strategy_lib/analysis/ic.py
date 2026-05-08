"""IC / Rank IC / IC 衰减：评估因子对未来收益的预测能力。

约定：
- factor_df / forward_ret_df：宽表，index=time, columns=symbol
- IC 是横截面相关系数（每个时间点跨 symbol 计算一个 IC，时间序列即 IC 序列）
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_forward_returns(
    prices: pd.DataFrame, periods: tuple[int, ...] = (1, 5, 10, 20)
) -> dict[int, pd.DataFrame]:
    """计算未来 N 期收益。prices 为宽表（每列一个 symbol 的收盘价）。"""
    out: dict[int, pd.DataFrame] = {}
    for p in periods:
        out[p] = prices.pct_change(p).shift(-p)
    return out


def ic_timeseries(factor: pd.DataFrame, fwd_ret: pd.DataFrame) -> pd.Series:
    """每期横截面 Pearson IC。要求 ≥3 个有效 symbol。"""
    factor, fwd_ret = factor.align(fwd_ret, join="inner")
    ics: list[float] = []
    idx: list[pd.Timestamp] = []
    for ts in factor.index:
        a = factor.loc[ts]
        b = fwd_ret.loc[ts]
        mask = a.notna() & b.notna()
        if mask.sum() < 3:
            continue
        ic = np.corrcoef(a[mask], b[mask])[0, 1]
        ics.append(ic)
        idx.append(ts)
    return pd.Series(ics, index=pd.DatetimeIndex(idx), name="ic")


def rank_ic_timeseries(factor: pd.DataFrame, fwd_ret: pd.DataFrame) -> pd.Series:
    """Spearman 排序 IC。对极端值更稳健。"""
    factor, fwd_ret = factor.align(fwd_ret, join="inner")
    ics: list[float] = []
    idx: list[pd.Timestamp] = []
    for ts in factor.index:
        a = factor.loc[ts]
        b = fwd_ret.loc[ts]
        mask = a.notna() & b.notna()
        if mask.sum() < 3:
            continue
        ic = a[mask].rank().corr(b[mask].rank())
        ics.append(ic)
        idx.append(ts)
    return pd.Series(ics, index=pd.DatetimeIndex(idx), name="rank_ic")


def ic_decay(
    factor: pd.DataFrame,
    prices: pd.DataFrame,
    periods: tuple[int, ...] = (1, 3, 5, 10, 20, 60),
) -> pd.DataFrame:
    """因子在不同前瞻期的 IC 均值与 ICIR。返回 DataFrame[period x stats]。"""
    fwd = compute_forward_returns(prices, periods)
    rows = []
    for p, ret in fwd.items():
        ic = ic_timeseries(factor, ret)
        rank_ic = rank_ic_timeseries(factor, ret)
        rows.append(
            {
                "period": p,
                "ic_mean": ic.mean(),
                "ic_std": ic.std(),
                "icir": ic.mean() / ic.std() if ic.std() else np.nan,
                "rank_ic_mean": rank_ic.mean(),
                "rank_icir": rank_ic.mean() / rank_ic.std() if rank_ic.std() else np.nan,
                "n": int(len(ic)),
            }
        )
    return pd.DataFrame(rows).set_index("period")


def summarize_factor(
    factor: pd.DataFrame,
    prices: pd.DataFrame,
    fwd_period: int = 5,
) -> dict:
    """单点综合评估：IC 均值、ICIR、Rank IC、t 值。"""
    fwd = prices.pct_change(fwd_period).shift(-fwd_period)
    ic = ic_timeseries(factor, fwd)
    rank_ic = rank_ic_timeseries(factor, fwd)
    n = len(ic)
    return {
        "fwd_period": fwd_period,
        "n_periods": int(n),
        "ic_mean": float(ic.mean()),
        "ic_std": float(ic.std()),
        "icir": float(ic.mean() / ic.std()) if ic.std() else float("nan"),
        "ic_t_stat": float(ic.mean() / ic.std() * np.sqrt(n)) if ic.std() else float("nan"),
        "ic_pos_pct": float((ic > 0).mean()),
        "rank_ic_mean": float(rank_ic.mean()),
        "rank_icir": float(rank_ic.mean() / rank_ic.std()) if rank_ic.std() else float("nan"),
    }
