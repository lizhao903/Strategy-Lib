# Benchmark Suite V2 — Crypto 数字货币基准策略组（计划）

把 V1 全套（A 股 ETF）的工具与方法论移植到**数字货币标的**上。本文档定义 V2 共享基线，后续每个具体策略走同样的 `ideas/S{N}_<slug>/v1/` 流程。

**当前状态：planning（未跑回测）**。本文档先确定基线、universe、初始策略候选清单；具体回测延迟到设计成熟后启动。

## 为什么做 V2

V1 揭示「池子 >> 信号 >> 仓位」。Crypto 与 A 股是两个**几乎完全不相关**的市场，在 crypto 上重跑同样的策略可以验证哪些发现是**普适规律**、哪些是 A 股窗口特定的。

**重点验证假设**：
1. 等权 + 月度再平衡（S3 同款）在 crypto 上是否仍然胜过 timing/factor 类策略
2. DCA 不对称性（S2v2 finding）在 crypto 上是否成立
3. 横截面动量（S4 系列）在 crypto 池上反向的 A 股发现是否可重现 / 反转
4. 趋势退出（S5/S7）在 crypto 高波动环境下是否更有效

## 共享基线（所有 V2 策略必须遵守）

| 项 | 值 | 说明 |
|---|---|---|
| 初始资金 | 100,000 USDT | 与 V1 100k RMB 同结构（便于横向比照） |
| 市场 | crypto（USDT 永续 / 现货）| 默认现货 spot；后续可加永续 perp 版 |
| 现金代理 | USDT | 类似 V1 的 511990，但 USDT 无利息（除非接入 lending 收益模型）|
| 数据源 | ccxt → Binance | 已实现 `CryptoLoader`（`src/strategy_lib/data/crypto.py`）|
| 时间频率 | 4h（建议）/ 1h / 1d | crypto 24/7 交易，4h 是社区常用平衡点；先用 1d 与 V1 对齐再迭代 |
| 回测窗口 | 2021-01-01 ~ 2024-12-31（4 年）| 包含 2021 牛市 + 2022 熊市 + 2023 震荡 + 2024 反弹 |
| 基准 (Benchmark) | BTC/USDT buy-and-hold | crypto 的"沪深300"等价物 |
| 交易成本 | fees=0.001（10 bps，比 A 股 5x），slippage=0.001 | crypto 实际成本 5-15 bps，0.1% 是稳妥估计 |
| 数据质量注意 | 24/7 + 闪崩频繁；部分 alt 历史 < 4 年 | 选 universe 时优先头部、剔除合约换币 / 跑路标的 |

## V2 Universe 候选（待注册到 universes.py）

### 已注册（基础设施已落，等具体策略调用）

| Universe | 标的 | n | cash | benchmark | 描述 |
|---|---|---:|---|---|---|
| `CRYPTO_TOP_3` | BTC/USDT、ETH/USDT、SOL/USDT | 3 | USDT | BTC/USDT | 三大主流 |
| `CRYPTO_TOP_5` | + BNB/USDT、XRP/USDT | 5 | USDT | BTC/USDT | 头部 5 只 |
| `CRYPTO_TOP_10` | + DOGE、ADA、AVAX、LINK、DOT | 10 | USDT | BTC/USDT | 多元化版本（部分 alt 2021 后才上市） |

### 暂未注册（等数据可得性确认）

| 候选 | 用途 |
|---|---|
| `CRYPTO_BTC_ETH_2` | 极简 2 池，对照 A 股 broad_3 |
| `CRYPTO_DEFI_5` | UNI / AAVE / MKR / CRV / COMP（DeFi 板块）|
| `CRYPTO_L1_5` | ETH / SOL / AVAX / DOT / NEAR（L1 公链） |
| `CRYPTO_BTC_VS_GOLD` | BTC / GLD（"数字黄金"假说测试，需跨市场） |

## 适配现有策略到 Crypto

11 个现有 factory 在 crypto 上的可适用性：

| Factory | 直接复用 | 需要适配 | 不适用 |
|---|---|---|---|
| `s3_equal_rebalance` | ✅ | | |
| `s4v2_momentum_tilt` | ✅ | | |
| `s5v2_trend_tilt` | ✅ | | |
| `s7v2_market_ma_filter` | | ⚠️ 信号资产 BTC/USDT 替代 510300 | |
| `s1_dca_basic` | | ⚠️ 月度 DCA 改为周度（crypto 24/7） | |
| `s2v2_dca_swing` | | ⚠️ 同上 | |
| `s6_value_averaging` | | ⚠️ 目标 CAGR 重新定标（crypto 历史 CAGR ~50% vs A 股 ~5%）| |

直接复用 = factory 不改代码；适配 = 改默认参数；不适用 = 概念上不可行（V1 暂无）。

**推荐 V2 起步策略**（覆盖前 4 个 V1 的核心机制）：
- **V2-S1**: `crypto_basket_equal_v1`（S3 同款 + CRYPTO_TOP_5）—— **首推**，最简 baseline
- **V2-S2**: `crypto_dca_basic_v1`（S1 同款 + 周度 DCA + USDT cash）
- **V2-S3**: `crypto_btc_ma_filter_v1`（S7 同款 + BTC 200日 MA）
- **V2-S4**: `crypto_trend_tilt_v1`（S5v2 同款 + 连续趋势）
- **V2-S5**: `crypto_momentum_tilt_v1`（S4v2 同款 + 横截面动量）

## 与 V1 的关系

- **共享代码**：所有 strategy class、factor、universe 工具，无新代码需求
- **不同 docs**：V2 有自己的 `docs/benchmark_suite_v2_crypto.md`（本文）+ 自己的策略 idea/summary
- **slug 命名**：建议加 `crypto_` 前缀避免与 V1 冲突（如 `crypto_basket_equal` vs V1 的 `cn_etf_overseas_equal`）
- **编号体系**：V2 单独从 S1 起编号，命名 `V2-S{N}` 避免与 V1 S1-S8 撞号

## V2 启动 checklist

- [ ] 在 `universes.py` 注册 `CRYPTO_TOP_3` / `CRYPTO_TOP_5` / `CRYPTO_TOP_10`
- [ ] 测试 `CryptoLoader` 拉取 `BTC/USDT`、`ETH/USDT` 等是否顺畅（rate limit / 数据质量）
- [ ] 预拉 V2 universe 全部标的的 1d / 4h 数据到本地缓存
- [ ] 写 V2-S1 (`crypto_basket_equal`) idea/summary，跑首次回测建立 V2 baseline
- [ ] 用 `sweep()` 工具在 crypto universe 上做与 V1 同形式的 4×3 grid（4 策略 × 3 池）
- [ ] 把 V1 的「池子 >> 信号 >> 仓位」假设在 crypto 上独立验证

## 已知风险与挑战

1. **数据质量**：alt 标的历史短、合约换名（如 LUNA → LUNC）、跑路标的（FTT、UST）会污染回测
2. **24/7 vs A 股的特殊性**：vbt 默认假设交易日历，crypto 数据需要按真实时戳；可能需要修改 `vbt.Portfolio.from_orders` 的 `freq` 参数
3. **波动率量级差异**：BTC 年化 60-80% vol vs A 股 ETF 15-20% vol —— 同样的「20% 偏离阈值」在 crypto 上可能每天触发
4. **基准选择争议**：BTC BH 是 crypto 默认基准但偏 single asset；可考虑用 CRYPTO_TOP_5 等权作为多元化基准
5. **样本期短**：2021-2024 仅 4 年，且 2021 是疯狂牛市顶部样本——会过度乐观

## 期望的可迁移结论

如果 V1 的「池子 >> 信号 >> 仓位」是普适规律，那么在 crypto 上：
- ✅ S3 等权基线（V2-S1）应当跑赢绝大多数复杂策略
- ✅ 横截面动量（V2-S5）效果应弱（对 crypto 现象级暴涨标的尤甚）
- ✅ 趋势退出（V2-S4 / V2-S3）在 crypto 大波动下应当比 A 股更有效（高 vol + 长趋势）

如果**这些都不成立**，说明 V1 的发现是 A 股市场结构特定的；需要修订对「池子选择」的认知。

---

**本文档不上 git 索引中（不是策略 idea），但 V2 启动后所有具体策略都引用本文做共享基线。**
