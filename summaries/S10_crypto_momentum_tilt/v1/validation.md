---
slug: crypto_momentum_tilt
status: in_progress
---

# Validation — V2-S4 (S10) crypto_momentum_tilt

## 2026-05-08 主回测 + ablation（完整跑）

**配置**：CRYPTO_TOP_5 / 100k USDT / 2021-01 ~ 2024-12 / fees=10bp / slippage=10bp / 365d 年化 / lookback=120 skip=5 signal=raw alpha=1.0 / rebalance=20

### 1. 主结果

| 指标 | V2-S4 momentum (TOP_5) | V2-S1 equal (TOP_5) | BTC/USDT BH |
|---|---:|---:|---:|
| Final NAV (100k 起) | **3,138.2k** | 2,282.6k | 319.0k |
| CAGR | **+136.55%** | +118.46% | +33.62% |
| Sharpe | **1.511** | 1.410 | 0.777 |
| Vol ann | 76.6% | 76.1% | ~70% |
| MaxDD | -77.1% | -78.9% | ~-77% |
| Sharpe / Vol（risk-eff） | 1.97 | 1.85 | 1.11 |

### 2. Alpha 拆分（关键）

| 来源 | CAGR 增量 | Sharpe 增量 |
|---|---:|---:|
| V2-S4 vs BTC BH | **+102.93 pp/yr** | +0.73 |
| V2-S1 vs BTC BH（"池子+等权"贡献） | **+84.85 pp/yr** | +0.63 |
| V2-S4 vs V2-S1（"momentum 信号"增量贡献） | **+18.08 pp/yr** | +0.10 |

**alpha 归因结论**：在 crypto TOP_5 上，整体 +103 pp/yr alpha 中 ~83% 来自「池子选择 + 等权再平衡」（V2-S1 已经吃下），momentum 倾斜本身仅贡献剩余 ~17%（+18 pp/yr）。再次印证 V1 总结的「池子 >> 信号 >> 仓位」在 crypto 仍成立。

### 3. Lookback sweep（参数稳健性）

| lookback | NAV (100k 起) | CAGR | Sharpe |
|---:|---:|---:|---:|
| 60  | 1,603.5k | +100.02% | 1.286 |
| **120** | **3,138.2k** | **+136.55%** | **1.511** |
| 240 | 2,430.0k | +121.90% | 1.420 |

**解读**：lookback=120 是局部最优。60 太短（被短期波动主导），240 太长（错过快速崛起标的）。120 是 V1 默认值（事前选择），不是过拟合调出的——但在 4 年样本上"恰好"是最优意味着 OOS 风险中等。

### 4. Signal sweep（raw vs vol_adj）

| signal | NAV (100k 起) | CAGR | Sharpe |
|---|---:|---:|---:|
| **raw** | **3,138.2k** | **+136.55%** | **1.511** |
| vol_adj | 2,862.0k | +131.16% | 1.468 |

**解读**：raw 略胜 vol_adj。vol-adjust 在 V1（A 股 11 池）的动机是"防止高 vol 资产长期主导"，但 crypto 的"高 vol 资产"恰恰是动量信号本身的来源（SOL）—— 除以 vol 反而抑制了 alpha。**crypto momentum 应当用 raw，不是 vol_adj。**

### 5. Universe ablation（核心验证）

| Universe | n | momentum NAV | momentum Sharpe | equal NAV | equal Sharpe | momentum vs equal CAGR α |
|---|---:|---:|---:|---:|---:|---:|
| crypto_top_5      | 5  | 3,138.2k | 1.511 | 2,282.6k | 1.410 | **+18.08 pp** |
| crypto_top_10     | 10 | 3,798.6k | 1.423 | 2,267.8k | 1.351 | **+30.00 pp** |
| crypto_top_5_no_sol | 4  | 1,081.5k | 1.172 | 1,134.8k | 1.195 | **-2.19 pp** |

**关键发现**：
- **TOP_10 上 momentum alpha 反而最大**（+30 pp/yr）—— 横截面分散度更高 → z-score 信息密度上升 → momentum 倾斜更精准
- **NO_SOL 上 momentum alpha 翻负**（-2.19 pp/yr）—— 去 SOL 后 5 标的 → 4 标的，失去"暴涨 outlier"，z-score 接近随机，倾斜无效甚至轻微负向（高换手成本吃掉收益）
- **crypto momentum alpha 高度依赖 outlier**：与"crypto basket equal alpha 也来自 SOL 100x"（V2-S1 conclusion）属同一现象的不同侧写——crypto 内部"分散度"主要来自少数 outlier，而非池子整体

### 6. 分年度收益（CAGR %）

| 年份 | V2-S4 mom | V2-S1 eq | BTC BH | mom vs eq | 解读 |
|---|---:|---:|---:|---:|---|
| 2021 | +1025.9% | +1031.2% | +57.6% | -5.3 pp | momentum 略输等权（SOL 暴涨阶段两者都 100% 满仓 SOL，倾斜机制无差） |
| 2022 | -67.7% | -71.5% | -65.3% | +3.8 pp | momentum 在熊市略好（z-score 轻微减仓 SOL） |
| 2023 | +199.6% | +183.4% | +154.5% | +16.2 pp | SOL 复苏期 momentum 逆势加仓收益 |
| 2024 | +165.6% | +132.7% | +111.8% | +32.9 pp | XRP/SOL 强势期 momentum 倾斜抓住 |

**解读**：momentum alpha 主要在 2023-2024 兑现（共 +49 pp），2022 -67% 反映这不是 timing 策略——动量倾斜不能避险。

### 7. 与 V1 S4v2 的跨市场对比（普适性 vs 池子结构）

| 维度 | V1 S4v2（A 股 11 池） | V2-S4（crypto 5 池） |
|---|---|---|
| Sharpe | ~0.43 | 1.511 |
| Vol ann | ~14% | 77% |
| Sharpe / Vol（risk-eff） | **3.0** | 1.97 |
| vs S3 等权 alpha CAGR | ~+0.5 pp（弱） | **+18.1 pp** |
| 信号有效性 | 边际正向 | 显著正向 |

**解读**：
1. crypto 的 Sharpe 高 3.5x 但 risk-efficiency 反低 35%——同一现象，与 V2-S1 已观察到的一致
2. 信号 alpha 在 crypto 上量级是 A 股 36x，但**主因是池子（NO_SOL ablation 印证 alpha 80% 来自 SOL outlier）**，不是 crypto market 本身让信号变强
3. **V1 总结「池子 >> 信号 >> 仓位」在 crypto 跨市场再次得到验证**

### 8. 工程修复验证

`MomentumTiltV2Strategy` 小 N 池边界自动放宽逻辑修复后：
- N=11（V1 默认）行为完全不变（w_max=0.30 未触发放宽分支）
- N=5（CRYPTO_TOP_5）正常工作
- N=4（NO_SOL）正常工作（w_max 自动放宽到 1/(4-1)=0.333）
- N=2 / 3（BTC_ETH_2 / TOP_3）此前 ValueError 现已可跑（本次未纳入主测，留作未来 sweep 一致性）

## artifacts
- `equity_curve.png` — V2-S4 vs V2-S1 vs BTC BH log-y 净值
- `drawdown.png` — 三者回撤（含 2022 LUNA/FTX 高亮）
- `yearly_returns.png + .csv` — 分年度对比
- `lookback_sweep.csv` — lookback ∈ {60, 120, 240}
- `signal_sweep.csv` — raw vs vol_adj
- `universe_ablation.csv` — TOP_5 / TOP_10 / NO_SOL
- `real_backtest_summary.json` — 主结果汇总
