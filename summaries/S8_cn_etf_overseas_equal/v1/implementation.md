---
slug: cn_etf_overseas_equal
created: 2026-05-08
updated: 2026-05-08
config_path: configs/S8_cn_etf_overseas_equal_v1.yaml
related_idea: ideas/S8_cn_etf_overseas_equal/v1/idea.md
---

# Implementation — S8 v1 (overseas_equal)

## 整体方案
**完全没有新代码**。S8 = `EqualRebalanceStrategy` (S3 同款) + `CN_ETF_OVERSEAS_4` universe。

```python
from strategy_lib.strategies.factories import s3_equal_rebalance
from strategy_lib.universes import CN_ETF_OVERSEAS_4
from strategy_lib.backtest import run_on_universe

metrics = run_on_universe(s3_equal_rebalance, CN_ETF_OVERSEAS_4)
```

## 因子清单
无。

## 新增因子（如有）
无。

## 策略配置
- 配置文件：`configs/S8_cn_etf_overseas_equal_v1.yaml`
- 类型：`equal_rebalance`（复用）
- 关键参数：`rebalance_period=20`（月度）
- 池组成：159920 恒生 / 513100 纳指 / 513500 标普500 / 518880 黄金

## 数据
- 标的池来源：手工选 4 只 CN-listed 跟踪海外/黄金的 ETF（去掉 A 股内部标的）
- 数据范围：2019-09-01 ~ 2024-12-31（120 日暖机 + 5 年绩效统计）
- 数据预处理：复用 `cn_etf` loader 的前复权（akshare adjust="qfq"）
- 已缓存：所有 4 标的 + 现金代理 511990 + benchmark 510300 都在 `data/raw/cn_etf/` 中

## 关键代码（无新增，引用现有）
- 等权机制：`src/strategy_lib/strategies/cn_etf_equal_rebalance.py::EqualRebalanceStrategy.run()`
- universe 定义：`src/strategy_lib/universes.py::CN_ETF_OVERSEAS_4`
- factory: `src/strategy_lib/strategies/factories.py::s3_equal_rebalance`

## 踩过的坑
- **没踩过坑**：S8 的实测在 sweep 工具里第一次就跑通，没有改任何代码
- 唯一注意：159920 / 513500 / 513100 / 518880 在 akshare 上数据齐全（5y ~1338 bars），但 159920（恒生 ETF）在 QDII 额度紧张时段可能有 1-2% 跟踪误差，长期累积误差暂时未单独计算

## 相关 commits
（uncommitted；S8 与所有 V1 v2 共在一个工作树）

## 与现有代码的接口契约
- S8 复用 S3 的 `target_weights` 钩子（默认实现 = 等权 1/N）
- universe 切换通过 `factory(universe)` 模式自动适配
- 不影响 S3 v1 / S4v2 / S5v2 / S7v2 等任何已有策略
