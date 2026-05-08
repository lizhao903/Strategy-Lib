---
slug: crypto_btc_ma_filter
created: 2026-05-08
---

# Notes — V2-S2 (S11) crypto_btc_ma_filter

## 2026-05-08 启动备忘

- S9 conclusion 优先 2。先决条件：CryptoLoader 必须能合成 USDT const-1 panel（已修）。
- 与 V2-S1 / V2-S4 共享窗口和基线（2021-2024 / 100k USDT / fees=10bp / slippage=10bp）。
- V1 S7v2 默认 ma_length=200 + lag=1；V2-S2 沿用，仅改 risky pool / signal_symbol。

## 工程坑修复记录

**bug**：`MarketMAFilterStrategy.build_target_weight_panel` 检查 panel 必须含 cash_symbol：
```
KeyError: 'panel 缺少 symbol: USDT'
```
**根因**：USDT 是稳定币，CCXT 上不存在 USDT/USDT 交易对。但策略需要 cash 资产价格序列做组合定价。

**修复**：在 `CryptoLoader.load()` 拦截稳定币 set `{USDT, USDC, BUSD, DAI, FDUSD}`，调用 `_synthesize_const_ohlcv()` 生成与主标的对齐的 close=open=high=low=1.0、volume=0 的 DataFrame。
- 不影响其它 crypto 标的的 ccxt 加载流程
- 自动适配 timeframe（1d / 4h / 1h 等）→ pd.date_range 对应 freq
- 索引自然对齐 BTC 等 crypto 主标的（连续 daily UTC）

**影响范围**：所有 V2 crypto 策略中需要 cash 代理的（S7v2 / S1 DCA / S2 swing / S6 VA）。

## 待跟进

- 等本次 V2-S2 跑完，应用 sweep 重跑一次 V2 全套 → 应该不再有 USDT KeyError
- 如果 V2-S2 在 crypto 上 risk-eff 显著高（Sharpe / Vol > V2-S1）则升级为 ship
- 如果 OFF 时间 < 30% 说明信号稀疏，未必是 timing 价值
