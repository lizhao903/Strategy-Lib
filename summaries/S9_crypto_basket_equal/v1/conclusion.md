---
slug: crypto_basket_equal
status: shipped (in-sample) / OOS-pending
finalized: 2026-05-08
---

# Conclusion — V2-S1 (S9) crypto_basket_equal

## 一句话结论
**V1 的 S3 等权机制在 crypto 上 0 代码改动直接跑出 Sharpe 1.41 / CAGR +118%（vs BTC BH +84.84%/yr alpha）**——同一个机制跨市场普适。**NO_SOL ablation（2026-05-08 第二轮）修正**：去 SOL 后仍 CAGR +83.46% / Sharpe 1.195 / vs BTC BH +49.84%/yr，证明 alpha 不完全依赖 SOL（SOL 贡献 ~41% alpha，剩余 59% 来自等权再平衡机制本身）。但 OOS 风险仍极高（4 年样本 + crypto 极端 outlier 频繁）。

## 关键数据
| | 值 |
|---|---|
| 样本期 | 2021-01-01 ~ 2024-12-31 (in-sample, 4y) |
| 样本外 | 待 2025+ 数据验证 |
| NAV (100k 起) | 2,282,604 (22.8x) |
| CAGR | +118.46% |
| Sharpe | 1.410 |
| Sortino | (未单算，估 ~1.6-1.8) |
| MaxDD | -78.9% |
| Calmar | 1.50 |
| vs BTC/USDT BH alpha/yr | **+84.84%** |
| vs ETH/USDT BH alpha/yr | +72.22% |
| 2022 单年 | -71.49% |
| 信息比率 vs BTC BH | ~0.96 |

## 在什么情况下有效，什么情况下失效

✅ **有效（已验证）**：
- crypto 长周期上行（每个 5y 窗口期内有 1+ 个标的 100x，等权再平衡能反复"卖盈"）
- 池中含极速崛起的 alt（2021 SOL 是关键）
- 5 标的等权（TOP_5），不要再加更多 alt（边际递减）

❌ **失效（已验证 / 风险大）**：
- 系统性崩盘期：2022 LUNA/FTX 让 5 池等权 -71%，**没有任何 diversification 价值**（crypto 内部高度同向）
- 没有 100x 标的的池子（btc_eth_2 仅 +43% CAGR，与 BTC BH 接近）
- 2025+ OOS：SOL 已 100x 后再 100x 概率低，BTC 在 95k 附近回归压力大
- 任何持仓限制 / 大资金（>1M USDT）—— 2021 SOL 暴涨期流动性可能不够支持等权大额买卖

## 这个策略教会我什么（可迁移的经验）

1. **V1 工具的普适性是真的**：`Universe + EqualRebalanceStrategy` 0 代码改动从 A 股迁移到 crypto，跑出有效结果。这证明 V1 后期的「池子选择」抽象是正确的设计。

2. **Per-vol-unit alpha 才是公平比较**：
   - V1 S8: Sharpe 0.85 / Vol 14% = **6.1 per pp vol**
   - V2-S1: Sharpe 1.41 / Vol 76% = **1.85 per pp vol**
   - 看似 V2-S1 Sharpe 高 66%，但单位波动产生的 alpha 远低于 V1 S8
   - **下次跨市场对比策略，先除以 vol 看 risk-efficiency**

3. **等权多元化在 crypto 系统性崩盘下完全失效**：2022 LUNA/FTX 期间 5 池齐跌 -71%，比单 BTC -65% 更深。crypto 内部相关性 0.85+ 让"等权 = 多元化"是错觉。**真正的 diversification 需要跨市场（crypto + 股 + 债），不是 crypto 内部分散**。

4. **池中含一个 100x 标的就足够撬动整体**：去 SOL 后 V2-S1 等于 BTC BH。这意味着 crypto 等权策略本质是「投个 100x 标的，靠等权再平衡及时获利离场」的赌博。下个周期（2025+）哪个标的会 100x 没人知道——这是 V2-S1 最大 OOS 风险。

5. **跨市场命题验证应当先做最简对照**：本验证用 V1 完全相同的 S3 等权机制 + 完全相同的 rebalance_period=20 + 完全相同的工具链。跨市场普适性的证据是「机制不变下数据本身的差异」，不是"我们调整了 N 个参数让它在 crypto 工作"。

## 后续动作

**修订（2026-05-08 sweep 之后）**：

- [x] ~~SOL ablation~~ → 已做（NO_SOL 仍 CAGR +83.46%，alpha 仅部分依赖 SOL）
- [ ] **优先 1（修订 后）**：V2-S4 crypto_momentum_tilt dedicated 验证 —— sweep 显示它在 top_5/10 是冠军（Sharpe 1.51/1.42, NAV 3.1M/3.8M），与 V1 完全相反，需要专门写 idea/impl/validation/conclusion
- [ ] **优先 2**：修 S7v2 USDT 工程问题（panel 加 const USDT），跑 V2-S2 BTC MA filter
- [ ] **优先 3**：V2-S3 trend_tilt dedicated（sweep 显示 MaxDD 从 -78% 砍到 -30%，但 CAGR 损失 67 pct，risk profile 切换）
- [ ] **优先 4**：4h 频率重测 —— crypto 24/7 + 高波动可能让 4h 比 1d 更适合
- [ ] **优先 5（等数据）**：2025+ OOS 测试

## 相关链接
- Idea：`ideas/S9_crypto_basket_equal/v1/idea.md`
- Notes：`ideas/S9_crypto_basket_equal/v1/notes.md`
- 实现：`summaries/S9_crypto_basket_equal/v1/implementation.md`
- 验证：`summaries/S9_crypto_basket_equal/v1/validation.md`
- 共享基线：`docs/benchmark_suite_v2_crypto.md`
- 数据来源：`data/raw/crypto/{BTC,ETH,SOL,BNB,XRP}_USDT_1d.parquet`
- artifacts: `summaries/S9_crypto_basket_equal/v1/artifacts/`
- V1 对照：`summaries/S8_cn_etf_overseas_equal/v1/`
