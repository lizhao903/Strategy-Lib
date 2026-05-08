---
slug: crypto_btc_ma_filter
title: V2-S2 · Crypto BTC 大盘 MA 过滤（risky pool ON/OFF）
market: crypto
status: idea
created: 2026-05-08
updated: 2026-05-08
tags: [crypto, ma-filter, timing, defensive, v2-suite]
---

# V2-S2 · Crypto BTC 大盘 MA 过滤

## 一句话概括
V1 的 S7v2 二元 ON/OFF 大盘 MA 过滤套到 crypto——用 BTC 200日 MA 决定 5/10 池 ON 或全仓 USDT，2022 年熊市要么避险（-71% → 接近 0），要么时机滞后吃下大半下跌。

## 为什么单独做 dedicated 验证

V2 sweep（2026-05-08）显示 S7v2 在 crypto 全失败：
```
KeyError: 'panel 缺少 symbol: USDT'
```

**根因**：策略要求 panel 包含 cash_symbol=USDT，但 USDT 是稳定币不能 ccxt 加载。**已修**：CryptoLoader 在 load `USDT/USDC/BUSD/DAI/FDUSD` 时自动合成 close=1.0 的 const OHLCV，对齐主标的索引。

修通后值得做 dedicated 是因为：
- crypto 趋势比 A 股久（BTC 牛熊明显），200MA 信号可能有效
- 2022 -65% BTC + V2-S1 -71% 单年回撤是 V2 baseline 最大风险敞口
- 如果 MA filter 能砍掉 2022 一半回撤，即使 CAGR 略输 V2-S1 也能在 risk-eff 上胜出

## 核心逻辑（What）

完全复用 `MarketMAFilterV2Strategy`（V1 已实现），无新代码：

1. **信号资产**：BTC/USDT（universe.benchmark）
2. **过滤规则**：close > 200日MA → ON；close ≤ MA → OFF；连续 lag_days=1 日确认（V1 v2 默认）
3. **ON 仓位**：risky pool 等权（CRYPTO_TOP_5 各 20%）
4. **OFF 仓位**：100% USDT（无利息）
5. **执行**：信号 t 日生成，t+1 日开盘成交（vbt close+shift(1) 防 lookahead）
6. **再平衡**：信号变化时切换；ON 期间无再平衡（与 V1 S7 一致）

## 假设与依据（Why）

**核心假设**：crypto 的长趋势 + 大波动让"close vs MA"这一极简 timing 信号在 crypto 比在 A 股更有效。

**为什么 200MA 在 crypto 可能 work**：
- BTC 周期长：2018-2020 熊市 ~2 年，2021-2022 熊市 ~1 年——200 日 MA 能跟上
- crypto 单边性强：进入熊市后 6+ 个月连跌（vs A 股震荡居多），MA 退出后能避免持续下跌
- 没有 A 股的"政策闪崩"（瞬时 -10% 单日），MA 信号不会被尖峰假触发

**为什么 lag_days=1**：
- V1 S7v1→v2 的 sensitivity 已证 lag=1 是最佳，更高滞后反而损害收益
- crypto 24/7 + 高 vol 让"连续 N 日确认"窗口被快速跳变击穿；信号简洁更稳

**为什么 ma_length 默认 200 而非 50**：
- V1 S7 默认 200，已知有效
- 50 日 MA 在 crypto 高波动下会大量假信号（一周可能切 2 次）
- 但需要做 sensitivity sweep [50, 100, 200] 印证

## 标的与周期

- 市场：crypto（CCXT → Binance spot）
- 主测池：CRYPTO_TOP_5（risky pool）+ BTC/USDT（signal）
- 副测：CRYPTO_TOP_10（看更大池能否补 alpha）
- cash 代理：USDT（CryptoLoader 合成 const 1.0；无利息）
- 频率：日线（1d）
- 数据范围：2021-01-01 ~ 2024-12-31（与 V2-S1 / V2-S4 同窗口）
- 暖机：200 日（与 ma_length 对齐）

## 信号定义

- **入场（ON）**：BTC close > MA200 → risky pool 等权满仓
- **离场（OFF）**：BTC close ≤ MA200 → 100% USDT
- **lag**：信号 t 日生成 → t+1 日开盘成交
- **lag_days**：1（无连续天数过滤）
- **止盈止损**：无（仅靠 MA filter ON/OFF）

## 涉及因子

- 无新因子。MA200 计算直接在 strategy 内 `signal_close.rolling(200).mean()`

## 预期表现（事前估计）

| 指标 | 范围 | 依据 |
|---|---:|---|
| CAGR | +50% ~ +90% | 比 V2-S1 (+118%) 低，因 2021 牛市后期 BTC < MA 会过早离场；但比 BTC BH (+34%) 高 |
| Sharpe | 1.0 ~ 1.4 | 比 V2-S1 (1.41) 略低或持平 |
| MaxDD | **-30% ~ -45%** | **关键预期**：MA filter 兑现，2022 大半时间 OFF → 回撤砍半 |
| 2022 单年 | -10% ~ -35% | vs V2-S1 -71%；这是核心 alpha 来源 |
| ON 时长占比 | 60% ~ 75% | 4 年大约 1y OFF |

## 风险与已知坑

**1. MA 滞后**：
- 200 日 MA 反应慢；2022-04 BTC 已跌破 MA 时实际已从顶部下来 ~30%
- mitigation：测 [50, 100, 200] 看哪个最优；大概率 100 是 sweet spot

**2. 假信号 / 频繁切换**：
- 2023-01 ~ 2023-07 BTC 在 MA 上下震荡可能多次切换
- mitigation：观察 switch_dates 分布；> 20 次/年说明信号噪声大

**3. ON 期间满仓 5 池 vs 仅 BTC**：
- weight_mode="equal" 默认让 risky pool 等权
- 但 OFF 期间只看 BTC——产生"信号源 vs 持仓资产"不对称
- 这是 V1 S7 的设计（风险代理 = 池 / 信号代理 = 单标的），保持一致便于比较
- 必要时测 weight_mode="signal_only"（仅持 BTC）做 ablation

**4. 工程问题（已修）**：
- CryptoLoader 现支持 USDT/USDC/BUSD/DAI/FDUSD 合成 const-1 OHLCV
- 验证：`s7v2_market_ma_filter(CRYPTO_TOP_5)` smoke 测试已通过

**5. cash 无利息**：
- USDT 持有 0 carry（V1 在 A 股是 511990 ~2% APY）
- 这意味着 OFF 期间纯防御，无 carry alpha
- mitigation：在 conclusion 中明确 OFF 期机会成本 = 该时间窗 USDT BH 收益（即 0）

## 验证计划

1. **主回测**（CRYPTO_TOP_5, MA200, lag=1, equal）
2. **MA length sweep** [50, 100, 200]（核心：找 crypto 的最优 MA）
3. **池 ablation**：CRYPTO_TOP_5 vs CRYPTO_TOP_10 risky pool
4. **weight_mode ablation**: equal vs signal_only（仅持 BTC）
5. **ON/OFF 时间分布**：每年 ON 天数 / OFF 天数（要看 2022 是否大半 OFF）
6. **2022 单年回撤** vs V2-S1：核心 alpha 度量
7. **跨市场对比**：与 V1 S7v2 在 A 股 11 池上的表现对比 risk-eff

## 与现有策略的关系

- **代码层面**：完全复用 `MarketMAFilterV2Strategy`（V1 已实现）；CryptoLoader 修了 USDT 合成路径（影响所有 crypto 策略）
- **概念层面**：V2 的 timing 类策略，对照 V2-S1 等权 baseline 看 timing 价值
- **后续派生**：
  - 如果有效：可加 vol-target overlay（参考 V1 S5v2）
  - 如果失效：仍是有用 baseline，证明 crypto 无新 alpha 来源
  - V2-S3 (trend_tilt) 是更细粒度的 timing 类策略

## 待启动 checklist

- [x] 修 CryptoLoader USDT 合成（影响所有 V2 sweep）
- [x] smoke 测试 `s7v2_market_ma_filter(CRYPTO_TOP_5).run(panel)` 跑通
- [ ] 写 dedicated `validate.py`（参考 S10）
- [ ] 跑主回测 + MA length sweep + 池 ablation + weight_mode ablation
- [ ] 写 implementation/validation/conclusion
- [ ] 在 README 索引追加
