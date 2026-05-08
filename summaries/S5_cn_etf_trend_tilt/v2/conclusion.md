---
slug: cn_etf_trend_tilt_v2
status: shelved  # 避险命题数据兑现，但 Sharpe 未提升、bond overlay 主导让策略漂移；保留代码作 defensive 对照
finalized: 2026-05-08
parent: cn_etf_trend_tilt (v1)
---

# Conclusion — A股 ETF 等权 + 趋势倾斜 v2

## 一句话结论

**避险命题数据上兑现（MaxDD -47.8% → -20.5%，2022 -21.6% → -7.6%），但 Sharpe 与 v1 持平、CAGR 倒退 1.35 pct/yr，且 bond overlay 占用 37% 平均仓位让策略漂移成「股债混合」**——v2 实现了「保守型变体」但没有产生新 alpha。状态：**shelved**（保留代码作为 v1 的 risk profile 对照，不推荐替代 v1）。

## 关键数据（2020-01-02 ~ 2024-12-31）

| 指标 | v2 | v1 | S3 | 510300 BH | 解读 |
|---|---:|---:|---:|---:|---|
| NAV (100k) | **112.9k** | 120.3k | 110.8k | 104.2k | v2 中等 |
| CAGR | +2.57% | +3.92% | +2.16% | +0.86% | v2 落后 v1 1.35 pct |
| Sharpe | **0.28** | 0.28 | 0.21 | 0.15 | **持平 v1**（同 risk-adj） |
| Vol(ann) | **11.07%** | 22.01% | 23.78% | 21.77% | **降到一半** |
| MaxDD | **-20.52%** | -47.80% | -45.18% | -44.75% | **5 个策略最佳** |
| Calmar | **0.13** | 0.08 | 0.05 | 0.02 | **5 个策略最佳** |
| **2022 单年** | **-7.58%** | -21.61% | -23.47% | -21.68% | **改善 14 pct** |
| **2024 单年** | +0.47% | +28.09% | +8.82% | +18.39% | **错过单边行情** |
| cash 介于 5-95% 比例 | **70.2%** | 0.0% | — | — | **完全连续化** |
| cash≥0.99 vs BH down corr | 0.031 | 0.033 | — | — | 未改善（与 v1 同水平） |
| bond 平均仓位 | 36.8% | 0% | — | — | 主导 risk budget |

## v1 → v2 的诊断与处方

| v1 问题 | v2 处方 | 是否兑现 |
|---|---|---|
| 现金双峰 | 连续 ramp（不归一化的 `raw/N`） | ✅ **完全兑现**（70% 中间段） |
| 2022 避险未兑现 | 60 日年化波动 > 30% 时 ×0.5 | ✅ **完全兑现**（-21.6% → -7.6%） |
| 全空仓 carry=0 | 511260 十年国债 ETF 替代 ≤40% | ✅ **兑现**（贡献 ~3-4% bond return） |
| 信号对快下跌识别滞后 | （未直接修复，靠 vol filter 间接缓解） | ⚠️ **部分缓解**（cash 与 BH 跌相关性仍 0.03） |

## 在什么情况下有效，什么情况下失效

- ✅ **极端下跌年**：2022 v2 -7.6%（v1 -21.6%, BH -21.7%）—— vol filter + 连续降仓真正发挥
- ✅ **震荡市**：2023 v2 -8.0%（v1 -18.9%）—— bond carry + 降仓双重得益
- ✅ **任何时候的 risk-adjusted return**：Calmar 0.13 是基准簇 5 个策略中最佳
- ❌ **结构性单边牛市**：2024 v2 +0.5%（v1 +28%, BH +18%）—— 9-24 行情前 vol 没飙升、score_full=1.0 偏严、bond 占 40% 让组合稀释成股 60/债 40，错过单边
- ❌ **疫情冲击急跌后的 V 型反弹**：2020 v2 +22%（v1 +41%）—— 2020-03 vol filter 触发后没及时撤防，错过 4-12 月反弹
- ⚠️ **常态期**：v2 cash median = 79%，趋势倾斜的纯度被稀释，更像「股债混合 + 趋势 sizing」

## 这个策略教会我什么

1. **「连续化」与「真避险」是两件事**：
   - v2 完美解决了 cash 双峰（70% 介于 5-95% 中间段）
   - 但 cash↔BH down 相关性几乎没动（0.033 → 0.031）
   - 因为 v2 的避险**来自结构性降仓（sizing）而非 timing**——常态期就只 50-70% 仓位，下跌时被动跌一半
   - **教训**：「连续 ramp」不等于「精准择时」。如果想要 timing 类避险，需要更短 lookback 的快速反转信号（ATR、价格突破均线幅度），而不只是平滑权重曲线
2. **vol filter 是 sizing 工具不是 timing 工具**：
   - 在 sample 内的 5 年里，vol 飙升通常**滞后**于真实下跌起点（vol 是 ex-post 度量）
   - vol filter 真正的价值是「让组合在高波 regime 自动收缩」，与「预测下跌」无关
   - **教训**：定位 vol filter 为「risk budget control」而不是「avoid drawdown」
3. **bond overlay 是双刃剑**：
   - 在债牛年（2022/2023）确实贡献 +3% 左右 carry
   - 但默认 40% 上限太激进，让 risky 暴露被结构性压低
   - **教训**：bond overlay 应**只在 vol filter 触发时打开**（regime-conditional），不是常开
4. **Sharpe 持平意味着没有新 alpha**：
   - v2 与 v1 Sharpe 都是 0.28——v2 用更低 vol 换 CAGR，risk-adj 没改进
   - 真正的 alpha 提升要么来自更准的信号（识别拐点）、要么来自更好的 sizing 函数（vol-target 的精细化）
   - **教训**：避险命题的合格指标是 Calmar/MaxDD/单年极值；Sharpe 是「真有信息」的指标，v2 没通过

## 后续动作

- [x] 真实回测出结果，决定 status = **shelved**（保留代码作为 v1 的 defensive 对照）
- [ ] 衍生想法：
  - **v2.1（消融）**：关 bond overlay 单跑，看纯 vol filter + 连续 ramp 的纯净 trend tilt 效果
  - **v2.2（regime-conditional bond）**：bond 仅在 vol haircut 触发时打开，常态期不占仓
  - **v3 方向**：换更快信号（ATR breakout / 收盘相对 MA20 的 z-score）而不是更长 MA，让信号本身能跟上 A股快速下跌节奏
  - **v3 方向**：把 `score_full` 改成动态（基于宽基波动率：低波时 score_full=2.0 偏激进，高波时 score_full=0.5 偏保守）
- [ ] 等 2025 H1 数据后做 OOS 验证

## 相关链接
- Idea：`ideas/S5_cn_etf_trend_tilt/v2/idea.md`
- Notes：`ideas/S5_cn_etf_trend_tilt/v2/notes.md`
- 实现：`summaries/S5_cn_etf_trend_tilt/v2/implementation.md`
- 验证记录：`summaries/S5_cn_etf_trend_tilt/v2/validation.md`
- 验证脚本：`summaries/S5_cn_etf_trend_tilt/v2/validate.py`（`smoke` / `real` / `all`）
- Artifacts：`summaries/S5_cn_etf_trend_tilt/v2/artifacts/`（5 张 PNG）
- 配置：`configs/S5_cn_etf_trend_tilt_v2.yaml`
- v1 conclusion：`summaries/S5_cn_etf_trend_tilt/v1/conclusion.md`
- 父策略 (v1)：`src/strategy_lib/strategies/cn_etf_trend_tilt.py`
- 祖父策略 (S3)：`src/strategy_lib/strategies/cn_etf_equal_rebalance.py`
