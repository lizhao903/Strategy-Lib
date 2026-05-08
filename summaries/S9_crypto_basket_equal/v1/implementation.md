---
slug: crypto_basket_equal
created: 2026-05-08
updated: 2026-05-08
config_path: (无；直接用 EqualRebalanceStrategy + universes.CRYPTO_TOP_5)
related_idea: ideas/S9_crypto_basket_equal/v1/idea.md
---

# Implementation — V2-S1 (S9) crypto_basket_equal

## 整体方案
**完全没有新代码**。复用 V1 的 `EqualRebalanceStrategy`（S3 同款）+ V2 新注册的 `CRYPTO_TOP_5` universe。一行启动：

```python
from strategy_lib.strategies.cn_etf_equal_rebalance import EqualRebalanceStrategy
from strategy_lib.universes import CRYPTO_TOP_5

strat = EqualRebalanceStrategy(
    symbols=list(CRYPTO_TOP_5.symbols),
    rebalance_period=20,  # 月度（与 V1 同口径）
)
panel = CRYPTO_TOP_5.load_panel(since="2020-09-01", until="2024-12-31",
                                 include_cash=False)
result = strat.run(panel, init_cash=100_000, fees=0.001, slippage=0.001)
```

## 因子清单
无。纯等权再平衡机制。

## 标的池组成（CRYPTO_TOP_5）

| symbol | 类别 | 注释 |
|---|---|---|
| BTC/USDT | 数字黄金 | 起 11.6k → 终 93.6k（5y 8x）|
| ETH/USDT | L1 | EVM 生态 |
| SOL/USDT | L1 | 2021 暴涨 100x，2022 -95% 暴跌 |
| BNB/USDT | 平台币 | Binance 平台风险敞口 |
| XRP/USDT | 跨境支付 | 监管风险高 |

## 数据
- 来源：CCXT → Binance spot
- 时间频率：1d
- 数据范围：2020-09-01 ~ 2024-12-31（4 个月暖机 + 4 年绩效）
- 已缓存：5 个标的全部已存 `data/raw/crypto/*_1d.parquet`，每个 1583 bars
- 数据质量：5 个标的 2020-09 起 binance 上 USDT spot 流动性充足，无明显断档

## V2 vs V1 关键参数差异

| 参数 | V1 (A 股) | V2 (crypto) | 原因 |
|---|---|---|---|
| 初始资金 | 100,000 RMB | 100,000 USDT | 量级相当 |
| 现金代理 | 511990 (~2% APY) | USDT (无利息) | crypto 无被动 carry |
| fees | 5 bp | 10 bp | 现实 binance 0.1% 现货费 |
| slippage | 5 bp | 10 bp | crypto 大额订单滑点高 |
| 年化天数 | 252 | 365 | 24/7 vs 工作日 |
| rebalance_period | 20 (月度) | 20 (与 V1 同) | 保持横向可比 |

## 策略配置
- 等权机制：5 标的目标权重各 1/5 = 0.20
- 月度再平衡：每 20 个交易日（这里"交易日"= crypto 1 天，约 4 周一次）
- 满仓 risky，零现金缓冲
- vbt: `Portfolio.from_orders(close, size=weights_df, size_type="targetpercent",
  group_by=True, cash_sharing=True)`

## 踩过的坑

1. **CryptoLoader 缓存覆盖**：第一次小测试只拉 BTC 12 月数据 → cache 命中后再拉全量被截断。修复：用 `loader = get_loader('crypto', refresh=True)` 重拉一次 BTC，覆盖部分缓存。
2. **Matplotlib 中文字体警告**：`Glyph missing` warning 但图正常输出。后续可以改用英文标题或安装中文字体。
3. **年化天数差异**：V1 用 252，V2 用 365。`compute_perf_metrics()` 默认是 252，所以 V2-S1 没用 `sweep.compute_perf_metrics`，自己写了 `calc_crypto_metrics`。**未来 V2 全套都需要这个适配**。

## 与 V1 代码的接口契约

V2-S1 完全用 V1 既有代码：
- `EqualRebalanceStrategy.run()` 不做任何 crypto 特殊处理
- `vbt.Portfolio.from_orders` 在 1583 bars × 5 symbols 输入下正常工作
- `Universe.load_panel()` 是 V1 引入的工具，对 crypto market 同样有效
- 无任何 V2 专属代码改动

**这是 V1 工具普适性的最佳证据**：从 A 股 ETF 迁移到 crypto 0 代码改动。
