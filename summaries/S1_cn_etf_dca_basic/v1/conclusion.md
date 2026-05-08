---
slug: cn_etf_dca_basic
status: validating-realdata-done
finalized: TBD
---

# Conclusion — 基础 DCA（cn_etf_dca_basic）

> 状态：**真实数据回测已完成，待用户审阅 + 与 Strategy 2/3/4/5 横向对比后定稿。**

## 一句话结论

在 2020-01 ~ 2024-12 的 A股 ETF 真实样本上，基础 DCA 跑输 510300 BH（CAGR -2.25% vs +0.86%，超额 -14.54%）；
现金缓冲仅覆盖前 21 个月（2021-09 耗尽），既错过 2020 的疫情反弹、又没赶上 2022 熊市的对冲价值，
此后策略退化为 6 ETF 静态等权组合，与基准的差异完全由池子构成决定，而非 DCA 节奏。

## 关键数据

| | DCA basic | 510300 BH |
|---|---:|---:|
| 样本期 | 2020-01-02 ~ 2024-12-31 | 同左 |
| 样本外 | 无（DCA 规则无参数拟合，整段即样本外）| 同左 |
| 最终 NAV (RMB) | 89,647.22 | 104,275.01 |
| 总收益 | -10.35% | +4.28% |
| 年化收益 (CAGR) | -2.25% | +0.86% |
| 年化波动 | 20.24% | 21.76% |
| Sharpe | -0.012 | +0.148 |
| 最大回撤 | -45.13% | -44.75% |
| Calmar | -0.050 | +0.019 |
| 年化换手率 | 21.33% | 0% |
| 超额总收益 | -14.54% | —— |
| 信息比率 | -0.278 | —— |
| 跟踪误差 | 12.44% | —— |

分年度：

| 年份 | DCA | BH | 差 |
|---:|---:|---:|---:|
| 2020 | +13.35% | +31.11% | -17.76% |
| 2021 | +4.72%  | -4.32%  | +9.03% |
| 2022 | -23.78% | -21.68% | -2.10% |
| 2023 | -9.90%  | -10.43% | +0.54% |
| 2024 | +9.98%  | +18.39% | -8.41% |

## 在什么情况下有效，什么情况下失效

- ✅ **2021 类行情有效**：现金未耗尽 + 风险池中小盘 / 行业 ETF 跑赢沪深 300 主板时，DCA 能产生 +9pct 的超额。
- ❌ **2020 类牛市无效**：现金缓冲在牛市初期是机会成本，本轮代价为 -17.76pct。
- ❌ **现金耗尽后失效**：第 21 个月起策略退化为 6 ETF 静态等权，不再具备"慢入场对冲下行"属性，
  2022 熊市反而比 BH 多跌 2.10pct（因池子里小盘 / 医疗权重高于 510300）。
- ❌ **池子构成决定 2024 反弹的迟钝度**：医疗 (512170)、中证 1000 (512100) 在 2024 跑输沪深 300，
  而非 DCA 节奏导致。

## 这个策略教会我什么（可迁移的经验）

1. **DCA 的现金缓冲长度必须和回测窗口匹配**：`init_cash / (dca_amount * 12)` 决定缓冲月数，
   超过该窗口后 DCA 节奏失效，策略退化为静态权重。基线 100k / 5k = 20 月，对 5 年回测显然不够。
2. **风险池构成 ≫ 入场节奏**：现金耗尽后 alpha 全部由池子里 6 只 ETF 与基准的相对走势决定。
   DCA 类策略的横向对比应控制池子一致，单独研究节奏。
3. **"DCA 在熊市保护下行" 的常见叙事**：只在 **缓冲未耗尽** 的窗口内成立。
   要让叙事通用，得引入 swing / rebalance 把现金重新生成出来——即 Strategy 2。

## 后续动作

- [x] 真实数据回测：`python summaries/cn_etf_dca_basic/validate.py`
- [x] 追加 `validation.md` `## 2026-05-08 真实数据回测` 小节
- [x] 产出三张关键图（equity / drawdown / cash_vs_risk）+ weights_stack.png
- [ ] 敏感性测试：`dca_amount`、`dca_frequency`、`risk_allocation=inverse_price`
- [ ] 修复 `DCABasicStrategy.run` 内部 tz mismatch 边界
- [ ] 与 Strategy 2/3/4/5 横向对比
- [ ] 决策：状态 → `shipped` / `shelved` / `rejected`

## 相关链接
- Idea：`ideas/cn_etf_dca_basic/idea.md`
- Notes：`ideas/cn_etf_dca_basic/notes.md`
- 实现：`summaries/cn_etf_dca_basic/implementation.md`
- 验证记录：`summaries/cn_etf_dca_basic/validation.md`
- 配置：`configs/cn_etf_dca_basic.yaml`
- Artifacts：`summaries/cn_etf_dca_basic/artifacts/{equity_curve,drawdown,cash_vs_risk,weights_stack}.png`
- 关键 commit：（待提交，本次回测基于工作树快照）
