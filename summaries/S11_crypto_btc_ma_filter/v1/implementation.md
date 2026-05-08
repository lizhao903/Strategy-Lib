---
slug: crypto_btc_ma_filter
created: 2026-05-08
updated: 2026-05-08
config_path: (无；直接用 MarketMAFilterV2Strategy + universes.CRYPTO_TOP_5)
related_idea: ideas/S11_crypto_btc_ma_filter/v1/idea.md
---

# Implementation — V2-S2 (S11) crypto_btc_ma_filter

## 整体方案
**完全没有新策略代码**。复用 V1 的 `MarketMAFilterV2Strategy`（S7v2 同款）+ V2 既有 `CRYPTO_TOP_5` universe。**唯一改动**：`CryptoLoader.load()` 增加稳定币（USDT/USDC/BUSD/DAI/FDUSD）合成 const-1 OHLCV 路径，让 panel 完整支持 cash 代理。

```python
from strategy_lib.strategies.cn_etf_market_ma_filter_v2 import MarketMAFilterV2Strategy
from strategy_lib.universes import CRYPTO_TOP_5

strat = MarketMAFilterV2Strategy(
    symbols=list(CRYPTO_TOP_5.symbols),
    cash_symbol=CRYPTO_TOP_5.cash_proxy,      # "USDT"（合成 const 1.0）
    signal_symbol=CRYPTO_TOP_5.benchmark,     # "BTC/USDT"
    ma_length=100,                            # crypto 最佳（V1 200 太长）
    lag_days=1,
    weight_mode="equal",
)
panel = CRYPTO_TOP_5.load_panel(since="2020-09-01", until="2024-12-31",
                                 include_cash=True)  # USDT 合成
result = strat.run(panel, init_cash=100_000, fees=0.001, slippage=0.001)
```

> **重要**：`include_cash=True` 让 USDT 进入 panel；CryptoLoader 自动合成 const-1.0 序列（与 BTC 索引完全对齐）。

## 因子清单

无新因子。MA 直接在策略内 `signal_close.rolling(ma_length).mean()` 实现。

## 标的池

| 角色 | symbol | 数据来源 |
|---|---|---|
| risky pool | BTC/ETH/SOL/BNB/XRP /USDT | CCXT Binance spot |
| signal | BTC/USDT | 同上（用 close 计算 MA） |
| cash | USDT | **CryptoLoader 合成 const 1.0**（不走 ccxt） |

## 数据
- 来源：CCXT → Binance spot
- 时间频率：1d
- 数据范围：2020-09-01 ~ 2024-12-31（200 日暖机 + 4 年绩效）
- USDT cash panel：`pd.date_range(since, until, freq="1D", tz="UTC")`，OHLCV=1.0/0
- 缓存：5 个 risky 标的均已存 `data/raw/crypto/*_USDT_1d.parquet`

## V2 共享基线参数（与 V2-S1 / V2-S4 一致）

| 参数 | 值 | 备注 |
|---|---:|---|
| init_cash | 100,000 USDT | V2 baseline |
| fees | 10 bp | Binance 现货 |
| slippage | 10 bp | 保守 |
| TDPY | 365 | crypto 24/7 |
| ma_length | **100** | **crypto 最佳，V1 默认 200 太长** |
| lag_days | 1 | V1 S7v2 已验证最佳 |
| weight_mode | equal | risky pool 等权 |
| signal_lag | 1 | t 日信号 → t+1 日成交 |

## 踩过的坑

### 坑 1：USDT 不能从 ccxt 加载

V2 sweep（`results/v2_crypto_sweep_20260508_162436.csv`）显示 S7v2 在 5 个 crypto universe 上全失败：
```
KeyError: 'panel 缺少 symbol: USDT'
```

**根因**：USDT 是稳定币，CCXT 上没有 USDT/USDT 交易对。但 `MarketMAFilterStrategy.build_target_weight_panel` 检查 panel 必须包含 cash_symbol。

**修复**（`src/strategy_lib/data/crypto.py`）：
1. 加 `_CONST_CASH_SYMBOLS = {"USDT", "USDC", "BUSD", "DAI", "FDUSD"}`
2. `CryptoLoader.load()` 在 symbol 命中集合时调用 `_synthesize_const_ohlcv()`，生成与 timeframe 对应 freq 的 daily 索引 + close=open=high=low=1.0、volume=0 的 DataFrame
3. 不影响其它 crypto 标的的 ccxt 加载流程

**验证**：`smoke test 已过`：`s7v2_market_ma_filter(CRYPTO_TOP_5).run(panel)` 跑出 NAV 435,578 / 35 次切换，无报错。

**影响范围**：所有 V2 crypto 策略中需要 cash 代理的（S7v2 / S1 DCA / S2 swing / S6 VA）现已可在 crypto 上跑。

### 坑 2：默认 MA 长度（V1 200 → V2 100）

V1 S7v2 默认 ma_length=200（A 股 200 日 ≈ 10 个月），但 sweep 显示在 crypto:
- MA=200: CAGR +44.50% / Sharpe 1.019（V1 默认值，弱）
- MA=100: CAGR **+143.28%** / Sharpe **1.951**（最佳）
- MA=50:  CAGR +136.27% / Sharpe 1.914（次之，但 74 次切换噪声多）

**根因**：crypto 趋势比 A 股短（牛市 1y vs 美股 / A 股牛市 2-3y）；200 日 MA 反应过慢，2021 牛市顶部 BTC < MA 时已经从顶部跌 30%；MA=100 兼顾"够长滤噪 + 够短跟趋势"。

**未改默认值**：保留 V1 的 ma_length=200 默认，不破坏 A 股回测。在 V2-S2 dedicated 的 conclusion 中明确推荐 crypto 用 ma_length=100。后续可考虑加一个 `MarketMAFilterCryptoStrategy` 子类把默认改成 100，但目前一行参数已够用。

### 坑 3：年化天数

与 S9 / S10 同：crypto 用 365 天而非 V1 的 252。`calc_crypto_metrics` 沿用。

## 与 V1 代码的接口契约

V2-S2 完全用 V1 既有代码：
- `MarketMAFilterV2Strategy.run()` 在 crypto panel + USDT 合成 cash 上正常工作
- `vbt.Portfolio.from_orders` size_type="targetpercent" + cash_sharing 兼容稳定币 cash
- `Universe.load_panel(include_cash=True)` 触发 CryptoLoader 合成 USDT 路径

**这是 V1 工具普适性的第三个证据**（继 V2-S1 / V2-S4 后）：MA filter 机制从 A 股 ETF 迁移到 crypto 仅需 1 个数据层修复（USDT 合成）。**最大发现是 crypto 最佳 MA 长度 ≠ V1 默认值**，这种"参数最优值需重新探索"的现象比"机制需重写"更典型也更便宜。

## 实现 commits
- 数据层修复：`src/strategy_lib/data/crypto.py` 增加稳定币合成路径
- validate 脚本：`summaries/S11_crypto_btc_ma_filter/v1/validate.py`
