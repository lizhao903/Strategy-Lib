---
slug: cn_etf_momentum_tilt_v2
status: shipped (pool value, not factor value)
finalized: 2026-05-08
parent_version: v1
---

# Conclusion — A股 ETF 等权 + 动量倾斜（v2）

## 一句话结论
**v2 的改进显著有效**（CAGR +5.73pp / Sharpe ×3.7 / MaxDD 减半 vs v1，且首次跑赢 510300 BH +2.6%/yr），**但收益主要来自「扩池 6 → 11」对 S3 baseline 的提升，动量 tilt 信号本身仍未带来 alpha**（v2 vs S3-11 IR=-0.17，α 敏感性中 α=0 仍是最优档）。**Ship v2 配置**，但备注「价值在跨资产分散，而非动量」；status 为 **shipped (pool value, not factor value)**。

## 关键数据（v2 default：11 pool, lookback=120, skip=5, α=1, raw, rebal=20）

| 指标 | v2 (11 pool) | v1 (6 pool) | S3 (11 pool) | S3 (6 pool) | 510300 BH |
|---|---:|---:|---:|---:|---:|
| 样本期 | 2020-01-02 ~ 2024-12-31 | 同 | 同 | 同 | 同 |
| Final NAV | **1.307** | 1.001 | 1.366 | 1.138 | 1.089 |
| 总收益 | +30.69% | +0.11% | +36.60% | +13.82% | +8.85% |
| CAGR | **+5.75%** | +0.02% | +6.73% | +2.74% | +1.79% |
| 年化波动 | 15.17% | 24.18% | 16.06% | 23.78% | 21.74% |
| Sharpe | **0.444** | 0.121 | 0.486 | 0.232 | 0.190 |
| 最大回撤 | **-22.17%** | -47.93% | -23.03% | -44.26% | -41.45% |
| Calmar | 0.259 | 0.001 | 0.292 | 0.062 | 0.043 |
| 年化目标周转 | 168.5% | 426.3% | 0% (恒为 1/N) | 0% | — |
| **vs S3-11 alpha (年化)** | **-1.06%** | (n/a) | — | — | — |
| **vs S3-11 IR** | **-0.17** | (n/a) | — | — | — |
| vs S3-11 t-stat | -0.37 (n=1207) | — | — | — | — |
| vs BH alpha (年化) | **+2.61%** | -1.05% | +4.94% | +0.95% | — |
| 平均主动权重 \|Δw\| | 0.0465 | 0.0916 | 0 | 0 | — |

**最优档：α=0**（v1 现象在 v2 上完整复现）。任何非零倾斜都把 Sharpe 从 0.486 拉低到 0.38~0.46。

## 控制变量 — 扩池贡献 vs 参数贡献

把 v2 总改进 +5.73%/yr (vs v1) 分解：

| 因素 | 贡献 | 占比 |
|---|---:|---:|
| 扩池 6 → 11（lookback/skip 不变） | +4.17%/yr | **~73%** |
| 参数 (lookback 20→120, skip 0→5, shift, 边界) | +1.56%/yr | ~27% |

进一步：**v2 参数在 6 池上 vs S3 在 6 池上 IR = -0.26**（仍负） → 扩池**不是**让动量信号变好，而是让 S3 baseline 本身变好。「真正的 alpha 属于扩池 S3，不属于动量 tilt」。

## 在什么情况下有效，什么情况下失效（v2）

| 年份 | v2 - S3-11 | 备注 |
|---|---:|---|
| 2020 单边大牛市 | **-3.83%** | ❌ 防御资产（黄金/国债）拖累；S3 全押满仓占便宜 |
| 2021 A 股震荡港美强 | +1.09% | ✅ 微胜，跨资产受益 |
| 2022 单边熊市 | **-4.61%** | ❌ 倾斜倒过来加仓正在跌的资产，符合 v1 担忧 |
| 2023 海外科技牛 + A 股震荡跌 | +1.97% | ✅ 微胜（vs v1 +13.19% 大胜，主要靠扩池） |
| 2024 美股延续 + A 股反弹 | +1.52% | ✅ 微胜 |

3/5 年正贡献 vs S3，2/5 年负贡献且幅度大（单边市的痛点没解决）→ 方向不算稳定。

## 这个策略教会我什么（可迁移的经验）

1. **池的设计 > 因子的精细调参**。v1 在 5α × 3lookback × 1 池上探索全负，v2 仅靠换池就把 NAV 从 1.001 推到 1.307。下次做 cross-section 因子，第一件事**先看池内 pairwise correlation**，再调因子。
2. **「先验测过的失败」可能是「池子选错了」而非「因子错了」**。但反过来也成立：v2 把池换好后动量 tilt 仍 IR < 0，才能下定论说**横截面动量在 A 股可投资 ETF 上经济意义不显著**——这个结论现在比 v1 更可靠。
3. **更长 lookback 的边际帮助有限**。v2 lb sweep 中 lb=250 是唯一 IR > 0 的档（+0.077），但 t≈0.17 完全不显著。在 5 年样本上做年度动量本质上只有 ~5 个独立观测，过拟合空间巨大。
4. **vol-adjusted 信号在跨资产场景下「不输」**。raw signal IR=-0.17，vol_adj IR≈0，且 Sharpe/MaxDD 更优。这不是动量 alpha，是 risk parity 雏形。
5. **不修父类、子类只覆盖钩子，并行写两个版本（v1, v2）共存** 在多迭代研究中比 monkey-patch v1 更安全：同一份父类同一段数据，三个不同子策略一起跑，apples-to-apples 对比无懈可击。
6. **「事前估计 → 事后差距」依然是最有用的诊断工具**。事前估 IR ∈ [0.2, 0.5]，v1 实测 -0.49（差 1σ+），v2 实测 -0.17（差 0.5σ）→ 与事前一致地朝错误方向偏离 → 强烈说明「我们对市场动量的先验仍然过于乐观」。

## 后续动作

- [x] v1 的 4 个候选改进按优先级实施（扩池 / 长 lookback+skip / shift(1) / vol-adjust）
- [x] 真实数据 2020-2024 全样本回测 + α/lookback/signal 三轴敏感性 + pool ablation
- [x] **决定**：ship v2（备注 pool value）；回写 `summaries/S4_cn_etf_momentum_tilt/README.md`（next）
- [ ] **v3 候选（按优先级）**：
  1. **直接 ship「11 池 + S3 等权」**：α=0 始终最优，省掉倾斜层；与 S3 v2 合并讨论
  2. **大盘趋势二元过滤**：510300 在 200MA 之上时启用动量倾斜，跌破退化等权（v1 conclusion 已提）
  3. **vol_adj × lookback=250** 单独跑（已在 sweep 中观察到，但未做 ablation）
- [ ] 不再继续：v1/v2 形式的 raw 横截面动量倾斜（α=0 一致最优 → **已被两次证伪**）

## 相关链接
- Idea：`ideas/S4_cn_etf_momentum_tilt/v2/idea.md`
- Notes：`ideas/S4_cn_etf_momentum_tilt/v2/notes.md`
- 实现：`summaries/S4_cn_etf_momentum_tilt/v2/implementation.md`
- 验证记录：`summaries/S4_cn_etf_momentum_tilt/v2/validation.md`（2026-05-08 真实数据回测小节为本结论的依据）
- 配置：`configs/S4_cn_etf_momentum_tilt_v2.yaml`
- 入口脚本：`summaries/S4_cn_etf_momentum_tilt/v2/validate.py`（`smoke` / `real` / `sweep`）
- 关键 artifacts：`summaries/S4_cn_etf_momentum_tilt/v2/artifacts/{equity_curve,drawdown,weight_evolution,tilt_strength,pool_ablation}.png`
- v1 对照：`summaries/S4_cn_etf_momentum_tilt/v1/conclusion.md`（shelved）
- 关键 commit：`<待提交>`
