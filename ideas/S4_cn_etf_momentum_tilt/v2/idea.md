---
slug: cn_etf_momentum_tilt_v2
title: A股 ETF 等权 + 动量倾斜（v2 — 扩池 + shift(1) + 长 lookback + vol-adjust）
market: cn_etf
status: implementing
created: 2026-05-08
updated: 2026-05-08
parent: cn_etf_momentum_tilt (v1, shelved)
tags: [momentum, rebalance, tilt, etf, cross-asset, benchmark_suite_v1, v2]
---

# A股 ETF 等权 + 动量倾斜（v2）

## 一句话概括
把 v1 的 6-ETF 池（A股宽基/行业，高度同涨同跌）扩为 11-ETF 跨资产池（+ 港股/黄金/纳指/标普/十年国债），叠加严格 shift(1)、长 lookback（120）+ skip(5)、可选 vol-adjusted 信号 — 旨在**让横截面动量真正有信息可用**。

## 核心逻辑（What）
1. 标的池 = v1 的 6 只 A股 ETF + 5 只跨资产 ETF（恒生/黄金/纳指/标普500/十年国债）共 **11 只**。
2. 每个再平衡日（每 20 个交易日）按 `MomentumReturn(lookback=120, skip=5)` 计算各标的动量；可选改用 `VolAdjustedMomentum(lookback=120, skip=5, vol_lookback=60)`。
3. **`target_weights` 内严格 shift(1)**：用 `df.loc[df.index < date]` 切片，保证信号只用前一日及更早数据，杜绝 same-bar 偷看。
4. 横截面 z-score → 线性倾斜 `w_i = 1/N + α·z_i/N` → clip 到 `[0.03, 0.30]`（N=11 适配后比 v1 的 [0.05, 0.40] 对称收紧） → water-fill 归一化。
5. 100% 满仓、无现金缓冲，与 S3 保持同口径再平衡。

## 假设与依据（Why）
v1 失败的**根本原因诊断**（来自 v1 conclusion 的 5 条经验）：
- 6 只 A股 ETF 的 pairwise correlation 高、横截面 σ 小 → z-score 信息密度低、容易被噪音淹没
- 20 日动量在 A 股 ETF 上被短期反转（mean-revert）盖过
- 单边市（2020 普涨、2022 普跌）下「相对动量」≈ 几周噪音

**v2 的对应假设**：
1. **扩池假设**（最关键）：跨 5 大资产类别（A 股 / 港股 / 美股 / 黄金 / 债券）让 pairwise correlation 真正下降，z-score 才能编码出信息；即使倾斜信号本身不强，更分散的池**至少能给出 S3 等权的「免费 alpha」**。
2. **长 lookback + skip 假设**：120 日（约一个季度）跨过短期反转噪声窗口；skip=5 跳过最近 1 周避免微观结构反转。理论上 A 股「短期反转 + 中长期趋势」经验下，这个组合应该比 lb=20 表现更稳。
3. **shift(1) 假设**：S3 父类用 `from_orders` + `targetpercent`，rebalance 日 close 价成交；信号若用到当日 close 就有 same-bar lookahead。严格 `< date` 切片消除这个隐患。
4. **vol-adjust 假设**：扩池后纳入了高波动（纳指/创业板）和低波动（国债/黄金）资产，原始动量倾斜会让权重过度偏向高波动资产；除以 60 日 vol 做风险调整后，权重变化更接近「横截面 risk parity 风格」，理论上 Sharpe 更稳。

## 与 v1 的关键差异

| 维度 | v1 | v2 | 动机 |
|---|---|---|---|
| 标的池 | 6 (全 A股 ETF) | **11 (跨 5 资产类)** | 提升横截面分散度（最重要） |
| Lookback | 20 | **120** | 跨过 A 股短期反转 |
| Skip | 0 | **5** | 跳过最近 1 周 |
| shift(1) | 隐式（依赖 vbt 次日成交） | **显式 `df.index < date`** | 消除 same-bar 风险 |
| 信号 | raw mom | raw + 可选 **vol_adj** | 跨资产时控制 vol 偏向 |
| w_min, w_max | 0.05, 0.40 | **0.03, 0.30** | N=11 时对称（1/N≈0.091） |
| 父类 | `EqualRebalanceStrategy` | `EqualRebalanceStrategy`（同） | 不动父类 |

## 标的与周期
- 市场：A股 ETF (`market: cn_etf`)
- 标的池（11 只）：
  - A股 6 只：`510300, 510500, 159915, 512100, 512880, 512170`（与 v1 一致）
  - 跨资产 5 只：`159920`（恒生）`518880`（黄金）`513100`（纳指）`513500`（标普500）`511260`（十年国债）
- 频率：日线
- 数据起止：2020-01-01 ~ 2024-12-31

## 信号定义
- 入场：每个 rebalance 日重置目标权重（按 v2 倾斜公式）
- 出场：无显式止损，下次 rebalance 重新计算
- 仓位/权重：`w_i = clip(1/N + α·z(mom_i)/N, 0.03, 0.30)`，归一化；α 默认 1.0
- 因子：`MomentumReturn(lookback=120, skip=5)`，可选切换 `VolAdjustedMomentum`

## 涉及因子
- [x] 现有因子复用：`MomentumReturn(lookback=120, skip=5)`
- [x] 新增因子：`VolAdjustedMomentum(lookback=120, skip=5, vol_lookback=60)`（动量 / 60 日 realized vol）

## 预期表现（事前估计）
**与 v1 不同的事前评估**：
- v2 即使**信号本身仍然无效**，扩池带来的等权红利就足以让 NAV/Sharpe 大幅改善。
- 因此 v2 的成败关键不是「比 v1 好」（必然好）而是 **vs S3 (11 pool) 的 IR 是否扭转**。门槛 ≥ +0.30 才算 ship；零附近说明动量 tilt 没贡献，但扩池价值要单独认。
- 年化收益区间：4% ~ 8% CAGR（vs v1 -0.30%）
- 期望 Sharpe：0.4 ~ 0.6（vs v1 0.108）
- 最大回撤容忍：-25% ~ -35%（扩池后债券/黄金抗跌；vs v1 -48.7%）
- 换手率粗估：~150% ~ 250%（lookback 长 → 信号变化慢 → 换手降）

## 风险与已知坑
- 若动量 tilt 真的无效（IR ≈ 0 vs S3），v2 实际就是「11 资产 S3 + 一个无害的 tilt」。这不算策略，算 S3 扩池版本。要诚实区分「pool alpha」vs「factor alpha」。
- 11 ETF 中部分（513500/513100/159920/511260）在样本期内有阶段性大趋势（如纳指 2020/2023），动量倾斜可能错买在高位（2021 H2 纳指调整）。
- A 股、港股、美股交易日历不同 → 父类 `build_target_weight_panel` 会做共同交易日 intersection，可能少量损失日期。
- vol-adjust 在 vol 突变期（如 2020/3 covid）可能放大或抑制信号，需要看分年度归因。

## 验证计划
1. 拉取数据范围：2020-01-01 ~ 2024-12-31，11 只 ETF + 510300 BH。akshare loader（已缓存）。
2. **核心对比矩阵**：
   - v2 default vs v1 default（NAV / Sharpe / MaxDD）
   - v2 vs **S3 (11 pool)**：IR / TE / t-stat（**因子是否真正有效**）
   - **Pool ablation**：v2 参数在原 6 池 vs S3 (6 池) → 衡量「扩池本身」贡献
   - vs 510300 BH（绝对基准）
3. α 敏感性（5 档：0/0.5/1/2/5）：是否仍是 α=0 最优？
4. lookback 敏感性（4 档：20/60/120/250）：长 lookback 是否真的更好？
5. signal 类型对比：raw vs vol_adj。
6. 分年度归因：哪一年 v2 - S3 为正/为负？

判定标准：
- **Ship**：v2 vs S3 (11 pool) IR ≥ +0.30，且分年度方向稳定（≥3/5 年正）
- **Pool-only ship**：IR ≈ 0 但 v2 vs v1 alpha ≥ +3%/yr 且 MaxDD 减半 → 上线 v2 配置但备注「价值在 pool 不在 factor」
- **再次搁置**：IR < 0 且分年度无稳定方向

## 与现有策略的关系
- **派生自 v1**（`cn_etf_momentum_tilt`，shelved）。
- 仍然继承 `EqualRebalanceStrategy`（S3）；仅覆盖 `target_weights` 钩子。
- 与 S5 (trend_tilt) 平行；v2 的扩池经验若成立可反哺 S5 v2。
- 相关 slug：`cn_etf_momentum_tilt`（v1）、`cn_etf_equal_rebalance`、`cn_etf_trend_tilt`
