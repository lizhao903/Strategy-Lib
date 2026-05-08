---
slug: cn_etf_trend_tilt
status: shelved  # 边际有效但下行保护未兑现；保留代码，参数/触发逻辑需迭代后再上
finalized: 2026-05-08
---

# Conclusion — A股 ETF 等权 + 趋势倾斜 (S5)

## 一句话结论
**边际有效但不及预期：搁置（shelved）**。在 2020-2024 样本期 S5 总收益 +20.26% 优于 S3 (+10.80%) 和 510300 BH (+4.18%)，Sharpe 也更高 (0.28 vs 0.21 vs 0.15)，但**核心命题「下行保护」未兑现**——2022 单年 S5 -21.61% 与 BH -21.68% 几乎完全重合，超额主要来自 2024 单年的板块行情。

## 关键数据（2020-01-02 ~ 2024-12-31）
| | S5 | S3 | 510300 BH | S4 |
|---|---:|---:|---:|---:|
| 总收益 | +20.26% | +10.80% | +4.18% | +16.68% |
| CAGR | +3.92% | +2.16% | +0.86% | +3.27% |
| Sharpe | 0.28 | 0.21 | 0.15 | 0.25 |
| MaxDD | -47.80% | -45.18% | -44.75% | -48.90% |
| 2022 单年 | -21.61% | -23.47% | -21.68% | -25.28% |
| 2024 单年 | +28.09% | +8.82% | +18.39% | +11.61% |
| 全空仓天数占比 | 18.2% | — | — | — |
| 空仓 vs BH 当日下跌相关性 | 0.033 | — | — | — |

## 在什么情况下有效，什么情况下失效（事后修正）
- ✅ **结构性单边趋势**：2024 年的板块大行情，趋势倾斜大幅领先（S5 +28% vs S3 +9%）
- ✅ **avoid 极端下行的拐点已确认**之后：2022 年下半年的部分时段 S5 空仓有效
- ❌ **真正的快速下跌**：A股下跌速度往往超过 MA 切换速度，等趋势翻负时已跌一半（2022 上半年 S5 与 BH 同跌）
- ❌ **震荡市**：2023 跑输 S3 8.7 pct，频繁假突破吃成本
- ❌ **cutoff 调高**：cutoff=0.3/0.5 都显著恶化（CAGR 转负），趋势信号有效区域在「弱趋势仍介入」一端

## 这个策略教会我什么
- **「时序方向」信号在 A股 ETF 上对**真实下跌起点**识别能力较弱**：MA 多头排列 + Donchian 通道这套教科书组合的滞后性，在快速下跌的 A股节奏里效用有限。
- **「全空仓」是合法状态——子类放宽校验比父类预先支持更解耦**：通过覆盖 `_validate_weights` 优雅扩展 S3 钩子契约，没有污染共享父类。
- **vectorbt `targetpercent + cash_sharing` 完全支持权重和 < 1**：缺失的资金会留作 cash group 的现金，无需绕路。这个验证扫除了 S5 路径上最大的工程风险点。
- **事前预期与事后结果的方向性偏差**：原以为 S5 主要靠 2022 熊市避险加分，实际主要靠 2024 单边行情加分——再次说明回测结论很容易被单年事件主导，5 年样本不够。

## 后续动作
- [x] 真实回测出结果，决定 status = **shelved**（边际有效，但下行保护命题未确认；不建议直接投产）
- [ ] 衍生想法：
  - 用更短均线（10/30/60）或加入价格相对 ATR 的快速反转判定，提升下跌识别速度
  - cutoff 之上做线性 ramp（替代当前 0/1 双峰），降低拐点附近的硬切换成本
  - 用 511990 货基占据空仓段（年化 ~2%），把现金时段也变现一点
  - 把 S5 的 cutoff 做成动态（基于宽基趋势的 regime switch）
- [ ] 等 2025 年样本外数据后做 OOS 验证

## 相关链接
- Idea：`ideas/cn_etf_trend_tilt/idea.md`
- Notes（含动量 vs 趋势讨论）：`ideas/cn_etf_trend_tilt/notes.md`
- 实现：`summaries/cn_etf_trend_tilt/implementation.md`
- 验证记录：`summaries/cn_etf_trend_tilt/validation.md`（含 2026-05-08 真实数据回测）
- 验证脚本：`summaries/cn_etf_trend_tilt/validate.py`（`smoke` / `real` / `all` 三种入口）
- Artifacts：`summaries/cn_etf_trend_tilt/artifacts/{equity_curve,drawdown,cash_ratio,regime_overlay}.png`
- 配置：`configs/cn_etf_trend_tilt.yaml`
- 父策略 (S3)：`ideas/cn_etf_equal_rebalance/idea.md`
- 兄弟策略 (S4)：`ideas/cn_etf_momentum_tilt/idea.md`
