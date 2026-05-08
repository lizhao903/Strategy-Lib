---
slug: cn_etf_market_ma_filter
created: 2026-05-08
updated: 2026-05-08
config_path: configs/S7_cn_etf_market_ma_filter_v1.yaml
related_idea: ideas/S7_cn_etf_market_ma_filter/v1/idea.md
---

# Implementation — Strategy 7 v1：A股 ETF 大盘 MA 过滤

## 整体方案

**新策略类**（不继承 S3）：`src/strategy_lib/strategies/cn_etf_market_ma_filter.py`
→ `MarketMAFilterStrategy`

**为什么不继承 EqualRebalanceStrategy？**
S3 的核心是「按再平衡日历产生稀疏权重 panel（NaN 表示不下单）」，而 S7 是
「逐日产生密集权重 panel（每日都有 0/1 状态切换）」。两者结构差异大，独立
实现更清晰。但下游回测引擎完全一致：`vbt.Portfolio.from_orders +
size_type="targetpercent" + cash_sharing=True`，与 S3/S4/S5 保持回测可比。

核心流程：

1. **`build_signal(panel)`** —— 生成两条信号序列：
   - `raw_signal`：`close_510300[t] > MA_N[510300, t]` 的 0/1 序列。MA 暖机期 = 0
   - `signal`（filtered）：滞后过滤 —— 连续 `lag_days` 日同向才切换（粘滞）
2. **`build_target_weight_panel(panel, signal)`** —— 逐日权重 DataFrame：
   - 信号 ON → risky pool 等权（6 只 ETF 各 1/6，cash_symbol = 0）
   - 信号 OFF → cash_symbol 100%（risky 全 0）
   - 每日 sum = 1，无 NaN（与 S3 的「触发日才有值」不同）
3. **`run(panel, init_cash, fees, slippage, signal_lag=1)`** —— vbt 主回测：
   - `weights.shift(signal_lag).fillna(0)` 把 t 日权重错位到 t+1 → 防 lookahead
   - 头 `signal_lag` 行手动设为 cash 100%（避免 NaN 全 0 被解读为全清仓）

## 因子清单

| Factor 类 | 文件 | 参数 | 方向 | 是新增还是复用 |
|---|---|---|---|---|
| **N/A** | — | — | — | **本策略不使用任何 Factor 类**（直接 close.rolling(N).mean()） |

设计上故意不依赖 `factors/trend.py` 的 `MABullishScore` / `DonchianPosition`：
- S7 命题是「单一市场信号」，不需要多因子组合
- 简化超参空间：只有 `ma_length` 和 `lag_days` 两个核心参数
- 与 S5（MA + Donchian + cutoff + score_weights）形成对比，**S7 是更简的版本**

## 新增因子（如有）

无。S7 v1 完全用 pandas 原生 rolling.mean() 实现 MA，避免引入新的 Factor 类。

## 策略配置

- 配置文件：`configs/S7_cn_etf_market_ma_filter_v1.yaml`
- 类型：`market_ma_filter`（自定义；非现有 single_threshold/cs_rank/weight_based）
- 关键参数：
  - `signal_symbol: "510300"`（沪深300 大盘代理）
  - `cash_symbol: "511990"`（华宝添益货币基金，risk-off 时 carry ~2%/yr）
  - `ma_length: 200`（Faber 经典；同时跑 100/150/200/250 敏感性）
  - `lag_days: 2`（连续 2 日同向才切换；同时跑 1/2/3/5 敏感性）
  - `weight_mode: "equal"`（risk-on 时 6 ETF 等权 1/6）
- 标的池：6 只 risky ETF（V1 baseline）+ 1 只 cash ETF
- 回测参数：100k / fees=0.00005 / slippage=0.0005（V1 共享基线）

## 数据

- 数据范围：2019-07-01（暖机 200MA） ~ 2024-12-31
- 来源：本地缓存 `data/raw/cn_etf/{510300,510500,159915,512100,512880,512170,511990}_1d.parquet`
- 复权：前复权（akshare qfq）
- 共同交易日历：取 risky 6 池 + cash_symbol 的 index 交集

## 信号生成实现细节

### 滞后过滤的粘滞行为
当 `lag_days = N > 1` 时：
- 滚动窗口大小 = N
- 窗口内 raw 全 1 → filtered 切到 1
- 窗口内 raw 全 0 → filtered 切到 0
- 否则 filtered 保持上一日（粘滞）

这样确保单日穿越 / 反复穿越**不会**触发切换，只有信号"稳定"了才动。
副作用：每次切换会延迟 N-1 天（这是用噪音过滤换的代价）。

### lookahead 防护
1. `raw_signal[t]` 只用 `close[≤t]` 计算（rolling.mean 默认右对齐）
2. `weights[t]` 是 `signal[t]` 决定的目标仓位
3. `weights.shift(1)` 把 weights[t] 错位到 t+1 → vbt 在 t+1 bar 用 close[t+1] 成交
4. 等价于「t 日信号、t+1 日开盘成交」（以 close 近似）

## 不变量（v2 子类如果出现请遵守）

- **每日权重 sum == 1**：要么 risky ON 要么 cash ON，无中间态（与 S5v2 连续 ramp 不同）
- **从 risk-off 启动**：策略首日强制 cash 100%（避免 shift 导致首日全空仓）
- **信号 ↔ 持仓解耦**：signal_symbol 可以与 risky symbols 完全无交集（虽然 v1 默认 510300 在两者中）

## 踩过的坑

- **`weights.shift(1)` 头 N 行变 NaN→0 → vbt 解读为全清仓**：vbt 看到 size=0
  会执行清仓而不是「保持现状」。手动把头 signal_lag 行设为 cash 100% 避免
  这个边界 bug（影响微弱但严重的话会导致首日就开/平仓多吃一笔成本）。
- **滞后过滤的"暖机"**：rolling(N) 在前 N-1 天返回 NaN。我把这段强制保持
  `last=0`（默认 risk-off）—— 与「策略保守启动」的逻辑一致。
- **信号资产 ≠ 持仓资产时的资产对齐**：`_all_assets()` 自动把 signal_symbol、
  symbols、cash_symbol 去重合并，避免 signal 资产没在 vbt portfolio 里 → 取
  close 时 KeyError。v1 默认 510300 既是信号也是持仓，这个 bug 不会触发，但
  代码已防御性写好。
- **`pf.value()` 返回类型**：cash_sharing=True 时返回 Series；某些 vbt 版本
  返回单列 DataFrame。统一在外面 `if isinstance(eq, DataFrame): eq = eq.iloc[:, 0]`
  防御性处理（沿用 S3/S5 v2 的模式）。

## 与 S5 实现的对比

| 维度 | S5 (trend_tilt) | S7 (market_ma_filter) |
|---|---|---|
| 父类 | EqualRebalanceStrategy (S3) | 独立类 |
| 信号源 | 6 个 ETF 各自的 trend_score | 1 个市场代理（510300）的 close vs MA |
| 信号数量 | 6（每只 ETF 一个） | 1（全局） |
| 权重生成时机 | 每 rebalance_period 触发 | 每日（连续） |
| 权重连续度 | v1 双峰、v2 连续 ramp | 二元（0 或 1/N） |
| 因子依赖 | MABullishScore + DonchianPosition | 无 |
| 超参数 | ma_short/mid/long + donchian + cutoff + score_weights (5+) | ma_length + lag_days (2) |
| 切换次数（5y） | 每 20 日重算 = 60+ 次评估 | 25 次实际切换 |

## 相关 commits

- 实现：`<待提交>`
