---
slug: cn_etf_market_ma_filter_v2
status: shipped (vs v1) / shelved (vs S3 11 池)
finalized: 2026-05-08
---

# Conclusion — S7 v2 (lag=1 + 11 池)

## 一句话结论
**v2 在 v1 默认 (lag=2 6池) 上全面胜出**（NAV +10.8k / Sharpe 翻倍 / MaxDD 改善 12.8 pct），**但跑输首次直测的 S3 等权 11 池 baseline**（-2.66%/yr，NAV 差 15.3k）—— **timing 在 11 池上反而损害收益**，最大新发现是 S3 等权 11 池是当前 best ship 候选。

## 关键数据
| | 值 |
|---|---|
| 样本期 | 2020-01-02 ~ 2024-12-31 |
| 样本外 | (待 2025+ 数据) |
| 最终 NAV | 119,010（init 100k） |
| CAGR | +3.70% |
| Sharpe | 0.403 |
| MaxDD | -17.5%（**5 个策略中最佳**） |
| 2022 单年 | +0.01% |
| 2024 单年 | +7.82% |
| 切换次数 | 31（5y） |
| ON 占比 | 36.2% |
| vs BH 510300 | +2.84%/yr |
| vs S3 6 池 | +1.54%/yr |
| **vs S3 11 池** | **-2.66%/yr** |

## 在什么情况下有效，什么情况下失效
- ✅ **有效（vs 6 池版本）**：v2 显著改进 v1 默认。lag=1 + 11 池组合的两项贡献接近相等
- ✅ **有效（避险）**：MaxDD -17.5% 是迄今 7 个策略中最佳，证明 timing + 多元化的协同
- ❌ **失效（vs S3 11 池）**：在已经多元化的 11 池上，timing 多砍 5 pct MaxDD 不抵 5y +15k NAV 损失
- ⚠️ **过拟合警告**：lag=1 是 4 档 sweep 中最佳，可能仅是 5y 窗口特性。OOS 验证迫切

## 这个策略教会我什么（可迁移的经验）

1. **timing 的边际价值与 baseline 风险水平耦合**：6 池 MaxDD -45% 时 timing 砍一半很有价值；11 池 MaxDD -22% 时 timing 再砍一半的代价超过收益。**下次评估 timing 类策略，先看 baseline 风险水平**。

2. **Sensitivity sweep 应当反向使用**：v1 默认 lag=2 是事前直觉（"加层过滤更稳"），sweep 推翻了它（lag=1 反而最好）。**新策略的"默认参数"不应靠直觉，必须 sweep 后再定**。

3. **首次直测 baseline = 真正的发现**：本次 ablation 第一次单独测了"S3 等权 11 池"，结果 NAV 134.3k / Sharpe 0.465 直接打爆所有 7 策略。**做新策略前先把"最简 baseline"当独立策略测一下**——可能根本不需要复杂版本。

## 后续动作
- [ ] **优先**：创建 **S8 = "S3 等权 11 池" 作为独立 ship 候选**（CAGR +6.36% / Sharpe 0.465 是当前最佳）
- [ ] S7 v3：换更快信号（ATR breakout / 价格通道）替代慢 MA，看能否在 11 池上挽回 timing 价值
- [ ] OOS 测试（2025+ 数据）验证 lag=1 + 11 池组合是否稳健
- [ ] S5v2 + S7v2 的 ensemble（sizing + timing 协同）—— 如果 risk profile 互补，可能值得

## 相关链接
- Idea：`ideas/S7_cn_etf_market_ma_filter/v2/idea.md`
- 实现：`summaries/S7_cn_etf_market_ma_filter/v2/implementation.md`
- 验证：`summaries/S7_cn_etf_market_ma_filter/v2/validation.md`
- 配置：`configs/S7_cn_etf_market_ma_filter_v2.yaml`
- v1 上下文：`summaries/S7_cn_etf_market_ma_filter/v1/`
