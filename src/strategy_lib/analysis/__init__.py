"""因子分析层：IC、分位数分组、衰减、绘图。"""

from strategy_lib.analysis.ic import (
    compute_forward_returns,
    ic_decay,
    ic_timeseries,
    rank_ic_timeseries,
    summarize_factor,
)
from strategy_lib.analysis.grouping import quantile_cumulative_returns, quantile_returns
from strategy_lib.analysis.plots import (
    plot_ic_decay,
    plot_ic_timeseries,
    plot_quantile_cumret,
)

__all__ = [
    "compute_forward_returns",
    "ic_decay",
    "ic_timeseries",
    "plot_ic_decay",
    "plot_ic_timeseries",
    "plot_quantile_cumret",
    "quantile_cumulative_returns",
    "quantile_returns",
    "rank_ic_timeseries",
    "summarize_factor",
]
