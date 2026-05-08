---
slug: crypto_btc_ma_filter
status: shipped (in-sample, MA=100 推荐) / OOS-pending
finalized: 2026-05-08
---

# Conclusion — V2-S2 (S11) crypto_btc_ma_filter

## 一句话结论
**V1 的 BTC MA filter 二元 ON/OFF 套到 crypto，用 ma_length=100（V1 默认 200 在 crypto 错误）跑出 NAV 3.51M / Sharpe 1.951——是 V2 系列迄今 risk-eff 最高（高于 V2-S4 1.51 / V2-S1 1.41），同时 2022 单年完美 0% 避险（vs V2-S1 -71%）+ MaxDD 砍半（-79% → -43%）。最大教训是 V1 默认参数不能盲套到 crypto——MA 长度必须重新探索。**

## 关键数据（推荐配置 MA=100）

| | 值 |
|---|---|
| 样本期 | 2021-01-01 ~ 2024-12-31（in-sample, 4y） |
| 样本外 | 待 2025+ 数据验证 |
| NAV (100k 起) | 3,511,700 (35.1x) |
| CAGR | +143.28% |
| Sharpe | **1.951**（V2 系列最高） |
| Vol ann | ~73% |
| MaxDD | **-43.4%**（V2 系列最佳，几乎砍半） |
| Calmar | 3.30 |
| vs BTC BH alpha/yr | **+109.66%** |
| vs V2-S1 alpha/yr | +24.82% |
| 2022 单年 | **0.0%** （perfect timing） |
| ON / OFF | 53% / 47% |
| n_switches (4y) | 53 次（约月度切换） |

## 在什么情况下有效，什么情况下失效

✅ **有效（已验证）**：
- crypto 长牛长熊明确：2021 牛 / 2022 熊 / 2023+ 复苏让 MA 信号能精准识别
- ma_length=100 是 sweet spot（50 太短噪声多，200 太长滞后）
- equal weight risky pool（ON 期持 5 池等权显著优于仅持 BTC）
- TOP_5 risky 优于 TOP_10（小币在 ON 期贡献波动 > 收益）
- lag_days=1（V1 已知最佳；> 1 引入额外滞后损害收益）

❌ **失效 / 风险**：
- **MA=200（V1 默认）灾难**：CAGR 仅 +44%，Sharpe 1.02，错过 2021 牛市顶部
- **ma_length 过拟合风险**：4 年仅 1 个完整周期，100 是事后最优；OOS 周期不同长度可能改变结论
- **2022 全年 OFF 是巧合还是规律**：BTC 全年破 200MA 是事实，但下个熊市未必如此清晰
- **frequent switching cost**：53 次 4 年 = 月均 ~1 次，每次往返成本 20bp×2 = 40bp，4y 累计 ~21% 直接成本（已纳入 NAV，但仍是风险）

## 这个策略教会我什么（可迁移的经验）

1. **V1 工具普适性的第三个证据**：MA filter 从 A 股 ETF 迁移到 crypto 仅需 1 个数据层修复（USDT 合成）。V2-S1 / V2-S4 / V2-S2 三个策略加起来仅修了 2 行核心代码（mom_tilt 边界 + crypto USDT），策略层 0 改动。

2. **「机制不变 + 参数重调」是跨市场迁移的真正工作**：
   - V2-S1（等权）：参数 0 调整即直接 ship
   - V2-S4（momentum）：参数 0 调整（lookback=120 在 crypto 仍最佳，恰好）
   - V2-S2（MA filter）：**参数从 200 → 100 决定了策略从"差"变"V2 最佳"**
   - 教训：跨市场不能默认 V1 参数有效，必须 sensitivity sweep；每个策略 1-3 个核心参数即可
   
3. **timing 类策略在 crypto 比 A 股显著更有效**：
   - V1 S7v2 A 股: 2022 -1.9%，vs S3 等权 alpha +1.54 pp / Sharpe 0.40
   - V2-S2 crypto: 2022 **0.0%**，vs V2-S1 等权 alpha +24.82 pp / Sharpe **1.951**
   - 原因：crypto 牛熊周期更明确（持续 6m+ 单向行情），A 股震荡居多让 MA 信号被频繁假触发
   - **V1 总结「timing 类避险在 A 股需要更快信号」在 crypto 不成立** —— crypto 直接用慢信号 (MA100) 即可

4. **Sharpe 1.951 + MaxDD -43% 的意义**：
   - 这是 V2 系列**首个同时打败 V2-S1 / V2-S4 在 risk-eff（Sharpe）和 risk-aware（MaxDD）两个维度的策略**
   - V2-S1 / V2-S4 都是"暴力裸多"风险敞口；V2-S2 是"周期性暴露"
   - 对资金管理来说 V2-S2 是更可承受的策略（-43% 比 -78% 心理负担差太多）
   - **如果只能 ship 一个 V2 策略，应当是 V2-S2（MA=100），不是 V2-S1**

5. **跨市场 risk-eff 公平比较**：
   - V1 S7v2（A 股 11 池）：Sharpe 0.40 / Vol ~9% = **4.4 per pp vol**
   - V2-S2（crypto MA=100）：Sharpe 1.95 / Vol ~73% = **2.7 per pp vol**
   - V1 S8（A 股 overseas 等权）：Sharpe 0.85 / Vol 14% = **6.1 per pp vol**
   - **A 股 risk-efficient 仍胜出**，但 V2-S2 是 V2 系列最接近 A 股的（相对 V2-S1 1.85 / V2-S4 1.97 提升明显）

## 与 V2 / V1 系列的关系矩阵

| 维度 | V2-S1 等权 | V2-S4 momentum | **V2-S2 MA=100** | V1 S7v2 A 股 |
|---|---|---|---|---|
| 机制 | 满仓等权 | 满仓 + 信号倾斜 | 满仓 / 全仓 cash 二元 | 同 V2-S2 |
| Sharpe | 1.41 | 1.51 | **1.95** | 0.40 |
| MaxDD | -78.9% | -77.1% | **-43.4%** | -17.5% |
| 2022 单年 | -71.5% | -67.7% | **0.0%** | -1.9% |
| 信号 alpha vs 等权 | (基准) | +18 pp | **+25 pp** | +1.5 pp |
| OOS 风险来源 | SOL outlier | SOL outlier | MA 长度过拟合 | 池子小且 A 股弱 |

## 后续动作

- [ ] **V2-S3（V1 S5v2 trend_tilt 套用 crypto）** — 优先 3，sweep 显示也是 risk profile 切换效果，dedicated 验证
- [ ] **重跑 V2 全 sweep**：CryptoLoader USDT 修复后所有 5 个 universe × 4 个策略矩阵应该全部能跑（之前 S7v2 5 项都失败）
- [ ] **派生 V2-S2v2**：把 ma_length 默认改成 100（仅对 crypto），写 `crypto_btc_ma_filter_v2`
- [ ] **ma_length sensitivity 在 OOS（2025+）**：核心问题是 100 是否仍是最优；如果 OOS 上 200 反而胜 → 100 是过拟合
- [ ] **vol_target overlay**：在 ON 期间按 BTC vol 缩放仓位，可能再砍 MaxDD 到 -25-30%
- [ ] **4h 频率重测** — 优先 4，可能让 MA 反应更快进一步降低 MaxDD

## 相关链接
- Idea：`ideas/S11_crypto_btc_ma_filter/v1/idea.md`
- Notes：`ideas/S11_crypto_btc_ma_filter/v1/notes.md`
- 实现：`summaries/S11_crypto_btc_ma_filter/v1/implementation.md`
- 验证：`summaries/S11_crypto_btc_ma_filter/v1/validation.md`
- artifacts：`summaries/S11_crypto_btc_ma_filter/v1/artifacts/`
- V2-S1 对照：`summaries/S9_crypto_basket_equal/v1/conclusion.md`
- V2-S4 对照：`summaries/S10_crypto_momentum_tilt/v1/conclusion.md`
- V1 S7v2 对照：`summaries/S7_cn_etf_market_ma_filter/v2/conclusion.md`
