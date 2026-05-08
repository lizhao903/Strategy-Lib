---
slug: cn_etf_dca_swing_v2
parent_slug: cn_etf_dca_swing
status: shelved
finalized: 2026-05-08
---

# Conclusion — A股 ETF DCA + 阈值再平衡 V2（DCA-priority + vol-adaptive）

> 状态：**shelved**——核心 KPI（高抛/低吸比、2024 vs BH 改善）未达 idea.md 预期。
> v2 的两个机制（A: DCA 优先回流；C: 波动率自适应阈值）功能层面都正确运转，但相互抵消，
> 净效果只是把 v1 重新分配到「换手降低 + MaxDD 略浅 + Sharpe 略升 + 高抛比几乎不变」。
> v1 仍是 S2 的最佳实现版本。

## 一句话结论

**「停 DCA 灌入」无法治愈 v1 的高抛/低吸不对称——根因是 5 年里 6 只 ETF 整体偏多头 + 资金长期占在风险池，
单边停 DCA 只是减缓权重上漂、没有反转它。** v3 若要继续应改用方向 B（不对称阈值）或完全跳出 DCA 框架。

## 关键数据（2020-01-01 ~ 2024-12-31）

| 指标 | v1 baseline | v2 | Δ | 评价 |
|---|---:|---:|---:|---|
| NAV (init=100k) | 113,808 | 114,209 | +401 | 几乎相同 |
| CAGR | +2.75% | +2.82% | +0.07pct | 略升 |
| Sharpe | 0.152 | 0.164 | +0.012 | 略升 |
| MaxDD | -37.10% | -35.12% | +1.98pct | 略浅 |
| Calmar | 0.074 | 0.080 | +0.006 | 略升 |
| 高抛 / 低吸 | 177 / 15 | 187 / 16 | +10 / +1 | 反向 |
| **高抛/低吸比** | **11.80:1** | **11.69:1** | -0.11 | **几乎未改善** |
| 2024 vs BH | -11.70pct | -11.42pct | +0.28pct | 几乎未改善 |
| **年化换手** | **154%** | **96%** | **-58pct** | **显著降低** |

V2 特有：DCA NORMAL/OFF/BOOST = 31/25/3 → DCA OFF 占 42.4%（核心机制确实在工作）；band_t 均值 0.111 / max 0.229 / min 0.10。

## V2 的设计 vs 实际效果对照

| idea.md 预期 | 实际 | 评价 |
|---|---|---|
| A 方向减少 DCA 引起的上沿偏置 | DCA OFF 触发 25 次但高抛次数反增 | ✗ 未兑现 |
| C 方向让 band 在低波时更敏感、高波时更宽容 | band_t mean=0.111, max=0.229 | ✓ 部分兑现（系数偏低让整体偏紧） |
| 高抛/低吸比降到 3:1 ~ 6:1 | 11.69:1（v1 11.80:1） | ✗ 完全未兑现 |
| 2024 vs BH 改善 > 3pct | 仅 +0.28pct | ✗ 未兑现 |
| Sharpe 不降、MaxDD 不深 | 都略改善 | ✓ 兑现 |
| 换手率降低 | -58pct | ✓ 超出预期 |

## 为什么 A+C 没能解决「不对称」？

**根因诊断**（这是这次 v2 实验最值钱的部分）：

1. **「停 DCA」只能停止"新增注入"，无法消化"已有过热"**。
   v1 在 5 年里风险权重长期 > 0.70（净流入 + 市场上涨双重作用），即使 v2 把 25 个月的 DCA 关掉，原本 0.85 的过热权重仍然在那——swing 上沿照样触发。要根治得加上「主动减仓回到 0.70」，但那本来就是 swing 的工作 → 循环。

2. **A 和 C 互相抵消**。
   - A：DCA OFF 应当让风险权重不再过度上漂，**减少**高抛触发
   - C：vol_band_coef=0.6 让 band_t 平均 0.11（远小于 v1 的 0.20），swing 触发更敏感、**增加**高抛触发
   - 净效应：187 vs 177，几乎抵消。
   即使把 vol_band_coef 提到 0.9 让 band 接近 v1，也只是回到 v1 的不对称状态，A 单独的效果太弱以致看不到。

3. **「6 只 ETF 在 5 年里整体偏多头」是结构性事实**。
   2020 V 反、2021 抱团切换、2024 9.24 反弹三个段都是市场强反弹；2022/2023 单边熊里 swing 也几乎只有零星几次低吸——风险标的不会同时全跌（512170 医疗 2022 跌但 510500 不跌那么深）。**任何"对称"做T 的设计在结构性多头偏置上都会偏向高抛**。

## 这个策略教会我什么（可迁移的经验）

1. **在 DCA 框架下做"对称做T"是矛盾命题**。如果坚持 DCA + 再平衡两条腿，要么接受不对称（v1），要么改用不对称阈值（B 方向）从机制上承认这个事实。
2. **波动率自适应阈值的设计中，系数选择直接决定 band 长期撞下限还是中段游走**。`vol_band_coef × vol_ann_60d ∈ [min, max]` 这个公式在 vol_ann≈18% 时会把 0.6 系数压到 0.108 → 撞下限 0.10。下次写 vol-adaptive 应当先用历史 vol 的中位数测算系数选什么值能让 band 落在 mid-range（比如 [min, max] 的中点），而不是机械给 0.5/0.6 之类的"圆整值"。
3. **多旋钮组合在样本内的"最佳值"未必能改善样本内 KPI，但增加了 OOS 不可验证性**。v2 加了 4 个新参数；从这次结果看，去掉 C（保留 A）甚至可能效果更好（A 单独的效果会更纯）——但这只是回头看的猜测，**必须重新在 idea 阶段单独写 v3 才能验证**，不能在 v2 上事后调参。
4. **MaxDD/换手率这种"被动副产品"才是 v2 的真实收获**。换手降 58pct 是真金白银，下次设计应该把这两类副产品在 idea.md 阶段就写明（而不是只盯一个 KPI）。

## 后续动作

- [x] V2 真实数据回测产出 + v2 vs v1 vs BH 对比
- [x] 4 张 artifacts 图（equity / drawdown / swing_events / risk_weight_band）
- [x] 失败归因写入 validation.md
- [ ] v3 候选方向（**不在本 v2 上事后调参**，单独立项）：
  - **方向 B**：不对称阈值（上沿 +12%、下沿 -25%）—— 直接承认结构性偏置
  - **方向 D**：去掉 DCA 月度净流入，改成「DCA 仅在 w_risk < target × 0.95 时启动」（A 的极端版本）—— 接近 S3 但保留 30% 现金缓冲
  - **方向 E**：保留 v2 但把 vol_band_coef 提到 0.9（让 band 平均落在 0.16，接近 v1 但保留 vol 自适应）—— 单独验证 C 是否独立有效
- [ ] 在 `summaries/README.md` 索引加 v2 一行（只追加一行）

## 决策

V2 → **shelved**（不替代 v1；v1 仍作为 S2 的 V1 baseline）。

理由：
- 核心 KPI（高抛/低吸比）几乎未改善
- 2024 vs BH 改善仅 0.28pct（未达 3pct 期望）
- alpha/IR 略降（v1 1.11% / 0.110 → v2 1.02% / 0.100）
- 仅 Sharpe / MaxDD / 换手 三项小幅改善——不足以替代 v1
- 4 个新参数在 OOS 上无依据（样本内未做 grid search 但样本外仍是黑盒）

V2 的代码和数据保留作为「DCA-priority routing」+「vol-adaptive band」两个机制的 reference 实现，未来 v3 可参考。

## 相关链接

- Idea：`ideas/S2_cn_etf_dca_swing/v2/idea.md`
- Notes：`ideas/S2_cn_etf_dca_swing/v2/notes.md`
- 实现：`summaries/S2_cn_etf_dca_swing/v2/implementation.md`
- 验证记录：`summaries/S2_cn_etf_dca_swing/v2/validation.md`
- 配置：`configs/S2_cn_etf_dca_swing_v2.yaml`
- Artifacts：`summaries/S2_cn_etf_dca_swing/v2/artifacts/`
- 父版本：`summaries/S2_cn_etf_dca_swing/v1/conclusion.md`
- 关键 commit：待提交
