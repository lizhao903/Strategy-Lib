# S3 · cn_etf_equal_rebalance — 版本索引

6 只 ETF 等权满仓 + 定时再平衡。是 S4/S5 的父类（暴露 `target_weights` 钩子）。

| Version | 关键参数 | NAV (100k) | CAGR | Sharpe | MaxDD | vs BH | Status |
|---|---|---:|---:|---:|---:|---:|---|
| [v1](v1/) | rebal=20d, drift_threshold=None | 111.9k | +2.37% | 0.26 | -45.2% | +1.51% | shipped |

## 关键学习（v1）
等权满仓的 alpha 与窗口耦合度极高：板块轮动期赚 alpha（2021 +9.5%），单边集中行情吃亏（2024 -10.2%）。`run()` 未做 `shift(1)`，等权策略不影响，但价格信号子类（S4/S5）需关注 same-bar lookahead。
