# Strategy-Lib

多市场量化策略研究库。覆盖 **Crypto / A股 / 港股 / 美股 / ETF**，基于 **vectorbt** 回测，研究流程：Notebook 探索 → 库代码沉淀。

## 项目状态（2026-05-08）

- ✅ **V1 Suite (A股 ETF)**: 9 个策略实现（S1-S8 含 v2），完整 in-sample 回测
- ✅ **V2 Suite (Crypto)**: V2-S1 baseline 已 ship；S2-S5 设计中
- ✅ **核心工具**: Universe 抽象 + 11 个 strategy factory + sweep grid + quickrun 一键 CLI
- 🔜 **进行中**: 13 个 [GitHub issues](https://github.com/lizhao903/Strategy-Lib/issues) 含 OOS 测试、扩展验证、工程改进

详细策略对比见 [`summaries/README.md`](summaries/README.md)；详细发现见 [`docs/benchmark_suite_v1.md`](docs/benchmark_suite_v1.md) / [`docs/benchmark_suite_v2_crypto.md`](docs/benchmark_suite_v2_crypto.md)。

## 快速上手

### 安装
```bash
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e ".[dev]"
# 网络不稳时加 mirror: --index-url https://mirrors.aliyun.com/pypi/simple/
```

### 1 行验证任意标的池（推荐）

```bash
# Crypto（含 / 自动识别）
slib quickrun --symbols 'BTC/USDT,ETH/USDT,SOL/USDT' --strategies 'S3,S4v2,S5v2'

# A股 ETF（6 位数字自动识别）
slib quickrun --symbols '510300,510500,159915,512100' --since 2020-01-02

# 美股（字母自动识别）
slib quickrun --symbols 'AAPL,MSFT,GOOG' --benchmark SPY
```

输出：strategy 对比表 + BH baseline + `results/quickrun_<ts>/{summary.md, results.csv}`。

Python 等价：
```python
from strategy_lib import quickrun
quickrun("BTC/USDT,ETH/USDT,SOL/USDT", strategies=["S3", "S4v2", "S5v2"])
```

`quickrun` 自动推断：market（含 `/` → crypto / 6 位数字 → cn_etf / 字母 → us_stock）、cash_proxy（USDT / 511990 / BIL）、benchmark（BTC/USDT / 510300 / SPY）、年化天数（crypto 365 / 其他 252）、交易成本。

### 跑预定义策略 grid

```python
from strategy_lib.backtest import sweep
from strategy_lib.universes import CN_ETF_EXPANDED_11, CRYPTO_TOP_5
from strategy_lib.strategies.factories import s3_equal_rebalance, s4v2_momentum_tilt

df = sweep(
    strategies={"S3": s3_equal_rebalance, "S4v2": s4v2_momentum_tilt},
    universes=[CN_ETF_EXPANDED_11, CRYPTO_TOP_5],
    since="2021-01-01", until="2024-12-31",
)
```

### 已注册的 universe（10 个）

| Universe | 标的数 | Market | 描述 |
|---|---:|---|---|
| `CN_ETF_BASE_6` | 6 | cn_etf | V1 baseline：沪深300/中证500/创业板/中证1000/证券/医疗 |
| `CN_ETF_EXPANDED_11` | 11 | cn_etf | base_6 + 跨资产 5（恒生/黄金/纳指/标普500/十年国债）|
| `CN_ETF_BROAD_3` | 3 | cn_etf | A股宽基 3 只 |
| `CN_ETF_OVERSEAS_4` | 4 | cn_etf | 港股+海外+黄金（无 A 股，**S8 全维度第一**）|
| `CN_ETF_DEFENSIVE_3` | 3 | cn_etf | 防御组合：国债+黄金+货币 |
| `CRYPTO_BTC_ETH_2` | 2 | crypto | 极简 BTC/ETH |
| `CRYPTO_TOP_3` | 3 | crypto | BTC/ETH/SOL |
| `CRYPTO_TOP_5` | 5 | crypto | **V2-S1 默认**：+BNB/XRP |
| `CRYPTO_TOP_5_NO_SOL` | 4 | crypto | 剔除 SOL ablation 池 |
| `CRYPTO_TOP_10` | 10 | crypto | +DOGE/ADA/AVAX/LINK/DOT |

临时池一行造：`Universe.custom("test", ["A","B","C"], market="crypto", cash_proxy="USDT")`

## 当前最佳配置（in-sample 数据，OOS 待验）

| 目标 | 推荐配置 | 数据 |
|---|---|---|
| 🥇 **总收益（A股 ETF）** | S8 = `s3_equal_rebalance(CN_ETF_OVERSEAS_4)` | NAV 171.3k / Sharpe 0.85 / MaxDD -20.9% |
| 🥇 **最低 MaxDD（A股）** | S5v2 + overseas_4 | MaxDD -8.5% |
| 🥇 **总收益（Crypto）** | S4v2 momentum + CRYPTO_TOP_10 | NAV 3798.6k / Sharpe 1.42 |
| 🥇 **最高 Sharpe（Crypto）** | S5v2 trend + CRYPTO_TOP_10 | Sharpe 1.583 / MaxDD -30% |

**核心规律（多次 ablation 印证）**：池子选择 >> 信号选择 >> 仓位选择。

## 目录结构

```
Strategy-Lib/
├── src/strategy_lib/                     # 核心库
│   ├── data/                             # 4 类市场 loader（crypto/cn_*/hk/us）+ parquet 缓存
│   ├── factors/                          # Factor 基类 + 12 个示例因子（含 V2 新增）
│   ├── analysis/                         # IC、分位数分组、可视化
│   ├── strategies/                       # 12 个策略类 + factories.py 适配层
│   ├── backtest/                         # vectorbt 包装 + sweep + run_on_universe
│   ├── universes.py                      # Universe 类 + 10 预定义池
│   ├── quickrun.py                       # 无脑一行验证
│   └── cli.py                            # slib 命令行入口
├── ideas/                                # 策略想法库（每策略一目录，多版本）
│   └── S{N}_<slug>/v{X}/{idea,notes}.md
├── summaries/                            # 策略实现与验证留痕
│   └── S{N}_<slug>/
│       ├── README.md                     # 版本索引
│       └── v{X}/
│           ├── implementation.md         # 怎么实现的
│           ├── validation.md             # IC/分组/回测（按日期追加，不覆盖）
│           ├── conclusion.md             # 最终结论
│           ├── validate.py               # 可重跑验证脚本
│           └── artifacts/                # 图表 / CSV / JSON
├── configs/                              # yaml 策略配置
│   └── S{N}_<slug>_v{X}.yaml
├── docs/                                 # 共享基线文档
│   ├── benchmark_suite_v1.md             # V1 (A 股 ETF) 全套
│   └── benchmark_suite_v2_crypto.md      # V2 (Crypto) 计划
├── data/raw/                             # parquet 缓存（gitignore）
├── results/                              # 回测产物（gitignore）
├── scripts/                              # 一次性脚本（universe_sweep_demo / v2_crypto_sweep）
└── tests/                                # 单元测试
```

## 设计原则

1. **因子和策略与市场解耦**：所有因子函数接收 `pd.DataFrame`（标准 OHLCV 列），不关心数据来源。
2. **数据层有缓存**：第一次拉取写入 `data/raw/<market>/<symbol>.parquet`，之后从本地读。
3. **因子是类，不是函数**：每个因子继承 `Factor`，封装参数、依赖列、计算逻辑、方向（高值看多/看空）。
4. **策略 + universe 分离**：策略不写死 symbols，通过 `factory(universe)` 注入。任意标的池都可复用任意策略。
5. **Notebook 只是探索**：可复用的代码必须沉淀到 `src/`。
6. **双层文档**：`ideas/` 记录想法（不覆盖），`summaries/` 记录验证（追加日期，不覆盖）。失败也写——下次类似想法可查。

## 添加新策略（标准流程）

每个策略走完整四步，全程留痕：

1. **想法**：`mkdir -p ideas/S{N}_<slug>/v1`，填 `idea.md`（依据 `ideas/_template/idea.md` 模板）
2. **实现**：写 `src/strategy_lib/strategies/<slug>.py`（或继承现有类）+ `configs/S{N}_<slug>_v1.yaml`，同步 `summaries/S{N}_<slug>/v1/implementation.md`
3. **验证**：写 `summaries/S{N}_<slug>/v1/validate.py`，跑出来后追加结果到 `validation.md`（按日期，不覆盖）
4. **结论**：策略状态确定时写 `conclusion.md`，更新 `summaries/README.md` 顶级表

后续 v2 改进 → 新建 `v2/` 子目录，v1 完整保留对照。

详见 [CLAUDE.md](CLAUDE.md) 协作约定。

## 进一步阅读

- [`summaries/README.md`](summaries/README.md) — 全策略横向对比 + 跨版本核心学习
- [`docs/benchmark_suite_v1.md`](docs/benchmark_suite_v1.md) — V1 共享基线 + 实测结果
- [`docs/benchmark_suite_v2_crypto.md`](docs/benchmark_suite_v2_crypto.md) — V2 Crypto 计划
- [`CLAUDE.md`](CLAUDE.md) — Claude Code 协作约定与项目教训
- [GitHub Issues](https://github.com/lizhao903/Strategy-Lib/issues) — 待解决问题与 roadmap
