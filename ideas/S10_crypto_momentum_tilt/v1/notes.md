---
slug: crypto_momentum_tilt
created: 2026-05-08
---

# Notes — V2-S4 (S10) crypto_momentum_tilt

## 2026-05-08 启动备忘

- 启动动机：S9 conclusion.md 优先 1。sweep 已示 momentum 在 crypto top_5/10 是冠军（与 V1 完全相反）—— 必须做 dedicated 弄清楚 alpha 来源。
- 关键开放问题：alpha 是「等权 + 池子」贡献还是「z-score 倾斜」贡献？验证目标：把这两个部分分解开。
- 不做的事：不调 alpha / w_min / w_max（V1 默认值即可）；不重写策略代码；不引入新因子。

## 与 V1 S4v2 的对比预案

| 维度 | V1 S4v2 (A 股 11 池) | V2-S4 (crypto 5 池) | 解读预期 |
|---|---|---|---|
| Sharpe | 0.40-0.60（待补） | sweep 1.51 | crypto 高 |
| Vol | ~14% | ~76% | crypto 5x |
| Sharpe / Vol（risk-eff） | ~3-4 | ~2 | A 股 risk-efficient 更高 |
| vs S3 alpha/yr | 弱（部分组合 <0） | sweep 显示 +37% NAV (4y) ≈ +8 pct/yr | crypto 信号有效 |

> 核心解读模式：crypto 看似 Sharpe 高，但单位波动产生的 alpha 反而低，与 V1 conclusion 已知规律一致。

## 工程坑修复记录

**bug**：`MomentumTiltV2Strategy._tilt_weights` 在 N=2/3/4 池触发：
```
ValueError: w_min*N=0.06 与 w_max*N=0.6 与归一化和=1 矛盾
```

**根因**：默认 w_min=0.03 / w_max=0.30 是按 N=11 调过的（0.30*11=3.3 包住 1.0）。crypto V2-S4 的 N=2/3 池 w_max*N<1 → 上限内放不下归一化和。

**修复**：构造时按 N 自动放宽：
- w_max → max(w_max, 1/(N-1))（N=2 → 1.0；N=3 → 0.5；N=4 → 0.333）
- w_min → 0 if w_min*N>1（N≥4 默认不会触发）

不影响 N≥5 行为。N=11（V1 默认）下 w_max 仍是 0.30。

## 待跟进

- 若 NO_SOL ablation 揭示 alpha 完全来自 SOL → 写一份"crypto momentum 等价于 SOL 押注"的解读
- 4h 频率重测可能让 momentum 反应更快（S9 conclusion 优先 4）；这里先跑 1d
- 与 V1 S8（cn_etf_overseas_4 等权）的横向 sharpe-per-vol 对比应当并入 conclusion
