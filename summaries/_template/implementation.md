---
slug: <strategy_slug>
created: YYYY-MM-DD
updated: YYYY-MM-DD
config_path: configs/<your_config>.yaml
related_idea: ideas/<slug>/idea.md
---

# Implementation — <策略名称>

## 整体方案
<对应 idea 中的核心逻辑，简述最终落到代码层面是怎么实现的>

## 因子清单
| Factor 类 | 文件 | 参数 | 方向 | 是新增还是复用 |
|---|---|---|---|---|
| `MomentumReturn` | `src/strategy_lib/factors/momentum.py` | `lookback=20` | +1 | 复用 |
| ... | | | | |

## 新增因子（如有）
<新因子的数学定义、为什么这么算、实现时关注的细节（比如 lookahead bias、复权处理）>

```python
# 关键代码片段（可选）
```

## 策略配置
- 配置文件：`configs/<...>.yaml`
- 类型：`single_threshold` / `cs_rank` / 自定义
- 关键参数：阈值、rebalance、top_n 等

## 数据
- 标的池来源（手工列 / 指数成分 / 板块）：
- 数据范围：
- 数据预处理（剔除新股/ST/停牌等）：

## 踩过的坑
- <比如：忘了 `shift(-1)` 导致未来函数偷看>
- <比如：A股 ETF 的成交量在 akshare 是手数，不是张数>

## 相关 commits
- 实现：`<sha>`
- 调参：`<sha>`
