# Notes — crypto_basket_equal (V2-S1)

## 2026-05-08 想法起源

**触发**：用户在 V1 全套 + universe sweep 工具完成后，提出"换成数字货币标的验证策略实现效果"。这是 V2 Suite 的开篇。

**编号方式**：用 V1 续编号（S9）而不是「V2-S1」——简化命名空间。docs 内用 V2-S1 别称便于阅读。

**作为 V2 第一个策略的角色**：
- V1 第一个 baseline 是 S1 DCA（设计上含现金缓冲），但 V1 v2 阶段证实 S3 等权才是真 baseline
- V2 直接从「等权 baseline」起步，跳过 V1 走过的弯路（DCA / swing）
- 后续 V2-S2/S3/S4/S5 应当**已知 baseline 数据下做 ablation**，而非把 V1 全套照搬一遍

## 和 V1 S8 的对偶

S8 (cn_etf_overseas_equal) 揭示：S3 等权 + overseas_4 在 A 股市场上是当前最佳。
V2-S1 (crypto_basket_equal) 命题：S3 等权 + crypto top 5 在 crypto 市场上是当前最佳？

如果两边都成立 → **「等权 + 月度再平衡」是跨市场普适的 alpha**
如果只一边成立 → 找出差异在哪（市场结构？样本期？标的相关性？）
如果都不成立 → V1 的 universe sweep 发现是窗口偶然，需要回炉

## 待解决的设计选择

**1. 月度（20 日）vs 周度（5 日）再平衡**：
- V1 用 20 日是因为 A 股月度交易日 = 20
- crypto 24/7 没有明确"月度"概念（30 日 = 30 日）
- 选项 A：保持 20 日（与 V1 完全同口径，便于横向对比）
- 选项 B：用 30 日更符合 crypto 自然周期
- 建议：默认 20 日（A），用 sensitivity 测 30 / 60 / 90 几档

**2. 起点选择 2021-01-01 还是更晚**：
- BTC/ETH 在 2017 已成熟，但 SOL 2020-04 上线、BNB 2017 上线
- SOL 在 binance 早期流动性不足，2021 后才稳定
- 如果用 2020-01 起点，SOL 早期数据可能噪音大
- **建议**：2021-01-01 起点（牺牲 1 年样本换更干净数据）；可在 sensitivity 里做 2020-01 vs 2021-01 对比

**3. 是否包含 stablecoin 收益模型**：
- USDT 现实中可以放 lending 平台拿 5-10% APY（Aave、Compound）
- V1 用 511990 货币基金 ~2% APY
- 选项 A：USDT carry = 0（保守）
- 选项 B：USDT carry = 5%（接近真实但要假设可获取）
- **建议**：默认 A（保守，避免 OOS 失败），把 lending 收益作为可选 + 文档说明

**4. 交易成本调整**：
- 选项 A：和 V1 一致（fees=5bp, slippage=5bp）
- 选项 B：crypto 现实（fees=10bp, slippage=10bp）
- **建议**：B（更接近真实），V1 数据不直接可比但更可信

## 比较矩阵：V1 S8 vs V2-S1（待跑后填）

| 维度 | V1 S8 (cn_etf_overseas) | V2-S1 (crypto_basket) | 解读 |
|---|---:|---:|---|
| 市场 | A 股 ETF | Crypto Spot | |
| 池 | 4 (海外+黄金) | 5 (top crypto) | |
| 基准 | 510300 BH | BTC/USDT BH | |
| 期间 | 2020-2024 (5y) | 2021-2024 (4y) | |
| CAGR | +11.87% | TBD | |
| Sharpe | 0.851 | TBD | |
| MaxDD | -20.9% | TBD | |
| Vol | ~14% | ~70% (估) | crypto 高 5x |
| Sharpe / Vol | 6.1 (per pp vol) | ? | risk-adjusted 可比性 |

## 启动顺序建议

1. 先在工程上把 CryptoLoader + data 缓存验证一次（小测试，1-2 个标的，避免大批量后才发现配置问题）
2. 跑 V2-S1 主结果 + 与 BTC BH 详细对比
3. 注册 4 个 crypto universe 后，跑 V2 sweep（4 universe × 4 策略 = 16 次回测）
4. 把 V2-S1 数据加进 S8 的横向对比表
5. 写 V2-S1 完整 summary

---
