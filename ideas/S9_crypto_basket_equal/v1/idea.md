---
slug: crypto_basket_equal
title: V2-S1 · Crypto 头部 5 只等权 + 月度再平衡
market: crypto
status: idea
created: 2026-05-08
updated: 2026-05-08
tags: [crypto, equal-weight, v2-suite, baseline]
---

# V2-S1 · Crypto 头部 5 只等权 + 月度再平衡

## 一句话概括
V1 的 S3 等权机制原样套到 5 只头部加密货币，作为 Crypto V2 Suite 的 baseline。

## 核心逻辑（What）
- **risky pool（5 只）**：BTC/USDT、ETH/USDT、SOL/USDT、BNB/USDT、XRP/USDT（CRYPTO_TOP_5 universe）
- **再平衡**：月度（rebalance_period=20 个交易日；crypto 24/7 但保持与 V1 同口径，每 20 日重平）
- **现金代理**：USDT（无利息，相当于 V1 的 511990 但 carry=0）
- **基准**：BTC/USDT buy-and-hold（crypto 默认）
- **代码**：复用 `EqualRebalanceStrategy`（同 V1 S3）；factory `s3_equal_rebalance(CRYPTO_TOP_5)` 一行启动

## 假设与依据（Why）
**核心假设**：V1 揭示的「池子 >> 信号 >> 仓位」+「等权 + 月度再平衡是简单胜出」如果是普适规律，那么在 crypto 上应该再次胜过其他复杂策略。

**为什么先做 baseline 而不是直接做 trend/momentum**：
- V1 S4/S5/S7 等复杂版本最终都被 S3 11 池 / S3 overseas_4 这些"简版"打爆
- crypto 常识告诉我们「BTC + ETH 是 90% 收益」，但常识也告诉我们「crypto 趋势超强、应当用 timing」
- 必须先建立 baseline 数据，后续 V2-S2/V2-S3 的"复杂版本"才有 alpha 度量基准

**为什么选 TOP_5 而不是 TOP_10**：
- TOP_10 的 DOGE/ADA/AVAX/LINK/DOT 中部分 2021 年下半年才上 binance，回测窗口 < 主测期
- TOP_5 全部 2020 年前已经流动性充足，能完整覆盖 2021-2024 4 年回测
- TOP_3 (BTC/ETH/SOL) 太集中，5 只更像"crypto bluechip basket"

## 标的与周期
- 市场：crypto（CCXT → Binance spot）
- 标的池：BTC/USDT, ETH/USDT, SOL/USDT, BNB/USDT, XRP/USDT
- cash 代理：USDT（处理：每日价格 = 1.0，无变动）
- 频率：日线（1d）—— 与 V1 同口径
- 数据范围：2021-01-01 ~ 2024-12-31（4 年；起点选 2021 是为了 SOL 流动性充足）
- 暖机：120 日（与 V1 S3 一致）

## 信号定义
- 入场：初始等权买入 5 只（各 20%）
- 调仓：每 20 日（约月度）再平衡回等权
- 仓位：100% 满仓 risky，0% USDT
- 止盈止损：无（被动等权再平衡 = 自动卖盈买亏）

## 涉及因子
- [x] 现有：无因子；纯等权机制
- [ ] 不需新增

## 预期表现（事前估计，基于 crypto 历史经验）

| 指标 | 范围 | 依据 |
|---|---:|---|
| CAGR | +30% ~ +60% | BTC 2021-2024 CAGR ~+5%，ETH ~+10%，SOL ~+50%；等权 + 月度再平衡可能 +30-40% |
| Sharpe | 0.6 ~ 1.0 | crypto 高波动稀释 sharpe；预期低于 V1 S8 (0.85)|
| MaxDD | -50% ~ -65% | 2022 年 LUNA / FTX / Terra 熔断期 BTC -75%、ETH -82%；等权多元化能稍缓和但仍深 |
| 年化波动 | 60% ~ 80% | 与 V1 14% 完全不同量级 |

## 风险与已知坑

**1. 数据陷阱**：
- 2021 年初 SOL/USDT 在 Binance 流动性可能不足；BNB 受平台事件影响
- USDT 在 2022 LUNA 危机中短暂脱钩 ~5%（理论上无影响但要注意）
- mitigant: 检查每个标的最早交易日，必要时缩短回测起点到 2021-04 或 2021-06

**2. 24/7 vs A 股的 vbt 适配**：
- vbt.Portfolio.from_orders 默认假设交易日历，crypto 数据无周末停牌
- `freq="1D"` 在 V1 用 252 假设，在 crypto 应该用 365
- mitigant: 在 V2 启动时单独验证一次 vbt freq 参数

**3. 交易成本量级**：
- V1 默认 fees=5bp + slippage=5bp = 10bp 总
- crypto 实际 spot 成交 5-15bp（大额订单滑点更大）
- 建议 V2 baseline: fees=10bp + slippage=10bp = 20bp 总
- mitigant: 在 implementation 中说明并加敏感性测试

**4. 样本期短 + 包含异常事件**：
- 2021 = LUNA 牛市顶部 / SOL 暴涨 / NFT 泡沫
- 2022 = LUNA 崩盘 / 3AC 倒闭 / FTX 跑路
- 2023 = "crypto 寒冬" + 美国监管打压
- 2024 = ETF 通过 + BTC 新高
- 4 年覆盖了 crypto 一整个完整周期，但样本量仍小

**5. 基准选择**：
- BTC/USDT BH 是默认基准但 single asset
- 或考虑 1/N 等权 5 只（S9 自身），但这会让 S9 vs benchmark 永远 = 0
- 建议 BTC BH + S9 自身做"两个基准"

## 验证计划

1. 拉取数据范围：BTC/USDT, ETH/USDT, SOL/USDT, BNB/USDT, XRP/USDT 的 2020-09-01 ~ 2024-12-31 1d 数据（120 日暖机 + 4 年绩效）
2. 确认数据质量：检查每个标的最早可用日；如有断档需要选择处理方式
3. 跑 v1 默认（rebalance=20，等权 5 池）
4. 与 BTC BH 详细对比：超额、信息比率、跟踪误差
5. 分年度收益（2021/2022/2023/2024）—— 重点看 2022 熊市里 5 池 vs 单 BTC 的差异
6. 与 V1 S8 (cn_etf_overseas_equal) 横向比较：同一个机制（S3 等权）在两个市场上的 Sharpe / MaxDD 对比
7. 在 V2 sweep 中对比 4 个 crypto universe（BTC_ETH_2 / TOP_3 / TOP_5 / TOP_10）

## 与现有策略的关系

- **代码层面**：完全复用 `EqualRebalanceStrategy`（V1 S3 同款），无新代码
- **概念层面**：V2 的 baseline，类似 V1 中 S3 的角色
- **后续派生**（V2 完整 roadmap）：
  - V2-S2 = `crypto_dca_basic`（V1 S1 同款，月度→周度 DCA + USDT）
  - V2-S3 = `crypto_btc_ma_filter`（V1 S7 同款 + BTC 200 日 MA 信号）
  - V2-S4 = `crypto_trend_tilt`（V1 S5v2 同款 + 连续 trend）
  - V2-S5 = `crypto_momentum_tilt`（V1 S4v2 同款 + 横截面动量）
- 完整 roadmap 见 `docs/benchmark_suite_v2_crypto.md`

## 待启动 checklist
- [ ] 先确认 CryptoLoader 拉数据通畅（一次最小测试）
- [ ] 预拉 5 标的 + 基准 1d 数据到 `data/raw/crypto/`
- [ ] 启动专门的 validate.py 跑首次回测（按 V2 共享基线）
- [ ] 写 implementation/validation/conclusion.md
- [ ] 把 V2-S1 数据加进 V1 S8 的横向对比表（同一个 S3 机制在不同市场的可迁移性）
