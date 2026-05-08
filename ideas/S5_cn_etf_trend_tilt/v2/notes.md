# Notes — cn_etf_trend_tilt v2

> 持续追加，不要覆盖。每条笔记带日期。

---

## 2026-05-08 v2 设计要点

### 一句话动机
v1 的两个失败点都不是「趋势信号本身不好」，而是「权重映射」和「整体 regime 闸门」缺失。v2 直接改这两点，**保留 v1 的趋势核心**。

### 连续化的数学形式（关键）

v1 的双峰元凶在归一化：
```
v1: weight_i = max(score_i, 0) / Σ_j max(score_j, 0)
```
任意一只 score > 0 → 分母 > 0 → 总和 = 1。

v2 改成：
```
v2: raw_i = clip((score_i - cutoff) / score_full, 0, 1)
    weight_i = raw_i / N        # N = 风险资产数量（不含 bond）
    weights_sum = Σ raw_i / N ∈ [0, 1]
```
关键变化：**不归一化**。`score_full` 是「打满 1/N 所需的临界分数」。

举例（cutoff=0, score_full=1, N=6）：
- 6 只全 score=1.0 → raw=1 → weight=1/6 each → sum=1.0
- 3 只 score=1, 3 只 score=0 → 3 个 1/6 + 3 个 0 → sum=0.5
- 6 只 score=0.5 → raw=0.5 → weight=1/12 each → sum=0.5
- 6 只 score 都 ≤ 0 → 全 0 → sum=0（与 v1 一致）

cash_ratio = 1 - sum 自然成为 score 强度的连续函数。

### 趋势分数为什么也要连续化（次要修改）
v1 的 `MABullishScore` 用 `sign()` 输出 ∈ {-3, -1, +1, +3}，本身就是阶跃。即使在 v2 的连续 ramp 框架下，这个阶跃也会让权重在 score=1 与 score=3 之间瞬变（因为 score_full=1，超过 1 就饱和）。

`MABullishContinuous(k=20)` 的 tanh 形式：
```
score_continuous = mean(tanh(20 * (close/MA - 1)) for MA in [MA20, MA60, MA120])
```
- `close/MA - 1 = 0.0`（贴合）→ tanh(0) = 0
- `close/MA - 1 = +0.05`（高 5%）→ tanh(1) ≈ 0.76
- `close/MA - 1 = +0.20`（高 20%）→ tanh(4) ≈ 0.999（近饱和）

k=20 的选择：让「高于均线 5%」对应中等强度信号（0.76），符合 A股 ETF 的典型偏离量级。k 太小（如 5）会让信号迟钝；k 太大（如 100）退化回 sign()。

### 波动率过滤的阈值标定

A股宽基 ETF 的 60 日年化波动率经验分布（基于 2020-2024 样本）：
- 低位（牛市平稳期）：12-15%
- 常态（震荡期）：18-22%
- 高位（趋势转折/暴跌期）：30-50%
- 极值（如 2015 股灾）：> 50%

设 `vol_high = 0.30`，breadth threshold = 0.5：
- 触发条件 = 6 只里至少 3 只 vol > 30% —— 对应「半数风险资产进入高波 regime」
- 历史上对应 2020-03（疫情）、2021-02（抱团破裂）、2022-04（疫情底）、2024-09（政策底）等关键时点

`vol_haircut = 0.5`：高波时全体降仓一半。激进可降到 0.3，温和可设 0.7。先取 0.5 中位。

### bond overlay 的边界

`bond_max_weight = 0.4`：bond 占比上限。
- cash_gap = 1 - sum(risky)
- bond_w = min(cash_gap, 0.4)
- 剩余 (1 - sum_risky - bond_w) 作纯现金

为什么不直接 100% 替换：
1. 511260 不是无风险（duration ~7-8 年，2022 期间最大 DD 约 -3%）
2. 2024 出现过股债同跌时段，纯现金留 60% 留缓冲
3. bond_max_weight 上限是「最坏情况控制」——即便国债 -10%，组合损失 ≤ 4%

### 避免过拟合的几条纪律

1. **新参数都用业务先验设定**，不对回测结果调参
   - score_full = 1.0：朴素的「拿满 1/N 需要至少打 1 分」
   - vol_high = 0.30：A股经验阈值
   - vol_haircut = 0.5：「半仓」直觉
   - bond_max_weight = 0.4：留 60% 现金缓冲的反向
2. **先跑主线，不调参**——结果出来再决定是否做敏感性扫描
3. **关键判断指标**：cash↔BH down 相关性 + 2022 单年 + MaxDD，三个一起看；只有 CAGR 提升不够（v1 也提升了）

### 与 v1 的兼容性边界

v2 继承 v1 的 `TrendTiltStrategy`，但覆盖了 4 个方法：
- `__init__`（追加 v2 参数）
- `compute_trend_scores`（用连续 MA 因子 + 跳过 bond_symbol）
- `_tilt_weights`（连续 ramp 而非归一化）
- `target_weights`（叠加 vol filter 和 bond overlay）

v1 的 `_validate_weights` 直接复用（已经放宽过了）。**v1 文件不改**。

### 待跟进
- 真实数据回测后，看 cash_ratio 的实际分布是否真的连续
- 如果 cash↔BH down 相关性仍然 < 0.2，需要回到「信号层」改造（用更短 lookback 或 ATR 加速触发）

---

## 2026-05-08 真实数据回测结果发现（追加）

### 主结果一句话
**MaxDD 从 -47.8% 砍到 -20.5%，2022 年从 -21.6% 改善到 -7.6%——避险命题首次真正兑现。** 但代价是 2024 单年只赚 +0.5%（v1 +28%），CAGR 从 +3.92% 降到 +2.57%。

### cash_ratio 真的连续了
- v1: median = 0.000, std = 0.386, **介于 5-95% 的天数 = 0%**（完美双峰）
- v2: median = 0.789, std = 0.294, **介于 5-95% 的天数 = 70.2%**（真正连续）

### 但避险命题的「相关性」并没显著提升
- v1: cash≥0.99 vs BH down corr = 0.033
- v2: cash≥0.99 vs BH down corr = 0.031（基本一样）
- v2 continuous cash vs BH down indicator = 0.021（更低）

**这说明 v2 的避险**不是来自「精准对齐下跌」，而是来自「**结构性降仓**」——常态期就只有 50-70% 仓位，所以 BH 跌时 v2 也跌但只跌一半。这其实是 vol-target portfolio 的本质，不是「择时」。

### bond overlay 触发率 98%
median bond_w = 0.40（满档）。v2 实际是把 60% 风险预算分给 risky ETF + 40% 给 bond。这让组合更像「股债 60/40」而非「趋势倾斜」。如果想保留更多趋势性，可以把 bond_max_weight 降到 0.2 或者只在 vol haircut 触发时才打开 bond overlay。

### 2024 损失定位
v2 在 2024 +0.47%（v1 +28.09%）。原因：
1. 9-24 行情前的低 vol 使 vol filter 不触发（正常）
2. 但 score_full=1.0 偏严，常态期 risky 仓位只 50-60%，错过部分上涨
3. bond overlay 占 40% 仓位，bond 在 2024 收益约 4-5%，整体被稀释

这是「保守—激进」trade-off 的明确选择，**不是 bug**。

### v2 是否值得 ship
**Sharpe 与 v1 相同 (0.28)，MaxDD 砍半，但 CAGR 降低 1.35 pct/yr**。
- 如果用户偏好绝对收益，v1 更好
- 如果用户偏好风险调整后收益、且 MaxDD < 25% 是硬约束，v2 更好
- 但**两者 Sharpe 相同**说明仍然没有明显「真 alpha」，更多是 risk profile 的不同切片

待用户确认 ship/shelved 决策。建议状态：**shelved with notes**——避险命题确实兑现，但 alpha 没有提升，且引入了 bond_max_weight 等需要二次调参的新自由度。
