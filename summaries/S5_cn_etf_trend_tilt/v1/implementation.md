---
slug: cn_etf_trend_tilt
created: 2026-05-08
updated: 2026-05-08
config_path: configs/cn_etf_trend_tilt.yaml
related_idea: ideas/cn_etf_trend_tilt/idea.md
---

# Implementation — A股 ETF 等权 + 趋势倾斜 (S5)

## 整体方案
继承 S3 (`EqualRebalanceStrategy`)，覆盖两个钩子：
1. `target_weights(date, prices_panel)`：核心倾斜逻辑——按每只 ETF 的时序趋势分数分配权重，弱趋势退出。
2. `_validate_weights(weights)`：放宽父类「sum == 1」「禁止全 0」两条约束，使全空仓在熊市可表达。

实现拆分两个独立函数（便于单测）：
- `compute_trend_scores(date, panel) -> pd.Series`：把面板 → 每只 ETF 的标量 trend_score ∈ [-2, +2]
- `_tilt_weights(scores) -> dict`：trend_score → 归一化权重 dict（≤0 的 symbol 不出现）

## 因子清单

| Factor 类 | 文件 | 参数 | 方向 | 是新增还是复用 |
|---|---|---|---|---|
| `MABullishScore` | `src/strategy_lib/factors/trend.py` | `short=20, mid=60, long=120` | +1 | **新增** |
| `DonchianPosition` | `src/strategy_lib/factors/trend.py` | `lookback=120` | +1 | **新增** |

## 新增因子（详细说明）

### `MABullishScore`
```python
score = sign(close > MA_short) + sign(MA_short > MA_mid) + sign(MA_mid > MA_long)
# 取值 ∈ {-3, -1, +1, +3}（中间组合产生 ±1）
```
- **为什么用**：经典趋势跟踪信号。三个二元判断的离散组合，抗参数扰动。
- **暖机期**：`MA_long` 还没 ready 时返回 NaN（被上游处理为「该 ETF 此期间不参与」）。

### `DonchianPosition`
```python
pos = (close - low_N) / (high_N - low_N)  ∈ [0, 1]
# 1.0 = 通道顶端（强势），0.0 = 通道底部（弱势）
```
- **为什么用**：与 MA 系列在数学性质上互补——一个看离散方向，一个看连续位置。Turtle 体系经典指标。
- **除零保护**：通道宽度 = 0（常量价格）时返回 NaN。

### 这两个因子**没有改 `factors/__init__.py`**
按硬约束要求，`factors/__init__.py` 不修改。下游用法：
```python
from strategy_lib.factors.trend import MABullishScore, DonchianPosition  # ✓
# from strategy_lib.factors import MABullishScore  # ✗ 暂不可用，等合并
```
合并到主分支时**外部代理**应在 `factors/__init__.py` 增补两行 import 与 `__all__` 项；本子代理任务范围内不动。

## 关键设计决策

### 1. 全空仓的契约扩展（与 S3 协调点）

S3 当前实现的 `_validate_weights` 强制：
- `sum(weights) == 1.0`（误差 < 1e-6），违反则自动重归一化
- `total <= 0` 抛 `ValueError(f"target_weights 全为 0，无法再平衡")`

S5 需要在熊市返回 `sum < 1` 甚至全 0（全空仓）。**采用方案 B**：在子类覆盖 `_validate_weights`，放宽这两条约束：
- 允许 sum ∈ [0, 1+ε]，**不重归一化**（保留现金留底语义）
- 允许 total == 0（全空仓 → 让 vectorbt 把所有 size 设为 0 → 全平仓）
- 仍然校验非负 / keys ⊂ symbols / sum > 1+ε 时归一化（防御性）

**这是对 S3 钩子契约的扩展**。S3 父类 `build_target_weight_panel` 调用 `target_weights → _validate_weights → 写入 weights_df`，本子类的覆盖刚好生效。已确认 S3 父类不在其他地方再次断言 `sum == 1`。

### 2. 趋势分数的归一化

两个因子的原生量纲不同：
- `MABullishScore` ∈ [-3, +3]
- `DonchianPosition` ∈ [0, 1]

把它们各自映射到 `[-1, +1]` 后等权相加：
- MA：`score / 3` → 截断到 [-1, +1]
- Donchian：`2 * pos - 1` → 截断到 [-1, +1]

最终 `trend_score = w_ma * ma_norm + w_dc * dc_norm`，理论值域 [-2, +2]（默认 score_weights = (1.0, 1.0)）。**好处**：cutoff 阈值在不同标的之间可比；调超参时改 `score_weights` 即可改变两个信号的相对重要性。

### 3. 避免 lookahead

`compute_trend_scores(date, panel)` 内部对每个 symbol 做 `df.loc[df.index <= date]` 切片再算因子，确保 t 时刻只用 t 及之前的数据。S3 父类的 `from_orders` 会在下一根 bar 成交，叠加之后实现 t 信号 → t+1 开盘成交，**无未来函数**。已用 `test_lookahead_bias` 验证（截断 panel 与完整 panel 在同一截止日给出完全相同分数）。

## 策略配置
- 配置文件：`configs/cn_etf_trend_tilt.yaml`
- 类型：`trend_tilt`（自定义；尚未注册到 `strategies/registry.py`，注册由后续 PR 处理）
- 父策略：继承 `cn_etf_equal_rebalance`
- 关键参数：`rebalance_period=20`、`ma_short/mid/long=20/60/120`、`donchian_lookback=120`、`cutoff=0.0`

## 数据
- 标的池：V1 共享基线 6 只 ETF（与 S3 完全一致）
- 数据范围：2020-01-01 ~ 2024-12-31；**额外回拉 6 个月（2019-07-01 起）做暖机**
- 数据预处理：依赖 `data.get_loader('cn_etf')` 的 `qfq` 复权

## 踩过的坑
- **S3 `_validate_weights` 的严格断言**：第一次实现时直接返回 `{}`，但 S3 父类在 `_validate_weights` 里把 `total <= 0` 当成致命错误抛错。最终通过覆盖 `_validate_weights` 解决，没有改 S3 父类。
- **smoke test flake**：最初用 GBM 合成数据，`drift > 0` 也偶发把某些 symbol 在最近一日的 close 推到 MA 下方导致权重变 0。改用纯指数路径（无噪声）做断言，排除随机性。
- **120 日暖机**：MA120 / Donchian120 在数据起点前 120 日均为 NaN，必须让 data loader 多拉至少 120 个交易日（约 6 个月）历史；不然回测开头几个月会被全空仓。

## 与并行实现的对接点
- 等 S3 主线合并：本类的 import `from strategy_lib.strategies.cn_etf_equal_rebalance import EqualRebalanceStrategy` 已经能 resolve（S3 文件已存在于本仓库 `src/strategy_lib/strategies/cn_etf_equal_rebalance.py`）。
- 等 `factors/__init__.py` 合并增补：暂时使用 `from strategy_lib.factors.trend import ...` 直接 import。
- `strategies/__init__.py` 与 `strategies/registry.py` 的注册由集成 PR 统一处理，本子代理范围内不动。

## 相关 commits
- 实现：`<待commit>`

## 2026-05-08 vectorbt sum<1 兼容性验证（事后）

**背景**：S5 允许 `target_weights` 返回 sum<1 的权重 dict（含全空仓），需要先确认 vectorbt 在 `from_orders(size_type="targetpercent", group_by=True, cash_sharing=True)` 模式下能正确把缺失资金留作 cash，而不是错误地分配给某个资产。

**验证脚本**：`/tmp/vbt_subunit_test.py`（临时文件，已用毕）

**关键测试与结果**：
| 测试 | 输入 | 期望 | 实测 |
|---|---|---|---|
| sum=0.6（[0.3, 0.3, 0]） | 三资产 | A=30000, B=30000, C=0, cash=40000 | 完全一致 |
| 全清仓（[0,0,0]） | 先满仓再清仓 | 资产全 0，cash=全 equity | 资产=0, cash=111494（含期间收益） |
| NaN 表示「不下单」 | A=0.3, B=0.3, C=NaN | C 持仓不变 | 行为正确 |

**结论**：vectorbt 完整支持权重和 < 1 的 targetpercent。S3 父类 `run()` 不需任何修改，本子类只覆盖 `_validate_weights` 即可。这扫除了 S5 工程路径上最大风险点。

## 2026-05-08 真实数据回测发现（追加）

- **价值密度命题失败**：原以为 S5 主要靠 2022 熊市避险加分，实际 2022 单年 S5 (-21.61%) 与 BH (-21.68%) 几乎完全重合。S5 vs S3 的超额主要来自 **2024 单年的板块行情**（+19.27 pct）。
- **现金占比是双峰分布而非连续**：cash_ratio 几乎只有 0 / 1 两种状态，因为 `_tilt_weights` 用「正分数 / 正分数和」做归一化——只要有 ≥1 个标的的 trend_score > cutoff，权重和就 = 1。要做出连续的现金缓冲，需要把权重计算改成「正分数 / N」（不归一化）+ 上限 clip，或者引入大盘 trend_score 作为整体仓位调节器。
- **cutoff 灵敏度方向出乎意料**：cutoff 从 0.0 提到 0.3/0.5 反而恶化（CAGR 转负）。说明趋势分数在 [0, 0.3] 区间携带了主要的有用信号——A股 ETF 的「弱趋势但还在涨」比「强趋势」更值得介入。
- **空仓时段命中率低**：220 个全空仓天数与 BH 「当日下跌」的相关性仅 0.033，几乎随机。MA + Donchian 这套信号对 A股快速下跌的反应速度不够。

