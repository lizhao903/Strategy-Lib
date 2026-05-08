---
slug: cn_etf_dca_swing_v2
parent_slug: cn_etf_dca_swing
created: 2026-05-08
updated: 2026-05-08
config_path: configs/S2_cn_etf_dca_swing_v2.yaml
related_idea: ideas/S2_cn_etf_dca_swing/v2/idea.md
---

# Implementation — A股 ETF DCA + 阈值再平衡 V2

## 整体方案

V2 落到代码上是**一个独立、自包含的 weight-based 策略类**，不继承 v1：
`src/strategy_lib/strategies/cn_etf_dca_swing_v2.py::DCASwingV2Strategy`。

不复用 v1 类的理由（与 idea.md 一致）：
- v1 的 `simulate` 把月度 DCA 写得很「死」（固定 5000 等额买 6 只）；v2 要切三态分支。继承会让代码读不顺。
- v1 的 swing 阈值是固定参数；v2 要按日动态算 `band_t`，需要在循环里维护 NAV 历史用于 vol 计算。
- 避免「v1 修 bug 牵连 v2 / v2 加 feature 影响 v1」这种相互纠缠。
- v1 已 shipped，按硬约束**不修改 v1 任何文件**。

实现路径与 v1 同样是「纯 numpy/pandas 单循环 + 可选 vbt Portfolio 包装」。

## 因子清单

V2 不依赖外部 Factor 类。**唯一新引入的中间量**是「过去 60 日组合 NAV pct_change 的实现波动率」，但这是策略内部 rolling 计算，不抽象成独立 Factor（不暴露 IC、不被其他策略复用）。

## 策略配置

- 配置文件：`configs/S2_cn_etf_dca_swing_v2.yaml`
- 类型：`dca_swing_v2`（**未注册到 registry**，遵守硬约束）
- 加载方式：由 `summaries/S2_cn_etf_dca_swing/v2/validate.py` 直接实例化 `DCASwingV2Strategy`

参数（与 v1 共享 vs v2 新增）：

| 参数 | v2 默认 | 来源 | 说明 |
|---|---|---|---|
| `risk_target_weight` | 0.70 | v1 | 风险池目标合计权重 |
| `monthly_dca_amount` | 5000.0 | v1 | NORMAL 模式下的 DCA 金额 |
| `adjust_ratio` | 0.50 | v1 | swing 单次拉回比例 |
| `cooldown_days` | 5 | v1 | 同标的触发冷却天数 |
| `fees`/`slippage`/`init_cash` | 共享基线 | v1 | 不变 |
| **`dca_band_high`** | 0.05 | v2 新 | DCA OFF 触发的上沿余地（w_risk > 73.5%） |
| **`dca_band_low`** | 0.05 | v2 新 | DCA BOOST 触发的下沿余地（w_risk < 66.5%） |
| **`dca_boost_factor`** | 1.5 | v2 新 | BOOST 模式下 DCA 金额乘数 |
| **`vol_lookback`** | 60 | v2 新 | NAV 实现波动率回看天数 |
| **`vol_band_coef`** | 0.60 | v2 新 | `band_t = coef × vol_ann` 的系数 |
| **`vol_band_min/max`** | 0.10 / 0.30 | v2 新 | band_t clip 区间 |
| **`warmup_band`** | 0.20 | v2 新 | 前 60 日 warmup 期固定阈值（与 v1 一致） |

## 数据

与 v1 完全一致：
- 标的池：`511990` + `510300/510500/159915/512100/512880/512170`
- 时间窗：2020-01-01 ~ 2024-12-31
- 数据预处理：akshare qfq → parquet 缓存；inner join 7 只共有交易日
- 起始 T0 全部 init_cash 买入 511990 货基

## 关键设计决策

### 1. DCA 三态判定（A 方向核心）

每月第一个交易日 T 的前一日 T-1 决策（`pending_dca` 写在 t 循环末尾，t+1 是月初）。判定基于 **T 收盘的风险池总权重 `w_risk`**：

```python
target = self.risk_target_weight  # 0.70
if w_risk > target * (1 + dca_band_high):     # > 0.735
    pending_dca = "OFF"                        # 5000 留货基不动
elif w_risk < target * (1 - dca_band_low):    # < 0.665
    pending_dca = "BOOST"                      # 7500 等额买 6 只
else:
    pending_dca = "NORMAL"                     # 5000 等额买 6 只（与 v1 一致）
```

**T+1 开盘执行**——保持与 v1 相同的「T 决策、T+1 成交」无未来函数节奏。

### 2. 波动率自适应阈值（C 方向核心）

每个交易日 t 在循环里直接算：

```python
window_nav = nav_hist[t - vol_lookback : t + 1]   # 含 t；只用历史
rets = np.diff(window_nav) / window_nav[:-1]
vol_ann = np.std(rets, ddof=0) * np.sqrt(252)
band_t = clip(vol_band_coef * vol_ann, vol_band_min, vol_band_max)
```

注意：
- `nav_hist[:t+1]` 是当日 close 后估值的 NAV，只用历史信息——**无未来函数**。
- 前 `vol_lookback=60` 个交易日 warmup 期 band_t 固定 `warmup_band=0.20`（与 v1 完全一致），避免冷启动噪声把 band 压到下限。
- `band_t` 立即用于当日的 swing 触发判定（向 t+1 下单）。

### 3. swing 触发逻辑（保持与 v1 一致，仅替换阈值变量）

```python
upper = w_target_per_symbol * (1 + band_t)
lower = w_target_per_symbol * (1 - band_t)
```

`adjust_ratio=0.5`、`cooldown_days=5`、单标的偏离绝对额 < 1 RMB 不动单（防小数噪声）——全部沿用 v1。

### 4. 防止 v1 bug 传染

V2 不导入 v1 类。`DCASwingV2Strategy` 是独立类；`DCASwingV2Result` 是独立 dataclass。validate.py 同时实例化 v1（仅作对比）和 v2，但运行轨道独立。

### 5. 现金/持仓不足缩单

与 v1 同样的兜底：
- DCA OFF 不动钱
- DCA BOOST 时若 511990 余额不足 7500，缩单到可用上限（极端连续 BOOST 会受此影响）
- swing 加仓现金不足按可用缩；swing 减仓持仓不足按可用缩

## 踩过的坑

1. **DCA mode 决策时点**：起初想把判定逻辑放到 t=月初当日（"今天是月初就决定"），但这违背 v1 的 `pending_dca` 模型（v1 是 t-1 决策、t 执行）。改为「t 是月初前一交易日时决策」→ `index[t+1] in month_firsts` 时算 mode → t+1 执行。这样保持和 v1 完全相同的时间轴。
2. **vol 窗口含 t 还是不含**：写成 `nav_hist[t - vol_lookback : t + 1]` 含当日 close。当日 NAV 基于 T close，是已经实现的信息——不属于未来函数（与 v1 的 swing 决策同源时点）。
3. **warmup 期固定 0.20**：第一版尝试在 warmup 期就用 t=10/20 的短窗口算 vol，结果 band_t 在前 60 日剧烈震荡。改为固定 0.20（v1 默认值）后早期 NAV 与 v1 几乎重合，便于事后归因到底是「DCA 路由」还是「vol 自适应」贡献了差异。

## 相关 commits

待提交（2026-05-08 v2 批次）。

## 后续 follow-up

- [ ] 如果 v2 结果显示「band_t 长期撞底（vol_ann × 0.6 < 0.10）」，考虑把 `vol_band_coef` 从 0.6 上调到 0.9（让低波期更接近 v1 的 0.20）
- [ ] 如果 BOOST 几乎不触发，考虑放宽 `dca_band_low` 到 0.03（更敏感）
- [ ] 真实数据下 v2 vs v1 head-to-head 出表（在 validation.md）
