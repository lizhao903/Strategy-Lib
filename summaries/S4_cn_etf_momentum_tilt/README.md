# S4 · cn_etf_momentum_tilt — 版本索引

S3 派生：z-score 线性倾斜动量因子调权重。

| Version | 关键参数 | NAV (100k) | CAGR | Sharpe | MaxDD | vs S3 | Status |
|---|---|---:|---:|---:|---:|---:|---|
| [v1](v1/) | 6 pool, lookback=20d, α=1.0, [5%, 40%] | 98.6k | -0.30% | 0.11 | -48.7% | -2.56% | shelved |
| [v2](v2/) | **11 pool**, lookback=120, skip=5, α=1.0, [3%, 30%] | **130.7k** | **+5.75%** | **0.44** | **-22.2%** | -1.06% | shipped (pool value) |

## v1 → v2 待解决问题
v1 在本 6-ETF 池上 5α × 3lookback = 8 次实验**全部 IR 负**，方向稳定。可能原因：池子太集中（行业/宽基）、20 日动量在 A 股反转过强。v2 候选改进：
- 更长 lookback（120/250 日，跨过短期反转）
- 扩池（加港股/黄金/海外 ETF 增加分散度，让横截面有效）
- 加 vol-adjusted（risk parity 风格）
- 加显式 `shift(1)` 排除 same-bar 影响

## v2 → v3 待解决问题
v2 把 4 项改进全部上线：扩池 6→11 + 严格 shift(1) + lookback=120/skip=5 + 可选 vol-adjusted。结果：
- **NAV/Sharpe/MaxDD 三项全面碾压 v1**（NAV 1.31 vs 1.00，Sharpe 0.44 vs 0.12，MaxDD -22% vs -48%），且首次跑赢 510300 BH +2.6%/yr。
- 但 **vs S3 (11 pool) IR = -0.17 仍为负**；α 敏感性 5 档中 α=0（等权）仍是 Sharpe 最优 → **动量 tilt 信号在跨资产 ETF 池上仍未带来 alpha**。
- Pool ablation 证明：v2 总改进 +5.73%/yr 中 **~73% 来自扩池**（让 S3 baseline 变好），仅 ~27% 来自参数。

⇒ v3 候选：
- 直接 ship「11 池 + S3 等权」，跳过倾斜层（α=0 一致最优，已被 v1+v2 两次证伪）
- 大盘 510300 200MA 二元过滤（跌破退化等权）
- vol_adj × lookback=250 单独 ablate（v2 sweep 中唯一 IR > 0 的档）
