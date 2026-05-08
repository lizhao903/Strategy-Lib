---
slug: crypto_trend_tilt
created: 2026-05-08
updated: 2026-05-08
config_path: (无；直接用 TrendTiltV2Strategy + universes.CRYPTO_TOP_5)
related_idea: ideas/S12_crypto_trend_tilt/v1/idea.md
---

# Implementation — V2-S3 (S12) crypto_trend_tilt

## 整体方案
**完全没有新策略代码**。复用 V1 的 `TrendTiltV2Strategy`（S5v2 同款），不需 cash_symbol（trend_tilt 通过 sum<1 自动留现金）。

```python
from strategy_lib.strategies.cn_etf_trend_tilt_v2 import TrendTiltV2Strategy
from strategy_lib.universes import CRYPTO_TOP_5

strat = TrendTiltV2Strategy(
    symbols=list(CRYPTO_TOP_5.symbols),
    rebalance_period=20,
    vol_high=0.30,        # V1 默认；crypto 上偶然就是 risk-eff 最优
    vol_haircut=0.5,      # V1 默认
    score_full=1.0,
    use_continuous_score=True,
)
panel = CRYPTO_TOP_5.load_panel(since="2020-09-01", until="2024-12-31",
                                 include_cash=False)
result = strat.run(panel, init_cash=100_000, fees=0.001, slippage=0.001)
```

## 因子清单

- `MABullishContinuous`（trend score；连续版 v2 默认）
- `DonchianPosition`（trend score 子组件）
- `AnnualizedVol(lookback=60)`（vol filter）

均位于 `src/strategy_lib/factors/`，V1 已实现，本次复用。

## 标的池

| 角色 | symbol | 备注 |
|---|---|---|
| risky pool | TOP_5 / TOP_10 / NO_SOL | trend_tilt 用 sum<1 留现金 |
| cash | （隐式 USDT，sum<1 缺额） | 不需要显式 cash_symbol |

## 数据
- 来源：CCXT → Binance spot
- 频率：1d
- 范围：2020-09-01 ~ 2024-12-31（120 日暖机 + 4 年绩效）

## V2 共享基线参数

| 参数 | 值 | 备注 |
|---|---:|---|
| init_cash | 100,000 USDT | V2 baseline |
| fees / slippage | 10 bp / 10 bp | V2 baseline |
| TDPY | 365 | crypto 24/7 |
| vol_high | **0.30**（V1 默认，crypto 偶然最优） | 见验证 |
| vol_haircut | 0.5（V1 默认） | 触发时全权重 ×0.5 |
| score_full | 1.0（V1 默认） | ramp 饱和点 |
| rebalance_period | 20 | 与其它 V2 一致 |

## 踩过的坑

### 坑 1：vol_high=0.30 在 crypto 是否合适？

**事前担心**：A 股 ETF 常态 vol 15-25%，0.30 是"加速触发"阈值；crypto 常态 vol 60-90%，0.30 → 永远触发降仓 → 等价"硬性 50% 仓位上限"。

**实测结论**（vol_high sweep）：

| vol_high | NAV | CAGR | Sharpe | MaxDD | **Calmar** |
|---:|---:|---:|---:|---:|---:|
| **0.30**（V1 默认）| 377k | +39.32% | 1.373 | **-34.6%** | **★1.14** |
| 0.50 | 456k | +46.13% | 1.333 | -44.1% | 1.05 |
| 0.80 | 474k | +47.50% | 1.198 | -57.9% | 0.82 |
| 1.00（关闭） | 572k | +54.58% | 1.286 | -58.0% | 0.94 |

**反直觉发现**：
- vol_high=0.30 在 crypto 上 Calmar 反而最高（1.14）
- 提高 vol_high → CAGR 上涨（+39 → +55 pp）但 MaxDD 同步翻倍（-35 → -58%）
- **A 股设计的阈值移植到 crypto 偶然是最优** —— 因为 V1 默认本质是"始终强制减半仓"，这一行为恰好对 crypto 高 vol 是合适的"vol target"

**保留 V1 默认 vol_high=0.30**。

### 坑 2：trend_tilt 平均仓位极低（mean 1.1%）

仓位时序统计显示 `target_weights.sum(axis=1)` 平均仅 1.1%（median 0%, max 98%）。原因：
1. crypto 趋势分数大部分时间 ≤ cutoff（无明确多头趋势）→ raw_w = 0
2. `target_weights` 仅在 rebalance day 更新（每 20 日），中间日是 0
3. 但实际持仓在 rebalance 日设定后，期间持续到下次 rebalance

**这不是 bug**——portfolio NAV 增长（CAGR +39%）证明持仓正常工作。但用 `target_weights.sum().mean()` 衡量"平均仓位"时数值会失真，应当用 `target_weights.replace(0, NaN).bfill()` 等价"持仓延续"后再统计。本验证用原始 weights 仅做时序对照。

### 坑 3：vol_haircut=1.0 关闭过滤

vol_haircut=1.0（不降仓）下：NAV 844k / CAGR +70.39% / Sharpe 1.345 / MaxDD -58%。CAGR 翻倍但 MaxDD 也翻倍。**vol filter 是"砍 vol 工具"，不是"alpha 来源"**。

## 与 V1 代码的接口契约

V2-S3 完全用 V1 既有代码：
- `TrendTiltV2Strategy.target_weights()` 用 sum<1 自动留现金
- `vbt.Portfolio.from_orders` 在 sum<1 + cash_sharing 下正确把缺额留作 group cash
- 不需要 cash_symbol（与 V2-S2 / V2-S1 不同）

**V1 工具普适性的第四个证据**（V2-S1 / V2-S2 / V2-S4 后）：trend_tilt 从 A 股 ETF 迁移到 crypto **0 代码改动**，仅参数 sweep 验证默认值仍最优。

## 实现 commits
- 无策略层代码改动
- validate 脚本：`summaries/S12_crypto_trend_tilt/v1/validate.py`
