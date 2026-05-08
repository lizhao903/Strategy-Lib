---
slug: cn_etf_dca_swing_v2
title: A股 ETF DCA + 阈值再平衡 V2（DCA 优先回流 + 波动率自适应阈值）
market: cn_etf
status: implementing
created: 2026-05-08
updated: 2026-05-08
parent: S2_cn_etf_dca_swing/v1
tags: [dca, rebalance, threshold, swing, cn_etf, benchmark_v1, asymmetric_fix, vol_adaptive]
---

# A股 ETF DCA + 阈值再平衡 V2

## 一句话概括
v1 baseline 上修复「DCA 净流入推权重 → 高抛远多于低吸」的结构性偏差：
**DCA 优先回流（A）+ 波动率自适应阈值（C）**——让 DCA 节奏先把权重拉回目标，仅在偏离仍然过大时才动 swing；阈值随实现波动率呼吸，避免高波期反复刷单。

## 与 V1 的差异（核心）

V1 的失败模式是结构性的：
1. **高抛 177 vs 低吸 15（11.8:1）**——DCA 月度等额买入 6 只 ETF 让风险池权重持续上漂，触发上沿的概率天然 >> 触发下沿
2. **2024 单边反弹年跑输 BH -11.7pct**——swing 把领涨标的提前减仓，错过单边乘数
3. **平均触发偏离 24.78%**——超阈值 ~5pct 才成交，意味实际下沿成交往往晚于阈值（cooldown + adjust_ratio 共同延迟）

v2 解决思路（A + C 组合）：

### A. DCA 优先回流（DCA-priority routing）
DCA 的本质就是「持续注入风险池」。当**风险池总权重已经超过目标**时，继续灌 DCA 等于火上浇油。v2 改成：
- 当月度 DCA 触发时，先看当下风险池总权重 `w_risk` 和目标 `w_target`：
  - `w_risk > w_target × (1 + dca_band_high)`：**全部 DCA 资金留在 511990 货基**（不买入风险池）
  - `w_risk < w_target × (1 - dca_band_low)`：**DCA 金额放大 1.5×**，把缺口加速补回（资金来自 511990，相当于把 swing buy 的工作交给 DCA）
  - 否则：常规 DCA（等额 6 等分买入）

`dca_band_high / dca_band_low` 默认都用 0.05（即只要风险权重 > 73.5% 就停 DCA 流入；< 66.5% 就放大 DCA）——这个值刻意设小、让 DCA 自然回流先于 swing 触发。

### C. 波动率自适应阈值（vol-adaptive band）
v1 阈值 `rel_band = 0.20` 固定。v2 改成动态：

```
band_t = clip(0.5 × realized_vol_60d × sqrt(252) / sqrt(252), [0.10, 0.30])
       = clip(0.5 × daily_vol_60d × sqrt(252), [0.10, 0.30])  # 简化
```

实操上用「过去 60 个交易日组合 NAV 的 std × sqrt(252)」作为年化波动率代理，按 `band_t = clip(0.6 × vol_ann, 0.10, 0.30)` 取值：
- 低波时段（vol_ann ≈ 15%）→ band ≈ 0.10（更敏感）
- 高波时段（vol_ann ≈ 30%）→ band ≈ 0.18
- 极端高波（vol_ann ≈ 50%+）→ 上限 0.30 拦住，避免完全失效

这样在 2022 那种高波熊市里 band 自动放宽（避免「越跌越买」反复套牢），在 2023 那种低波震荡里 band 自动收紧（更敏感地刷单）。

### 不做的事
- ❌ **不做不对称阈值（方向 B）**：上沿/下沿用不同 band 看似直接，但阈值差是「在 OOS 上无依据的额外旋钮」；A+C 已经从根因（资金流不对称）入手，B 是治标。
- ❌ **不为不同 ETF 设不同 band**——增加 6 个旋钮，过拟合风险大
- ❌ **不调 cooldown / adjust_ratio**——保留 v1 的 5d / 0.50，便于和 v1 直接对比

## 核心逻辑（What）

每个交易日 T 收盘：

1. **月度 DCA（修正）**：若次日是月初，根据当下 `w_risk` 选择 DCA 模式：
   - `OFF`（停灌）：把 5000 留在 511990 不动
   - `BOOST`（加速）：取 7500 = 5000 × 1.5 等额买 6 只 ETF
   - `NORMAL`：取 5000 等额买 6 只 ETF（与 v1 一致）

2. **波动率自适应阈值**：算过去 60 日 NAV 的实现波动率 `vol_ann`，得到当日 `band_t = clip(0.6 × vol_ann, 0.10, 0.30)`；前 60 日 warmup 期内 `band_t = 0.20`（与 v1 一致避免冷启动）

3. **swing 触发**：和 v1 一致——按 `band_t` 判定每只 ETF 的相对偏离，超过则部分回归（cooldown 5d，adjust_ratio 0.50）

4. **下单**：T 日决策、T+1 open + slippage 成交（防未来函数）

## 假设与依据（Why）

- **DCA 净流入是 v1 偏差的"根因"，不是「市场单边」**：v1 的 11.8:1 不对称在 5 年里横跨 3 种行情（2020 V 反、2021 抱团切换、2023 震荡下行）都成立——这强烈暗示是结构问题而非行情。
- **波动率 → 阈值 是 well-known 的实务做法**（PIMCO 的 vol-targeting，CTA 的 rolling vol bands）。在 ETF rebalance 上，Bernstein 也提到过「band 应当随实现波动调整」。
- **风险偏差**：A 的副作用是 2024 那种 9 月剧烈反弹时，前 8 个月 `w_risk` 被高抛压低，9 月单边后 BOOST 模式触发——理论上能比 v1 更快地把仓位补回来（v1 是月度 5000 慢慢补；v2 是 7500 加速补，且高波时期阈值放宽 swing 触发更少，避免再次过早高抛）。
- **过拟合担忧**：A 引入 2 个新参数（dca_band_high/low），C 引入 2 个新参数（vol 系数 0.6、上下限 0.10/0.30），共 4 个旋钮。本版**全部用「圆整、非优化」值**，不在 v1 数据上调参；如果 OOS（未来年度数据）失败再回头反思。

## 标的与周期
- 市场：A股 ETF（`market: cn_etf`）
- 标的池：与 v1 完全一致（共享基线 7 只）
- 频率：日线
- 数据起止：2020-01-01 ~ 2024-12-31（共享基线）

## 信号定义

- **DCA 模式判定**（每月第一个交易日 T，次日 T+1 成交）：
  - `w_risk_T > 0.70 × 1.05 = 0.735` → DCA OFF
  - `w_risk_T < 0.70 × 0.95 = 0.665` → DCA BOOST（5000 × 1.5）
  - 否则 → DCA NORMAL（5000）
- **swing 加仓信号（低吸）**：T 日收盘 `w_i / w_target_i < 1 - band_t` → T+1 开盘买入 `(w_target_i - w_i) × NAV × 0.50`
- **swing 减仓信号（高抛）**：T 日收盘 `w_i / w_target_i > 1 + band_t` → T+1 开盘卖出 `(w_i - w_target_i) × NAV × 0.50`
- **band_t**：`clip(0.6 × vol_ann_60d, 0.10, 0.30)`，前 60 日 warmup 期固定 0.20
- **cooldown**：与 v1 一致 5 日
- **止盈止损**：无

## 涉及因子
- [x] 不依赖现有因子层（纯权重 + 阈值规则）
- [x] **新增内部因子**：`realized_vol_60d`（NAV pct_change 的 60 日 std × sqrt(252)）—— 但这个不抽出 Factor 类（仅策略内部使用，不暴露 IC）

## 预期表现（事前估计 vs v1）

|  | v1 | v2 期望 |
|---|---:|---:|
| NAV (100k) | 113,808 | 110k ~ 120k（与 v1 同量级） |
| Sharpe | 0.152 | 0.15 ~ 0.25（DCA OFF 减少高位接盘） |
| MaxDD | -37.10% | 不差于 v1（band_t 高波放宽不会导致更深回撤）|
| 高抛/低吸比 | 11.8:1 | **3:1 ~ 6:1**（核心 KPI） |
| 2024 vs BH | -11.70% | 跑输幅度收窄到 -8% 内（DCA BOOST 在 9 月后补仓） |
| 年化换手 | 153.9% | 略低（DCA OFF 减少部分流入；swing 在低波期更频繁、高波期更少，净效应近似） |

## 风险与已知坑

1. **DCA OFF 期间累积货基**：长期单边牛会让 DCA 持续 OFF，资金堆在 511990，机会成本大。但本框架 5 年窗口里 v1 已显示风险权重不会持续超 0.85，OFF 应是间歇性的。
2. **vol_ann 60 日 lookback 含未来函数风险**：必须用 T-1 及更早的数据算（**T 日 close 之后才算 vol，但用的是 T 之前 60 日**——和 v1 的"T 日决策"对称、不破坏 shift(1)）。
3. **2022 高波熊市**：band_t ↑ 会让 swing 低吸频次降低，**可能错失抄底机会**。但 v1 在 2022 就只有零星几次低吸，所以预期影响小。
4. **过拟合**：4 个新旋钮全用圆整值；不做 grid search；如果 v2 vs v1 差距 < 1pct 就 shelved（说明 A+C 没有边际价值）。

## 验证计划

1. **Smoke test**：合成数据（与 v1 同合成生成器）跑通，确认：
   - DCA 三态切换正确（OFF / NORMAL / BOOST 计数合理）
   - vol_ann 序列在 warmup 后非空
   - band_t 序列在 [0.10, 0.30] 范围
   - cooldown 仍然有效
   - NAV 重算恒等
2. **真实回测**：2020-01-01 ~ 2024-12-31 共享窗口
   - 与 v1 head-to-head：必填对比表（高抛/低吸比、2024 vs BH、各年度收益、Sharpe/DD）
   - vs 510300 BH：alpha / IR / TE
3. **决策**：
   - 高抛/低吸比 < 5:1 且 2024 vs BH 改善 > 3pct 且 Sharpe 不降 → **shipped**
   - 否则 → **shelved**（保留分析、不替代 v1）

## 与现有策略的关系

- **父版本**：S2 v1（`cn_etf_dca_swing`）—— v2 解决其结构性高低不对称
- **横向对照**：
  - S1 (`cn_etf_dca_basic`)：纯 DCA 无再平衡（v2 在 DCA OFF 时退化为 S1）
  - S3 (`cn_etf_equal_rebalance`)：等权满仓定时再平衡（v2 在 BOOST 时更接近 S3）
- **不替代 v1**：v1 已 shipped 作 baseline，v2 单独评估
