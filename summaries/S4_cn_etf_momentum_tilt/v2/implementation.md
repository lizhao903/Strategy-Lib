---
slug: cn_etf_momentum_tilt_v2
created: 2026-05-08
updated: 2026-05-08
config_path: configs/S4_cn_etf_momentum_tilt_v2.yaml
related_idea: ideas/S4_cn_etf_momentum_tilt/v2/idea.md
parent_version: v1
---

# Implementation — A股 ETF 等权 + 动量倾斜（v2）

## 整体方案
派生自 Strategy 3 的 `EqualRebalanceStrategy`（沿用 S3 的 `build_target_weight_panel` / `run`），仅覆盖 `target_weights(date, prices_panel)` 钩子。**与 v1 保持父类不变、保持 water-fill 归一化算法不变**，但有 4 处显著改动：

1. **扩池 6 → 11**：默认 symbols 改为 11 只跨资产 ETF（A股 6 + 港股 1 + 黄金 1 + 美股 2 + 国债 1）
2. **严格 shift(1)**：`target_weights` 内先用 `df.loc[df.index < date]` 切片再算因子（`_slice_strict`），把 shift 逻辑前移
3. **更长 lookback + skip**：默认 `lookback=120, skip=5`（v1 默认 `lookback=20, skip=0`）
4. **可选 vol-adjusted 信号**：`signal="vol_adj"` 时使用 `VolAdjustedMomentum` 而非 `MomentumReturn`
5. **边界对称收紧**：`[w_min, w_max] = [0.03, 0.30]`（v1 是 `[0.05, 0.40]`），适配 N=11 的 1/N≈0.091

## 因子清单

| Factor 类 | 文件 | 参数 | 方向 | 是新增还是复用 |
|---|---|---|---|---|
| `MomentumReturn` | `src/strategy_lib/factors/momentum.py` | `lookback=120, skip=5` | +1 | 复用 |
| `MomentumReturn`（可选 secondary） | 同上 | `lookback=60, skip=5` | +1 | 复用 |
| `VolAdjustedMomentum` | `src/strategy_lib/factors/momentum.py` | `lookback=120, skip=5, vol_lookback=60` | +1 | **新增** |

## 新增因子

### `VolAdjustedMomentum`

数学定义：`mom_vol_adj = (close.shift(skip) / close.shift(skip+lookback) - 1) / std(log_returns over vol_lookback)`

```python
class VolAdjustedMomentum(Factor):
    name = "mom_vol_adj"
    required_columns = ("close",)
    direction = 1

    def __init__(self, lookback=60, skip=0, vol_lookback=60):
        super().__init__(lookback=lookback, skip=skip, vol_lookback=vol_lookback)

    def _compute(self, df):
        c = df["close"]
        mom = c.shift(skip) / c.shift(skip + lookback) - 1.0
        vol = np.log(c).diff().rolling(vol_lookback).std()
        return mom / vol.replace(0.0, np.nan)
```

- **为什么需要**：扩池后池内资产波动差异巨大（纳指 σ ~25% / 国债 σ ~3%）。原始动量倾斜在跨资产场景下会过度偏向高 vol 资产（因为 raw return 的尺度本身和 vol 正相关），vol-adj 把信号正规化到「σ-单位 risk-adjusted return」。
- **细节**：`vol.replace(0.0, np.nan)` 防 divide-by-zero；不加 `skip` 同步到 vol 窗口（vol 用 `[date - vol_lookback, date)` 区间，与 mom 的 `skip` 是分别独立的）。
- **不修改 `factors/__init__.py`**：按硬约束由主 agent 合并。

## 策略配置
- 配置文件：`configs/S4_cn_etf_momentum_tilt_v2.yaml`
- 类型：`momentum_tilt_v2`（与 v1 的 `momentum_tilt` 并列）
- 关键参数：
  - `tilt.alpha=1.0`、`tilt.w_min=0.03`、`tilt.w_max=0.30`
  - `signal.type=raw`（默认）/`vol_adj`（可切换）；`signal.vol_lookback=60`
  - `factors[0].params={lookback: 120, skip: 5}`
  - `rebalance: 20`
- 与 v1 关系：`strategy.parent: cn_etf_equal_rebalance`（仍是 S3 派生），不是 v1 派生

## 类签名

```python
class MomentumTiltV2Strategy(EqualRebalanceStrategy):
    DEFAULT_SYMBOLS_V2 = (
        "510300", "510500", "159915", "512100", "512880", "512170",   # A 股 6
        "159920", "518880", "513100", "513500", "511260",              # 跨资产 5
    )

    def __init__(
        self,
        symbols=None,
        *, rebalance_period=20, drift_threshold=None,
        lookback=120, skip=5,
        secondary_lookback=None, secondary_skip=None,
        alpha=1.0, w_min=0.03, w_max=0.30,
        signal="raw", vol_lookback=60,
        name="cn_etf_momentum_tilt_v2", **kwargs,
    ): ...

    def target_weights(self, date, prices_panel) -> dict[str, float]:
        sliced = self._slice_strict(prices_panel, pd.Timestamp(date))
        scores = self._momentum_scores(sliced)
        if scores.isna().all(): return {s: 1/N for s in symbols}
        z = self._zscore(scores).fillna(0.0)
        weights = self._tilt_weights(z)
        return {s: float(weights.loc[s]) for s in symbols}

    @staticmethod
    def _slice_strict(panel, date):
        return {s: df.loc[df.index < date] for s, df in panel.items()}
```

## 数据
- 标的池：11 只 ETF（V1 6 池 + 5 只跨资产）
- 数据范围：2020-01-01 ~ 2024-12-31
- 数据预处理：依赖 `data/cn_etf` loader 的前复权（akshare `qfq`）
- 11 只 ETF 全部覆盖整段样本期（1211~1212 个交易日）；交易日历差异极小，父类 `build_target_weight_panel` 做 intersection 后 1208 个共同交易日

## 与 v1 接口契约的差异

| 维度 | v1 (`MomentumTiltStrategy`) | v2 (`MomentumTiltV2Strategy`) |
|---|---|---|
| 父类 | `EqualRebalanceStrategy`（带 ImportError 兜底） | `EqualRebalanceStrategy`（直接 import，不再 stub） |
| 默认 symbols | 显式传入或父类的 6 只 | 类属性 `DEFAULT_SYMBOLS_V2`（11 只） |
| `target_weights` 参数 | `(date, prices_panel)` | 同 |
| 内部因子 API | `_momentum_scores(date, prices_panel)` | `_momentum_scores(prices_panel)`（已切片） |
| shift 处理 | `_row_at(panel_wide, date)` 取 ≤date 的行 | `_slice_strict(panel, date)` 用 < date 切片 |
| 边界 | [0.05, 0.40] | [0.03, 0.30] |
| signal 选项 | 仅 raw | `raw` 或 `vol_adj`（新增） |

## 踩过的坑

- **shift 语义**：`<` vs `<=` 在 close-to-close 模型里只差一个 bar，但 v2 显式选 `<` 以确保 rebalance 日的 close 价**不进**因子计算（vbt `from_orders` 在 rebalance 日 close 就成交了，因子用了同日 close 等于「下单时的成交价已经被自己的信号知道」）。
- **vol_adj 在低 vol 资产上的放大效应**：511260（十年国债）vol 极低，vol_adj 会把它的动量信号放大数倍。被 z-score 截面化后这个绝对值放大被吃掉，但仍可能挤进 z-score 分布尾部。实测看 vol_adj 信号在 11 池上 IR ≈ 0，没出现明显异常。
- **跨资产交易日历**：理论上港股/美股 ETF 与 A 股交易日不完全一致，但因为这些都是 A 股**交易所**上市的 ETF（513500/513100 在上交所），交易日历跟 A 股一致。loader 拉出来都是 1211~1212 行，可直接 intersection。
- **1/N 边界对称**：N=11 时 1/N≈0.091。v1 的 [0.05, 0.40] 在 1/N=0.167 上是大致对称的；移植到 N=11 上会变成 [0.05, 0.40]→[0.55x, 4.4x] 严重偏右。改为 [0.03, 0.30] 对称为 [0.33x, 3.3x]。

## 相关 commits
- 实现：`<待提交>`
- v1 → v2 增量：仅 `src/strategy_lib/strategies/cn_etf_momentum_tilt_v2.py`、`src/strategy_lib/factors/momentum.py`（追加 `VolAdjustedMomentum`）、`configs/S4_cn_etf_momentum_tilt_v2.yaml`、`summaries/S4_cn_etf_momentum_tilt/v2/`、`ideas/S4_cn_etf_momentum_tilt/v2/`
