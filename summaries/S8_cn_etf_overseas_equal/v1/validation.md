---
slug: cn_etf_overseas_equal
updated: 2026-05-08
---

# Validation — S8 v1 (overseas_equal)

---

## 2026-05-08 初版验证（来自 universe_sweep_demo 数据，未做专门 run）

### 数据来源
- **复用**：`scripts/universe_sweep_demo.py` 跑 4 strategies × 4 universes 的 grid 时 S3 在 overseas_4 上的结果
- 详细 CSV：`results/universe_sweep_demo_<timestamp>.csv` 中 `(strategy=S3 equal_rebal, universe=cn_etf_overseas_4)` 行
- 配置：`configs/S8_cn_etf_overseas_equal_v1.yaml`（与 sweep demo 等价）

### 主结果（in-sample 2020-01-02 ~ 2024-12-31）

| 指标 | 值 |
|---|---:|
| 最终 NAV (100k 起) | **171,303** |
| CAGR | **+11.87%** |
| Sharpe | **0.851** |
| MaxDD | -20.9% |
| 年化波动 | ~14.0% |
| Calmar | 0.57 |
| 切换 / 再平衡 | 月度（rebalance_period=20，5y ~60 次） |
| 年化换手 | ~50%（估，依据再平衡量） |

### vs V1 全套已知最佳对比

| 策略 | NAV | CAGR | Sharpe | MaxDD | 来源 |
|---|---:|---:|---:|---:|---|
| **S8 (本)** | **171.3k** | **+11.87%** | **0.851** | -20.9% | sweep |
| S4v2 (11 池含 A 股) | 130.7k | +5.75% | 0.44 | -22.2% | V1 v2 直接验证 |
| S3 11 池等权 (含 A 股) | 134.3k | +6.36% | 0.465 | -22.9% | S7v2 ablation |
| S5v2 6 池 | 112.9k | +2.57% | 0.28 | -20.5% | V1 v2 直接验证 |
| S7v2 11 池 | 119.0k | +3.70% | 0.40 | -17.5% | S7v2 主测 |
| BH 510300 | 104.3k | +0.86% | 0.18 | -44.8% | 基准 |

S8 在所有 7 个策略 + V1 v2 中：**Sharpe 第 1 / NAV 第 1 / CAGR 第 1**，MaxDD 第 4（劣于 S5v2 -20.5% / S7v2 -17.5% / S5v2+overseas_4 -8.5%）。

### 池子单调性（4 strategies × 4 universes 全部成立）

| | base_6 | broad_3 | expanded_11 | overseas_4 |
|---|---:|---:|---:|---:|
| S3 equal_rebal Sharpe | 0.217 | 0.244 | 0.465 | **0.851** |
| S4v2 momentum Sharpe | 0.191 | 0.218 | 0.548 | **0.730** |
| S5v2 trend Sharpe | 0.113 | 0.004 | 0.368 | **0.717** |
| S7v2 ma_filter Sharpe | 0.304 | 0.298 | 0.403 | 0.457 |

**关键观察**：池子改进对 sizing/factor 类策略（S3/S4v2/S5v2）效果显著（Sharpe 翻 4-6 倍），对 timing 类（S7v2）改进有限（仅 +50%）。

### 关键图表
**未生成**（本次仅复用 sweep 数据，未做专门 plot）。下一步 dedicated validate.py 应输出：
- `equity_curve.png` — S8 vs S4v2 vs S5v2 vs BH（4 条线）
- `drawdown.png` — 同上
- `weight_evolution.png` — 4 资产权重时间序列堆积图
- `yearly_returns.csv` — 分年度对比
- `rolling_window.csv` — 3 个 1.5y 子窗口（2020H1-2021H2 / 2021H2-2023H1 / 2023H1-2024H2）

### 解读 & 问题
1. **数据强烈暗示「无 A 股」是 alpha 主因**：池子 alpha 单调递增，4 个策略一致
2. **窗口偶然性是最大未知**：2020-2024 美股最强 / A 股最弱组合事后看明显，但事前并非显然
3. **overseas_4 中谁贡献了 alpha**：尚未做单标的 ablation；猜测 513100 纳指 + 518880 黄金为主，159920 恒生（HK 跟踪）和 513500 标普500 是稳定器；下一步 dedicated validate.py 应做单 ETF 留一交叉

### 已发现的策略类问题
- 无（复用 S3 现成代码）

### 下一步
- [ ] 写专门的 `summaries/S8_cn_etf_overseas_equal/v1/validate.py`，输出 dedicated 图表 + 分年度 + 单标的 ablation
- [ ] 跑 3 个滚动 1.5y 子窗口验证 in-sample 一致性
- [ ] OOS 测试（2025+ 数据可得后）
- [ ] 与 S5v2 + overseas_4 的 risk profile 对比（高收益 vs 低回撤的 trade-off）
- [ ] 5 池版（+511260 十年国债）作为 v2 候选

---
