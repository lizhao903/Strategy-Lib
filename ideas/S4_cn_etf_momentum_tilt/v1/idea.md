---
slug: cn_etf_momentum_tilt
title: A股 ETF 等权 + 动量倾斜
market: cn_etf
status: implementing
created: 2026-05-08
updated: 2026-05-08
tags: [momentum, rebalance, tilt, etf, benchmark_suite_v1]
---

# A股 ETF 等权 + 动量倾斜

## 一句话概括
在 6 只 ETF 等权满仓的基础上，按动量得分把权重从 1/N 微幅倾斜到强势资产。

## 核心逻辑（What）
1. 标的池固定为 Benchmark Suite V1 共享的 6 只风险 ETF（沪深300/中证500/创业板/中证1000/证券/医疗），起点权重均为 1/6。
2. 每个再平衡日（默认每 20 个交易日）计算各标的的动量得分（`MomentumReturn(lookback=20)`，可叠加 `MomentumReturn(lookback=60)`）。
3. 把动量得分横截面 z-score 化，按 **z-score linear tilt** 公式生成目标权重：`w_i = 1/N + α * z_i / N`。
4. 应用上下限：`w_i ∈ [0.05, 0.40]`，再归一化使 `sum(w) == 1`。
5. 仍然 100% 满仓、无现金缓冲，Rebalance 周期与 S3 默认一致。

## 假设与依据（Why）
- A股板块指数中期存在动量延续（典型半年度反转之外的 1–3 个月窗口）。Asness 等的截面动量、ETF 动量轮动文献有支持。
- 倾斜而不是「全仓 top-K」的好处：在 6 只池子里用 top-N 噪音太大、换手太高；轻倾斜既保留分散，又不至于完全无视截面信息。
- 上下限保证最坏情况下任一资产权重不会过度集中（≤40%）或被清仓（≥5%），避免单点风险。

## 标的与周期
- 市场：A股 ETF (`market: cn_etf`)
- 标的池：`510300, 510500, 159915, 512100, 512880, 512170`
- 频率：日线（`1d`）
- 数据起止：2020-01-01 ~ 2024-12-31

## 信号定义
- 入场：每个 rebalance 日重置目标权重（来自动量倾斜）
- 出场：无显式止损，下次 rebalance 重新计算
- 仓位/权重：`w_i = clip(1/N + α * z(mom_i)/N, 0.05, 0.40)`，归一化；α 默认 1.0
- 止盈止损（如有）：无

## 涉及因子
- [x] 现有因子可表达：`MomentumReturn(lookback=20)`，可选叠加 `MomentumReturn(lookback=60)`（等权融合 z-score）
- [ ] 需要新增因子：暂无

## 预期表现（事前估计）
- 年化收益区间：略优于 S3 等权基线（+0% ~ +3% CAGR），主要在动量明显的年份（2020/2021）受益
- 期望 Sharpe：与 S3 接近或略高（0.5 ~ 0.8 区间，与 A股 ETF 池历史一致）
- 最大回撤容忍：与 S3 类似（35% ~ 45%），熊市没有现金缓冲
- 换手率粗估：年化 ~150% ~ 250%（rebalance=20，倾斜幅度温和）

## 风险与已知坑
- A股板块在熊市集体下跌时动量倾斜没用（甚至反向，如 2022 上半年）
- α 太大 → 接近 top-K，noise 主导；α 太小 → 退化为等权
- 动量 lookback 选择过拟合风险高；先固定 20 日，notes 中讨论 60 日叠加
- 与 S3 共享同一标的池，差异只来自倾斜，绩效差异可能很小

## 验证计划
1. 拉取数据范围：2020-01-01 ~ 2024-12-31，6 只 ETF + 基准 510300
2. IC / 分组：在该 6 资产小池子里 IC 意义有限，重点看「与 S3 等权的超额、信息比率、跟踪误差」
3. 走样本外的方式：暂用 2020-2022 做内样本调 α，2023-2024 做样本外（v1 先报全样本）

## 与现有策略的关系
- 派生自 Strategy 3（`cn_etf_equal_rebalance`）。继承其 `EqualRebalanceStrategy` 类，仅覆盖 `target_weights`。
- 与 Strategy 5（`cn_etf_trend_tilt`）平行：两者都是 S3 的倾斜变体，Strategy 5 用趋势强度（MA/ADX），本策略用横截面动量。
- 相关 slug：`cn_etf_equal_rebalance`、`cn_etf_trend_tilt`
