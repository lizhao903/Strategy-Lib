# S1 · cn_etf_dca_basic — 版本索引

货币基金（511990）+ 风险池等额 DCA 定投，零主动调仓。

| Version | 关键参数 | NAV (100k) | CAGR | Sharpe | MaxDD | vs S3 | Status |
|---|---|---:|---:|---:|---:|---:|---|
| [v1](v1/) | DCA 5k/月，等权 6 ETF | 89.6k | -2.25% | -0.01 | -45.1% | -4.62% | shipped (跑输) |

## 关键学习（v1）
现金缓冲 2021-09 耗尽后退化为静态等权篮子；DCA 节奏本身不创造 alpha。

## 后续派生
- **S6 (`cn_etf_value_averaging`)**：跳出 DCA 框架，按目标 NAV 路径调仓（VA），见 `summaries/S6_cn_etf_value_averaging/v1/`
- 后续 S1 v2 候选：换 11 跨资产 ETF 池（S4v2 已证扩池是真 alpha 来源），观察 DCA 框架能否在非单边多头池上扭转
