# Strategy-Lib — Claude Code 协作约定

这是一个**多市场量化策略研究库**。技术选型固定：vectorbt + 自研因子层 + Notebook 探索。

## 核心边界

- **因子层和策略层与市场解耦**。因子接收标准 OHLCV DataFrame（列名：`open/high/low/close/volume`，索引：`DatetimeIndex`），不关心是 Crypto 还是 A股。
- **每个市场只有一个差异点：数据层**。`src/strategy_lib/data/` 下每个文件对应一个市场。
- **Notebook 不是源头**。可复用的逻辑必须放在 `src/strategy_lib/`，notebook 只能调用、不能定义新的因子函数或回测流程。

## 添加新因子的流程

1. 在 `src/strategy_lib/factors/<category>.py` 写一个 `Factor` 子类（参数化、声明依赖列、实现 `compute()`）
2. 在 `notebooks/factors/` 写一个探索 notebook，跑 IC、Rank IC、分组收益
3. 如果效果好，进 `configs/` 的策略配置里组合使用

## 添加新策略的流程

每个策略走「想法 → 实现 → 验证 → 结论」四步，全部用统一 slug（如 `btc_momentum_rsi`）：

1. **想法**：`cp -r ideas/_template ideas/<slug>`，填 `idea.md`（核心逻辑、依据、预期）
2. **实现**：
   - 优先写 `configs/<slug>.yaml` 用现有因子组合表达
   - 表达不了再在 `src/strategy_lib/factors/` 加新因子，或在 `src/strategy_lib/strategies/` 加新 `BaseStrategy` 子类（注册到 registry）
   - 同步起 `summaries/<slug>/`（从 `_template` 拷贝），在 `implementation.md` 记录关键决策
3. **验证**：notebook 跑 IC / 分组 / 回测，结果按日期**追加**到 `summaries/<slug>/validation.md`（不要覆盖历史），图表存 `summaries/<slug>/artifacts/`
4. **结论**：策略状态确定（上线/废弃/搁置）时写 `summaries/<slug>/conclusion.md`，并在 `summaries/README.md` 索引追加一行

## 无脑快速验证（quickrun）

**最简路径**——一行 Python 或一行 CLI 跑任意标的池，自动推断 market / cash / benchmark：

```python
from strategy_lib import quickrun

quickrun("BTC/USDT,ETH/USDT,SOL/USDT")                           # 含 / → crypto，自动 USDT cash + BTC bench
quickrun(["510300", "510500", "159915"], strategies=["S3", "S4v2"])  # 6 位数字 → cn_etf
quickrun("AAPL,MSFT,GOOG", strategies=["S3", "S5v2"])            # 字母 → us_stock
```

CLI:
```bash
slib quickrun --symbols 'BTC/USDT,ETH/USDT,SOL/USDT' --strategies 'S3,S4v2,S5v2'
slib quickrun --symbols '513100,518880,159920,513500'    # 复现 S8 cn_etf_overseas
slib quickrun --symbols 'AAPL,MSFT' --benchmark SPY --since 2022-01-01
```

输出（自动保存到 `results/quickrun_<ts>/`）:
- `summary.md` — 标准报告（包含 BH 对比）
- `results.csv` — 长格式数据
- stdout 含 strategy 对比表

适用场景：日常想"换组标的看哪个策略好"——3 秒内出结果，不写代码。

## 快速切换标的池（Universe + Sweep）

不要在 validate.py / notebook 里硬编码 symbol list。用 `Universe` 抽象：

```python
from strategy_lib.universes import CN_ETF_BASE_6, CN_ETF_EXPANDED_11, Universe
from strategy_lib.strategies.factories import s3_equal_rebalance, s4v2_momentum_tilt
from strategy_lib.backtest import sweep, run_on_universe

# 单点：在某个 universe 上跑某策略
metrics = run_on_universe(s3_equal_rebalance, CN_ETF_EXPANDED_11)

# Grid：策略 × universe sweep
df = sweep(
    strategies={"S3": s3_equal_rebalance, "S4v2": s4v2_momentum_tilt},
    universes=[CN_ETF_BASE_6, CN_ETF_EXPANDED_11],
    since="2020-01-02", until="2024-12-31",
)
```

**预定义 universe**：见 `src/strategy_lib/universes.py`。当前注册的 cn_etf 池：
- `CN_ETF_BASE_6` — V1 baseline 6 池
- `CN_ETF_BROAD_3` — A 股宽基 3 只（最简）
- `CN_ETF_EXPANDED_11` — base 6 + 5 跨资产（V1 v2 起用）
- `CN_ETF_OVERSEAS_4` — 港股 + 海外 + 黄金 4 只（无 A 股）
- `CN_ETF_DEFENSIVE_3` — 国债 + 黄金 + 货币（防御）

**临时池**：`Universe.custom("my_pool", ["510300", "159915"], market="cn_etf", cash_proxy="511990")`

**新策略加 factory**：在 `src/strategy_lib/strategies/factories.py` 加一个 `s{N}_xxx(universe, **overrides)` 函数，把 universe 字段适配成策略类的构造参数。这样后续 sweep 直接复用。

**已知教训**：
- A 股池 (base_6, broad_3) 在 2020-2024 是结构性拖累；overseas_4 (无 A 股) Sharpe 4-6 倍于 base_6
- 大 universe 上 timing/factor 边际价值很低，**alpha 优先级：池子 >> 信号 >> 仓位**
- 选 universe 之前先 sweep 一下；不要假设"复杂版本一定胜出"

**Crypto V2 Suite**（计划阶段，见 `docs/benchmark_suite_v2_crypto.md`）：
- 已注册 universe：`CRYPTO_BTC_ETH_2` / `CRYPTO_TOP_3` / `CRYPTO_TOP_5` / `CRYPTO_TOP_10`
- baseline 资金 100k USDT；基准 BTC/USDT BH；窗口 2021-01-01 ~ 2024-12-31；交易成本 fees=10bp + slippage=10bp（比 V1 高 2x）
- V2 起步策略：S9 (V2-S1) `crypto_basket_equal`（S3 等权同款）作 baseline
- 注意：crypto 24/7 + 高波动（年化 ~70%），vbt freq 参数与 V1 不同；启动 V2 时单独验证

## 关于 ideas/ 和 summaries/ 的写作约定

- **ideas/<slug>/idea.md** 是想法的**原始版本**——除非根本性修订，不要改写它。增量讨论、AI 给的建议、新的发现写到 `notes.md` 里，每条带日期。
- **summaries/<slug>/validation.md** 是**追加日志**——每轮新回测加一个 `## YYYY-MM-DD` 小节，旧结论不要删。
- 已废弃的策略也要写 `conclusion.md`，写明废弃原因——下次有类似想法时能查到避免重复试。
- 索引文件（两个 `README.md`）每加一个策略就追加一行，方便扫读。

## 不要做的事

- 不要在 notebook 里实现因子函数 / 回测循环。要么沉淀到 src/，要么不写。
- 不要直接 `pd.read_csv` 或调外部 API 加载数据。永远走 `data.get_loader(market).load(...)`。
- 不要为多个市场写多套因子代码。如果某个因子真的市场特定（比如 A股涨跌停），在因子内部判断或参数化，不要复制。
- 不要绕过 vectorbt 自己撸回测循环。如果 vectorbt 表达不了某个策略，先 issue 讨论再说。

## 数据约定

- 数据缓存：`data/raw/<market>/<symbol>_<timeframe>.parquet`
- 标准列：`open, high, low, close, volume`，索引为 UTC `DatetimeIndex`，命名 `timestamp`
- A股需要做前复权（akshare adjust="qfq"）

## 运行测试

```bash
pytest                      # 全部
pytest tests/factors/       # 单个目录
pytest -k momentum          # 关键字过滤
ruff check src/ tests/      # lint
```
