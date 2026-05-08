# Ideas — 策略想法库

存放**所有未实现 / 进行中 / 已实现**的策略想法。每个策略一个子文件夹（slug 命名，如 `btc_momentum_rsi`）。

## 目录结构

```
ideas/
├── README.md                # 本文件 + 想法索引
├── _template/               # 创建新想法时复制这个目录
│   └── idea.md
└── S{N}_<strategy_slug>/     # N = 策略编号；版本在子目录区分
    ├── README.md             # 该策略的版本索引（可选，多版本时建议）
    ├── v1/
    │   ├── idea.md           # 核心：想法本身（必需）
    │   └── notes.md          # 与 AI 或自己讨论留下的笔记（可选）
    └── v2/                   # 后续版本（如有改进想法）
        └── ...
```

## 工作流

1. **新想法**：复制 `_template/` 为 `ideas/<your_slug>/`，填写 `idea.md`
2. **持续讨论**：在 `notes.md` 里追加新发现、问题、修订（带日期），不要覆盖原始 idea
3. **进入实现**：实现完成后，去 `summaries/<your_slug>/` 建对应总结目录
4. **状态流转**：在 `idea.md` 顶部 `status` 字段维护当前阶段

## 命名约定

`<market>_<core_logic>[_<filter>]`，全小写下划线，例如：
- `btc_momentum_rsi` —— Crypto 上的动量+RSI 过滤
- `cn_etf_rotation_lowvol` —— A股 ETF 低波轮动
- `us_etf_dual_momentum` —— 美股 ETF 双动量

## 想法索引

> 新增策略后在此追加一行：`- [slug](slug/idea.md) — 一句话概述 — status`

<!-- 索引开始 -->

### Benchmark Suite V1 — A股 ETF 基准对照组（基线见 [docs/benchmark_suite_v1.md](../docs/benchmark_suite_v1.md)）

- [S1 cn_etf_dca_basic](S1_cn_etf_dca_basic/v1/idea.md) — 货币基金 + 风险池等额定投 — v1 shipped (CAGR -2.25%, 跑输 BH)
- [S2 cn_etf_dca_swing](S2_cn_etf_dca_swing/v1/idea.md) — DCA + 阈值偏离触发部分做T — v1 shipped (CAGR +2.75%) / v2 shelved (DCA 不对称是结构性矛盾)
- [S3 cn_etf_equal_rebalance](S3_cn_etf_equal_rebalance/v1/idea.md) — 6 只 ETF 等权满仓 + 定时再平衡，target_weights 钩子 — shipped (CAGR +2.37%, S4/S5 baseline)
- [S4 cn_etf_momentum_tilt](S4_cn_etf_momentum_tilt/v1/idea.md) — z-score 线性倾斜动量因子 — v1 shelved (IR=-0.49) / **v2 shipped(pool value)** CAGR +5.75% (扩池贡献 73%)
- [S5 cn_etf_trend_tilt](S5_cn_etf_trend_tilt/v1/idea.md) — MA多头+Donchian 趋势倾斜 — v1 shelved (避险命题未兑现) / v2 shelved (兑现但无新 alpha, **MaxDD -20.5% 最佳**)
- [S6 cn_etf_value_averaging](S6_cn_etf_value_averaging/v1/idea.md) — 价值平均法 (VA) 跳出 DCA 框架 — shipped(partial) (机制对称 0:0 但 NAV 全程低于目标→揭示池问题)
- [S7 cn_etf_market_ma_filter](S7_cn_etf_market_ma_filter/v1/idea.md) — 510300 200MA 二元 ON/OFF — v1 shelved (lag=2 6池) / **v2 shipped** (lag=1 11池, MaxDD -17.5% 最佳；但 vs S3 11池 baseline -2.66%/yr → 揭示 S8 候选)
- [S8 cn_etf_overseas_equal](S8_cn_etf_overseas_equal/v1/idea.md) — S3 等权 + 4 池（恒生+纳指+标普500+黄金，**无 A 股**）— validating（Sharpe **0.85** 全维度第一，OOS 风险高，未做 dedicated run）
- [S9 crypto_basket_equal](S9_crypto_basket_equal/v1/idea.md) (V2-S1) — Crypto 头部 5 只等权（BTC/ETH/SOL/BNB/XRP）— **shipped (in-sample)** Sharpe **1.41** / NAV 22.8x / vs BTC BH **+84.84%/yr**；2022 -71% / OOS 风险大
- [S10 crypto_momentum_tilt](S10_crypto_momentum_tilt/v1/idea.md) (V2-S4) — V1 S4v2 横截面动量倾斜套到 Crypto TOP_5 — **shipped (in-sample, outlier-dependent)** Sharpe **1.51** / NAV 31.4x / vs BTC BH **+102.93%/yr** / vs V2-S1 **+18.08%/yr**；NO_SOL ablation 翻负证 alpha 高度依赖 SOL outlier
- [S11 crypto_btc_ma_filter](S11_crypto_btc_ma_filter/v1/idea.md) (V2-S2) — V1 S7v2 BTC 200日MA 二元 ON/OFF 套到 Crypto TOP_5（推荐 MA=100）— **shipped (in-sample, MA-tuned)** Sharpe **★1.95** / NAV 35.1x / MaxDD **★-43.4%** / 2022 单年 **0.0%**；**核心发现：crypto 最佳 MA=100 而非 V1 默认 200**；timing 在 crypto 比 A 股显著有效；含 USDT 合成工程修复
- [S12 crypto_trend_tilt](S12_crypto_trend_tilt/v1/idea.md) (V2-S3) — V1 S5v2 连续趋势 + vol filter 套到 Crypto — **shelved (risk profile shifter)** Sharpe 1.37 / NAV 3.77x / MaxDD **★-34.6%**（V2 系列最低）；Calmar 1.14 输给 V2-S1 / V2-S2 / V2-S4；vol_high=0.30 (V1 默认) 偶然在 crypto 仍最优；niche use only
<!-- 索引结束 -->
