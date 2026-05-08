# Notes — cn_etf_momentum_tilt_v2

> 持续追加，不要覆盖。每条笔记带日期。

---

## 2026-05-08 v2 设计选型 — 4 个改进方向选哪几个 + 为什么

### v1 失败诊断（继承 v1 conclusion / validation 的关键证据）

| 证据 | 解读 |
|---|---|
| 5α × 3lookback = 8 次实验 IR vs S3 全负 | 不是参数问题，是**信号在 6-ETF 池上系统性反向** |
| α=0（等权）是 8 档最优 | 任何动量倾斜都减损 → 不是「倾斜不够」 |
| 平均主动权重 \|Δw\| = 0.092（≈9.2%） | 倾斜幅度合适，**不是因为信号太弱才没效果** |
| lb=20 最差，lb=60 稍好但仍负 | A 股 ETF 短期反转盖过中期动量 |
| 6 只 ETF 全是 A 股宽基/行业 | **池内 pairwise correlation 高** → z-score 信息密度低 |

⇒ v1 的根本问题是**池太小、概念太集中**，参数怎么调都救不回来。

### 4 个 v2 候选方向

| 方向 | 选 | 理由 |
|---|---|---|
| **(A) 扩池 6 → 11**（加 港股/黄金/纳指/标普/十年国债） | ✅ **必选** | 直击 v1 根本问题。即使因子无效，扩池本身能改善 S3 等权 baseline 的风险/收益（黄金、债券抗跌；纳指 2020/2023 大涨） |
| **(B) 显式 shift(1)** | ✅ **必选** | 父类 S3 用 `from_orders + targetpercent`，rebalance 日 close 价成交。v1 在 `target_weights` 内未做 `< date` 切片 → 理论上 same-bar lookahead 风险（虽然影响很小因为 rebalance 用的是当日 close 算的因子，vbt 在下一根 bar 才下单，但严谨起见显式切片） |
| **(C) 长 lookback (120) + skip(5)** | ✅ **必选** | v1 conclusion 第 2 条：「下次试动量先 skip=21」；v1 lb sweep 显示 lb=60 比 lb=20 稍好（IR -0.14 vs -0.49）→ 顺着曲线延长到 120 应该更好 |
| **(D) Vol-adjusted momentum** | ✅ **作为可选信号** | 扩池后纳入了高/低波动差异巨大的资产（纳指 σ ~25% vs 国债 ~3%）。原始动量倾斜会过度偏向高波动资产；vol_adj = mom/vol 控制这个偏向。当 alternative 信号验证 |

### 为什么 4 个全选 vs 「先做扩池/shift 看效果再加 C/D」

考虑过先做最小 v2（A+B）看效果，再决定 C/D。但：
- C 的成本很低（一行参数），且 v1 的 lookback sweep 已经给了「越长越好」的方向证据，没必要再独立验证
- D 作为**次选信号**而非主信号，不增加默认参数的过拟合风险，但提供了一个对照
- 一次跑完所有改进 + 用 sweep 做控制变量分解（pool ablation / lookback sweep / signal sweep），比串行分两轮更有效

### 对 v1 的批判性继承

- **保留**：`EqualRebalanceStrategy` 父类、water-fill 归一化算法（v1 已验证数学正确）、横截面 z-score 公式、α 默认 1.0
- **改动**：
  - 边界 [0.05, 0.40] → [0.03, 0.30]：N=11 时 1/N≈9.1%，v1 的边界相对 1/N 不再对称（v1 的 [0.05, 0.40] 对 1/6=16.7% 是 ±60%/+140%；v2 [0.03, 0.30] 对 1/11=9.1% 是 ±67%/+230%，仍然偏向「允许加仓」但比 v1 更谨慎）
  - `_row_at(panel_wide, date)` → 改为 `_last_row(panel_wide)` 配合 `_slice_strict`：把 shift 逻辑从「内部按 date 取行」前移到「先切片再算因子」，减少出错面
  - `_momentum_scores(date, panel)` → `_momentum_scores(panel)`：API 简化，因为切片后只需要看 panel 末端即可

### 为什么不动 v1 文件

按硬约束，v1 任何文件不修改。新增类 `MomentumTiltV2Strategy` 在 `cn_etf_momentum_tilt_v2.py`；新增 factor `VolAdjustedMomentum` 在现有 `factors/momentum.py`（**只追加**，不动 `MomentumReturn`）。

---

## 2026-05-08 实测结果速记（详见 summaries/.../v2/validation.md）

- v2 default: NAV 1.307 / CAGR 5.75% / Sharpe 0.44 / MaxDD -22.2%（vs v1 default NAV 1.001 / 0.02% / 0.12 / -47.9%）
- **vs S3 (11 pool) IR = -0.17**（v1 是 -0.49）→ 大幅改善但仍未扭转为正
- Pool ablation：v2 参数在 **6 池上 vs S3 (6 池)** IR = -0.26 → 在原池上 v2 仍输 S3，**扩池贡献了几乎全部 alpha**
- α=0（等权）仍是 sweep 最优 → **动量 tilt 信号在跨资产 ETF 池上仍未产生 alpha**
- lookback=250 是唯一 IR > 0 的 (+0.077)，但很微小
- vol_adj 信号 IR ≈ 0 vs S3（alpha 接近 0），CAGR 7.11%、Sharpe 0.57、MaxDD -18.5% — **达成「不亏」**

### 关键解读

1. **扩池价值真实存在**：v2 (11 pool) 比 v2 (6 pool) CAGR 高 4.17%，几乎全部 alpha 来自池子，不来自因子。S3 (11 pool) 也比 S3 (6 pool) CAGR 高约 4.0%（6.73% vs 2.74%）→ **「pool alpha」属于 S3，不属于 momentum**。
2. **动量 tilt 在 A 股 ETF 跨资产截面仍然未带来 alpha**：v2 默认配置仍输 S3 (11 pool)。这与 v1 在小池上的发现一致 → A 股可投资的 ETF 池上**横截面动量是失效因子**（无论池大小）。
3. **唯一接近不亏的配置**：vol-adj 长 lookback。v2 + vol_adj IR ≈ 0、Sharpe 比 raw 更高（0.57 vs 0.44）。这是「跨资产 risk parity 风格」更胜出，而非「动量信号」更胜出。
4. v2 vs v1 alpha = +3.81%/yr，IR = +0.27。这是 v2 比 v1 好的硬证据，但混合了「池 + 参数」两个变化，要小心归因。

### 决策建议

- 若 v2 唯一目的是「比 v1 好」→ 已达成，**ship v2**。
- 若 v2 的目的是「证明动量 tilt 在 A 股 ETF 上有效」→ **未达成**，IR 仍负。
- 折中：**ship v2 但状态标记为 "shipped (pool 价值，非 factor 价值)"**，并把 conclusion 中「动量 tilt 失效」的判断保留下来供 v3 参考。

---

## 2026-05-08 数据加载 / 缓存

11 只 ETF 全部命中 cache（`data/raw/cn_etf/<sym>_1d.parquet`），无 akshare 调用。所有 ETF 均覆盖 2020-01-02 ~ 2024-12-31 完整范围（1211~1212 日）。

---

## 待跟进 / v3 候选

- **v3：彻底放弃倾斜，做扩池版 S3**：把 11 ETF 池接到 S3 直接 ship，省掉 momentum 这一层。证据：v2 sweep 中 α=0 始终最优。
- **v3-alt：跨资产 + 大盘趋势过滤**：只在 510300 在 200 日 MA 之上时启用 momentum tilt，否则退化等权。借鉴 v1 conclusion 的 binary filter 思路。
- **v3-alt2：minimum-variance / risk parity**：跨资产场景下，最优解可能不是动量 tilt 而是 vol-weighted 等。
- 样本外测试：拿 2025 H1 数据再验。
