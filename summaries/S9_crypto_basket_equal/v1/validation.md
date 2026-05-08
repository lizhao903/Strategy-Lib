---
slug: crypto_basket_equal
updated: 2026-05-08
---

# Validation — V2-S1 (S9) crypto_basket_equal

---

## 2026-05-08 真实数据回测（V2 第一个 baseline）

### 配置 & 数据
- 共享基线：`docs/benchmark_suite_v2_crypto.md`
- 数据：CRYPTO_TOP_5（BTC/ETH/SOL/BNB/XRP），2020-09-01 ~ 2024-12-31，1d
- 绩效统计窗口：2021-01-01 ~ 2024-12-31（4 年）
- 配置：100k USDT / fees 10bp / slippage 10bp / rebalance=20 / 年化天数 365
- 工作目录脚本：`summaries/S9_crypto_basket_equal/v1/validate.py`
- 真实数据 summary：`artifacts/real_backtest_summary.json`

### V2-S1 主结果

| 指标 | 值 |
|---|---:|
| 最终 NAV (100k 起) | **2,282,604** (22.8x) |
| CAGR | **+118.46%** |
| 年化波动 | 76.1% |
| Sharpe | **1.410** |
| MaxDD | -78.9% |
| Calmar | 1.50 |

### 与 BH 基准对比

| | NAV | CAGR | Sharpe | MaxDD |
|---|---:|---:|---:|---:|
| **V2-S1** | **2,282.6k** | **+118.46%** | **1.410** | -78.9% |
| BTC/USDT BH | 319.0k | +33.62% | 0.777 | -76.6% |
| ETH/USDT BH | 457.9k | +46.25% | 0.875 | (~) |
| **alpha vs BTC BH** | | **+84.84%/yr** | +0.633 | -2.3 pct |
| **alpha vs ETH BH** | | **+72.22%/yr** | +0.535 | (~) |

V2-S1 在所有维度（除 MaxDD 略深）暴揍单一标的 BH。**信息比率 ≈ 0.96 跨 4 年**（α 84.84% / 跟踪误差估计 ~88%）。

### 分年度收益

| 年份 | V2-S1 | BTC BH | ETH BH | 解读 |
|---|---:|---:|---:|---|
| 2021 | **+1031.22%** | +57.57% | +404.35% | SOL 2021-Q4 100x 暴涨被等权再平衡反复"卖盈"放大 |
| 2022 | **-71.49%** | -65.34% | -68.23% | LUNA/FTX 双崩盘；V2-S1 比单 BTC/ETH 跌得**更深** |
| 2023 | +183.38% | +154.46% | +90.10% | crypto 寒冬触底反弹 |
| 2024 | +132.74% | +111.81% | +41.91% | ETF 通过 + BTC 新高 |

**关键观察**：
- 2021 +1031% 是绝对支配 5y 累计的关键年
- 2022 -71% 比单 BTC -65% 更深，说明等权多元化在系统性崩盘期**没有缓冲作用**——所有 crypto 同向下跌
- 2023+2024 V2-S1 仍然跑赢 BTC BH，说明 alpha 不只是 2021 一年的运气

### Universe ablation: 等权 S3 在 4 个 crypto universe

| Universe | n | NAV | CAGR | Sharpe | MaxDD |
|---|---:|---:|---:|---:|---:|
| crypto_btc_eth_2 | 2 | 424.7k | +43.52% | 0.874 | -76.2% |
| crypto_top_3 | 3 | 1904.2k | +108.79% | 1.343 | -85.2% |
| **crypto_top_5** | 5 | **★2282.6k** | **★+118.46%** | **★1.410** | -78.9% |
| crypto_top_10 | 10 | 2267.8k | +118.11% | 1.351 | -82.0% |

**关键观察**：
1. **加 SOL（top_3 vs btc_eth_2）是 alpha 跳跃的关键**：CAGR +43.5% → +108.8% 一步翻倍
2. **TOP_5 是 sweet spot**：再加 BNB/XRP 让 Sharpe 略升 (1.34 → 1.41)
3. **TOP_10 加 8 个 alt 反而 Sharpe 略降**（-0.06）：DOGE/ADA/AVAX 等中长尾 alt 在 2021-22 大跌时拖累
4. **池子 alpha 单调性 ≈ 成立**：n=2 → n=5 显著上升，n=5 → n=10 边际递减
5. **与 V1 不同**：V1 是「池子越大越好」单调，V2 是「池子大到 5 就饱和」

### V1 S8 vs V2-S1 横向对比（同 S3 等权机制，跨市场）

| | V1 S8 (cn_etf_overseas_4) | V2-S1 (crypto_top_5) | Δ |
|---|---:|---:|---:|
| 市场 | A 股 ETF (CN-listed) | Crypto Spot | |
| 池大小 | 4 | 5 | |
| 资金 | 100k RMB | 100k USDT | |
| 期间 | 2020-2024 (5y) | 2021-2024 (4y) | |
| NAV | 171.3k (1.71x) | 2,282.6k (22.8x) | **+13x** |
| CAGR | +11.87% | +118.46% | +106.6 pct |
| Sharpe | 0.851 | 1.410 | **+0.56** |
| Vol | ~14% | 76.1% | +62.1 pct |
| MaxDD | -20.9% | -78.9% | -58 pct |
| Sharpe / Vol | 6.1 (per pp vol) | 1.85 | -4.2 |

**结论**：
- **同一个 S3 等权机制在 crypto 上 Sharpe +66%、CAGR +10x，但 MaxDD 4x 更深**
- 「等权 + 月度再平衡」命题跨市场有效
- 但 **per-vol-unit 来看 V1 S8 是更好的 risk-adjusted alpha 来源**（6.1 vs 1.85）
- 2 个市场是不同 risk profile：V1 S8 适合追求 Sharpe，V2-S1 适合追求绝对收益（acceping 巨大波动）

### 关键图表
- `artifacts/equity_curve.png` — V2-S1 vs BTC BH vs ETH BH 净值曲线（log scale）
- `artifacts/drawdown.png` — 三者回撤对比（2022 LUNA/FTX 高亮红色）
- `artifacts/weight_evolution.png` — 5 资产权重时序堆积（再平衡日清晰可见）
- `artifacts/yearly_returns.png` — V2-S1 vs BTC BH 分年度条形图

### 解读 & 问题

1. **V2-S1 alpha 本质归因**：
   - 主要由 SOL 在 2021 单年 100x 表现提供
   - 等权 + 月度再平衡 = 在 SOL 暴涨时反复减仓、把利润转移到其他标的
   - 类似 V1 S8 的「等权 + 跨资产」机制，但 crypto 池内 SOL 提供了远超 V1 任何标的的 carry
   - 没有 SOL（btc_eth_2）的版本只有 +43.5% CAGR，与 BTC BH 接近

2. **2022 的失败**：等权多元化在 crypto 系统性崩盘时**完全失效**（5 池 -71% vs BTC -65% 更深）。V1 中 overseas_4 在 2022 也跌但只 -20% 左右；crypto 5 池 -71% 是质的不同。**没有真正的 cross-asset diversification（crypto 内部高度同向）**。

3. **OOS 风险（最大未知）**：
   - SOL 2021 100x 是一次性事件，不会重复
   - 2024-12 的 BTC 在 95k 附近，OOS（2025+）极可能均值回归
   - 4 年样本含一次完整周期但样本太小，事前难判断未来 risk profile

### 与 V1 已知教训的关系

✅ **池子 >> 信号 >> 仓位** 在 crypto 上**部分成立**：
- TOP_5 (5 池) 击败 TOP_3 (3 池) 验证「池子越大越好」
- 但 TOP_10 不再改善，说明 crypto 池有 saturation point
- 没测过的：crypto 上 timing/factor 是否仍然边际价值低？需要后续 V2-S2/S3/S4/S5 验证

❌ **避险靠 sizing 不靠 timing** 在 crypto 上**不成立**：
- V2-S1 等权满仓在 2022 -71%，没任何避险机制
- 这点说明 crypto 上 timing 可能比 A 股更有价值（高 vol + 长趋势）
- 后续 V2-S3 (BTC MA filter) 应当能验证

### 下一步

- [ ] 实现 V2-S2 ~ V2-S5（DCA / MA filter / trend tilt / momentum tilt 在 crypto 上）
- [ ] 考虑 4h 频率 vs 1d 的对比（crypto 24/7 可能 4h 更合适）
- [ ] OOS 测试（2025+）—— 这是最大未知，必须做
- [ ] 缩短样本到 2022-2024（剔除 2021 SOL 暴涨这个 outlier 年）做 robustness 测试
- [ ] 验证「2022 -71% 是否可避免」—— 用 V2-S3 BTC MA filter 看能否在 LUNA 崩盘前离场

---
