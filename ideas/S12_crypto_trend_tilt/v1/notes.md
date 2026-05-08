---
slug: crypto_trend_tilt
created: 2026-05-08
---

# Notes — V2-S3 (S12) crypto_trend_tilt

## 2026-05-08 启动备忘

- S9 conclusion 优先 3。承接 V2-S2 MA filter（已 ship）；本策略侧重 risk profile shifter
- 关键问题：V1 默认 vol_high=0.30 在 crypto 永远触发降仓，等价于"vol-target 50% 上限"
- 真正的 dedicated 价值：找 crypto-appropriate vol_high；如果 0.30 偶然是最优则更微妙

## 待跟进

- 如 vol_high sweep 显示 0.80 或 1.00 显著优 → 派生 v2 默认值
- 与 V2-S2 MA filter 互补关系：连续 vs 离散；trend ramp vs 二元 ON/OFF
- Calmar 比较：MaxDD 砍半比 CAGR 损失 40% 是否值得？取决于资金管理偏好

## 与 V1 S5v2 的对比预案

| 维度 | V1 S5v2（A 股 11 池） | V2-S3 (crypto 5/10 池) | 解读预期 |
|---|---|---|---|
| 主参数 vol_high | 0.30 | 0.30（V1 默认）vs 0.80（crypto 适配） | 对比看默认是否 mismatch |
| 平均仓位 | ~70% | ~40-50% | crypto 高 vol → 频繁降仓 |
| Sharpe | 0.28 | sweep 示 1.37-1.58 | crypto Sharpe 高 |
| MaxDD | -20.5% | -30~-37% | crypto 仍深，但相对 V2-S1 -78% 大幅改善 |
| Sharpe / Vol | ~5 | ~3-4 | A 股 risk-eff 更高（同 V2-S1/S4 模式） |

## 工程依赖
- CryptoLoader USDT 合成（V2-S2 已修）—— TrendTiltV2 不直接需要 cash_symbol，但配合 panel 调用方便
- TrendTiltV2 不强求 cash_symbol
