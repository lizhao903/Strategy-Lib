---
slug: cn_etf_trend_tilt_v2
created: 2026-05-08
updated: 2026-05-08
config_path: configs/S5_cn_etf_trend_tilt_v2.yaml
related_idea: ideas/S5_cn_etf_trend_tilt/v2/idea.md
parent: cn_etf_trend_tilt (v1)
---

# Implementation — A股 ETF 等权 + 趋势倾斜 v2

## 整体方案
继承 v1 的 `TrendTiltStrategy`（间接继承 S3 `EqualRebalanceStrategy`），覆盖 4 个方法解决 v1 的两大问题：
1. `_tilt_weights`：从「正分数 / 正分数和」（归一化）改成「(score - cutoff) / score_full / N」（不归一化）→ 让 cash 自然存在
2. `compute_trend_scores`：用连续版 MA 因子（tanh 风格）替代 v1 的离散 sign 版；同时跳过 bond_symbol 不参与 trend 排序
3. `target_weights`：在 risky 权重之上叠加（a）波动率过滤（b）债券 overlay
4. `__init__`：透传父类参数 + 新增 v2 的 5 个参数

v1 的 `_validate_weights` 直接复用（v1 已经放宽过 sum<1 的约束）。

## 因子清单

| Factor 类 | 文件 | 参数 | 方向 | 新增/复用 |
|---|---|---|---|---|
| `MABullishContinuous` | `factors/trend.py`（**末尾新增**） | `short=20, mid=60, long=120, k=20` | +1 | **新增** |
| `DonchianPosition` | `factors/trend.py` | `lookback=120` | +1 | 复用 v1 |
| `AnnualizedVol` | `factors/volatility.py`（**末尾新增**） | `lookback=60` | -1 | **新增** |

`factors/__init__.py` **不修改**（按硬约束）。下游直接 import：
```python
from strategy_lib.factors.trend import MABullishContinuous, DonchianPosition
from strategy_lib.factors.volatility import AnnualizedVol
```

## 新增因子（详细说明）

### `MABullishContinuous(short, mid, long, k)`
```python
score = mean( tanh(k * (close/MA - 1)) for MA in (short, mid, long) )
# 取值 ∈ (-1, +1)
```
- **为什么**：v1 的 `MABullishScore` 用 `sign()` 输出 ∈ {-3,-1,+1,+3}，离散阶跃让权重在 ramp 区间瞬变。tanh 把价格相对均线的偏离平滑映射到 (-1, +1)，三层 MA 求平均后仍 ∈ (-1, +1)。
- **k=20 的标定**：`close/MA - 1 = 5%` → `tanh(20·0.05) = tanh(1) ≈ 0.76`。让 5% 偏离对应明显但不饱和的信号；这与 A股 ETF 典型 σ 在 1.5%/天 的 6 小时窗口偏离量级一致。
- **暖机期**：`MA_long` 还没 ready 时返回 NaN。

### `AnnualizedVol(lookback)`
```python
ret = log(close).diff()
vol = ret.rolling(lookback).std() * sqrt(252)
```
- 与 `RealizedVol` 的差别仅在 √252 缩放，便于策略侧直接用 0.30 这种「年化口径」阈值比较。

## 关键设计决策

### 1. 连续 ramp 替代归一化（修复双峰）
v2 的 `_tilt_weights`：
```python
def _tilt_weights(self, scores: pd.Series) -> dict[str, float]:
    valid = scores.dropna()
    n_risky = max(len(valid), 1)
    weights = {}
    denom = self._score_full   # 默认 1.0
    for sym, score in valid.items():
        raw = (score - self._cutoff) / denom
        raw = max(0.0, min(1.0, raw))
        if raw > 0:
            weights[sym] = raw / n_risky
    return weights
```
**关键点**：`weight_i = raw_i / n_risky`，**不再除以 Σraw_j**。score 在 cutoff 与 cutoff+score_full 之间时，权重正比于 score；超过 score_full 饱和到 1/n_risky。

### 2. 波动率过滤（修复避险命题）
```python
def _vol_breadth(self, date, prices_panel) -> float:
    # 池中 vol > vol_high 的资产占比 ∈ [0, 1]
def target_weights(...):
    risky_weights = self._tilt_weights(scores)
    if self._vol_breadth(date, panel) >= self._vol_breadth_threshold:
        risky_weights = {s: w * self._vol_haircut for s, w in risky_weights.items()}
    ...
```
默认 `vol_high=0.30 / vol_breadth_threshold=0.5 / vol_haircut=0.5`：池中 ≥ 50% 的风险 ETF 60 日年化波动 > 30% 时，全体权重 ×0.5。

**与趋势信号正交**：vol filter 不依赖方向判断，只看「整体风险 regime」。这是 vol-target portfolio 的标准思路，弥补 v1 「趋势信号对快速下跌识别滞后」的固有问题。

### 3. bond overlay（修复空仓 carry）
```python
risky_sum = sum(risky_weights.values())
cash_gap = 1.0 - risky_sum
bond_w = min(cash_gap, self._bond_max_weight)
if bond_w > 0.01:
    out[self._bond_symbol] = bond_w
```
`bond_max_weight = 0.4` 是上限——即便 cash_gap = 1（全空仓），bond 也只占 40%，剩余 60% 留作纯现金（防股债同跌）。

bond_symbol 在 `compute_trend_scores` 里被显式跳过——它**不参与 trend 排序**，只作为现金缺口的填充工具。

### 4. cash_ratio 的计算口径（vbt 集成）
v2 含 7 个 symbol（6 risky + 1 bond），vbt 的 `pf.cash()` 把 bond 占比也算成「非现金」。验证脚本里改用：
```python
cash_ratio = 1 - sum(risky_asset_value) / total_value
```
确保 bond 不被算作 cash，这样 cash_ratio 真实反映「无 risk 资产仓位」。

### 5. 避免 lookahead
与 v1 一致：`compute_trend_scores` 内部对每个 symbol 做 `df.loc[df.index <= date]` 切片再算因子。`_vol_breadth` 同样切片。父类 `from_orders` 默认 t+1 成交。

## 策略配置
- 配置文件：`configs/S5_cn_etf_trend_tilt_v2.yaml`
- 类型：`trend_tilt_v2`（不注册到 registry，本任务范围内）
- 父策略：v1 `cn_etf_trend_tilt` → S3 `cn_etf_equal_rebalance`
- 关键参数：
  - 趋势：`ma_short/mid/long=20/60/120, donchian=120, cutoff=0.0, score_full=1.0, use_continuous_score=True`
  - 波动率：`vol_lookback=60, vol_high=0.30, vol_breadth_threshold=0.5, vol_haircut=0.5`
  - 债券：`bond_symbol=511260, bond_max_weight=0.4`

## 数据
- 标的池：v1 的 6 只风险 ETF + 511260 十年国债 ETF（已缓存）
- 数据范围：2020-01-01 ~ 2024-12-31；暖机自 2019-07-01（120 日）
- 复权：akshare `qfq` 前复权（与 v1/S3 一致）

## 与 v1 / S3 的关系
- 直接继承 `TrendTiltStrategy(v1)`，复用其 `compute_trend_scores` 框架的部分代码（_normalize_to_unit）和 `_validate_weights`
- **不修改 v1 任何文件**（按硬约束）
- **不修改 S3 父类**（v1 已验证 vbt sum<1 兼容性，v2 继承同一保证）
- **不修改 factors/__init__.py**

## 踩过的坑

### 1. cash_ratio 计算口径
最初用 `pf.cash()` 计算 cash_ratio，但 vbt 在多 asset 共享资金池时 `pf.cash()` 包含的是「未配置到任何 asset 的现金」——bond 占比不算 cash。但用户问的「cash_ratio」语义上想看「真正没投资风险资产的比例」，所以改成 `1 - risky_value/total_value`。

### 2. bond_symbol 在 trend 排序里要跳过
最初没跳过，导致 511260 也被算 trend_score。但国债的 close > MA 形态对应「债券走牛」，反而得到正分数，与「股市趋势」语义错位。改成 `compute_trend_scores` 里显式 `if symbol == bond_symbol: continue`。

### 3. `MABullishContinuous` 已经 ∈ (-1, +1)，不要再 / 3
v1 的 `_normalize_to_unit(ma, max_abs=3)` 是为离散 score ∈ {-3, -1, +1, +3} 设计的。v2 替换连续因子后已经在 (-1, +1) 内，再除以 3 会让它 max_abs ~ 0.33 远小于 Donchian 的 1.0，破坏两者权重平衡。`compute_trend_scores` 里加了 isinstance 判断分支处理。

### 4. 浮点 score_full 与 cutoff 的边界
当 cutoff = 0、score_full = 1 时，score = 0.5 → raw = 0.5 → weight = 0.5/N。这是预期。但若 cutoff = 0.3、score_full = 0.5，需要 score ≥ 0.8 才饱和。文档里把这个含义说清楚以防误用。

## 与并行实现的对接点
- v1 文件已存在并合并，本子代理直接 import：`from strategy_lib.strategies.cn_etf_trend_tilt import TrendTiltStrategy, _normalize_to_unit`
- factors 已存在 v1 新增的 `MABullishScore / DonchianPosition`，v2 在文件末尾追加 `MABullishContinuous` 和 `AnnualizedVol`
- registry / `__init__.py` 注册由集成 PR 统一处理

## 相关 commits
- 实现：`<待commit>`
