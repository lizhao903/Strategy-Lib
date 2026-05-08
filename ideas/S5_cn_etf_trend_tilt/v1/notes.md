# Notes — cn_etf_trend_tilt

> 持续追加，不要覆盖。每条笔记带日期。

---

## 2026-05-08 初稿设计要点

### 为什么把动量（S4）和趋势（S5）拆成两个策略

很多文献和实务把这两个名字混着用，但在策略设计层面它们是两件事：

- **动量（cross-sectional momentum）**：横截面比较——「在 A/B/C/D/E/F 里谁过去 N 个月涨得最多？把权重往它们倾斜。」
  - 输入：`mom_return.rank()`
  - 决策：选谁、配多少
  - 即使全体在跌，仍然有「跌得最少」的赢家被加权
  - Jegadeesh & Titman 1993

- **趋势（time-series momentum / trend following）**：时序自比较——「这一个资产现在的价格相对它自己 60 天前/均线/通道是涨还是跌？」
  - 输入：`close vs MA`、`ADX`、`Donchian position`
  - 决策：进场 / 出场 / 趋势力度
  - 全体下行时可以**全部不持有**——这是趋势策略的核心保护机制
  - Moskowitz, Ooi & Pedersen 2012

S4 用 `MomentumReturn` 在 6 只里做排名（即使是熊市也总有 6 个权重之和 = 1）；S5 用 MA 多头排列 + Donchian 位置做单标的方向判断（熊市里所有 ETF 趋势分数都 ≤ 0 → 全空仓）。**唯一允许全空仓**是 S5 在 V1 五策略里独有的特征，也是用户特意把两个策略拆开评估的根本原因。

### 全市场趋势全负时的处理（关键设计决策）

S3 的 `EqualRebalanceStrategy` 钩子契约：`target_weights(date, prices_panel) -> dict[str, float]`，权重和 = 1、非负。

S5 一旦遇到极端熊市（所有 6 只 ETF 的 trend_score 都 ≤ 0），权重和无法 = 1。三种处理：

- **A. 塞个虚拟 cash key**（如 `"CASH"`）：破坏 S3 「键必须是池中 symbol」的隐式契约。
- **B. 允许返回总和 < 1 的 dict，缺失的 symbol 视作 0 权重，剩余视作现金**（推荐）：契约从「权重和 = 1」放宽为「权重和 ≤ 1，缺失即 0」。需要明确告知 S3 的实现者这是契约扩展。
- **C. 强制保留一个最弱信号资产 = 1**：破坏「趋势退出」的语义，否决。

**采纳 B**。理由：
1. 语义清晰——空仓就是空仓，不需要假装。
2. 实现简单——`from_orders` 用 size_type=TargetPercent + 缺失列视作 0 即可，不需要单独维护现金账户。
3. 把契约扩展在 `implementation.md` 显式声明，与 S3 子代理协调时可以让对方在父类里允许 `sum(weights) < 1`。

如果 S3 子代理的实现严格要求 `sum == 1`，需要在合并时协商修改父类（让父类 normalize 时跳过断言，而不是在 S5 里硬塞 cash）。

### 因子选择

排除已有的：
- `MomentumReturn` — S4 会用，且是横截面累计收益，不是趋势方向
- `MACDDiff` — 是 EMA 差值的归一化，方向偏短期；保留给以后多因子复合
- `RSIReversal` — 反转因子，方向相反
- `RealizedVol` / `ATRRatio` — 波动率，与趋势正交

新建（写到 `factors/trend.py`，**不**改 `factors/__init__.py`）：
- `MABullishScore(short=20, mid=60, long=120)`：离散多头排列得分，参数化的均线长度
- `DonchianPosition(lookback=120)`：连续通道位置 [0,1]

这两个组合理由：一个是离散信号（MA 排列），一个是连续位置（通道），数学性质互补。

### 与 S3 的钩子集成

- 假设 S3 父类导出 `EqualRebalanceStrategy`（来自 `strategy_lib.strategies.cn_etf_equal_rebalance`）
- 假设父类有 `target_weights(self, date, prices_panel) -> dict[str, float]` 钩子
- S3 subagent 是并行跑的——读到的文件可能不存在；smoke test 用 stub 父类（不入库）独立验证倾斜逻辑

### 暖机期处理

`MABullishScore` 默认要 120 日窗口，`DonchianPosition` 也是 120。回测窗口起点 2020-01-01 之前没有数据 → 2020 年前几个月 NaN。建议：
- 暖机期内（任何因子还在 NaN）整体空仓，避免靠垃圾数据下注
- 真实回测时让 data loader 多拉 6 个月历史数据预热

### 待与 S3 子代理协调的接口点

1. `target_weights` 是否允许返回 `sum < 1`
2. 钩子签名是否就是 `(self, date: pd.Timestamp, prices_panel: dict[str, pd.DataFrame]) -> dict[str, float]`
3. 子类是否能拿到 `self.symbols`（池中 6 只 ETF 列表）

我先按这三点假设写代码。如果 S3 实现不一致，调整 S5 的少量样板代码即可，倾斜逻辑本身（`compute_trend_scores` + `_tilt_weights`）保持不变。

---
