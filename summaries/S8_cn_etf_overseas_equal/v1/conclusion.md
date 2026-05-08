---
slug: cn_etf_overseas_equal
status: validating
finalized: 2026-05-08
---

# Conclusion — S8 v1 (overseas_equal)

## 一句话结论
S3 等权机制 + 4 只 CN-listed 海外/黄金 ETF（**完全无 A 股**）在 2020-2024 in-sample 跑出 **NAV 171.3k / CAGR +11.87% / Sharpe 0.851 / MaxDD -20.9%**——是 V1 全套（含所有 v2、所有 universe sweep）的**全维度第一**。但**窗口偶然性是最大未知**，OOS 验证必须先做才能 ship。

## 关键数据
| | 值 |
|---|---|
| 样本期 | 2020-01-02 ~ 2024-12-31 (in-sample) |
| 样本外 | (待 2025+ 数据) |
| NAV | 171,303 |
| CAGR | +11.87% |
| Sharpe | 0.851 |
| MaxDD | -20.9% |
| Calmar | 0.57 |
| vs BH 510300 alpha/yr | +11.01% |
| vs S3 expanded_11 alpha/yr | +5.51% |
| vs S4v2 (前 V1 best) alpha/yr | +6.12% |

## 在什么情况下有效，什么情况下失效

✅ **有效（已验证）**：
- 任何 5y in-sample 期 A 股相对海外+黄金 underperform 的环境
- 多元跨资产类别下的等权 risk parity 思路（与 Mebane Faber GTAA 同根源）
- 4 池标的相关性低（A股海外平时 corr ~0.3-0.5）让组合波动天然下降

❌ **可能失效（未验证、需 OOS）**：
- A 股牛市 + 美股熊市的反向情景（如 2014-15 / 2008-09 / 2017）
- QDII 额度断供导致跟踪误差爆发（513100/513500 历史多次溢价 5-10%）
- 美元周期反转（2014-15 强美元期金价跌 30%）
- 单一 ETF 的 idiosyncratic 风险（如 518880 黄金 ETF 重大 redemption）

## 这个策略教会我什么（可迁移的经验）

1. **池子选择是 alpha 的最大来源**：在 V1 全套验证「池子 >> 信号 >> 仓位」之后，本策略再次量化证实——同一个 S3 等权机制，换池子 Sharpe 从 0.217 跳到 0.851（4 倍）。**下次设计任何策略前，先用 `sweep()` 工具跑一下 universe 比较，避免在错误的池子上做大量参数调优**。

2. **expanded_11 的「6+5」组合是一种妥协**：当时设计 expanded_11 是「base_6 加 5 跨资产」的并集，看起来更全面。实际 sweep 显示 6 只 A 股是结构性拖累，5 跨资产单独跑反而更优。**「上策略」要敢于做减法，不一定 superset 就更好**。

3. **「最简方案」常常是真 winner**：S8 = 等权 + 月度再平衡 + 4 个标的，没有任何因子、timing、sizing。这种最简配置碾压所有"复杂版本"。**奥卡姆剃刀在策略研究里同样适用**。

4. **样本外验证比样本内胜出更重要**：S8 in-sample 的"全维度第一"如果 2025+ 失效，所有数字立刻贬值。**Ship 决策必须等 OOS 数据**。

## 后续动作

- [ ] **优先 1**：写专门的 `validate.py` 输出 dedicated 分年度 / vs BH 详细 / 滚动窗口
- [ ] **优先 2**：单标的留一 ablation（去掉 159920 / 513100 / 513500 / 518880 中的 1 个，看哪个贡献最大）
- [ ] **优先 3**：v2 候选 5 池版（+ 511260 十年国债 ETF）—— 看能否在保持 alpha 的同时 buffer 全大类下跌
- [ ] **优先 4**：与 S5v2 + overseas_4 (Sharpe 0.717 / MaxDD -8.5%) 做 risk profile 对比，确定是否 ship 两个
- [ ] **优先 5（最重要但等数据）**：OOS 测试（2025+ 可得后）

## 相关链接
- Idea：`ideas/S8_cn_etf_overseas_equal/v1/idea.md`
- 实现说明：`summaries/S8_cn_etf_overseas_equal/v1/implementation.md`
- 验证记录：`summaries/S8_cn_etf_overseas_equal/v1/validation.md`
- 配置：`configs/S8_cn_etf_overseas_equal_v1.yaml`
- 数据来源：`results/universe_sweep_demo_<timestamp>.csv`（2026-05-08 跑出）
- 工具：`src/strategy_lib/universes.py::CN_ETF_OVERSEAS_4`、`src/strategy_lib/backtest/sweep.py`
- 关联 memory: `project_universe_sweep_finding.md`
