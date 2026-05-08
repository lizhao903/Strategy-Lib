---
slug: cn_etf_momentum_tilt
created: 2026-05-08
updated: 2026-05-08
config_path: configs/cn_etf_momentum_tilt.yaml
related_idea: ideas/cn_etf_momentum_tilt/idea.md
---

# Implementation — A股 ETF 等权 + 动量倾斜

## 整体方案
派生自 Strategy 3 的 `EqualRebalanceStrategy`，仅覆盖 `target_weights(date, prices_panel)` 钩子。整体仍是「6 只 ETF 满仓 + 每 20 个交易日再平衡」，本策略的差异完全集中在「目标权重怎么算」：

1. 在 rebalance 日，对面板里每个 symbol 计算 `MomentumReturn(lookback=20)` 在 `date` 当天的值。
2. 横截面 z-score 标准化（NaN 当作 0）。
3. 线性倾斜：`w_raw_i = 1/N + alpha * z_i / N`。
4. 用「水位线迭代」处理 `[w_min=0.05, w_max=0.40]` 上下限：每轮按 sum=remaining 缩放未钉死资产，识别最严重的越界并钉死到边界，重复直至收敛或 free 集为空。
5. 输出权重严格满足 `sum(w)=1`、`w_i ∈ [w_min, w_max]`、非负。

可选：启用 `secondary_lookback=60`，主+次动量各自横截面 z-score 后等权融合。

## 因子清单
| Factor 类 | 文件 | 参数 | 方向 | 是新增还是复用 |
|---|---|---|---|---|
| `MomentumReturn` | `src/strategy_lib/factors/momentum.py` | `lookback=20` | +1 | 复用 |
| `MomentumReturn`（可选） | `src/strategy_lib/factors/momentum.py` | `lookback=60` | +1 | 复用 |

## 新增因子（如有）
无。`notes.md` 中提议了 `MomentumRiskAdjusted`（动量/波动率），暂不实现。

## 策略配置
- 配置文件：`configs/cn_etf_momentum_tilt.yaml`
- 类型：`momentum_tilt`（自定义；与 `cs_rank` 等内置类型并列）
- 关键参数：`tilt.method=zscore_linear`、`tilt.alpha=1.0`、`tilt.w_min=0.05`、`tilt.w_max=0.40`、`rebalance=20`
- 与 S3 的关系：`strategy.parent: cn_etf_equal_rebalance`，明确派生关系；`MomentumTiltStrategy(EqualRebalanceStrategy)`

## 类签名

```python
class MomentumTiltStrategy(EqualRebalanceStrategy):
    def __init__(
        self,
        *args,
        lookback: int = 20,
        secondary_lookback: int | None = None,
        alpha: float = 1.0,
        w_min: float = 0.05,
        w_max: float = 0.40,
        **kwargs,
    ): ...

    def target_weights(
        self,
        date: pd.Timestamp | datetime.date,
        prices_panel: dict[str, pd.DataFrame],
    ) -> dict[str, float]: ...
```

## 数据
- 标的池来源：手工 6 只 ETF（与 Benchmark Suite V1 共享基线）
- 数据范围：2020-01-01 ~ 2024-12-31
- 数据预处理：依赖 `data/cn_etf` loader 的前复权（akshare `qfq`）

## 与 S3 接口契约的差异（v1）
S3 的 subagent 与本任务并行运行；写本策略时 `src/strategy_lib/strategies/cn_etf_equal_rebalance.py` 还未落地。本实现按以下假设契约推进：

```python
class EqualRebalanceStrategy:
    def target_weights(self, date, prices_panel) -> dict[str, float]:
        # 返回非负、和=1 的权重字典
        ...
```

`MomentumTiltStrategy` 仅覆盖 `target_weights`，其余初始化签名通过 `*args, **kwargs` 透传到父类。如果 S3 的真实实现签名不一致（比如返回 `pd.Series` 而非 `dict`、或者钩子叫别的名字），按要求**优先采用本假设契约**，必要时在 S3 落地后做一次小适配（修改 `target_weights` 的返回类型即可），其它逻辑无需改动。

源码里的 `try/except ImportError` 兜底是为了在 S3 模块缺失时本模块仍可被 import；正式回测必须以 S3 真实落地为前提。

## 踩过的坑
- 第一版 `_tilt_weights` 用「单轮 clip + 归一化」，在 alpha 过大时所有资产都打到上限，归一化后又退化为等权（信号丢失）。改为水位线迭代后稳定。
- z-score 计算要把 NaN 当 0（中性），否则少数资产没历史数据会污染整个截面。
- `compute_panel(panel)` 返回 wide DataFrame，要按 `date` 取一行；如果 `date` 不在 index 里，回退到 `<= date` 的最后一行（典型场景：周末/停牌）。

## 相关 commits
- 实现：`<sha>`（待提交）
- 调参：未发生
