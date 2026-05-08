"""分位数分组回测：把 symbol 按因子值分组，看各组未来收益的差异。"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _qcut_row(row: pd.Series, n_groups: int) -> pd.Series:
    """对一行（横截面）做分位数分组，返回 0..n_groups-1。NaN 保持。"""
    valid = row.dropna()
    if len(valid) < n_groups:
        return pd.Series(np.nan, index=row.index)
    try:
        labels = pd.qcut(valid, n_groups, labels=False, duplicates="drop")
    except ValueError:
        return pd.Series(np.nan, index=row.index)
    return labels.reindex(row.index)


def quantile_returns(
    factor: pd.DataFrame, fwd_ret: pd.DataFrame, n_groups: int = 5
) -> pd.DataFrame:
    """每期按因子分组，计算各组等权未来收益。返回 DataFrame[time x group]。"""
    factor, fwd_ret = factor.align(fwd_ret, join="inner")
    groups = factor.apply(lambda r: _qcut_row(r, n_groups), axis=1)
    out = pd.DataFrame(index=factor.index, columns=range(n_groups), dtype="float64")
    for g in range(n_groups):
        mask = groups == g
        out[g] = fwd_ret.where(mask).mean(axis=1)
    out.columns = [f"Q{g + 1}" for g in range(n_groups)]
    return out


def quantile_cumulative_returns(
    factor: pd.DataFrame,
    prices: pd.DataFrame,
    n_groups: int = 5,
    holding_period: int = 1,
) -> pd.DataFrame:
    """各分位组的累计净值曲线（等权调仓）。

    holding_period: 多少期重新分组一次（rebalance）。
    """
    factor, prices = factor.align(prices, join="inner")
    daily_ret = prices.pct_change().shift(-1)  # 持有当期、下一期实现收益

    # 周期性重新分组：在 i % holding_period == 0 的行计算分组，向后 ffill
    groups = factor.apply(lambda r: _qcut_row(r, n_groups), axis=1)
    rebalance_mask = pd.Series(
        [i % holding_period == 0 for i in range(len(groups))], index=groups.index
    )
    groups = groups.where(rebalance_mask).ffill()

    out = pd.DataFrame(index=factor.index, columns=range(n_groups), dtype="float64")
    for g in range(n_groups):
        mask = groups == g
        out[g] = daily_ret.where(mask).mean(axis=1)
    out = out.fillna(0)
    out.columns = [f"Q{g + 1}" for g in range(n_groups)]
    out["LongShort"] = out[f"Q{n_groups}"] - out["Q1"]  # 多最高分位、空最低分位
    return (1 + out).cumprod()
