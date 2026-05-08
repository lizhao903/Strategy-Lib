---
slug: cn_etf_dca_swing
created: 2026-05-08
updated: 2026-05-08
config_path: configs/cn_etf_dca_swing.yaml
related_idea: ideas/cn_etf_dca_swing/idea.md
---

# Implementation — A股 ETF DCA + 阈值再平衡（做T）

## 整体方案

idea.md 中的「DCA + 阈值触发再平衡」落到代码上是一个**自包含的 weight-based 策略类**：
`src/strategy_lib/strategies/cn_etf_dca_swing.py::DCASwingStrategy`。

不复用 `BaseStrategy`（信号驱动 entries/exits），原因：
- 本策略依赖**多资产权重快照**做触发判定，不是单资产 long-only 信号。
- 月度 DCA 是「**净流入**+等额买入」，不是「entries 切换」。
- 货基 `511990` 同时充当现金等价物 + 实际 ETF（T+0、有真实净值），无法用 vbt 的 `init_cash` 模拟。

实现路径：
1. `DCASwingStrategy.simulate()` — **纯 numpy/pandas 单循环**，逐日：
   - 执行上一日决策的订单（DCA / swing），按 T+1 open + slippage 成交
   - 按 T 日 close 估值并计算每只权重
   - 判定是否需要月度 DCA（看下一个交易日是否月初）
   - 扫描 6 只 ETF 的相对偏离，超阈值且 cooldown 已过则进 pending 队列
2. `DCASwingStrategy.run()` — 包一层，惰性 import vectorbt 构造 `Portfolio.from_orders`（依赖未装时降级，仅返回 simulate 结果）。

## 因子清单

本策略**不依赖**因子层，纯权重规则。

| Factor 类 | 文件 | 参数 | 方向 | 是新增还是复用 |
|---|---|---|---|---|
| —— | —— | —— | —— | 不使用 |

## 新增因子

无。

## 策略配置

- 配置文件：`configs/cn_etf_dca_swing.yaml`
- 类型：自定义 `dca_swing`（**未注册到 registry**，遵守硬约束）
- 加载方式：由 `summaries/cn_etf_dca_swing/validate.py` 直接实例化 `DCASwingStrategy`
- 关键参数：

| 参数 | 默认值 | 说明 |
|---|---|---|
| `risk_target_weight` | 0.70 | 风险池目标合计权重 |
| `monthly_dca_amount` | 5000.0 | 每月 DCA 净流入 RMB |
| `rel_band` | 0.20 | 相对偏离触发阈值 ±20% |
| `adjust_ratio` | 0.50 | 单次拉回到目标的比例 |
| `cooldown_days` | 5 | 同标的触发冷却交易日 |
| `fees` | 0.00005 | 共享基线 |
| `slippage` | 0.0005 | 共享基线 |
| `init_cash` | 100000 | 共享基线 |

## 数据

- 标的池来源：手工列（共享基线 6 只 ETF + 货基）
- 数据范围：2020-01-01 ~ 2024-12-31
- 数据预处理：
  - akshare 前复权（qfq）
  - `dropna(how='any')` 对齐 7 只标的的共有交易日（缺一天就跳一天，避免单边持仓估值漂移）
  - 起始日 T0 把 `init_cash` 全数买入 511990 货基，形成现金缓冲

## 关键设计决策

### 1. 「做T」的实现 = 窄带刷单 + 频率防抖

每日 T 收盘扫描，每只 ETF 按相对偏离判定：
- `w_i / w_target > 1 + rel_band` → 高抛（卖偏离的 50%）
- `w_i / w_target < 1 - rel_band` → 低吸（从货基买偏离的 50%）

同一标的触发后写 `next_allowed_idx[s] = t + 1 + cooldown_days`，5 个交易日内不再触发。

### 2. 防未来函数

- 触发判定：T 日 close 后
- 下单价格：T+1 open × (1 ± slippage)
- 月度 DCA：T 日判定「下一日 index 是月初」，T+1 open 成交

### 3. 货基的处理

`511990` 当作真实 ETF 一起喂 OHLCV，但价格几乎线性：合成数据里我们用 `close = 1 + 0.02/252 × t` 模拟年化 2%。
真实回测时直接用 akshare 的 511990 净值序列。

### 4. 现金不足/持仓不足的处理

`simulate` 在执行 pending 订单时缩单到可用额度，避免负持仓。这意味着极端连续触发时实际下单量小于理论值，会在 diagnostics 里体现为 `swing_*` 计数比预期低。

## 踩过的坑

- 起初想用 `BaseStrategy` + entries/exits 表达，发现部分调仓（不是清仓）信号驱动表达不了 → 改自包含 run。
- 月度 DCA 的「第一个交易日」如果直接用 `index.to_period('M').drop_duplicates()` 会拿到 period 而非具体日期；正确做法是 `groupby(period).min()` 取每月 index 的最小值。
- 佣金和滑点容易重复扣：本实现把 fees 当成「从货基扣两腿手续费」，slippage 直接打在 open price 上；不要在 size 计算里再扣一次。

## 相关 commits

- 实现：待提交（2026-05-08 当日批次）
- 调参：本版固定参数，不调

## 后续 follow-up

- [ ] 装 vectorbt 后跑通 `_run_with_vbt`，对比 simulate vs vbt 的 NAV 差距应 < 0.5%
- [ ] 真实数据下重跑 validation
- [ ] 与 S1 横向对比表（等 S1 实现完成后）
