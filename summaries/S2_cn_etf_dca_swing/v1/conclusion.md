---
slug: cn_etf_dca_swing
status: shelved   # 真实数据回测已通，等 S1 出炉后再决定 shipped/rejected
finalized: 2026-05-08 (preliminary)
---

# Conclusion — A股 ETF DCA + 阈值再平衡（做T）

> 状态：smoke + 真实数据回测均已通过。**初步可保留为 V1 baseline**，待 S1 出炉做最终对比。

## 一句话结论
S2 在 2020-2024 跑出 +1.11% 年化 alpha、信息比率 0.11、最大回撤优于 BH 7.6 pct，
**alpha 主要由 2021/2022/2023 三个震荡或熊市贡献，2024 单边反弹年明显跑输 BH 11.7 pct**。
做 T 的「对称性」在 DCA 净流入下被结构性破坏（高抛 11.8× 低吸），这是设计问题不是实现问题。

## 关键数据（2020-01-01 ~ 2024-12-31）

| | S2 | 510300 BH |
|---|---:|---:|
| 样本期 | 1209 个交易日 | 同 |
| 最终净值 (init=100k) | 113,808 | 104,957 |
| 总收益 | +13.87% | +4.18% |
| 年化收益 (CAGR) | +2.75% | +0.86% |
| 年化波动 | 18.10% | 21.80% |
| Sharpe | 0.152 | 0.039 |
| 最大回撤 | -37.10% | -44.75% |
| Calmar | 0.074 | 0.019 |
| 换手率（年化） | 153.9% | 0% |
| Alpha (年化) | +1.11% | — |
| 信息比率 | 0.110 | — |
| 跟踪误差 | 10.09% | — |
| 与 S1 alpha | TBD（S1 未出） | — |

S2 特有：高抛 177 / 低吸 15 / 平均触发偏离 24.78% / cooldown 拦截 24.1%。

## 在什么情况下有效，什么情况下失效

- ✅ **有效**（已被本轮回测确认）：
  - 单边熊（2022）：现金缓冲 30% 直接降低 beta，跑赢 BH +3.66pct
  - 切换震荡（2021）：抱团→均衡切换中，频繁高抛锁定领涨利润，+9.17pct
  - 震荡下行（2023）：低波动 + 现金缓冲，+2.33pct
- ❌ **失效**（已被本轮回测确认）：
  - 单边强反弹（2024）：高抛过早离场 + 6 只权重分散，跑输 BH -11.70pct
  - V 反结尾（2020 Q4）：与 BH 接近，alpha 被换手成本吃掉

## 这个策略教会我什么（可迁移的经验）

1. **DCA + 阈值再平衡在「净流入」资金模式下不对称**。资金净流入会持续推高风险权重，导致触发上沿的频率远高于下沿。如果想做对称的「做T」，要么改成「无净流入 + 等权再平衡」（参见 S3），要么调成「上沿阈值 > 下沿阈值」让低吸更敏感。
2. **现金缓冲（30%）是 alpha 的主要来源，不是高抛节奏**。光看 BH 跑赢的年份分布即可推断：弱市 / 震荡赢，强单边输。这与权益多头基金「Beta 决定一切」一致。
3. **cooldown=5d 在 rel_band=20% 时拦截率约 24%**——这是 V1 默认值的工作区间。如果 cooldown=1d，预期换手会翻倍但 alpha 不一定增加（因为同一波动会被多次切片）。
4. **vbt 的 from_orders 跑通并不等于结果可信**：本仓库已经先用 simulate 算 NAV 再喂 vbt，vbt 主要用来做后续 trade analyzer，而非真值来源。

## 后续动作

- [x] 跑通真实数据回测
- [x] 出 S2 vs 510300 BH 全套指标 + 4 张关键图
- [ ] 等 S1 出炉，做 S1 vs S2 head-to-head 表（同 panel 同窗口）
- [ ] 敏感性扫描：rel_band / cooldown / adjust_ratio
- [ ] 决定最终 status：
  - **shipped**（保留为 V1 baseline）—— 如果 S2 vs S1 alpha > 0 且 Sharpe 不输
  - **shelved** —— 如果 S2 与 S1 接近（差距在噪声范围内）
  - **rejected** —— 如果 S2 跑输 S1（说明 swing 部分纯属增加成本）

## 相关链接
- Idea：`ideas/cn_etf_dca_swing/idea.md`
- Notes：`ideas/cn_etf_dca_swing/notes.md`
- 实现：`summaries/cn_etf_dca_swing/implementation.md`
- 验证记录：`summaries/cn_etf_dca_swing/validation.md`
- 配置：`configs/cn_etf_dca_swing.yaml`
- Artifacts（图 + csv + json）：`summaries/cn_etf_dca_swing/artifacts/`
- 关键 commit：待提交
