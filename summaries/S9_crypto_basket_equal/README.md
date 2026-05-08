# S9 · crypto_basket_equal (V2-S1) — 版本索引

V2 Crypto Suite 的第一个策略：5 只头部加密货币（BTC/ETH/SOL/BNB/XRP）等权 + 月度再平衡。

| Version | 池 | NAV (100k USDT) | CAGR | Sharpe | MaxDD | vs BTC BH | Status |
|---|---|---:|---:|---:|---:|---:|---|
| [v1](v1/) | CRYPTO_TOP_5 | **2,282.6k** (22.8x) | **+118.46%** | **1.410** | -78.9% | **+84.84%/yr** | shipped (in-sample) |

## 关键观察（2026-05-08 真实数据）
- 同 S3 等权机制（V1 S8 跑出 0.85 Sharpe）在 crypto 跑出 **Sharpe 1.41**，命题"等权 + 月度再平衡"跨市场普适
- **alpha 主要来自 2021 SOL 100x 暴涨**（去 SOL 的 btc_eth_2 仅 +43% CAGR，接近 BTC BH）
- 2022 LUNA/FTX 期 5 池齐跌 -71%（crypto 内部相关性高，等权多元化在系统性崩盘下失效）
- TOP_10 (10 池) 反而 Sharpe 略降，TOP_5 是 sweet spot

## OOS 风险（最大未知）
- SOL 100x 一次性事件不会重现
- BTC 2024-12 在 95k 附近，2025+ 均值回归压力大
- 4 年样本含一次完整周期但仍小

## 待启动 V2 后续
| 编号 | slug | 命题 |
|---|---|---|
| ✅ S9 (本) | crypto_basket_equal | baseline 跨市场可复用？已验 yes |
| 待 | crypto_dca_basic | DCA 在高波动 crypto 上的效果 |
| 待 | crypto_btc_ma_filter | timing 能避开 2022 -71% 吗？|
| 待 | crypto_trend_tilt | V1 S5v2 sizing 在 crypto 是否更有效 |
| 待 | crypto_momentum_tilt | crypto 横截面动量是否反向 |

## 起源
2026-05-08 用户提出"换成数字货币标的验证策略实现效果"，本策略是 V2 Suite 的 baseline，对应 V1 中 S3/S8 的角色。

## 当前 status: `idea`
- ✅ 设计完成（idea.md / notes.md）
- ✅ universe 已注册（`CRYPTO_TOP_5` 在 `universes.py`）
- ✅ V2 共享基线已写（`docs/benchmark_suite_v2_crypto.md`）
- ❌ 未拉数据
- ❌ 未跑回测
- ❌ 未写 implementation/validation/conclusion

## 启动 checklist（按顺序）
- [ ] 拉测试 BTC/USDT 1 个标的，验证 CryptoLoader（akshare 已验证、ccxt 待验证）
- [ ] 预拉 CRYPTO_TOP_5 + 基准 BTC/USDT 全部数据到 `data/raw/crypto/`
- [ ] 写 `summaries/S9_crypto_basket_equal/v1/validate.py`
- [ ] 跑首次回测（V2 baseline）
- [ ] 写 implementation.md / validation.md / conclusion.md
- [ ] 把 V2-S1 数据加进 V1 S8 横向对比表

## 后续 V2 策略 roadmap
| 编号 | slug | V1 对应 | 命题 |
|---|---|---|---|
| **S9** (本) | crypto_basket_equal | S3 / S8 | baseline 是否在 crypto 也胜出 |
| S10 候选 | crypto_dca_basic | S1 | DCA 在高波动 crypto 上是否更好 / 更差 |
| S11 候选 | crypto_btc_ma_filter | S7 | BTC 200日 MA 信号 timing |
| S12 候选 | crypto_trend_tilt | S5v2 | 连续 trend + vol filter |
| S13 候选 | crypto_momentum_tilt | S4v2 | 横截面动量在 crypto（A 股反向命题验证）|

详细计划见 `docs/benchmark_suite_v2_crypto.md`。
