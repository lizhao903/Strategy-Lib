---
slug: cn_etf_market_ma_filter_v2
created: 2026-05-08
updated: 2026-05-08
config_path: configs/S7_cn_etf_market_ma_filter_v2.yaml
related_idea: ideas/S7_cn_etf_market_ma_filter/v2/idea.md
---

# Implementation — S7 v2 (lag=1 + 11 池)

## 整体方案
把 v1 sensitivity sweep 已验证的两条结论变成默认 ship：
1. lag_days = 1（v1 sweep 4 档中唯一显著跑赢 S3 的）
2. risky pool = 11 跨资产 ETF（S4v2 已证扩池贡献 73% alpha）

## 代码组织
**最小化代码差异**：v2 类 `MarketMAFilterV2Strategy` 只继承 v1 类，**仅改默认参数**：

```python
class MarketMAFilterV2Strategy(MarketMAFilterStrategy):
    DEFAULT_SYMBOLS = RISKY_POOL_11   # 11 池

    def __init__(self, ..., lag_days=1, ...):  # 默认 1（v1 默认 2）
        super().__init__(..., lag_days=lag_days, ...)
```

v1 类不动，作为 baseline 对比版保留。

## 因子清单
无新增。MA200 信号在 v1 已实现。

## 11 池组成
| symbol | 类别 | 来自 |
|---|---|---|
| 510300 | 沪深300 | V1 6 池 |
| 510500 | 中证500 | V1 6 池 |
| 159915 | 创业板 | V1 6 池 |
| 512100 | 中证1000 | V1 6 池 |
| 512880 | 证券 | V1 6 池 |
| 512170 | 医疗 | V1 6 池 |
| 159920 | 恒生 ETF (港股) | S4v2 扩池 |
| 518880 | 黄金 ETF | S4v2 扩池 |
| 513100 | 纳指 ETF | S4v2 扩池 |
| 513500 | 标普500 ETF | S4v2 扩池 |
| 511260 | 十年国债 ETF | S4v2 扩池 |

## 策略配置
- 配置文件：`configs/S7_cn_etf_market_ma_filter_v2.yaml`
- 信号资产：510300（沪深300），用 200MA 做过滤
- ON 时仓位：11 ETF 等权 1/11
- OFF 时仓位：511990 货币基金 100%
- 切换：信号变化 → vbt 自动 from_orders + targetpercent

## 踩过的坑
- `plot_signal_overlay` 当 `result.signal` 与 panel index 长度不一致时（暖机期处理）`fill_between` 会 raise size mismatch → 修：先用 `.intersection()` 对齐到共同 index 再画
- v2 类继承 v1 实例化时如果不传 `symbols`，`super().__init__(symbols=None, ...)` 会用 v1 的 `DEFAULT_SYMBOLS` 而不是 v2 的 → 已通过覆盖 `DEFAULT_SYMBOLS` class attr 解决

## 相关 commits
（uncommitted at this stage; 与 v1 共用代码体）
