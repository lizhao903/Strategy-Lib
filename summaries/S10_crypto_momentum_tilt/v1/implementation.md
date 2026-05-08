---
slug: crypto_momentum_tilt
created: 2026-05-08
updated: 2026-05-08
config_path: (无；直接用 MomentumTiltV2Strategy + universes.CRYPTO_TOP_5)
related_idea: ideas/S10_crypto_momentum_tilt/v1/idea.md
---

# Implementation — V2-S4 (S10) crypto_momentum_tilt

## 整体方案
**完全没有新策略代码**。复用 V1 的 `MomentumTiltV2Strategy`（S4v2 同款）+ V2 既有 `CRYPTO_TOP_5` universe。仅做了 1 处工程修复（小 N 池边界自动放宽），其它沿用。

```python
from strategy_lib.strategies.cn_etf_momentum_tilt_v2 import MomentumTiltV2Strategy
from strategy_lib.universes import CRYPTO_TOP_5

strat = MomentumTiltV2Strategy(
    symbols=list(CRYPTO_TOP_5.symbols),
    rebalance_period=20,        # 月度（与 V2-S1 / V1 同口径）
    lookback=120, skip=5,       # V1 默认
    signal="raw", alpha=1.0,    # V1 默认
)
panel = CRYPTO_TOP_5.load_panel(since="2020-09-01", until="2024-12-31",
                                 include_cash=False)
result = strat.run(panel, init_cash=100_000, fees=0.001, slippage=0.001)
```

## 因子清单

- `MomentumReturn(lookback=120, skip=5)` — 累计收益动量（默认信号）
- `VolAdjustedMomentum(lookback=120, skip=5, vol_lookback=60)` — vol 归一化动量（备选信号，sweep 用）

均位于 `src/strategy_lib/factors/momentum.py`，V1 已实现，本次复用。

## 标的池（CRYPTO_TOP_5）

| symbol | 类别 | 备注 |
|---|---|---|
| BTC/USDT | 数字黄金 | 4y CAGR ~+34%（基准） |
| ETH/USDT | L1 | EVM 生态 |
| SOL/USDT | L1 | 2021 +12000%，2022 -94%，2023 +900% — momentum 主导驱动 |
| BNB/USDT | 平台币 | Binance 平台风险 |
| XRP/USDT | 跨境支付 | 2024 监管利好后大涨 |

副测：CRYPTO_TOP_10（加 DOGE/ADA/AVAX/LINK/DOT），CRYPTO_TOP_5_NO_SOL（剔除 SOL）。

## 数据
- 来源：CCXT → Binance spot
- 时间频率：1d
- 数据范围：2020-09-01 ~ 2024-12-31（120 日暖机 + 4 年绩效）
- 已缓存：5 个标的全部已存 `data/raw/crypto/*_USDT_1d.parquet`，每个 1583 bars
- 数据质量：5 个标的 2020-09 起均连续无断档

## V2 共享基线参数（与 V2-S1 完全一致）

| 参数 | 值 | 来源 |
|---|---:|---|
| init_cash | 100,000 USDT | V2 baseline |
| fees | 10 bp | V2 baseline（Binance 现货 0.1% 实际） |
| slippage | 10 bp | V2 baseline（保守估计） |
| trading_days_per_year | 365 | crypto 24/7 |
| rebalance_period | 20 | 与 V1 / V2-S1 同 |
| lookback | 120 | V1 S4v2 默认 |
| skip | 5 | V1 S4v2 默认 |
| alpha | 1.0 | V1 默认 |
| w_min, w_max | 0.03, 0.30 (N=11) → 自适应 | 见下文坑 1 |

## 踩过的坑

### 坑 1：MomentumTiltV2Strategy 在小 N 池触发 ValueError

V2 sweep（`results/v2_crypto_sweep_20260508_162436.csv`）显示在 BTC_ETH_2 / TOP_3 上报：
```
ValueError: w_min*N=0.06 与 w_max*N=0.6 与归一化和=1 矛盾
```

**根因**：默认 w_max=0.30 是按 N=11（V1 11 池）调过的（0.30*11=3.3 包住归一化和 1.0）。N=2 时 0.30*2=0.6 < 1.0 → 上限内放不下"和=1"。

**修复**：`cn_etf_momentum_tilt_v2.py` 构造时按 N 自动放宽：
- `w_max → max(w_max, 1/(N-1))` 当 `w_max*N < 1` 时
- N=2 → 1.0；N=3 → 0.5；N=4 → 0.333；N≥5 不变

不影响 N=11 行为（V1 默认下 w_max 仍是 0.30）。本次主测 N=5 / 10 也都不触发。

### 坑 2：matplotlib 中文字体 missing warning

与 S9 同：CJK 字符在 DejaVu Sans 缺失，warnings 但图片正常输出。后续可改英文标题或安装中文字体；不阻塞。

### 坑 3：年化天数

与 S9 同：crypto 用 365 天而非 V1 的 252。`calc_crypto_metrics` 沿用 S9 的实现。

## 与 V1 代码的接口契约

V2-S4 完全用 V1 既有代码：
- `MomentumTiltV2Strategy.target_weights()` 在 N=5 crypto 上正常生成 z-score → tilt → clip → normalize 权重
- `_slice_strict()` 严格 shift(1) 切片（`index < date`）杜绝 same-bar lookahead — crypto 同样适用
- `vbt.Portfolio.from_orders` 在 1583 bars × 5 symbols 输入下正常工作

**这是 V1 工具普适性的第二个证据**（继 V2-S1 后）：动量倾斜机制从 A 股 ETF 迁移到 crypto 仅需 1 行边界修复。

## 实现 commit
- 边界修复：`src/strategy_lib/strategies/cn_etf_momentum_tilt_v2.py` 增加小 N 池自动放宽逻辑
- validate 脚本：`summaries/S10_crypto_momentum_tilt/v1/validate.py`
