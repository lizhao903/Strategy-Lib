---
slug: cn_etf_market_ma_filter_v2
title: 大盘 MA 过滤 v2 — lag=1 + 11 跨资产池
market: cn_etf
status: implementing
created: 2026-05-08
updated: 2026-05-08
tags: [trend, timing, market-ma, multi-asset]
---

# 大盘 MA 过滤 v2 — lag=1 + 11 跨资产池

## 一句话概括
把 v1 sensitivity sweep 已验证的"真最佳配置"变成默认 ship 版本。

## 核心逻辑（What）
- 信号：510300 收盘 vs 200 日 MA（与 v1 同）
- **滞后过滤：lag=1（无滞后）**——v1 默认是 lag=2
- 切换在次日开盘（shift(1) 防 lookahead，与 v1 同）
- **risky pool：11 跨资产 ETF 等权 1/11**——v1 默认是 6 池
- cash pool: 511990

## 假设与依据（Why）
v1 sensitivity sweep 给出两个反直觉但稳健的结论：

1. **lag 单调反向**：lag=1 (NAV 119.1k) > lag=2 (108.1k) > lag=3 (99.1k) > lag=5 (90.8k)
   - 事前直觉「加层过滤减少假突破噪音」**完全错误**
   - 真实数据：A 股快速下跌中，每延迟 1 天就少接收一波避险机会
   - 4 档 lag 的 2022 单年都 ≈0%，所以避险结果是 MA 信号的稳健属性，不是 lag 调出来的；但收益侧 lag 越大越亏

2. **11 池 = 真 alpha 来源**（继承 S4v2 ablation）：S4v2 总 +5.73%/yr 中 73% 来自扩池
   - S7 v1 的 risk-on 持仓是 6 池，v2 直接换 11 池

把这两条结论组合，假设 v2 能同时获得：
- v1 lag=1 的 timing alpha（vs S3 +1.34%/yr）
- 扩池的 baseline alpha（继承 S4v2 +4%/yr 的 73%）

**预期 v2 vs S3 alpha ≥ +3%/yr**（如果两条 alpha 简单相加），更现实预期 +2%/yr。

## 标的与周期
- 市场：A 股 ETF
- risky pool：11 只跨资产 ETF（同 S4v2）
- 信号：510300（不在 risky pool 里也行；这里包含）
- cash：511990
- 频率：日线
- 数据范围：2019-07-01 ~ 2024-12-31（含 200MA 暖机）

## 信号定义
- 入场：510300 close > 200MA（连续 1 日，即即时）→ 11 池等权 1/11
- 出场：510300 close ≤ 200MA → 511990 100%
- 仓位：二元 ON/OFF，无中间档

## 涉及因子
- [x] 现有：无新因子；纯 MA 信号
- [ ] 不需新增

## 预期表现（事前）
- 年化收益：CAGR +5% ~ +8%（11 池基线 +5% + lag=1 timing ~+1%）
- Sharpe：0.40 ~ 0.55
- 最大回撤：-20% ~ -28%（lag=1 v1 已是 -27.3%，11 池可能略浅或不变）
- 换手率：~30 次切换 / 5 年（与 lag=1 v1 同，仅持仓资产变化）

## 风险与已知坑
1. **池差异不抵扣 timing 缺陷**：如果 11 池在 2024 单边市的"被错过"代价比 6 池更大（因为含国债/黄金 reblance 拖累），v2 可能反而不如 v1 lag=1 6 池
2. **过拟合担忧**：lag=1 在 v1 sweep 里"碰巧最佳"，可能仅是 5y 样本特性。需要 OOS 验证（2025+）
3. **国债 ETF 在 ON 时段贡献负 alpha**：511260 在 2020-2024 几乎平稳，等权 1/11 占用 ~9% 拖累

## 验证计划
1. 跑默认参数（lag=1, 11 池）的 5 年回测
2. **核心 ablation**：v1 lag=1 6 池 vs v2 lag=1 11 池 —— 量化扩池真贡献多少
3. 对比基准：S3 v1 / S4v2 / S5v2 / S7 v1 lag=2 / BH 510300
4. 关键指标：CAGR、Sharpe、MaxDD、2022 单年、2024 单年（11 池在牛市是否还赶得上？）
5. 确认 lag 趋势在 11 池上仍然成立（lag=1 优于 lag=2）

## 与现有策略的关系
- 是 S7 v1 lag=1 sweep 的 ship 版本
- 持仓池来自 S4v2 的 11-asset universe
- 与 S5v2 对比：S5v2 用连续 vol-target sizing 做 sizing-based 避险；v2 用单一信号做 timing-based 避险。两者机制不同，可能互补
