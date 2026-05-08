---
slug: cn_etf_momentum_tilt
status: shelved
finalized: 2026-05-08
---

# Conclusion — A股 ETF 等权 + 动量倾斜

## 一句话结论
**搁置 v1**。在 V1 共享基线（6 只宽基/行业 ETF、2020-2024、20 日 lookback、α=1.0、月频再平衡）上，横截面动量倾斜相对 S3 等权基线产生 **-2.56% 年化超额、IR=-0.49、t-stat=-1.08**，统计上未达到显著拒绝零假设，但**所有尝试过的 α 与 lookback 组合方向上一致为负**——属于经济意义上的系统性反向，不是噪音。

## 关键数据（α=1.0, lookback=20, rebal=20）

| 指标 | S4 momentum_tilt | S3 equal_rebal | 510300 BH |
|---|---:|---:|---:|
| 样本期 | 2020-01-01 ~ 2024-12-31 | 同上 | 同上 |
| Final NAV | 0.986 | 1.120 | 1.064 |
| 总收益 | -1.42% | +11.96% | +6.39% |
| CAGR | -0.30% | 2.38% | 1.30% |
| 年化波动 | 24.16% | 23.77% | 21.74% |
| Sharpe | 0.108 | 0.217 | 0.168 |
| 最大回撤 | -48.73% | -45.18% | -42.78% |
| Calmar | -0.006 | 0.053 | 0.030 |
| 年化目标周转 | 426.3% | 0% (目标恒为 1/N) | — |
| 与 S3 alpha (年化) | **-2.56%** | — | — |
| 与 S3 IR | **-0.49** | — | — |
| 与 S3 TE | 5.18% | — | — |
| 与 S3 t-stat | -1.08 (n=1209) | — | — |
| 与 BH alpha (年化) | -1.05% | +1.08% | — |
| 平均主动权重 \|Δw\| | 0.092 | 0 | — |

**最优档：α=0.0**（即 S3 等权）。任何非零倾斜都把 Sharpe 从 0.217 压到 ~0.10。

## 在什么情况下有效，什么情况下失效

- ❌ **失效（已观测）**：单边普涨年（2020：S4-S3 = -20.3%）、单边熊市（2022：-3.6%）、风格分化但池内重叠高的年份。
- ✅ **看似有效但不稳健**：2024 一年 +7.7% vs S3，主要靠抓住下半年证券（512880）反弹；这是单一年度单一资产驱动的「样本内胜利」，不能视为可重复的 alpha。
- 三个 lookback (10/20/60) × 五个 α (0/0.5/1/2/5) 全部 vs S3 IR 为负 → 不是参数问题，是**信号本身在这个池子上失效**。

## 这个策略教会我什么（可迁移的经验）

1. **池子分散度比因子参数更重要**。6 只 A股 ETF 的横截面 σ 太小，z-score 的信息密度被相关性吃掉了。下次做 cross-section 动量先看池内 pairwise correlation。
2. **A股 ETF 上短期反转盖过中期动量**。lookback=20 是最差的一档，符合传统经验中 A股一个月内的均值回复倾向。下次试动量先 `skip=21`。
3. **t-stat 不显著但方向稳定也是有用信号**。\|t\|=1.08 < 2 不能拒绝 0，但 8/8 (5α + 3lb) 实验全输等权 → 该结论有 8 次独立的「方向一致」证据，足以判定 v1 配置不可上线。
4. **「目标权重恒定」策略的 turnover 不能用目标权重差衡量**。S3 目标周转=0 但实际有漂移再平衡，下次跨策略 turnover 比较直接读 vbt `pf.trades.records`。
5. **事前指标预期值是有用的**。事前 IR 估计 0.2~0.5，实测 -0.49 → 偏离 ~1σ 以上 → 直接说明「我们对这个市场有错误先验」，比单看绝对收益更易识别问题。

## 后续动作

- [x] S3 真实落地后联合 import + 真实数据 2020-2024 全样本回测
- [x] 与 S3 等权基线、510300 BH 双重对比 + α/lookback 敏感性 + 分年度归因
- [x] 决定：**搁置 v1**，更新 `summaries/README.md` 索引（next）
- [ ] v2 候选改进（按优先级）：
  1. `MomentumReturn(skip=21)` 跳过最近 1 月，避开短期反转
  2. 「动量 × 大盘趋势」二元过滤：只在 510300 在 200 日 MA 之上时倾斜，跌破退化为 S3
  3. 风险调整动量 (`mom / σ`)，降低单一资产驱动的赌赛道
  4. 扩池到 ≥ 12 只 ETF（加更多行业/风格），提升横截面分散度
- [ ] **不再继续** v1 形式的 raw 横截面动量倾斜——已被证伪

## 相关链接
- Idea：`ideas/cn_etf_momentum_tilt/idea.md`
- Notes：`ideas/cn_etf_momentum_tilt/notes.md`
- 实现：`summaries/cn_etf_momentum_tilt/implementation.md`
- 验证记录：`summaries/cn_etf_momentum_tilt/validation.md`（2026-05-08 真实数据回测小节为本结论的依据）
- 配置：`configs/cn_etf_momentum_tilt.yaml`
- 入口脚本：`summaries/cn_etf_momentum_tilt/validate.py`（`smoke` / `real` / `sweep` 三个子命令）
- 关键 artifacts：`summaries/cn_etf_momentum_tilt/artifacts/{equity_curve,drawdown,weight_evolution,tilt_strength}.png`
- 关键 commit：`<待提交>`
