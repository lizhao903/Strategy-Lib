---
slug: cn_etf_equal_rebalance
created: 2026-05-08
updated: 2026-05-08
config_path: configs/cn_etf_equal_rebalance.yaml
related_idea: ideas/cn_etf_equal_rebalance/idea.md
---

# Implementation — Strategy 3：A股 ETF 等权 + 定时再平衡

## 整体方案

权重驱动策略，**与现有 `BaseStrategy`（信号驱动）并行存在**。代码：
`src/strategy_lib/strategies/cn_etf_equal_rebalance.py` → `EqualRebalanceStrategy`

核心流程：

1. **`build_target_weight_panel(panel)`**：在共同交易日历上，每隔 `rebalance_period` 个交易日生成一行目标权重；非触发日为 NaN。
2. **`target_weights(date, prices_panel)`** 钩子：基类返回 `{s: 1/n}`；S4/S5 子类覆盖此方法实现因子倾斜。
3. **`_validate_weights`**：约束权重非负、和=1（可自动重归一化）、key 覆盖 `self.symbols` 全集。
4. **`run(panel, init_cash, fees, slippage)`**：调用 `vbt.Portfolio.from_orders(size_type="targetpercent", group_by=True, cash_sharing=True)`。NaN 行自动表示「不下单」。

## 因子清单

| Factor 类 | 文件 | 参数 | 方向 | 是新增还是复用 |
|---|---|---|---|---|
| **N/A** | — | — | — | **本策略不使用因子**（恒等权） |

S4 / S5 会在子类中引入因子，但 S3 本身保持纯被动。

## 新增因子（如有）

无。

## 策略配置

- 配置文件：`configs/cn_etf_equal_rebalance.yaml`
- 类型：`weight_based`（自定义；非现有 `single_threshold` / `cs_rank`）
- 关键参数：
  - `rebalance_period: 20`（交易日，约月度。候选 5/10/20/60）
  - `drift_threshold: null`（纯日历再平衡。可选 0.03 / 0.05 / 0.10）
- 标的池：6 只 V1 基线 ETF（510300/510500/159915/512100/512880/512170）
- 回测参数：100k / fees=0.00005 / slippage=0.0005（V1 共享基线）

## 数据

- 标的池来源：手工列（V1 基线，与 `docs/benchmark_suite_v1.md` 同步）
- 数据范围：2020-01-01 ~ 2024-12-31（日线，前复权 `qfq`）
- 数据预处理：`build_target_weight_panel` 内部对 6 只 ETF 取交易日历交集，避免某只 ETF 上市晚导致的对齐问题

## target_weights 钩子接口契约（**S4 / S5 必读**）

> 这一节是 S4 (`cn_etf_momentum_tilt`) 和 S5 (`cn_etf_trend_tilt`) 的扩展契约。
> S4/S5 应**只覆盖 `target_weights` 一个方法**，不应改父类的下单/再平衡日历/权重校验逻辑。

### 签名

```python
def target_weights(
    self,
    date: pd.Timestamp,
    prices_panel: dict[str, pd.DataFrame],
) -> dict[str, float]:
    ...
```

### 调用时机

- 父类 `build_target_weight_panel(panel)` 在每个 **rebalance 候选日**调用一次。
- 候选日序列由 `_rebalance_calendar(common_idx)` 生成：`common_idx[0], common_idx[period], common_idx[2*period], ...`（即 T0 + 每 N 个交易日）。
- 设了 `drift_threshold` 时，候选日权重会先和"上一次实际权重"比较，未超阈值则不写入 panel（但 `target_weights` 仍被调用以判断是否触发）。

### 参数

| 参数 | 类型 | 说明 |
|---|---|---|
| `date` | `pd.Timestamp` | 当前再平衡触发日。**子类只能使用 `date` 当日及之前的数据**（避免 lookahead）。父类不主动切片，子类自行 `prices_panel[s].loc[:date]`。 |
| `prices_panel` | `dict[str, pd.DataFrame]` | OHLCV panel。每个 DataFrame 至少包含 `close` 列，索引为 `DatetimeIndex`。S4/S5 通常用 `close.loc[:date]` 计算动量/趋势。 |

### 返回值

`dict[str, float]`，键为 symbol、值为目标权重。**约束**：

| # | 约束 | 违反时父类行为 |
|---|---|---|
| 1 | keys 是 `self.symbols` 的子集；缺失视为 0 | 自动补齐为 0 |
| 2 | 所有 weight `>= 0`（不允许做空） | 抛 `ValueError` |
| 3 | 权重和 ≈ 1.0（误差 < 1e-6） | **自动重归一化**（容忍未归一返回） |
| 4 | 权重和 > 0（不可全 0） | 抛 `ValueError` |

### 子类最小示例（动量倾斜的简化版）

```python
class MomentumTiltStrategy(EqualRebalanceStrategy):
    def __init__(self, *, lookback: int = 60, top_k: int = 3, **kw):
        super().__init__(**kw)
        self.lookback = lookback
        self.top_k = top_k

    def target_weights(self, date, prices_panel):
        # 计算每只 ETF 截至 `date` 的 lookback 日动量
        rets: dict[str, float] = {}
        for s in self.symbols:
            close = prices_panel[s]["close"].loc[:date]
            if len(close) < self.lookback + 1:
                rets[s] = 0.0
                continue
            rets[s] = close.iloc[-1] / close.iloc[-self.lookback - 1] - 1.0
        # Top-K 等权（其余 0）
        ranked = sorted(self.symbols, key=lambda s: rets[s], reverse=True)
        winners = ranked[: self.top_k]
        return {s: (1.0 / self.top_k if s in winners else 0.0) for s in self.symbols}
```

返回的权重会被父类校验（自动重归一化、违反约束报错）后写入目标权重 panel。

### 关键不变量（S4 / S5 不要破坏）

- **永远满仓**：父类校验权重和 = 1，S3/S4/S5 都不持有现金缓冲（这是与 S1/S2 的本质差异）。
- **次日成交防未来函数**：`vbt.from_orders` 在下一根 bar 成交，配合 `target_weights` 只读 `date` 及之前的数据 → 无 lookahead。子类绝对不要在 `target_weights` 内访问 `prices_panel[s].loc[date+1日:]`。
- **下单时机由父类管**：子类不要自己调 vectorbt API。

## 踩过的坑

- **Python 3.13 + importlib spec 加载 dataclass**：在 smoke test 中通过 `importlib.util.spec_from_file_location` 直接加载模块时，必须把 module 注册进 `sys.modules` 之后再 `exec_module`，否则 `@dataclass` 装饰器解析 type 时会拿 `cls.__module__` 在 `sys.modules` 里找不到模块、抛 `AttributeError`。
- **vectorbt `from_orders` 的 size 语义**：用 `size_type="targetpercent"` 时，NaN 表示"该 bar 不下单"，0 表示"清仓该资产"，**两者不可混淆**。本实现里非触发日全部为 NaN。
- **6 只 ETF 上市时间不同**：512100（中证1000 ETF）、512170（医疗 ETF）等部分 ETF 在 2014-2016 才上市，但 V1 窗口从 2020-01-01 起，已经全部存在；`build_target_weight_panel` 用交易日历交集兜底。
- **未来函数边界**：`target_weights(date, ...)` 中 `date` 是用于产生权重的"参考日"，vectorbt 的 `from_orders` 默认在**当前 bar** 用 `close` 价成交。要做到次日成交，可在传入 `size` 时用 `weights_df.shift(1)`——本实现暂未 shift（等 validation 阶段确认 vectorbt 的语义后再决定，注释保留）。

## 相关 commits

- 实现：`<待提交>`
- 调参：N/A（V1 默认参数即可）
