---
slug: crypto_trend_tilt
status: shelved (risk profile shifter, no alpha) / niche-use
finalized: 2026-05-08
---

# Conclusion — V2-S3 (S12) crypto_trend_tilt

## 一句话结论
**V1 的 S5v2 trend tilt + vol filter 套到 crypto 0 代码改动 + V1 默认参数即跑出 NAV 377k / Sharpe 1.37 / MaxDD -34.6%（V2 系列最佳 MaxDD）—— 但 risk-adjusted Calmar 1.14 输给 V2-S1 等权 1.50 / V2-S2 MA filter 3.30。是 risk profile shifter 而非 alpha generator；niche use only（risk budget 极严的资金）。**

## 关键数据（V1 默认参数, TOP_5）

| | 值 |
|---|---|
| 样本期 | 2021-01-01 ~ 2024-12-31（in-sample, 4y） |
| 样本外 | 待 2025+ 数据验证 |
| NAV (100k 起) | 377,100 (3.77x) |
| CAGR | +39.32% |
| Sharpe | 1.373 |
| Vol ann | **26.8%**（V2 系列最低，与 V1 量级接近） |
| MaxDD | **-34.6%**（V2 系列最低） |
| Calmar | 1.14（**输给 V2-S1 1.50 / V2-S2 3.30 / V2-S4 1.77**） |
| 平均仓位（target weight sum, mean） | 1.1% / median 0% |
| vs BTC BH alpha/yr | +5.70% |
| vs V2-S1 alpha/yr | -79.14% |
| 2022 单年 | -13.4%（vs V2-S1 -71.5%；唯一显著兑现年） |

## 在什么情况下有效，什么情况下失效

✅ **有效（已验证）**：
- 2022 大熊市：vol filter + trend score 让 -13% vs V2-S1 -71%（兑现 58 pp 避险）
- TOP_10 universe：Calmar 1.60 略胜 V2-S1 TOP_10 Calmar 1.44（V2-S3 唯一 risk-adjusted 超越点）
- 风险预算极严的资金（institutional / 大资金）：MaxDD -34.6% + Vol 26.8% 显著低于其它 V2 策略

❌ **失效（已验证）**：
- 牛市 / 复苏期：2021 +190% vs V2-S1 +1031% 错过 5x；2023/2024 也只吃到 V2-S1 的 1/8 涨幅
- TOP_5 / NO_SOL：Calmar 输给 V2-S1 等权（**池小不要用 V2-S3**）
- 想要绝对收益的资金：CAGR +39% 仅略胜 BTC BH，远落后 V2-S2/S4

## 这个策略教会我什么（可迁移的经验）

1. **V1 工具普适性的第四个证据**：trend_tilt 从 A 股 ETF 迁移到 crypto **0 代码改动 + V1 默认参数偶然就是 risk-eff 最优**。这次不需要 sweep 找新参数（与 V2-S2 MA=100 形成对照）。

2. **「V1 调出来的参数」与「跨市场最优」的关系不是 universal**：
   - V2-S2 MA filter：V1 默认 200 在 crypto **错误**（应当用 100）
   - V2-S3 trend tilt：V1 默认 vol_high=0.30 在 crypto **偶然最优**（vol_high sweep 验证）
   - 教训：跨市场不能默认 V1 参数有效，但也不能默认要换；**每个策略都必须 sensitivity sweep**

3. **trend_tilt 在 crypto 不是 alpha 来源（与 V1 在 A 股相同）**：
   - V1 S5v2 在 A 股 11 池 Sharpe 0.28 = S3 持平 → 已知不产生新 alpha
   - V2-S3 在 crypto TOP_5 Sharpe 1.37 < V2-S1 1.41 → 同样不产生新 alpha（Sharpe 持平甚至略输）
   - **跨市场再次印证**：trend_tilt + vol_filter 只能"切换 risk profile"，不能"创造 alpha"
   - vol_haircut=1.0 实验证：关掉 vol filter → CAGR +31 pp / MaxDD +23 pp（risk-eff 几乎不变）

4. **V2-S3 vs V2-S2 的定位差异（重要）**：
   - V2-S2 (MA filter)：离散二元 ON/OFF + 满仓 / 全仓 cash → Sharpe 1.95 / MaxDD -43%
   - V2-S3 (trend tilt)：连续 ramp + vol filter → Sharpe 1.37 / MaxDD -35%
   - **V2-S2 全面胜出**——MA filter 的离散信号 + 满仓 ON 的杠杆优势让 risk-adjusted 远优于连续 ramp + vol target
   - **V2-S3 的存在意义**：仅当资金管理硬性要求 MaxDD ≤ -35% 时（V2-S2 不达标）

5. **crypto 高 vol 让"始终减半仓"恰好是合理 vol target**：
   - 事前预期 vol_high=0.80 应当是 crypto-appropriate；实测 vol_high=0.30（V1 默认，永远触发）才是 risk-eff 最优
   - 原因：vol_high=0.30 在 crypto 上等价于"硬性 50% 仓位上限"，这恰好是高 vol 资产的合理 sizing
   - **A 股调出来的"加速触发"逻辑在 crypto 异化为"vol target"**——同一参数不同语义

## 与 V2 系列的关系矩阵

| 维度 | V2-S1 等权 | V2-S2 MA=100 | V2-S3 trend | V2-S4 momentum |
|---|---|---|---|---|
| 机制 | 满仓等权 | ON/OFF + 等权 | 连续 ramp + vol filter | 满仓 + 信号倾斜 |
| Sharpe | 1.41 | **1.95** | 1.37 | 1.51 |
| Vol ann | 76% | 73% | **27%** | 77% |
| MaxDD | -78.9% | -43.4% | **-34.6%** | -77.1% |
| Calmar | 1.50 | **3.30** | 1.14 | 1.77 |
| 适合 | 暴力裸多 | risk-aware 主策略 | 风险预算严苛资金 | alpha 探索 |
| 推荐池 | TOP_5 | TOP_5 | TOP_10 | TOP_10 |

## 后续动作

- [ ] **不再投入 V2-S3 v2**：trend_tilt + vol_filter 在 crypto 上的 risk-eff 已被 V2-S2 / V2-S4 全面打败；继续优化的边际价值低
- [ ] **V2-S3 niche use 文档**：写一份"什么时候用 V2-S3"指南（资金管理偏好驱动而非 alpha 驱动）
- [ ] **V2 共享工具完善**：CryptoLoader USDT 合成已修；V2-S5 可作为 V2-S3+V2-S2 组合（vol filter overlay on MA filter）
- [ ] **4h 频率重测**（优先 4）：trend_tilt 信号反应可能更快；但参考 V1 经验"信号粒度变化不会创造新 alpha"，预期收益有限

## 相关链接
- Idea：`ideas/S12_crypto_trend_tilt/v1/idea.md`
- Notes：`ideas/S12_crypto_trend_tilt/v1/notes.md`
- 实现：`summaries/S12_crypto_trend_tilt/v1/implementation.md`
- 验证：`summaries/S12_crypto_trend_tilt/v1/validation.md`
- artifacts：`summaries/S12_crypto_trend_tilt/v1/artifacts/`
- V2-S1 对照：`summaries/S9_crypto_basket_equal/v1/conclusion.md`
- V2-S2 对照：`summaries/S11_crypto_btc_ma_filter/v1/conclusion.md`
- V2-S4 对照：`summaries/S10_crypto_momentum_tilt/v1/conclusion.md`
- V1 S5v2 对照：`summaries/S5_cn_etf_trend_tilt/v2/conclusion.md`
