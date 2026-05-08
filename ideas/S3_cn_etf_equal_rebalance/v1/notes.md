# Notes — cn_etf_equal_rebalance

> 持续追加，不要覆盖。每条笔记带日期。讨论中产生的临时想法、AI 给的建议、读到的新文献都丢这里。

---

## 2026-05-08 初版设计决策

### 为什么选 20 个交易日作为默认 rebalance 周期

候选周期对比（先验估计，待 validation 实证）：

| period | 年化触发次数 | 优点 | 缺点 |
|---|---|---|---|
| 5  日 | ~50 | 抓快速轮动、再平衡溢价大 | 万 5 滑点 + 万 0.5 佣金累计成本高，吃掉大部分溢价 |
| 10 日 | ~25 | 折衷 | 仍偏密；A股 ETF 月内噪声多，容易"卖盈又被打回去" |
| **20 日** | **~12** | **接近月度，A股板块轮动周期匹配；成本可控** | **月内极端走势抓不到** |
| 60 日 | ~4 | 成本极低、长期持有友好 | 偏离目标过久，再平衡溢价稀释 |

**默认值选 20**：理由是 A股板块/风格轮动的实证周期偏月度，且 6 资产组合的偏离速度不会快到需要更短周期。**敏感性扫描 {5, 10, 20, 60} 留给 validation 阶段**。

### 为什么 S3 没有现金 / 不投货币基金

这是一个**有意的设计差异**，用来与 S1/S2 形成对照：

- **S1（DCA basic）**：定期把现金从 511990（货币基金）拨入 6 只风险 ETF → 现金缓冲存在，资金流是单向的（逐步建仓）
- **S2（DCA swing）**：S1 + 偏离阈值再加/减仓 → 现金缓冲存在，资金流双向（部分高抛低吸）
- **S3（本策略）**：T0 一次性满仓，**永远 100% 在风险资产**，再平衡只是"风险资产之间互相调拨" → 无现金缓冲

这样 V1 基准簇可以分离出三个独立变量：
1. **有无现金缓冲**（S1/S2 vs S3）
2. **是否做再平衡**（S1 vs S2/S3）
3. **是否因子倾斜**（S3 vs S4/S5）

如果 S3 也持有现金，那么"权重倾斜带来的 alpha"会和"现金仓位的择时效应"混在一起，无法干净归因。

### target_weights 钩子的设计契机

明确把 `target_weights(date, prices_panel) -> dict[str, float]` 作为可继承钩子，是因为 S4/S5 的核心差异**只在权重产生上**，再平衡的执行逻辑（rebalance_period、drift_threshold、下单时机、shift(1) 防未来函数）应该完全复用。

S4/S5 的 subagent 会读 implementation.md 的 "target_weights 钩子接口" 一节理解契约。**约定：权重和恒为 1、非负、key 必须在 universe 内**。S4/S5 的子类只重写这一个方法即可，不应该改父类的下单逻辑。

### 与 vectorbt 的对接思路

V1 框架的 `BaseStrategy` 是信号驱动（`vbt.Portfolio.from_signals`），权重驱动需要走 `vbt.Portfolio.from_orders`：
- 在每个 rebalance 触发日，根据 `target_weights` 和当前组合净值，算出每个资产的目标持仓股数
- 用 `size=target_shares - current_shares`（差量）传给 from_orders，或者用 `size_type="targetpercent"` + `size=weight` 让 vbt 自己算

实际实现里我倾向于第二种（`size_type="targetpercent"`），更简洁，且天然处理"未触发日权重为 NaN → 不下单"的语义。

**未来函数防护**：rebalance 日 D 的 target_weights 用 D-1 收盘价计算 → 在 D+1 开盘成交（vectorbt 默认下一根 bar 成交即可）。本实现暴露 `target_weights(date, prices_panel)` 时传入的 `prices_panel` 应只含 `date` 之前（含 date）的数据，下单时机由父类统一 shift。

### 阈值再平衡（drift_threshold）作为可选项

虽然默认是纯日历再平衡，但保留 `drift_threshold` 参数：
- 在每个 rebalance 候选日，计算所有资产的 `|w_actual - w_target|`
- 若**任一**资产偏离 > threshold，则触发再平衡；否则跳过
- 用途：在低波动期减少不必要的交易，进一步降低成本

但这不是默认行为——纯日历再平衡的实证结果是 S4/S5 比较的"原点"，加阈值会引入额外参数耦合。

---
