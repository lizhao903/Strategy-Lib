---
slug: cn_etf_trend_tilt_v2
title: A股 ETF 等权 + 趋势倾斜（连续现金 + 波动率过滤 + 债券暴露）
market: cn_etf
status: implementing
created: 2026-05-08
updated: 2026-05-08
parent: cn_etf_trend_tilt (v1)
tags: [benchmark, rebalance, trend, allocation, time-series-momentum, vol-target, defensive]
---

# A股 ETF 等权 + 趋势倾斜 v2

## 一句话概括
在 v1 的趋势倾斜框架上**解决两个明确问题**——把现金占比从「双峰二值」改成「随趋势强度连续变化」，加一层「池中超过半数 ETF 高波时强制降仓」的避险闸门，并用十年国债 ETF 替代部分现金，让避险时段不仅是空仓而是实际有正收益的 carry。

## 与 v1 的关键差异（核心）

| 维度 | v1 | v2 |
|---|---|---|
| 权重归一化 | `weight_i = max(score_i, 0) / Σ_j max(score_j, 0)` | `weight_i = clip((score_i - cutoff) / score_full, 0, 1) / N`（**不归一化**） |
| 权重和 | 总是 0 或 1（bimodal） | ∈ [0, 1] 连续 |
| 现金缓冲 | 二值（要么 0% 要么 100%） | 连续——与 trend 强度成反比 |
| 趋势分数 | `sign(close>MA20) + sign(MA20>MA60) + ...` 离散 ∈ {-3,-1,+1,+3} | `tanh(k·(close/MA - 1))` 连续 ∈ (-1, +1) |
| 波动率过滤 | ❌ 无 | ✅ 池中 ≥ 50% 资产年化波动 > 30% 时全体权重 ×0.5 |
| 现金等价 | 100% 纯现金（年化 ~0%） | 用 511260 十年国债 ETF 替代最多 40% 仓位（年化 ~3-4%） |

## v1 的诊断与 v2 的解药

### 问题 1：现金占比双峰
**v1 现象**：cash_days_ratio = 18.2%，但介于 0% 和 100% 之间的天数 ≈ 0。原因是 `_tilt_weights` 用 `score / Σscore` 归一化，只要任一标的 trend > 0，权重和就 = 1。

**v2 修复**：改用 `score / score_full / N`，**不归一化**。`score_full = 1.0` 是「该资产拿满 1/N 的临界分数」，trend 只要小于 1.0 就拿不满，整体 sum < 1，缺额自动留作现金。
- 当所有 6 只都 score = 1.0：sum = 6·(1/6) = 1.0（满仓）
- 当 3 只 score=1, 3 只 score=0：sum = 3·(1/6) = 0.5（半仓）
- 这样 cash_ratio 在 [0, 1] 上连续分布

### 问题 2：避险命题未兑现
**v1 现象**：cash 与 BH 当日下跌相关性仅 0.033（接近随机），2022 单年 -21.6% 与 BH -21.7% 几乎一致。MA + Donchian 这类经典趋势信号对 A股快速下跌**反应过慢**——A股从顶到底常常 1-2 个月走完，等 MA120 翻空时已经跌了一半。

**v2 修复**：加一层与「趋势方向」**正交**的「整体 regime」闸门——年化波动率。当池中超过 50% 的资产 60 日年化波动 > 30% 时，强制把所有权重 ×0.5。逻辑：高波本身就是风险信号，不依赖趋势翻转的滞后判定。
- A股宽基波动率常态 15-25%，2022 / 2024-09 行情期间 > 30% 是高频出现的事件
- 不要求「波动率预测下跌」，只要求「高波时段降仓」（vol-target portfolio 的核心思路）

### 问题 3（次要）：空仓的 carry 机会成本
v1 全空仓段 220 天，纯现金年化 ≈ 0%。**v2 用 511260 十年国债 ETF**（年化 ~3-4%，与股市低相关）填充现金缺口最多 40%。在 2022 年股市深跌期间，债券通常正收益（duration positive），双倍受益。

## 标的与周期
- 市场：cn_etf
- 风险池：v1 同 6 只 ETF（510300 / 510500 / 159915 / 512100 / 512880 / 512170）
- **新增**：511260 十年国债 ETF（仅作 cash overlay，不参与 trend 排序）
- 频率：日线 1d
- 数据起止：2020-01-01 ~ 2024-12-31（暖机自 2019-07-01）

## 信号定义（v2）
1. 对每只**风险** ETF 计算 `trend_score` ∈ [-2, +2]（与 v1 同口径，但 MA 部分用连续 tanh 版）
2. **连续 ramp 权重**：`raw_i = clip((score_i - 0) / 1.0, 0, 1)`；`weight_i = raw_i / 6`
3. **波动率闸门**：若 `mean(vol_60d > 0.30) ≥ 0.5`，所有 weight_i ×0.5
4. **bond overlay**：`cash_gap = 1 - Σweight_i`；`bond_w = min(cash_gap, 0.4)`
5. **再平衡**：每 20 日一次（与 v1/S3 一致）

## 假设与依据（Why）

### 为什么把权重连续化（而不是单纯调高 cutoff）
v1 的 cutoff 敏感性显示：cutoff 提高反而恶化（CAGR 转负）。这说明**问题不在 cutoff 高低**，而在「分数归一化」的瞬变。即使 score 在 cutoff 附近徘徊，归一化让权重瞬间从 0 跳到 1/N。**v2 的连续 ramp 让权重正比于 score 强度**，避免「弱信号也满仓」和「强信号也只到 1/N」两种过度反应。

### 为什么加波动率过滤（不靠趋势信号本身改进）
v1 复盘的关键发现：**MA/Donchian 对 A股快速下跌识别过慢**。这不是参数问题（用 MA10/30/60 也不会快太多），而是「趋势信号」与「下跌起点」的固有错位。

波动率与趋势是**正交信号**——高波不一定意味着方向，但高波 = 风险预算被消耗。这是经典 vol-target portfolio 的逻辑：当 realized vol 上升，缩减仓位以维持目标波动。在 A股 ETF 上特别有效，因为：
- 牛市顶到熊市底的过渡通常伴随 vol 飙升（VIX-like 行为）
- 2022-04 的疫情底、2024-09 的政策底都先有 vol 显著上升

### 为什么用 511260 十年国债 ETF
- 与股票相关性低（多数时段微负）
- 年化收益 ~3-4%，比 511990 货基（~2%）高
- 2022 年股市深跌时，国债正收益（避险 carry 双重受益）
- 已经在缓存里（无需重新拉数据）

不直接 100% 替代是因为 2024 出现过股债同跌的极端情形，留 60% 留为纯现金（cash_gap - bond_max_weight 的部分）作为安全垫。

### 因子选择
- 沿用：`DonchianPosition(120)` —— v1 已验证有效
- **替换**：`MABullishScore` → `MABullishContinuous(20/60/120, k=20)` —— 把 sign() 离散化改成 tanh 连续化
- **新增**：`AnnualizedVol(60)` —— 60 日年化波动作为 vol filter 输入

新因子写在 `factors/trend.py` 和 `factors/volatility.py` 末尾，**不动 `factors/__init__.py`**（按硬约束）。

## 涉及因子
- 沿用：`DonchianPosition(lookback=120)`
- 新增：`MABullishContinuous(short=20, mid=60, long=120, k=20)` —— 连续 MA 多头排列
- 新增：`AnnualizedVol(lookback=60)` —— 年化已实现波动

## 预期表现（事前估计）
- **CAGR 区间**：2~6%（牛市跟得上 v1，熊市/震荡市靠降仓改善 risk-adjusted return）
- **期望 Sharpe**：0.30~0.45（v1 是 0.28，v2 应通过降低 vol 提升）
- **MaxDD 容忍**：**关键卖点 — 期望 25-35%（v1 -47.8%）**
- **2022 单年**：期望 < -15%（v1 -21.6%）
- **cash_ratio 分布**：std > 0.2，介于 5-95% 的天数 > 50%

## 风险与已知坑

### 1. vol filter 阈值 0.30 可能过严或过松
A股宽基波动率分布：低位 ~12%，常态 18-22%，高位 30-40%。设 30% 既能避开 2022/2024Q3 的极端，又不会在常态期频繁触发。**先用 0.30/0.5/0.5 做主线**，若结果不好再扫描。

### 2. score_full = 1.0 的标定
score 的理论上限 = 2.0（MA 和 Donchian 都打满）。**设 score_full = 1.0** 意味着 score 至少要 ≥ 1.0 才能拿 1/N。这是「有意保守」——常态期权重大约只有 50-70% 满仓（让 cash 自然存在）。score_full = 0.5 会偏激进，2.0 会过保守。**先 1.0 跑主线**。

### 3. 过拟合警惕
v1 的 cutoff 敏感性是反着调（提高反而变差）。v2 引入了 4 个新参数：`score_full / vol_high / vol_breadth_threshold / vol_haircut / bond_max_weight`，加上 v1 已有的 6 个，单次回测的随机度高。**结论的可信度需要看：**
- 主线 vs 关掉 vol filter / 关掉 bond overlay 的消融
- score_full = 0.7/1.0/1.5 三档敏感性
- 真正避险命题：cash↔BH down correlation 应当显著上升

### 4. bond overlay 在股债同跌时反而加大风险
2024 部分时段股债同跌。bond_max_weight = 0.4 限制了最坏情况（即便 bond -10%，组合也只 -4%）。可以接受。

### 5. 暖机期不变
MA120 / Donchian120 / vol60 共享，最长 120 → 暖机仍从 2019-07-01 起。

## 验证计划
1. 数据范围：2020-01-01 ~ 2024-12-31（前 120 日预热）
2. 验证重点（与 v1 对照表）：
   - **cash_ratio 是否真的连续（min/median/max/std + 中间段比例）**
   - **2022 单年 v1 vs v2 vs BH** —— 避险命题的关键
   - **MaxDD 改善幅度** —— 期望从 -47% 改到 -25~30%
   - **Sharpe / CAGR** —— 不能为了避险把 alpha 全损
   - 全空仓/高现金时段与 BH 当日跌相关性 —— 期望 > 0.2（v1 是 0.033）
3. 关键对照：
   - vs v1：是否真改善了避险命题
   - vs S3：超额是否依然存在
   - vs BH：alpha 是否依然 > 0
4. 消融（如时间允许）：
   - 关 vol filter（vol_haircut=1.0），看是否 ramp + bond 单独足够
   - 关 bond overlay（bond_symbol=None），看是否 vol filter 单独足够
   - 极端：score_full=2.0 / 0.5 各跑一次

## 与现有策略的关系
- **直接继承 `TrendTiltStrategy`（v1）**，复用 v1 的 `compute_trend_scores` / `_validate_weights` 框架
- **不改 v1 任何文件**（按硬约束）
- v2 的 idea 卖点：v1 已确认「趋势退出有边际效用」、v2 在此基础上加结构性的避险 + carry，而不是再去优化趋势信号本身（v1 复盘已显示 MA/Donchian 在 A股上识别下跌起点能力有限，靠改参数提升空间不大）

## 注册与下游
- 配置：`configs/S5_cn_etf_trend_tilt_v2.yaml`
- 类：`TrendTiltV2Strategy`（在 `src/strategy_lib/strategies/cn_etf_trend_tilt_v2.py`）
- registry / `__init__.py` 不在本任务范围
