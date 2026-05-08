---
slug: crypto_trend_tilt
title: V2-S3 · Crypto 连续趋势倾斜 + 波动率过滤
market: crypto
status: idea
created: 2026-05-08
updated: 2026-05-08
tags: [crypto, trend, vol-filter, risk-profile, v2-suite]
---

# V2-S3 · Crypto 连续趋势倾斜（dedicated 验证）

## 一句话概括
V1 的 S5v2 连续趋势倾斜 + 波动率过滤套到 crypto—— 把策略 risk profile 从"裸多 -77% MaxDD"切换到"-30% MaxDD + CAGR 损失 ~70 pct"。**不是 alpha 来源，是 risk profile shifter**。

## 为什么单独做 dedicated 验证

V2 sweep（2026-05-08）显示 S5v2 在 crypto 全部跑通，risk profile 变化极大：

| Universe | NAV | CAGR | Sharpe | MaxDD | vs V2-S1 NAV |
|---|---:|---:|---:|---:|---:|
| crypto_btc_eth_2 | 173k | +14.7% | 0.71 | -32% | 0.41x |
| crypto_top_3      | 456k | +46.1% | 1.53 | -34% | 0.24x |
| crypto_top_5      | 377k | +39.3% | 1.37 | -35% | 0.17x |
| crypto_top_5_no_sol | 220k | +21.7% | 0.88 | -37% | 0.19x |
| crypto_top_10     | 481k | +48.1% | **1.58** | **-30%** | 0.21x |

**核心观察**：
- **MaxDD 显著降低**：所有池都从 V2-S1 的 -78~-79% 砍到 -30~-37%（**减半还多**）
- **CAGR 同步打折**：从 V2-S1 +118%（TOP_5）→ +39%（同池），损失 ~80 pct
- **Sharpe 持平或略好**：TOP_10 上 1.58 略高于 V2-S1 1.41，TOP_5 上 1.37 略低
- **TOP_10 是冠军**（与 momentum 一致）：分散度让 vol filter 命中频率更稳定

值得 dedicated 是因为：
- 如果用户偏好 -30% MaxDD（机构 / 大资金），V2-S3 是 V2 系列**唯一**的低回撤策略（V2-S2 MA=100 也低 -43%，但需要事后调参）
- vol filter 在 crypto 上的默认参数（V1 vol_high=0.30）是 A 股 vol 范围设计的，crypto vol 70-90% 永远 > 0.30 → 实际上 vol_haircut=0.5 永远生效。值得测试 crypto 适配的 vol_high

## 核心逻辑（What）

完全复用 `TrendTiltV2Strategy`（V1 已实现），无新代码：

1. **trend score**（每标的）：`MABullishContinuous` 连续 score ∈ [-2, +2]（v1 默认开启）
2. **正分数 ramp**：`raw_i = clip((score - cutoff) / (score_full - cutoff), 0, 1)`
3. **不归一化**：`weight_i = raw_i / N`，sum < 1 自动留现金
4. **vol filter**：当 ≥50% 标的 60日年化 vol > 30% 时，全体权重 × 0.5
5. **再平衡**：每 20 日（与 V1/V2-S1 同口径）

## 假设与依据（Why）

**核心假设**：crypto 高波动 + 长趋势让 trend tilt 在 risk-aware 维度优于 V2-S1，但 in-sample CAGR 损失大；这是 risk profile 切换而非 alpha 增加。

**为什么不期望 alpha**：
- V1 S5v2 在 A 股 11 池 Sharpe 0.28 与 S3 持平 → 已知 trend filter 不产生新 alpha
- crypto 上 trend 也是滞后信号，与 V2-S2 MA filter 同源（trend score 本质是 MA 多头计数 + Donchian 位置）
- 真正的价值在「降仓减 vol」而非「精准 timing」

**为什么 vol_high=0.30 在 crypto 永远触发**：
- crypto 60 日年化 vol 常态 60-90%
- vol_high=0.30 → mean(vol > 0.30) 几乎永远 ≥ 0.5 → vol_haircut=0.5 永远生效
- 这等价于"trend_tilt + 强制 50% 仓位上限"
- 真正应当测试的是 crypto-appropriate vol_high（0.6 / 0.8 / 1.0）

## 标的与周期

- 市场：crypto（CCXT → Binance spot）
- 主测池：CRYPTO_TOP_5（与 V2-S1/S4 一致）+ CRYPTO_TOP_10（sweep 显示冠军）
- 副测：CRYPTO_TOP_5_NO_SOL（ablation）
- cash 代理：USDT（CryptoLoader 合成 const-1）
- 频率：日线（1d）
- 数据范围：2021-01-01 ~ 2024-12-31
- 暖机：120 日（与 V1 trend lookback 对齐）

## 信号定义

- **trend score**：MABullishContinuous（默认）
- **score_full**：1.0（V1 默认）
- **vol filter**：vol_lookback=60, vol_high=0.30（V1 默认；crypto 上永远触发）
- **vol_breadth_threshold**：0.5
- **vol_haircut**：0.5
- **再平衡**：每 20 日

## 涉及因子

- [x] 现有：`MABullishContinuous`（trend score）
- [x] 现有：`AnnualizedVol`（vol filter）
- [x] 现有：`DonchianPosition`（trend score 子组件）
- [ ] 不需新增

## 预期表现（事前估计）

| 指标 | TOP_5 | TOP_10 | 依据 |
|---|---:|---:|---|
| CAGR | +35% ~ +45% | +45% ~ +55% | sweep 已示 +39 / +48 |
| Sharpe | 1.30 ~ 1.45 | 1.50 ~ 1.65 | sweep 已示 1.37 / 1.58 |
| MaxDD | -30% ~ -40% | -25% ~ -35% | sweep 已示 -35% / -30% |
| 平均仓位 | 30-50% | 30-50% | vol filter 永远触发 + ramp 部分仓位 |

## 风险与已知坑

**1. CAGR 损失明显**：相对 V2-S1 损失 ~70 pct CAGR 是显著代价。这意味着如果只看绝对收益，V2-S3 不应作为主策略。

**2. vol_high 参数 mismatch**：V1 默认 0.30 在 crypto 上"过度敏感"（永远触发）。真正的 sensitivity 测试应该是 [0.50, 0.80, 1.00] 看哪个让 risk-eff 最优。

**3. 过早降仓 / 信号迟钝**：与 V2-S2 MA filter 类似，trend score 在快速下跌起点不够灵敏；但 vol filter 恰好补上这一缺陷（vol 上升通常先于价格快速下跌）。

**4. 工程依赖**：需要 USDT 合成（已修，影响所有 V2 策略），需要 vol_filter 在 crypto 数据范围运行（已知数学正确）。

**5. CAGR vs Calmar trade-off**：V2-S3 的真正度量应当是 Calmar 而非 CAGR / Sharpe。Calmar = CAGR / |MaxDD|，体现风险调整后的回报。

## 验证计划

1. **主回测**（CRYPTO_TOP_5 + V1 默认参数）
2. **Universe ablation**（TOP_5 / TOP_10 / NO_SOL）
3. **vol_high sweep** [0.30, 0.50, 0.80, 1.00]（**核心**：找 crypto 真正最优）
4. **vol_haircut ablation** [0.5, 1.0]（关 vs 开 vol filter）
5. **Calmar 对比**（V2-S1 / V2-S2 / V2-S4 vs V2-S3）—— 风险调整收益
6. **平均仓位时序**（看 vol filter 触发频率）
7. **2022 单年表现**（核心：vol_filter 是否兑现避险）

## 与现有策略的关系

- **代码层面**：完全复用 `TrendTiltV2Strategy`（V1 已实现）；CryptoLoader USDT 合成已在 V2-S2 修复
- **概念层面**：V2 系列 risk profile shifter，与 V2-S2 MA filter 互补（V2-S2 是离散二元，V2-S3 是连续 ramp）
- **后续派生**：
  - 如果 vol_high=0.80 显著优于默认：派生 `crypto_trend_tilt_v2` 改默认值
  - 如果 Calmar > V2-S2：作为 V2 ship 候选

## 待启动 checklist

- [x] 验证 TrendTiltV2Strategy 在 crypto 跑通（已通过 sweep）
- [ ] 写 dedicated `validate.py`
- [ ] 跑主 + vol_high sweep + universe ablation
- [ ] 写 implementation/validation/conclusion
- [ ] 在 README 索引追加
