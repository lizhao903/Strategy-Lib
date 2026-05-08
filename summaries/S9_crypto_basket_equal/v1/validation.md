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

## 2026-05-08（追加）V2 Crypto Sweep + NO_SOL Ablation

### 配置 & 数据
- 跑法：`python scripts/v2_crypto_sweep.py`
- 4 strategies × 5 universes = 20 次回测（其中 7 个因工程问题 fail）
- 窗口与 V2-S1 主测一致：2021-01-01 ~ 2024-12-31，100k USDT，fees+slip 各 10bp，年化 365
- sweep 工具升级：`compute_perf_metrics(trading_days_per_year=...)`，`run_on_universe` 按 universe.market 自动 252/365 适配
- 新注册 universe：`CRYPTO_TOP_5_NO_SOL = (BTC, ETH, BNB, XRP)`，剔除 SOL 验证 alpha 来源
- 完整 csv: `results/v2_crypto_sweep_<ts>.csv`

### 4 × 5 完整结果

#### Sharpe 矩阵
| | btc_eth_2 | top_3 | **top_5_no_sol** | top_5 | top_10 |
|---|---:|---:|---:|---:|---:|
| S3 equal_rebal | 0.874 | 1.343 | 1.195 | 1.410 | 1.351 |
| S4v2 momentum_tilt | NaN | NaN | 1.172 | **★1.511** | 1.423 |
| S5v2 trend_tilt | 0.710 | 1.533 | 0.879 | 1.373 | **★1.583** |
| S7v2 ma_filter | NaN | NaN | NaN | NaN | NaN |

#### Final NAV (100k USDT)
| | btc_eth_2 | top_3 | **top_5_no_sol** | top_5 | top_10 |
|---|---:|---:|---:|---:|---:|
| S3 equal_rebal | 424.7k | 1904.2k | **1134.8k** | 2282.6k | 2267.8k |
| S4v2 momentum_tilt | NaN | NaN | 1081.5k | **★3138.2k** | **★3798.6k** |
| S5v2 trend_tilt | 173.1k | 456.3k | 219.6k | 377.1k | 481.2k |

#### CAGR (%)
| | btc_eth_2 | top_3 | **top_5_no_sol** | top_5 | top_10 |
|---|---:|---:|---:|---:|---:|
| S3 equal_rebal | +43.52 | +108.79 | +83.46 | +118.46 | +118.11 |
| S4v2 momentum_tilt | NaN | NaN | +81.27 | **★+136.55** | **★+148.11** |
| S5v2 trend_tilt | +14.69 | +46.12 | +21.71 | +39.32 | +48.07 |

#### MaxDD (%)
| | btc_eth_2 | top_3 | **top_5_no_sol** | top_5 | top_10 |
|---|---:|---:|---:|---:|---:|
| S3 equal_rebal | -76.2 | -85.2 | -73.8 | -78.9 | -82.0 |
| S4v2 momentum_tilt | NaN | NaN | -76.4 | -77.1 | -79.4 |
| S5v2 trend_tilt | -32.1 | -34.5 | -36.8 | -34.6 | **★-30.0** |

### 【关键 ablation】SOL 贡献的边际 alpha（TOP_5 vs NO_SOL）

| 策略 | TOP_5 (5 池含 SOL) | NO_SOL (4 池) | Δ CAGR | Δ Sharpe | SOL alpha 占比 |
|---|---|---|---:|---:|---:|
| **S3 equal_rebal** | +118.46% / 1.41 | +83.46% / 1.20 | -35.00 pct | -0.215 | ~41% |
| S4v2 momentum_tilt | +136.55% / 1.51 | +81.27% / 1.17 | -55.27 pct | -0.339 | ~50% |
| S5v2 trend_tilt | +39.32% / 1.37 | +21.71% / 0.88 | -17.61 pct | -0.495 | ~75% |

**核心发现 1（修正 V2-S1 conclusion）**：

V2-S1 conclusion 之前判断"alpha 主要来自 SOL"——**ablation 数据修正这个判断**：
- 没 SOL，S3 等权仍然 CAGR +83.46% / Sharpe 1.195 / NAV 1134.8k
- 这仍然显著跑赢 BTC BH (319k / +33.62%)，**alpha vs BTC BH = +49.84%/yr**（去 SOL 后）
- vs 含 SOL 的 +84.84%/yr，**SOL 贡献 alpha 的 ~41%**，**59% alpha 来自 BNB/ETH/XRP 的等权再平衡机制本身**
- 不再说"SOL 是唯一原因"；正确表述："等权再平衡机制本身贡献了大部分 alpha，SOL 100x 把 alpha 又翻倍"

**核心发现 2（与 V1 命题对照）**：

| V1 命题（A 股 ETF）| 在 crypto 上的验证结果 |
|---|---|
| 「池子 >> 信号 >> 仓位」 | **部分成立**：n=2→5 单调改善，n=5→10 saturate；但 S4v2 momentum 在 top_5 比 S3 等权 Sharpe 还高（1.51 vs 1.41）— 信号在 crypto 有意义 |
| 「横截面动量在小池反向」 | **完全反转**：S4v2 在 crypto top_5 / top_10 是冠军（NAV 3.1M / 3.8M），V1 中 momentum 是负 IR vs S3 |
| 「避险靠 sizing 不靠 timing」 | **sizing 在 crypto 显著有效**：S5v2 trend tilt 把 MaxDD 从 -78% 砍到 -30%，避险幅度比 V1 更大；timing (S7v2) 因工程问题未跑出 |
| 「等权胜出复杂版本」 | **不成立**：crypto top_5 上 S4v2 momentum (Sharpe 1.51) > S3 等权 (Sharpe 1.41)；与 V1 完全相反 |

### 工程问题留痕（待修）

- **S7v2 ma_filter 全 fail**：错误 `KeyError: 'panel 缺少 symbol: USDT'`。原因：`universe.load_panel(include_cash=True)` 调用 `loader.load_many(['USDT'])`，但 ccxt 没有 USDT/USDT pair。
  - **修复方案**：(1) 在 ccxt loader 检测 cash_proxy 是 stable coin 时返回 const=1 series；或 (2) MarketMAFilterStrategy 对 USDT 类 stable cash 提前判断不调 panel
  - 优先级：实现 V2-S2 (BTC MA filter dedicated) 时一并修
- **S4v2 momentum 在 btc_eth_2 / top_3 上 fail**：`ValueError: w_min*N 与 w_max*N 与归一化和=1 矛盾`（默认 w_min=0.03, w_max=0.30, N=2 → 0.06 与 0.6 不能同时满足 sum=1）
  - **修复方案**：v2 类应当根据 N 动态调整上下限；或在 N < 4 时禁用 alpha tilt
  - 优先级：低，crypto 主要测 top_5+

### 解读 & 命题修正

1. **V1 → V2 最大差异：信号在 crypto 上有意义**：
   - V1 强诊断 S4v2 momentum 在 6 池上 IR 全负（动量在 A 股反向）
   - V2 在 5/10 池上 momentum 是冠军（CAGR +136% / +148%）
   - **可能原因**：crypto 趋势更强、动量持续性更长、池内"赢家通吃"更显著（SOL 持续涨 1 年 → momentum 正向加权 SOL → 进一步放大）
   - 但要警告：crypto top 5 太小（5 标的），momentum 排名信号噪声/信号比可能更高，OOS 风险大

2. **S5v2 vol-target sizing 在 crypto 是真正的避险**：
   - V1 中 S5v2 cash 与下跌相关性仅 0.03（V1 conclusion 说"避险靠 sizing 不靠 timing"）
   - V2 中 S5v2 把 MaxDD 从 -78% 砍到 -30%（改善 48 pct！），明显比 V1 改善 27pct (-47%→-20%) 更显著
   - **机制**：crypto 高 vol 让 sizing 信号更频繁触发；vol-target 在高波动环境天然更有效
   - 但代价：CAGR 从 +118% 降到 +39%（损失 67 pct），risk-adjusted（Sharpe 1.41 → 1.37）几乎持平

3. **TOP_10 vs TOP_5 不再 saturate**：
   - V2-S1 报告说"TOP_10 让 S3 Sharpe 略降"
   - 本次 sweep 数据：S3 TOP_10 NAV 2267.8k vs TOP_5 2282.6k，几乎相同
   - 但 S4v2 momentum 在 TOP_10 NAV **3798.6k** 比 TOP_5 3138.2k 更高，**+660k 反超**
   - 说明：在动量信号下，更多 candidate 资产让 ranking 更可靠

### 给 V2-S2/3/4 的优先级修订

基于本次 sweep（特别是 momentum 在 crypto 上反转 + sizing 真避险），V2 后续应当：

1. **优先 1：V2-S4 crypto_momentum_tilt 的 dedicated 验证**（之前预期负，实测正且最佳）—— 写完整 idea/notes/impl/validation
2. **优先 2：修 S7v2 USDT 工程问题**，跑 V2-S2 BTC MA filter（看 timing 在 crypto 是否能进一步改善 / 与 sizing 结合）
3. **优先 3：V2-S3 dedicated trend_tilt** 验证 sizing 与 timing 哪个 risk-adjusted 更好

### 新的 OOS 风险点

- **S4v2 momentum 在 crypto top_5/10 是冠军**：5 标的池排名信号噪声大；且 SOL 在 momentum tilt 下被进一步加权（暴涨过滤器），1 个标的 100x 放大了 momentum 的"虚假胜利"
- 需在 OOS（2025+）专门验证 momentum 是否持续

---

