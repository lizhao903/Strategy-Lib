---
slug: cn_etf_dca_basic
created: 2026-05-08
updated: 2026-05-08
config_path: configs/cn_etf_dca_basic.yaml
related_idea: ideas/cn_etf_dca_basic/idea.md
---

# Implementation — 基础 DCA（cn_etf_dca_basic）

## 整体方案

完全规则驱动，不依赖任何因子。核心循环：

1. **初始**：100,000 RMB 全部折算成 511990 货币 ETF 股数（开户入金，不收手续费）。
2. **遍历每日 close**：
   - 若该日是当月第 1 个交易日（DCA 触发日），从货币池卖出 `dca_amount=5000`，
     按 `risk_allocation`（默认等权）分配给风险池 6 只 ETF 买入；
     卖/买都按 `fees + slippage` 共享基线扣费。
   - 当日收盘簿记：cash = 货币 ETF 股数 × close；risk = ∑ 风险股数 × close；equity = cash + risk。
3. **不再平衡**：风险池一旦买入就持有到回测结束。

## 因子清单

| Factor 类 | 文件 | 参数 | 方向 | 是新增还是复用 |
|---|---|---|---|---|
| —— | —— | —— | —— | **本策略不使用任何 Factor** |

理由：DCA 是时间触发 + 等权规则，无需横截面/时序排名。

## 新增因子（如有）

无。

## 策略配置

- 配置文件：`configs/cn_etf_dca_basic.yaml`
- 类型：`dca_basic`（自定义类型，类路径 `strategy_lib.strategies.cn_etf_dca_basic.DCABasicStrategy`）
- 关键参数：
  - `dca_amount: 5000`（每月转入金额）
  - `dca_frequency: "M"`（月度触发）
  - `risk_allocation: "equal"`（风险池内部等权）

## 数据

- 标的池来源：手工列（与 Benchmark Suite V1 共享基线一致，6 只风险 ETF + 1 只货币 ETF）
- 数据范围：2020-01-01 ~ 2024-12-31（akshare `fund_etf_hist_em`，前复权 `qfq`）
- 数据预处理：
  - close 前向填充（停牌 / 早期数据缺失时维持上一日价格）
  - 货币 ETF 511990 起始价格异常时直接抛错（不做软兜底，避免无声错误）

## 关键代码思路

```python
class DCABasicStrategy:
    def run(self, panel, *, init_cash, fees, slippage, since, until) -> DCAResult:
        # 1. 拼宽表 close = panel[cash + risk_syms][close]
        # 2. 找出每月第 1 个交易日 dca_dates = idx.groupby([year, month]).first()
        # 3. cash_units = init_cash / close[cash, t0]   # 货币 ETF 股数
        # 4. for date in idx:
        #        if date in dca_dates:
        #            spend = min(dca_amount, cash_units * cash_price)
        #            cash_units -= spend / cash_price
        #            for sym, w in target_weights(date, prices).items():
        #                buy_px = price * (1 + slippage)
        #                units = (spend * w * (1 - fees)) / buy_px
        #                risk_units[sym] += units
        #        equity[t] = cash_units*cash_price + sum(risk_units * risk_prices)
```

设计选择：

- **不继承 BaseStrategy**：base 是 entries/exits 信号驱动，DCA 用不上，硬塞会让代码更乱。
- **不调 vectorbt**：DCA + 等权 + 无再平衡足够简单，纯 numpy 模拟反而清晰；当前环境也未装 vectorbt。
- **`target_weights(date, prices)` 暴露**：方便后续策略（Swing/Tilt）继承相同接口的"DCA 内部权重"语义。
- **货币池用真实 511990 价格**：而非 2% 年化简化。事后可在 validation 中和 2% 年化做对比。

## 踩过的坑

（首版实现，待真实回测后追加）

- ⚠️ **货币 ETF 价格语义**：511990 在 akshare `fund_etf_hist_em` 返回的 close 通常在 100 附近微涨，
  需确认前复权后是否产生不连续跳变。Smoke test 用合成数据无法暴露此问题，留待真实回测核对。
- ⚠️ **月初定位**：用 `idx.groupby([year, month]).first()` 而非 `MonthBegin offset`，
  避免月初遇周末时漏触发。

## 相关 commits

- 实现：（待提交）
