---
slug: crypto_momentum_tilt
status: shipped (in-sample) / OOS-pending / outlier-dependent
finalized: 2026-05-08
---

# Conclusion — V2-S4 (S10) crypto_momentum_tilt

## 一句话结论
**V1 的 S4v2 横截面动量倾斜机制 0 代码改动套到 crypto TOP_5 跑出 NAV 3.14M / Sharpe 1.51（vs V2-S1 等权 +18 pp/yr alpha）—— 但 NO_SOL ablation 翻负（-2.19 pp）证明 alpha 高度依赖 SOL 单点 outlier，与 V2-S1 一致。整体 +103 pp/yr alpha 中 ~83% 来自池子 + 等权（V2-S1 已吃下），momentum 信号增量仅 17%。**

## 关键数据

| | 值 |
|---|---|
| 样本期 | 2021-01-01 ~ 2024-12-31（in-sample, 4y） |
| 样本外 | 待 2025+ 数据验证 |
| NAV (100k 起) | 3,138,200 (31.4x) |
| CAGR | +136.55% |
| Sharpe | 1.511 |
| Vol ann | 76.6% |
| MaxDD | -77.1% |
| Calmar | 1.77 |
| vs BTC BH alpha/yr | **+102.93%** |
| vs V2-S1 (等权 baseline) alpha/yr | **+18.08%** |
| 信号信息比率 vs V2-S1 | ~0.18 |
| 2022 单年 | -67.7%（vs V2-S1 -71.5%, BTC -65.3%） |

## 在什么情况下有效，什么情况下失效

✅ **有效（已验证）**：
- crypto 内部存在 100x outlier 标的（2021-2024 的 SOL）→ 等权 + momentum 倾斜共同 capture
- 池容量 ≥ 5（更高分散度让 z-score 信息密度足）—— TOP_10 alpha (+30 pp) > TOP_5 (+18 pp)
- raw 信号 > vol_adj（高 vol 资产恰是 momentum 来源，除以 vol 反而抑制）
- lookback 120 日（季度趋势）；60 / 240 都更弱

❌ **失效（已验证 / 风险大）**：
- **去 outlier 池子**：NO_SOL ablation 显示 momentum alpha 翻负（-2.19 pp）+ Sharpe 低于等权
- **熊市**：2022 -67%，比 V2-S1 / BTC 略好但仍灾难性下跌（不是 timing 策略）
- 系统性崩盘期（LUNA/FTX）：crypto 内部相关性 0.85+，等权 / momentum 都无法分散
- 没有 100x 标的的 OOS 周期：2025+ 哪个标的会 100x 没人知道——这是最大 OOS 风险

## 这个策略教会我什么（可迁移的经验）

1. **V1 工具普适性的第二个证据**（V2-S1 是第一个）：动量倾斜从 A 股 ETF 迁移到 crypto 仅需 1 行边界修复（小 N 池 w_max 自动放宽）。`MomentumTiltV2Strategy` + `Universe` 抽象在跨市场场景设计正确。

2. **「池子 >> 信号 >> 仓位」在 crypto 再次成立**：
   - 总 alpha +103 pp/yr 中 V2-S1（池子+等权）已吃下 +85 pp，**momentum 信号仅占 18%**
   - V1 S8（A 股 overseas_4 等权）→ V2-S1（crypto TOP_5 等权）→ V2-S4（crypto TOP_5 momentum）路径清楚显示：每多一层"复杂度"，边际 alpha 显著递减
   - 投入产出比：写一个 universe 文件 vs 写一个动量倾斜策略 + 4 因子 + sweep 工具——投入差 10x，alpha 差 5x

3. **crypto momentum alpha 是「outlier 依赖」**：
   - NO_SOL ablation 是关键判据。去 SOL 后 momentum 不仅没有 alpha，反而轻微负（高换手成本）
   - 这意味着 crypto momentum 的实质 ≈ 「自动识别并加仓暴涨标的」，而非"动量是普适的横截面规律"
   - **OOS 必须问：下个 4 年周期里有几个 100x 标的？哪几个？**——这是事前不可知的，所以 momentum 在 crypto 不能被独立交易

4. **TOP_10 alpha (+30 pp) > TOP_5 (+18 pp) 的反直觉解读**：
   - 直觉：标的越多越分散，alpha 越弱
   - 实测：标的越多，z-score 横截面分散度越高，momentum 信号能识别的"显著极值"越多
   - 但代价是 vol 上升（TOP_10 vol 93% vs TOP_5 77%）和 Sharpe 下降（1.42 vs 1.51）
   - **更大池不是免费午餐**——alpha 在绝对 NAV 上更高但 risk-eff 下降

5. **跨市场 risk-efficiency 公平比较再次证明 A 股 ETF 依然胜出**：
   - V1 S8（cn_etf_overseas_4 等权）：Sharpe 0.85 / Vol 14% = **6.1 per pp vol**
   - V2-S4（crypto TOP_5 momentum）：Sharpe 1.51 / Vol 77% = **1.97 per pp vol**
   - **V1 S8 risk-efficiency 是 V2-S4 的 3.1 倍**——绝对收益 crypto 高，但单位风险产生 alpha A 股 ETF 完胜
   - 这意味着如果资金量足够大（>1M USD）需要稳健 sharpe，A 股 ETF 仍是更优选项

## 与 V2-S1 / V1 S4v2 的关系矩阵

| 维度 | V1 S4v2（A 股 11 池） | V2-S1（crypto 5 池等权） | V2-S4（crypto 5 池 mom） |
|---|---|---|---|
| 代码 | momentum_tilt_v2 + 11 池 | equal_rebalance + TOP_5 | momentum_tilt_v2 + TOP_5 |
| Sharpe | ~0.43 | 1.41 | **1.51** |
| Vol ann | ~14% | 76% | 77% |
| Sharpe / Vol | **3.0** | 1.85 | 1.97 |
| vs 上层基准 alpha CAGR | +0.5 pp（vs S3 11 池） | +85 pp（vs BTC BH） | +18 pp（vs V2-S1） |
| OOS 风险来源 | A 股池结构性拖累 | SOL outlier | SOL outlier + 高换手 |

## 后续动作

- [ ] **V2-S5（V1 S5v2 trend_tilt 套用 crypto）** — 优先 3，已经在 sweep 中显示 MaxDD -78% → -30% 但 CAGR -67 pct，risk profile 切换值得专门验证
- [ ] **V2-S2（V1 S7v2 BTC MA filter）** — 优先 2，需修 USDT 工程问题（panel 加 const USDT）
- [ ] **4h 频率重测 V2-S4** — sweep 显示 1d 已强，4h 是否更快捕获 momentum 反转值得测
- [ ] **2025+ OOS 测试** — 等数据；重点看 NO_SOL 池上 momentum 是否仍有效
- [ ] **大资金敏感性**：1M / 10M USDT 下成交是否影响 alpha（特别是 SOL 暴涨期）

## 相关链接
- Idea：`ideas/S10_crypto_momentum_tilt/v1/idea.md`
- Notes：`ideas/S10_crypto_momentum_tilt/v1/notes.md`
- 实现：`summaries/S10_crypto_momentum_tilt/v1/implementation.md`
- 验证：`summaries/S10_crypto_momentum_tilt/v1/validation.md`
- 共享基线：`docs/benchmark_suite_v2_crypto.md`
- artifacts：`summaries/S10_crypto_momentum_tilt/v1/artifacts/`
- V2-S1 对照：`summaries/S9_crypto_basket_equal/v1/conclusion.md`
- V1 S4v2 对照：`summaries/S4_cn_etf_momentum_tilt/v2/conclusion.md`
