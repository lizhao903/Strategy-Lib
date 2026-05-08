# ---
# jupyter:
#   jupytext:
#     formats: py:percent
# ---
# %% [markdown]
# # 因子研究示例：A股 ETF 动量因子
#
# 这个 notebook 展示标准研究流程：拉数据 → 计算因子 → IC 分析 → 分组回测。
# 转 `.ipynb`：`jupytext --to notebook 01_momentum_intro.py`

# %%
import pandas as pd

from strategy_lib import get_loader
from strategy_lib.factors import MomentumReturn, ShortTermReversal
from strategy_lib.analysis import (
    compute_forward_returns, ic_decay, ic_timeseries, rank_ic_timeseries,
    summarize_factor, quantile_cumulative_returns,
    plot_ic_timeseries, plot_ic_decay, plot_quantile_cumret,
)

# %% [markdown]
# ## 1. 加载数据：A股几个主流 ETF

# %%
loader = get_loader("cn_etf")
symbols = ["510300", "510500", "159915", "512100", "512880", "512170", "515030", "159825"]
panel = loader.load_many(symbols, timeframe="1d", since="2020-01-01", max_workers=4)
prices = pd.DataFrame({s: df["close"] for s, df in panel.items()})
prices.tail()

# %% [markdown]
# ## 2. 计算因子（注意已乘上 direction 让「越高越看多」）

# %%
mom = MomentumReturn(lookback=20)
factor_values = mom.compute_panel(panel) * mom.direction
factor_values.tail()

# %% [markdown]
# ## 3. IC 分析

# %%
fwd = compute_forward_returns(prices, periods=(1, 5, 10, 20))[5]
ic = ic_timeseries(factor_values, fwd)
rank_ic = rank_ic_timeseries(factor_values, fwd)
print("IC 均值:", ic.mean(), "ICIR:", ic.mean() / ic.std())
print("Rank IC 均值:", rank_ic.mean())
plot_ic_timeseries(ic, title=f"{mom.full_name} IC (5d fwd)")

# %% [markdown]
# ## 4. IC 衰减

# %%
decay = ic_decay(factor_values, prices, periods=(1, 3, 5, 10, 20, 60))
print(decay)
plot_ic_decay(decay)

# %% [markdown]
# ## 5. 分组累计收益

# %%
cum = quantile_cumulative_returns(factor_values, prices, n_groups=4, holding_period=5)
plot_quantile_cumret(cum)

# %% [markdown]
# ## 6. 综合摘要（5 日前瞻）

# %%
summarize_factor(factor_values, prices, fwd_period=5)

# %% [markdown]
# ## 思考与下一步
#
# - 如果 IC 衰减很快（前 1-3 期 IC 高，之后腰斩），意味着信号短期，提高换手频率
# - 如果 ICIR < 0.5，单因子稳定性不够，考虑组合多个因子
# - 如果 LongShort 净值不显著高于 Q4，说明做空端没贡献，可以只做多端
# - 验证有效后，把组合方案写到 `configs/<your_strategy>.yaml`，用 `slib backtest run` 跑回测
