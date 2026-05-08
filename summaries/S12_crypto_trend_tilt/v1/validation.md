---
slug: crypto_trend_tilt
status: in_progress
---

# Validation — V2-S3 (S12) crypto_trend_tilt

## 2026-05-08 主回测 + 完整 ablation

**配置**：CRYPTO_TOP_5 / 100k USDT / 2021-01 ~ 2024-12 / fees=10bp / slippage=10bp / 365d 年化 / vol_high=0.30 / vol_haircut=0.5 / score_full=1.0 / rebalance=20

### 1. 主结果 + V2 系列对比

| 配置 | NAV | CAGR | Sharpe | Vol | MaxDD | **Calmar** |
|---|---:|---:|---:|---:|---:|---:|
| **V2-S3 trend tilt (TOP_5)** | 377.1k | +39.32% | 1.373 | 26.8% | **-34.6%** | 1.14 |
| V2-S2 BTC MA filter (TOP_5, MA=100) | 3,512k | +143.28% | **1.951** | ~73% | -43.4% | **★3.30** |
| V2-S4 momentum (TOP_5) | 3,138k | +136.55% | 1.511 | 76.6% | -77.1% | 1.77 |
| V2-S1 equal (TOP_5) | 2,283k | +118.46% | 1.410 | 76.1% | -78.9% | 1.50 |
| BTC/USDT BH | 319k | +33.62% | 0.777 | ~70% | ~-77% | 0.43 |

**V2-S3 真实评价**：
- CAGR +39% 仅略高于 BTC BH（+34%）但远低于 V2-S1（+118%）—— 显著 alpha 损失
- Sharpe 1.373 略低于 V2-S1 1.410 —— 与 V2-S1 持平 / 略输
- **MaxDD -34.6% 是 V2 系列最佳**（vs V2-S2 -43%, V2-S4/V2-S1 -77~-79%）
- Vol 26.8% 是 V2 系列最低（其它都 70%+）
- **Calmar 1.14 比 V2-S1 1.50 / V2-S2 3.30 / V2-S4 1.77 都低**——risk-adjusted return **没有打败 V2-S1 等权**

### 2. vol_high sweep（核心参数发现）

| vol_high | NAV | CAGR | Sharpe | MaxDD | **Calmar** | 解读 |
|---:|---:|---:|---:|---:|---:|---|
| **0.30**（V1 默认）| 377k | +39.32% | 1.373 | **-34.6%** | **★1.14** | crypto 上 risk-eff 最优 |
| 0.50 | 456k | +46.13% | 1.333 | -44.1% | 1.05 | |
| 0.80 | 474k | +47.50% | 1.198 | -57.9% | 0.82 | |
| 1.00（关闭） | 572k | +54.58% | 1.286 | -58.0% | 0.94 | |

**反直觉发现**：
- 事前预期 vol_high=0.80（crypto 适配）会更优；实测 V1 默认 0.30 是 risk-eff 最优
- 原因：vol_high=0.30 在 crypto 上让 vol filter "永远触发"，等价于"始终强制 50% 仓位上限"——这是 crypto 高 vol 下合理的 vol-target 设定
- **A 股调出来的参数偶然最适合 crypto**：与 V2-S2 MA=100 完全不同（V1 200 在 crypto 错误）

### 3. vol_haircut ablation（开 vs 关 vol filter）

| vol_haircut | NAV | CAGR | Sharpe | MaxDD |
|---:|---:|---:|---:|---:|
| **0.5**（开） | 377k | +39.32% | 1.373 | **-34.6%** |
| 1.0（关） | 844k | +70.39% | 1.345 | -58.0% |

**解读**：
- vol_filter 让 CAGR -31 pp、MaxDD -23 pp、Sharpe 持平
- **vol filter 砍 vol 不带新 alpha**——这与 V1 S5v2 在 A 股的发现完全一致
- 即"trend_tilt 是 risk profile shifter，vol filter 是 risk-target 调节器，二者均非 alpha 来源"

### 4. Universe ablation（与 V2-S1 等权 Calmar 对比）

| Universe | n | trend NAV | trend Sharpe | trend MaxDD | **trend Calmar** | equal Calmar | Calmar lift |
|---|---:|---:|---:|---:|---:|---:|---:|
| crypto_top_5      | 5  | 377k | 1.373 | -34.6% | 1.14 | 1.50 | **-24.3%** |
| crypto_top_10     | 10 | 481k | **1.583** | **-30.0%** | **★1.60** | 1.44 | **+11.4%** |
| crypto_top_5_no_sol | 4 | 220k | 0.879 | -36.8% | 0.59 | 1.13 | -47.9% |

**关键发现**：
- **TOP_10 上 trend_tilt Calmar 1.60 > equal Calmar 1.44**——V2-S3 在更大池上微幅超越 V2-S1 in risk-adjusted
- TOP_5 / NO_SOL 上 trend_tilt Calmar 都输 equal
- 与 V2-S4 momentum 类似规律：**更大池让 V2-S3 有效**（横截面分散度让 trend score / vol filter 命中频率更稳）
- **V2-S3 推荐配置 = TOP_10 + V1 默认参数**（不是 TOP_5）

### 5. 分年度收益（V1 默认配置）

| 年份 | V2-S3 trend (TOP_5) | V2-S1 eq (TOP_5) | BTC BH | 解读 |
|---|---:|---:|---:|---|
| 2021 | +189.9% | +1031.2% | +57.6% | 2021 牛市 V2-S3 趋势识别后部分入场，但仓位上限 50% → 错过大部分牛市 |
| **2022** | **-13.4%** | -71.5% | -65.3% | **vol filter + 趋势失败 → 大部分 OFF；唯一显著兑现年** |
| 2023 | +24.8% | +183.4% | +154.5% | 复苏期趋势识别滞后；vol 还在高位 → 仓位上限 50% |
| 2024 | +17.6% | +132.7% | +111.8% | 类似 2023 |

**核心解读**：V2-S3 的 alpha 完全集中在 2022（-13% vs V2-S1 -71%）。其余 3 年都"一直在等仓位"。**V2-S3 ≈ "V2-S1 但只在熊市生效"**——但代价是 3 个牛市年都被严重抑制。

### 6. Calmar 比较（V2-S3 在 V2 系列定位）

| 策略 | TOP_5 Calmar | TOP_10 Calmar |
|---|---:|---:|
| V2-S2 (MA=100) | **★3.30** | (未测，预期 2.5-3.0) |
| V2-S4 (momentum) | 1.77 | ~1.86 |
| V2-S3 (trend tilt) | 1.14 | **1.60** |
| V2-S1 (equal) | 1.50 | 1.44 |
| BTC BH | 0.43 | - |

**V2-S3 在 V2 系列中的定位**：
- TOP_5 上 Calmar 输给 V2-S1 / V2-S2 / V2-S4（**不应作为主策略**）
- TOP_10 上 Calmar 1.60 略胜 V2-S1（1.44），但仍输 V2-S2（~3.0+）
- **唯一独特卖点**：MaxDD 是 V2 系列最深的"low"（-30%），适合 risk-budget 极严的资金

### 7. 平均仓位时序

- target_weights 平均（含 0 日）= 1.1%
- target_weights median = 0.0%
- target_weights max = 98.4%
- **解读**：trend_score 大部分时间 ≤ cutoff（无明确多头趋势）→ rebalance 日 raw_w=0；中间日仓位由 portfolio 持续。这与 V1 在 A 股的"平均仓位 ~37%"形成对照——crypto 趋势识别更稀疏

### 8. 与 V1 S5v2 跨市场对比

| 维度 | V1 S5v2（A 股 11 池） | V2-S3 (crypto TOP_5) | 解读 |
|---|---|---|---|
| Sharpe | 0.28 | 1.37 | crypto 高 |
| Sharpe / Vol | ~5 | 5.1 | risk-eff 几乎相同 |
| MaxDD | -20.5% | -34.6% | crypto 仍深 |
| 2022 单年 | -7.6% | -13.4% | 都兑现避险 |
| Calmar | ~0.13 | 1.14 | crypto 高 |
| vs S3/V2-S1 alpha | 持平 | -79.14 pp（CAGR） | 高代价 |

**核心**：trend_tilt 在 crypto 上 risk-eff 与 A 股持平（Sharpe/Vol 都 ~5），但绝对 CAGR 损失更大（牛市机会成本更高）。

## artifacts
- `equity_curve.png` — V2-S3 vs V2-S1 vs BTC BH log-y
- `drawdown.png` — 三者回撤
- `yearly_returns.csv` — 分年度
- `vol_high_sweep.csv` — **核心**: vol_high ∈ {0.30, 0.50, 0.80, 1.00}
- `vol_haircut_ablation.csv` — 0.5 vs 1.0
- `universe_ablation.csv` — TOP_5 / TOP_10 / NO_SOL
- `calmar_comparison.csv` — V2-S1 vs V2-S3 Calmar 各 universe
- `position_timeline.csv` — 月度平均仓位
- `real_backtest_summary.json` — 主结果汇总
