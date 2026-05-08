# Benchmark Suite V1 — A股 ETF 基准策略组

5 个互相对照的基准策略，用于评估「DCA / Rebalance / 因子加权」三类思路的相对优劣。所有策略共享一致的资金、标的池、回测窗口和基准，结果可直接横向对比。

## 共享基线（所有 5 个策略必须遵守）

| 项 | 值 |
|---|---|
| 初始资金 | 100,000 RMB |
| 市场 | A股 ETF (`market: cn_etf`) |
| 货币基金（现金等价） | `511990` 华宝添益（场内货币ETF，T+0、年化 ~2%） |
| 风险资产池（6 只） | `510300` 沪深300 / `510500` 中证500 / `159915` 创业板 / `512100` 中证1000 / `512880` 证券 / `512170` 医疗 |
| 回测窗口 | 2020-01-01 ~ 2024-12-31（含疫情、2021 抱团、2022 熊市、2023-24 震荡）|
| 数据频率 | 日线（`1d`） |
| 基准 (Benchmark) | `510300` 买入持有 |
| 交易成本 | 佣金 万 0.5（fees=0.00005），滑点 万 5（slippage=0.0005） |
| 复权 | 前复权（akshare `qfq`） |

## 5 个策略（与 slug）

| # | 策略名 | slug | 一句话核心 |
|---|---|---|---|
| 1 | 基础 DCA | `cn_etf_dca_basic` | 货币基金 + 风险资产池等额定投，不做主动调仓 |
| 2 | DCA + 阈值再平衡（做T） | `cn_etf_dca_swing` | 在 1 基础上，资产偏离目标比例触发部分减/加仓 |
| 3 | 等权 + 定时再平衡 | `cn_etf_equal_rebalance` | 6 只 ETF 等权满仓，定时再平衡，无现金缓冲 |
| 4 | 等权 + 动量倾斜 | `cn_etf_momentum_tilt` | 在 3 基础上，按动量因子调高/调低各资产权重 |
| 5 | 等权 + 趋势倾斜 | `cn_etf_trend_tilt` | 在 3 基础上，用趋势强度（MA/ADX）调整权重 |

## 验证统一指标（每个策略的 validation.md 必须给出）

- 最终净值 / 总收益
- 年化收益（CAGR）
- 年化波动 / Sharpe
- 最大回撤 / Calmar
- 换手率（年化）
- 与基准（510300 BH）对比：超额收益、信息比率、跟踪误差
- 分年度收益（2020/2021/2022/2023/2024）

## 关键设计原则

1. **资金一致**：所有策略起点都是 100k RMB，全部进入策略管理（其中现金等价部分自动存入 511990）
2. **避免未来函数**：当日信号最早在次日开盘成交（实务可用 `shift(1)`）
3. **统一交易成本**：避免成本差异掩盖策略差异
4. **文档留痕**：每个策略走 `ideas/<slug>/` → `summaries/<slug>/` 完整链路

## 与现有框架的关系

注意：现有 `BaseStrategy` 是**信号驱动**（entries/exits → `vbt.Portfolio.from_signals`），而本组 5 个策略大多是**权重驱动**（定期产生目标权重 → `vbt.Portfolio.from_orders`）。允许新建并行的 weight-based 策略基类，或在每个策略类内部直接用 vectorbt API。

## 索引到各策略

- [Strategy 1 — DCA basic](../ideas/S1_cn_etf_dca_basic/v1/idea.md)
- [Strategy 2 — DCA swing](../ideas/S2_cn_etf_dca_swing/v1/idea.md)
- [Strategy 3 — Equal rebalance](../ideas/S3_cn_etf_equal_rebalance/v1/idea.md)
- [Strategy 4 — Momentum tilt](../ideas/S4_cn_etf_momentum_tilt/v1/idea.md)
- [Strategy 5 — Trend tilt](../ideas/S5_cn_etf_trend_tilt/v1/idea.md)

## 真实数据回测结果（2026-05-08 完成）

完整结果与 artifacts 见各策略 `summaries/<slug>/validation.md`。横向对比表：

| # | NAV (start 100k) | CAGR | Sharpe | MaxDD | vs S3 alpha/yr | vs BH alpha/yr | status |
|---|---:|---:|---:|---:|---:|---:|---|
| BH 510300 | 104.3k | +0.86% | 0.18 | -44.8% | -1.51% | (基准) | benchmark |
| S1 DCA basic | 89.6k | -2.25% | -0.01 | -45.1% | -4.62% | -3.11% | shipped (跑输) |
| S2 DCA swing | 113.8k | +2.75% | 0.15 | **-37.1%** | +0.38% | +1.89% | shipped |
| S3 Equal rebal | 111.9k | +2.37% | **0.26** | -45.2% | (baseline) | +1.51% | shipped |
| S4 Momentum | 98.6k | -0.30% | 0.11 | -48.7% | **-2.56%** | -1.05% | shelved |
| S5 Trend | **120.3k** | **+3.92%** | **0.28** | -47.8% | +1.31% | **+2.60%** | shelved* |

\* S5 shelved 原因：超额来自 2024 单边行情而非 2022 避险，**下行保护命题未兑现**（2022 年 S5 -21.6% vs BH -21.7%）。

### 关键学习

1. **DCA 现金缓冲的 alpha 主要靠"再平衡"而非"DCA 节奏"**：S1 缓冲耗尽后退化、S2 阈值再平衡贡献了 alpha
2. **A股 ETF 池（6 只宽基+行业）上横截面 20 日动量系统性反向**：S4 五档 α × 三档 lookback 共 8 次实验 IR 全负，方向稳定（非随机）
3. **趋势退出在 A 股 ETF 边际有效但避险命题未兑现**：cash_days_ratio=18%，但与 BH 当日下跌相关性仅 0.033（接近随机）
4. **vbt `from_orders(targetpercent)` 兼容 sum<1**：S5 已实测验证，缺失部分自动留作现金（S3 父类无需修改）
5. **S3 父类 `run()` 未做 `shift(1)`**：等权策略不受影响；价格信号策略（S4/S5）需在子类内自行切片避免 lookahead

### 待跟进

- ~~S2 阈值/cooldown 敏感性测试~~ → **S2v2 已做**：组合 A+C 改进，结论 shelved（KPI 未改善，揭示 DCA 不对称为结构性矛盾）
- ~~S4 v2~~ → **S4v2 已做**：扩池 6→11 + shift(1) + lookback=120 + vol-adjusted，shipped(pool value)，但揭示 73% alpha 来自扩池而非动量信号
- ~~S5 v2~~ → **S5v2 已做**：连续 ramp + vol filter + bond overlay，shelved（避险兑现但无新 alpha）
- 样本外测试：2025 H1 数据（如可得）

## v2 实验回报（2026-05-08）

| 策略 | v1 → v2 关键变化 | 命题是否成立 |
|---|---|---|
| S2 (DCA swing) | + DCA 三态 + vol-adapt band → 高抛/低吸比仅 11.69 (v1 11.80) | ❌ DCA 框架下结构性不可对称 |
| S4 (Momentum tilt) | + 11 池 + shift(1) + lookback=120 → NAV 1.31 / Sharpe 0.44 | ❌ α=0 仍最优；扩池本身是真 alpha 来源 |
| S5 (Trend tilt) | + 连续 ramp + vol filter + 国债 → MaxDD -20.5%（最佳） | ⚠ 避险数据兑现但无新 alpha；本质是 risk profile 切换 |

### v2 派生的 v3 候选

- **S3 v2 (新派生)**：直接采用 S4v2 的 11 池配置 + 等权满仓 + 定时再平衡。S4v2 数据显示这是真正的 alpha 来源，简单胜出
- ~~S2 v3~~ → **已实现为 S6** (`cn_etf_value_averaging`)，shipped(partial)
- ~~S5 v3 (大盘 200MA)~~ → **已实现为 S7** (`cn_etf_market_ma_filter`)，shelved

## V1 扩展策略（S6 / S7，2026-05-08）

S6 与 S7 是基于 V1 v2 失败诊断派生的新框架策略，编号扩展非版本迭代。

| # | slug | 框架变化 | 主结果 | 命题是否成立 |
|---|---|---|---:|---|
| **S6** | cn_etf_value_averaging | DCA → 按目标 NAV 路径调仓（VA） | NAV 82.9k / Sharpe -0.20 / shipped(partial) | ⚠️ 机制层 yes，效果层 no — 6 ETF 池结构性多头偏置使 NAV 全程低于目标 |
| **S7** | cn_etf_market_ma_filter | 逐标的趋势 → 大盘单一 MA200 ON/OFF | NAV 108.1k @ lag=2 / 119.1k @ lag=1 / shelved | ⚠️ 2022 避险完美兑现 (-0.02%) 但 5y NAV 仍跑输 S3，timing 滞后未根治 |

### S6 / S7 派生的 v3 候选

- **S6 v2**：换池（11 跨资产 ETF，参 S4v2）+ 同样 VA 机制 → 首次让 SELL 真正触发，验证 VA 机制在非单边多头池上的对称性
- ~~S7 v2~~ → **已实现并 ship**（lag=1 + 11 池）
- ~~S8 候选~~ → **已派生为 S8** (`cn_etf_overseas_equal`)，但 status=validating（dedicated run 待做、OOS 待做）

## V1 v2 进一步派生（universe sweep 揭示）

2026-05-08 实现 `Universe + sweep` 工具后，4×4 grid 揭示**池子选择是 alpha 的最大来源**，已派生：

- **S8** = S3 等权 + cn_etf_overseas_4（恒生/纳指/标普500/黄金，无 A 股）—— **全维度第一**（NAV 171.3k / Sharpe 0.85 / MaxDD -20.9% / CAGR +11.87%）；OOS 风险高，validating
- **S9** = V2-S1 = crypto_basket_equal（V2 Crypto Suite 的 baseline）—— idea，详见 [docs/benchmark_suite_v2_crypto.md](benchmark_suite_v2_crypto.md)

后续 V2 全套（S9-S13 候选）将系统验证 V1 发现是否是 A 股窗口特定的还是普适规律。

