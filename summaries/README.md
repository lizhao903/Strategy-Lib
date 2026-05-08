# Summaries — 策略实现与验证总结库

存放**已进入实现阶段**的策略的实战记录。从写第一行因子代码、跑 IC、调参、回测、到最终结论或废弃，全部留痕。slug 与 `ideas/` 中保持一致。

## 目录结构

```
summaries/
├── README.md
├── _template/                   # 复制这个建新策略目录
│   ├── implementation.md
│   ├── validation.md
│   └── conclusion.md
└── S{N}_<strategy_slug>/        # N = 策略编号；版本在子目录区分
    ├── README.md                # 该策略的版本索引（每版一行结论）
    ├── v1/                      # 第一版
    │   ├── implementation.md    # 怎么实现的（因子、配置、坑）
    │   ├── validation.md        # IC、分组、回测、参数敏感性
    │   ├── conclusion.md        # 是否上线、关键经验、下一步
    │   ├── validate.py          # 可复跑的验证脚本
    │   └── artifacts/           # 关键图表、CSV、回测序列化结果
    └── v2/                      # 第二版（如有改进）
        └── ...
```

## 三个文件的分工

| 文件 | 写什么 | 何时更新 |
|---|---|---|
| `implementation.md` | 因子选型/新增、配置文件路径、关键代码改动、踩过的坑 | 每次代码改动后立刻补 |
| `validation.md` | IC、分组累计收益、敏感性、样本外、不同市场环境表现 | 每次跑出新结果就追加（带日期） |
| `conclusion.md` | 最终结论、是否上线、归档原因、可复用经验 | 策略状态确定时写一次 |

## 写作原则

- **写给三个月后的自己看**。结论要明确，不要写「效果还行」，要写「Sharpe 1.2，最大回撤 18%，2022 失效」
- **数据有源**。引用具体回测的 commit hash + 配置文件路径，结果文件留在 `artifacts/`
- **失败也写**。被废弃的策略也要 `conclusion.md`，写明为什么废弃。下次别人（或你自己）想起类似想法时能查到

## 总结索引

> 新增策略后在此追加：`- [slug](slug/) — 一句话结论（Sharpe/回撤/状态）`

<!-- 索引开始 -->

### Benchmark Suite V1 — A股 ETF 基准对照组（基线见 [docs/benchmark_suite_v1.md](../docs/benchmark_suite_v1.md)）

> 状态说明：smoke = 仅合成数据 mechanical 测试通过；real-data = 已跑真实数据回测；shipped = 已结论；shelved = 暂搁置

### Benchmark Suite V1 真实回测结果（2020-01-02 ~ 2024-12-31, init=100k）

> ★ = 该指标的当前最佳。**v2 是 V1 第二轮迭代**，每个策略 v2 在 vs v1 节单独对比。

| # | 版本 | NAV | CAGR | Sharpe | MaxDD | vs S3 alpha/yr | vs BH alpha/yr | status |
|---|---|---:|---:|---:|---:|---:|---:|---|
| BH | 510300 buy-and-hold | 104.3k | +0.86% | 0.18 | -44.8% | -1.51% | (基准) | benchmark |
| S1 | [v1](S1_cn_etf_dca_basic/v1/) | 89.6k | -2.25% | -0.01 | -45.1% | -4.62% | -3.11% | shipped (negative) |
| S2 | [v1](S2_cn_etf_dca_swing/v1/) | 113.8k | +2.75% | 0.15 | -37.1% | +0.38% | +1.89% | shipped |
| S2 | [v2](S2_cn_etf_dca_swing/v2/) | 114.2k | +2.82% | 0.16 | -35.1% | (~) | +1.96% | shelved |
| S3 | [v1](S3_cn_etf_equal_rebalance/v1/) | 111.9k | +2.37% | 0.26 | -45.2% | (baseline 6 池) | +1.51% | shipped |
| S4 | [v1](S4_cn_etf_momentum_tilt/v1/) | 98.6k | -0.30% | 0.11 | -48.7% | -2.56% | -1.05% | shelved |
| S4 | [v2](S4_cn_etf_momentum_tilt/v2/) | **★130.7k** | **★+5.75%** | **★0.44** | -22.2% | -1.06% (11 池) | **★+4.89%** | shipped (pool value) |
| S5 | [v1](S5_cn_etf_trend_tilt/v1/) | 120.3k | +3.92% | 0.28 | -47.8% | +1.31% | +2.60% | shelved\* |
| S5 | [v2](S5_cn_etf_trend_tilt/v2/) | 112.9k | +2.57% | 0.28 | -20.5% | +0.41% | +1.71% | shelved\*\* |
| S6 | [v1](S6_cn_etf_value_averaging/v1/) | 82.9k | -3.82% | -0.20 | -44.4% | -6.19% | -4.68% | shipped(partial)\*\*\* |
| S7 | [v1 lag=2 6池 (默认)](S7_cn_etf_market_ma_filter/v1/) | 108.1k | +1.64% | 0.18 | -30.3% | -0.73% | +0.78% | shelved |
| S7 | [v2 lag=1 11池](S7_cn_etf_market_ma_filter/v2/) | 119.0k | +3.70% | 0.40 | **★-17.5%** | +1.54% | +2.84% | shipped\*\*\*\* |
| - | (新基线) S3 等权 11 池 | 134.3k | +6.36% | 0.465 | -22.9% | +4.20% | +5.50% | (S8 已派生) |
| **S8** | [v1 cn_etf_overseas_equal](S8_cn_etf_overseas_equal/v1/) | **★171.3k** | **★+11.87%** | **★0.851** | -20.9% | (基准 ~) | **★+11.01%** | validating\*\*\*\*\* |
| **S9** | [v1 crypto_basket_equal](S9_crypto_basket_equal/v1/) (V2-S1) | **2,282.6k**\*\*\*\*\*\* | **+118.46%** | **1.410** | -78.9% | (跨市场) | **+84.84%** vs BTC BH | shipped (in-sample) |
| **S10** | [v1 crypto_momentum_tilt](S10_crypto_momentum_tilt/v1/) (V2-S4) | **3,138.2k** | **+136.55%** | **1.511** | -77.1% | +18.08% vs V2-S1 | **+102.93%** vs BTC BH | shipped (in-sample, outlier-dependent) |
| **S11** | [v1 crypto_btc_ma_filter](S11_crypto_btc_ma_filter/v1/) (V2-S2, MA=100) | **3,511.7k** | **+143.28%** | **★1.951** | **★-43.4%** | +24.82% vs V2-S1 | **+109.66%** vs BTC BH | shipped (in-sample, MA-tuned) |
| **S12** | [v1 crypto_trend_tilt](S12_crypto_trend_tilt/v1/) (V2-S3) | 377.1k | +39.32% | 1.373 | **★-34.6%** | -79.14% vs V2-S1 | +5.70% vs BTC BH | shelved (no alpha, niche risk-budget use) |

> S5v1 shelved\* 原因：超额来自 2024 单边而非 2022 避险（cash 与下跌相关性 0.033）
> S5v2 shelved\*\* 原因：避险数据兑现（2022 -7.6% vs v1 -21.6%、MaxDD 砍半），但 Sharpe 持平 0.28 没产生新 alpha；bond overlay 占 37% 仓位漂移成股债混合
> S6 shipped(partial)\*\*\* 原因：VA 机制对称完美兑现（高抛/低吸 0:0 vs S2 11.80:1）但 NAV 全程低于目标 → SELL 从未触发；6 ETF 池结构性多头偏置在 S2 与 S6 上同源重现，问题在池子不在框架
> S7 v2 shipped\*\*\*\* 仅相对 v1 默认；**vs S3 等权 11 池 (NAV 134.3k) 跑输 -2.66%/yr** —— S7 v2 ablation 首次直测 S3 11 池等权，揭示这是当前 best 策略（已派生 S8）
> S8 validating\*\*\*\*\* 全维度第一（NAV 171.3k / Sharpe 0.85）但样本来自 universe_sweep_demo，未做专门 dedicated run；OOS 风险大（2020-2024 是「A 股最弱+美股最强」窗口），**ship 前必须 OOS**
> S9 shipped(in-sample)\*\*\*\*\*\* 单位 USDT；窗口 2021-2024 (4y)；**alpha 主要来自 2021 SOL 100x**，去 SOL 后 crypto_btc_eth_2 仅 +43% CAGR；OOS 风险高；2022 -71% 单年回撤反映 crypto 内部相关性高（等权 ≠ 真多元化）
> S10 shipped(in-sample, outlier-dependent) 单位 USDT；窗口 2021-2024 (4y)；**alpha 拆分：83% 来自池子+等权（V2-S1 已吃下），momentum 信号增量仅 17%（+18 pp/yr）**；NO_SOL ablation 翻负（-2.19 pp）证明信号 alpha 高度依赖 SOL outlier；TOP_10 alpha (+30 pp) > TOP_5 (+18 pp) 反映横截面分散度 → z-score 信息密度的正向关系
> S11 shipped(in-sample, MA-tuned) **V2 系列 risk-eff 最佳**：Sharpe **1.951** + MaxDD **-43.4%** + 2022 单年 **0.0%**（全年 OFF）；**关键发现：crypto 最佳 MA=100，V1 默认 200 在 crypto 错误**（CAGR 144% vs 45%）；**timing 在 crypto 比 A 股显著有效**（V1 S7v2 A 股 alpha +1.5 pp vs V2-S2 crypto +24.8 pp）；如果只 ship 一个 V2 策略应当是 V2-S2
> S12 shelved (risk profile shifter, no alpha) Calmar 1.14 输给 V2-S1 (1.50) / V2-S2 (3.30) / V2-S4 (1.77)，CAGR +39% vs V2-S1 +118% 损失 ~80 pp；**唯一独特卖点：MaxDD -34.6% 是 V2 系列最低 + Vol 27% 量级最低**；vol_high=0.30 (V1 默认) 偶然就是 crypto risk-eff 最优（与 V2-S2 MA=100 ≠ V1 默认形成对照）；niche use only（risk budget 极严的资金）；trend_tilt + vol_filter 在 crypto 不产生新 alpha（与 V1 S5v2 在 A 股一致）

**v1 → v2 跨版本核心学习**：
1. **S2v2 失败的发现 > S2v2 成功的指标**：「DCA 框架下追求对称做T 是矛盾命题」——只要 DCA 净流入存在，上沿偏置结构性不可消除
2. **S4v2 的 alpha 73% 来自扩池（6→11 跨资产），27% 来自参数调整**：动量 tilt 在 A 股 ETF 上**第二次被证伪**（α=0 仍最优）。真正的价值在「**11 池 + S3 等权**」这个新 baseline，不在动量信号
3. **S5v2 避险来自结构性降仓 sizing 而非精准 timing**：cash_ratio 双峰 → 连续（5-95% 区间天数 0% → 70.2%）、MaxDD 砍半 -47.8% → -20.5%（**5 策略中最佳**）；但本质是 vol-target portfolio 切换 risk profile，不是新 alpha

**当前最佳配置（更新 2026-05-08，含 S7 v2 ablation 发现）**：
- 🏆 **总收益 / Sharpe / alpha**：**S3 等权 11 池**（CAGR +6.36% / Sharpe 0.465 / NAV 134.3k）—— 待派生为 S8 ship
- 🏆 **最低回撤**：**S7 v2 lag=1 11池**（MaxDD -17.5%）—— 7 策略最佳
- 🥈 总收益备选：S4v2 momentum 11 池（CAGR +5.75% / Sharpe 0.44）—— 但 v2 报告已说 73% alpha 来自池子，所以本质等同 S3 11 池
- 🥈 防御备选：S5v2（trend + vol filter，MaxDD -20.5%）

**核心结论**（多策略多 ablation 反复印证）：**池子选择 >> 信号选择 >> 仓位选择**。
扩池 6→11 是当前所有 alpha 来源的根本；timing/factor/sizing 在 11 池基础上的边际价值都 ≤ 0。

**S6/S7 跨版本核心学习**：
1. **S6 VA**：机制对称完美兑现，但 6-ETF 池结构性多头偏置使「实际 NAV 全程低于任一目标 CAGR 路径」→ **VA 与 DCA 在该池上同源失败，根源是池子**
2. **S6 反直觉敏感性**：cagr_target 越激进（12%）反而 NAV 越高 → 真 alpha 是「2022 前满仓时机」，不是 VA 节奏
3. **S7 大盘 MA**：2022 单年 -0.02%（5 策略最佳），但 5 年 NAV 跑输 S3，且 OFF↔BH 跌相关性仍仅 0.052（仅略优于 S5 的 0.03）→ **timing 类避险在 A 股需要更快信号（ATR / 价格突破带宽），MA 类无论 1 个还是 N 个信号都滞后**
4. **S7 sensitivity 推翻事前**：默认 lag=2 跑输 S3，**lag=1 才是真最佳**（NAV 119k）→ 滞后过滤反而损害收益
<!-- 索引结束 -->
