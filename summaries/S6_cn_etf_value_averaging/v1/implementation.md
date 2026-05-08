---
slug: cn_etf_value_averaging
created: 2026-05-08
updated: 2026-05-08
config_path: configs/S6_cn_etf_value_averaging_v1.yaml
related_idea: ideas/S6_cn_etf_value_averaging/v1/idea.md
---

# Implementation — A股 ETF 价值平均法（VA）

## 整体方案

S6 是 V1 共享基线下的「权重驱动」策略，但**锚点不再是资产权重**（S2/S3 系列）也不是**现金流量**（S1），而是**NAV 路径**。

每月第一个交易日 T 收盘评估：

```
target(t) = init_cash × (1 + cagr_target / 12) ** months_elapsed   (复利路径，B 方案)
gap = target(t) - NAV(t)
```

下一个交易日 T+1 开盘：
- `gap > min_action_amount`（NAV 落后）：从货币池抽 `min(gap, max_buy_per_period, cash_value)` → 等额 6 等分买入风险 ETF
- `gap < -min_action_amount`（NAV 超前）：按当下市值比例分摊到 6 只 ETF 卖出 `min(|gap|, max_sell_per_period)`，回流货币池
- `|gap| ≤ min_action_amount` 或货币池为空：跳过（NOOP / SKIP）

机制层关键点：
1. **没有阈值触发的高频动作**：所有动作仅在月度决策日；与 S2 v1 的 ~177 次/5 年 swing 相比量级低 1-2 个数量级
2. **机制层对称**：差>0 买、差<0 卖；不预设方向
3. **货币池触底硬刹车**：`cash_value < min_action_amount` 时 BUY 退化为 NOOP（不杠杆、不外部注资）
4. **单月上限 = 流量阀**：max_buy/sell 各 15k；防止极端市场单次砸光资金池

## 因子清单

本策略不使用任何 `Factor` 类。

| Factor 类 | 文件 | 参数 | 方向 | 是新增还是复用 |
|---|---|---|---|---|
| —— | —— | —— | —— | —— |

VA 的"目标 NAV 路径"不抽出 Factor 类——仅在策略内部计算（私有方法 `_target_value`），不暴露 IC 接口。

## 新增因子（如有）

无。

## 策略实现要点

- 文件：`src/strategy_lib/strategies/cn_etf_value_averaging.py`
- 类：`ValueAveragingStrategy`（不继承 S1/S2/S2v2，独立实现）
- 主真值：纯 python `simulate()` 算 NAV；vectorbt 仅作可选 trade analyzer（不存在时降级 portfolio=None）
- 时序：T 日 close 决策；T+1 open + slippage 成交 → 与 S1/S2 一致防未来函数

```python
# 核心循环简化伪代码
for t in range(n_days):
    if pending_action:
        execute_at_open(pending_action, day=t)  # T+1 成交
    nav[t] = mark_to_market(close[t])
    if next_day_is_month_first:
        target_t = init_cash * (1 + cagr_target/12) ** months_elapsed
        gap = target_t - nav[t]
        if gap > min_action:
            pending_action = ("BUY", min(gap, max_buy_per_period))
        elif gap < -min_action:
            pending_action = ("SELL", min(-gap, max_sell_per_period))
```

## 策略配置

- 配置文件：`configs/S6_cn_etf_value_averaging_v1.yaml`
- 类型：`value_averaging`（本类型不在 `strategies/registry.py` 注册，避免修改硬约束保护文件）
- 关键参数：
  - `target_path_kind: compound` （B 方案；可选 `linear` / `compound_floor`）
  - `cagr_target: 0.08`（默认；4 档敏感性 0.06/0.08/0.10/0.12）
  - `max_buy_per_period: 15000`，`max_sell_per_period: 15000`
  - `min_action_amount: 500`

## 数据

- 标的池：与共享基线一致（511990 货基 + 6 只风险 ETF）
- 数据范围：2020-01-01 ~ 2024-12-31（共 1209 个交易日）
- 数据来源：`data/raw/cn_etf/<sym>_1d.parquet`（cache hit，无网络请求）
- 复权：前复权（akshare qfq）
- 成本：万 0.5 fees + 万 5 slippage（共享基线）

## 踩过的坑

1. **货币池"近耗尽" vs "彻底耗尽"**：
   simulate 中 `cash_exhausted_date` 的判定用 `cash_value < min_action_amount=500` 而不是 `< 0`——
   因为浮点剩余几十块时再继续 NOOP 没意义。文档里"耗尽"指此点，**不是货币池真的为零**。

2. **目标路径月份对齐**：
   `months_elapsed` 用 `pandas.Period.n` 差值算，而不是按交易日数 / 21。这样在交易日数偏离 21 的月份（节假日多 / 春节）路径仍然平滑。

3. **vbt `from_orders` 的 `amount` 字段**：
   订单日志里增加了 `amount`（人民币金额）字段；`turnover_annual` 计算优先用它，避免 `size × price` 在不同 ETF 上的浮点累计误差。

4. **NAV 重算时初始日 `t=0` 必须先初始化货基持仓**：
   `init_buy` 把 init_cash 全部投入 511990，作为起始 NAV。第一个月底如果 target>init_cash 才会触发 BUY；如果第一个月就触发 BUY，要确保此前 t=0 的 holdings_hist 已被记录否则 NAV 重算对不上。

5. **决策日是 T，成交是 T+1**：
   month_first_set 判定用 `index[t+1] in month_firsts`（T 是月底/月中、T+1 是月初）。这种实现保证不偷看下个月数据。

## 决策记录

- 选 B（复利）而非 A（线性）/ C（有底线）：
  - A 在终值上同样能配出敏感性，但与"目标 CAGR"语义脱钩（线性增长 50% 等价 CAGR 8.4% 但只在 5 年端点），不直观
  - C 在 5 年回测里基本退化为 DCA 变体（NAV 长期 < init_cash + 复利→ max() 钳制 → 几乎全是买）；不能测对称性

- 4 档 cagr_target = [6%, 8%, 10%, 12%]：
  - 6% 是温和（接近本期 BH+5pct）
  - 8% 是默认（正好高于 BH 长期期望）
  - 10%/12% 是激进档（用于看货币池什么时候耗尽）

- 单月上限 15k 不调：
  - 原始假设：100k init_cash × 15k/月 = 6.7 月可耗尽（极端跌市）
  - 实测：8% 档 2022-01-04 耗尽（约 24 个月），印证上限是合理保守值

- 不引入 cash_min_reserve：
  - 让货币池能耗尽是核心实验意图——观察 VA 的极限行为

## 相关 commits

- 实现：`<待提交>`
- 调参：—— 本版无调参
