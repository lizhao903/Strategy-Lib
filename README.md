# Strategy-Lib

多市场量化策略研究库。覆盖 **Crypto / A股 / 港股 / 美股 / ETF**，基于 **vectorbt** 回测，研究流程：Notebook 探索 → 库代码沉淀。

## 目录结构

```
Strategy-Lib/
├── src/strategy_lib/         # 核心库（市场无关的因子、分析、回测包装）
│   ├── data/                 # 数据层：每个市场一个 loader，统一 OHLCV 接口
│   │   ├── base.py           # BaseDataLoader（抽象接口 + parquet 缓存）
│   │   ├── crypto.py         # ccxt
│   │   ├── cn_stock.py       # akshare（A股/港股/ETF）
│   │   └── us_stock.py       # yfinance（美股/ETF）
│   ├── factors/              # 因子库：每个因子是一个继承 Factor 的类
│   │   ├── base.py           # Factor 基类
│   │   ├── momentum.py       # 动量类
│   │   ├── reversal.py       # 反转类
│   │   ├── volatility.py     # 波动率类
│   │   └── volume.py         # 成交量类
│   ├── analysis/             # 因子评估：IC、分组、衰减
│   │   ├── ic.py
│   │   ├── grouping.py
│   │   └── plots.py
│   ├── strategies/           # 策略模板：从因子到信号到仓位
│   │   ├── base.py
│   │   └── registry.py
│   ├── backtest/             # vectorbt 包装 + 绩效指标
│   │   ├── runner.py
│   │   └── metrics.py
│   └── utils/
├── ideas/                    # 策略想法库（每个策略一个子文件夹）
│   ├── _template/            # 新想法从这里复制
│   └── <strategy_slug>/
│       ├── idea.md           # 核心想法
│       └── notes.md          # 持续讨论笔记
├── summaries/                # 策略实现与验证总结（每个策略一个子文件夹）
│   ├── _template/
│   └── <strategy_slug>/
│       ├── implementation.md # 怎么实现的
│       ├── validation.md     # IC/分组/回测结果（按日期累加）
│       ├── conclusion.md     # 最终结论
│       └── artifacts/        # 关键图表与数据
├── notebooks/                # 研究 notebook（探索性）
│   ├── factors/              # 因子探索
│   ├── strategies/           # 策略开发
│   └── reports/              # 研究报告
├── configs/                  # yaml 策略配置
│   └── examples/
├── data/                     # 数据缓存（gitignore）
│   ├── raw/
│   └── processed/
├── tests/
└── scripts/                  # CLI 入口
```

## 设计原则

1. **因子和策略与市场解耦**：所有因子函数接收 `pd.DataFrame`（标准 OHLCV 列），不关心数据来源。
2. **数据层有缓存**：第一次拉取写入 `data/raw/<market>/<symbol>.parquet`，之后从本地读。
3. **因子是类，不是函数**：每个因子继承 `Factor`，封装参数、依赖列、计算逻辑、方向（高值看多/看空）。
4. **策略是配置驱动**：`configs/*.yaml` 描述用哪些因子、组合方式、仓位规则，`slib backtest <config>` 运行。
5. **Notebook 只是探索**：可复用的代码必须沉淀到 `src/`。

## 安装

```bash
# 推荐使用 uv
uv venv
uv pip install -e ".[notebook,dev]"

# 或用 pip
python -m venv .venv && source .venv/bin/activate
pip install -e ".[notebook,dev]"
```

## 快速上手

```bash
# 1. 拉数据（示例：BTC 日线）
slib data fetch --market crypto --symbol BTC/USDT --tf 1d --since 2020-01-01

# 2. 跑示例策略
slib backtest run configs/examples/btc_momentum.yaml

# 3. 启动 notebook 探索
jupyter lab notebooks/
```

详细的研究流程见 `notebooks/factors/01_momentum_intro.ipynb`。

## 添加新因子

1. 在 `src/strategy_lib/factors/<category>.py` 新增类，继承 `Factor`
2. 在 `notebooks/factors/` 写探索 notebook，验证 IC / 分组收益
3. 通过验证后，把因子加进策略配置

## 添加新策略（标准流程）

每个策略走完整的「想法 → 实现 → 验证 → 结论」四步，文档留痕：

1. **想法 (ideas/)** — `cp -r ideas/_template ideas/<slug>`，填 `idea.md`：核心逻辑、依据、信号、预期表现
2. **实现 (configs/ + src/)** — 写 `configs/<slug>.yaml`；用现有因子表达不了就在 `src/strategy_lib/factors/` 新增；同步在 `summaries/<slug>/implementation.md` 记录
3. **验证 (notebooks/ + summaries/)** — 在 notebook 跑 IC / 分组 / 回测，关键结果按日期追加到 `summaries/<slug>/validation.md`，图表存 `artifacts/`
4. **结论 (summaries/)** — 上线/废弃/搁置时写 `conclusion.md`，并在 `summaries/README.md` 索引追加一行

slug 命名：`<market>_<core_logic>[_<filter>]`，如 `btc_momentum_rsi`、`cn_etf_rotation_lowvol`。
