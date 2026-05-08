---
slug: crypto_momentum_tilt
title: V2-S4 · Crypto 横截面动量倾斜（dedicated）
market: crypto
status: idea
created: 2026-05-08
updated: 2026-05-08
tags: [crypto, momentum, cross-sectional, v2-suite, vol-adjusted]
---

# V2-S4 · Crypto 横截面动量倾斜（dedicated 验证）

## 一句话概括
把 V1 的 `MomentumTiltV2Strategy`（S4v2，z-score + linear tilt + clip + normalize）原样套到 crypto TOP_5 / TOP_10，跑出比 V2-S1 等权更高的 NAV / Sharpe—— **与 V1 在 A 股 ETF 上 8 次实验全部 IR 为负的结论完全相反**。

## 为什么单独做 dedicated 验证

V2 sweep（2026-05-08，`results/v2_crypto_sweep_20260508_162436.csv`）显示：

| 池 | S3 等权 NAV | S4v2 momentum NAV | momentum 增量 |
|---|---:|---:|---:|
| crypto_top_5 | 2.28M | **3.14M** | +37.5% |
| crypto_top_10 | 2.27M | **3.80M** | +67.5% |
| crypto_top_5_no_sol | 1.13M | 1.08M | -4.7% |

- top_5 / top_10：**momentum 显著正向**（Sharpe 1.51 / 1.42 都打爆 V2-S1 的 1.41）
- no_sol：去 SOL 后 momentum 失去优势（基本与等权打平）—— 强烈暗示 momentum 在 crypto 的 alpha 主要来自「能识别并加仓快速崛起标的」
- btc_eth_2 / top_3：sweep 报 ValueError（w_min*N 与归一化和=1 矛盾）—— **工程问题，已修**

V1 工具直接复用 + 跨市场结论翻转，值得做完整 dedicated 验证。

## 核心逻辑（What）

完全复用 `MomentumTiltV2Strategy`（V1 已实现），无新代码。机制：

1. **横截面动量信号**：每个 symbol 在 rebalance 日的 `lookback - skip` 日累计收益（默认 lookback=120, skip=5）
2. **横截面 z-score**：把 N 个 symbol 的 raw 动量 z-score 化（均值 0，标准差 1）
3. **线性倾斜**：`raw_w = 1/N + alpha * z / N`（默认 alpha=1.0）
4. **clip + normalize**：`[w_min, w_max]` 边界裁剪 + iterative water-filling 归一化到和=1
5. **shift(1)**：信号严格使用 `index < date` 的数据，杜绝 same-bar lookahead
6. **再平衡**：每 `rebalance_period=20` 个交易日（≈月度，与 V1 / V2-S1 同口径）

## 假设与依据（Why）

**核心假设**：crypto 的「单标的 100x outlier 频繁 + 长趋势 + 高横截面分散度」三重特性使 momentum 在这里有效，与 A 股 ETF 「6 池高同质 + 短期反转主导」相反。

**为什么 momentum 在 crypto 可能 work**：
- crypto 内部仍有显著横截面分散：2021 SOL +12000%，BTC 仅 +60%；2024 SOL/XRP 强于 ETH。z-score 信息密度足。
- crypto 趋势比 A 股久：一个标的进入"顶 quintile"后通常持续数月而非数周。120 日 lookback 能捕捉。
- 没有涨跌停、T+1、监管政策跳变这些 A 股短期反转主导因素。

**为什么 NO_SOL 下失效（事前推测）**：去 SOL 后 5 池 → 4 池，失去 100x outlier，动量信号的 cross-sectional 方差大幅缩水，z-score 接近随机。这与 V1 6 池 A 股 ETF 失效是同一机制（横截面方差不足）。

## 标的与周期

- 市场：crypto（CCXT → Binance spot）
- 主测池：CRYPTO_TOP_5（BTC/ETH/SOL/BNB/XRP）—— 与 V2-S1 完全一致便于直接对比
- 副测：CRYPTO_TOP_10（加 DOGE/ADA/AVAX/LINK/DOT）+ CRYPTO_TOP_5_NO_SOL（ablation）
- cash 代理：USDT（不参与 momentum 倾斜，仅记账）
- 频率：日线（1d）
- 数据范围：2021-01-01 ~ 2024-12-31（4 年；与 V2-S1 同窗口）
- 暖机：120 日（与 lookback 对齐）

## 信号定义

- **入场**：首根 rebalance bar 按动量 z-score 倾斜后的目标权重一次性配齐
- **调仓**：每 20 日按当下 z-score 重算 target_weights，再平衡
- **仓位**：100% 满仓 risky pool（与 V2-S1 一致），USDT 始终 0
- **止盈止损**：无（动量 tilt 自动通过 z-score 反转切换权重）

## 涉及因子

- [x] 现有：`MomentumReturn`（lookback=120, skip=5）
- [x] 现有：`VolAdjustedMomentum`（vol_lookback=60，对应 signal="vol_adj"）
- [ ] 不需新增

## 预期表现（事前估计）

基于 sweep 已知结果（见上表）和 V2-S1 数据：

| 指标 | 范围 | 依据 |
|---|---:|---|
| CAGR (TOP_5) | +130% ~ +145% | sweep 显示 NAV 3.14M（4y） → CAGR ~136% |
| Sharpe (TOP_5) | 1.45 ~ 1.55 | sweep 1.51 |
| MaxDD (TOP_5) | -75% ~ -80% | sweep -77% |
| vs BTC BH alpha/yr | +95 ~ +110 pct | BTC 4y CAGR ~+62%，本策略 ~+136% |
| vs V2-S1 增量 alpha | +15 ~ +20 pct | V2-S1 +118% vs 本策略 ~+136%，差 ~18pct |

## 风险与已知坑

**1. SOL 单点依赖**（核心风险）：
- TOP_5 NAV 3.14M 中估计 50%+ 来自 momentum 在 2021Q1-Q2 抓住 SOL 暴涨
- NO_SOL ablation: NAV 1.08M（vs V2-S1 NO_SOL 1.13M）—— 实际 momentum 不仅没增强，反而**轻微负向**
- 解读：crypto momentum 不是"普遍有效"，而是"有 outlier 才有效"。OOS 极脆弱
- 必须把这一现象在 conclusion 写清楚

**2. 高换手 + 高交易成本**：
- 月度 + z-score 倾斜 + 5 标的 → 实际换手是 V2-S1 的 1.5-2x
- 在 V2 共享基线 fees=10bp + slippage=10bp 下，换手成本可能吃掉 5-8 pct/yr alpha
- 必须算 cost-adjusted alpha；事前估计 net alpha ≈ +12-15 pct vs V2-S1（不是 +18）

**3. 参数过拟合风险**：
- lookback=120 与 V1 默认相同（也是 V1 失败的版本），当前看起来好可能是 in-sample 好运
- 必须做 lookback sweep [60, 120, 240]；如果 60 也强，证明不是过拟合；只有 120 强 → 红旗
- secondary_lookback 不在本验证范围（保持 V1 默认 None）

**4. 工程坑（已修）**：
- `w_min*N` 与归一化和=1 在 N<5 池矛盾 → 已加自动放宽逻辑（构造时按 N 拉宽 w_max）
- 不影响 N=11 行为

**5. 与 V1 完全相反结论的解读**：
- V1 在 6 池 A 股 ETF 上 8 次实验全部 IR<0 → 结论"momentum 在小池高同质化资产上失效"
- V2-S4 在 5 池 crypto 上 IR>0 → 不矛盾：池子结构（横截面方差）才是决定因素
- 这与 V1 总结的「池子 >> 信号 >> 仓位」一致：信号能 work 与否取决于池子是否给出足够信息

## 验证计划

1. **主回测**（CRYPTO_TOP_5，默认参数 lookback=120 skip=5 alpha=1.0 signal=raw）
2. **lookback sweep** [60, 120, 240]：验证不是单点过拟合
3. **signal sweep** [raw, vol_adj]：验证 vol-adjust 是否带来稳定性提升
4. **池 ablation**：TOP_5 / TOP_10 / TOP_5_NO_SOL 三档（**核心**——验证 SOL 依赖）
5. **alpha 归因**：把 momentum vs V2-S1 等权增量 alpha 拆成「池子贡献」「信号贡献」
6. **分年度收益**：尤其看 2022 熊市里 momentum 是否兑现"动量退出"（应 NOT 兑现，因为不是 timing 策略）
7. **换手 / 成本**：测 fees+slippage=10/10/20bp 下 cost-adjusted alpha
8. **与 V1 S4v2** 跨市场对比表：同一个机制 + 11 池 A 股 vs 5 池 crypto

## 与现有策略的关系

- **代码层面**：完全复用 `MomentumTiltV2Strategy`（V1 已实现），仅修了「小 N 池边界自动放宽」的工程坑
- **概念层面**：V2 第二个 dedicated（继 V2-S1 后）；测试 V1 的"复杂版本一定输给等权"在 crypto 是否仍成立
- **后续派生**：
  - 如果 OOS 兑现：V2-S6 加 vol_target overlay，把 -78% MaxDD 砍到 -50%
  - 如果 SOL 单点过强：V2-S4b "过滤极端 outlier"版本（top z-score 强制 cap）

## 待启动 checklist

- [x] 修 `MomentumTiltV2Strategy` 小 N 池边界自动放宽
- [ ] 写 dedicated `validate.py`（参考 S9 模板）
- [ ] 跑主回测 + 3 组 ablation + lookback sweep
- [ ] 写 implementation/validation/conclusion
- [ ] 在 summaries/README.md 索引中追加一行
