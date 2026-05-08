# Notes — cn_etf_overseas_equal

## 2026-05-08 想法起源（universe sweep 工具产出的 finding）

**事件链**：
1. 7 个策略 + 多次 v2 完成后，发现 alpha 优先级是「池子 >> 信号 >> 仓位」
2. 实现 `Universe` + `sweep()` 工具，第一次系统对比池子
3. demo 跑 4×4 grid，发现 overseas_4 在所有策略上都暴揍其他 universe
4. **决定**：把 S3 + overseas_4 形式化为 S8

**为什么编号 S8 而不是 S3 v2**：
- S3 是「等权再平衡」机制；本策略仍然用 S3 同样机制
- 但「换 universe」不是 v2 改进（v2 应该是同 universe 机制升级）
- 编号 S8 更符合 universe 选择本身就是策略的一部分

**为什么不立刻做 OOS 验证**：
- 当前数据只到 2024-12-31，OOS 需要 2025+ 数据
- akshare 可拉到当下日期，但「样本外」要等真正的未来数据
- 短期内可做的：3 个滚动 1.5y 窗口检查内一致性

## 事后归因（为什么 overseas_4 = best 而 expanded_11 不是？）

**直觉错误的方向**：以为「11 池 = 6 + 5 跨资产」是 superset，应该 ≥ 4 池 overseas（含其中 4 只）。
**实际情况**：11 池里的 6 只 A 股是**结构性拖累**，加进来反而稀释 alpha。

数学上：等权下，池子的预期收益 = 各资产预期收益的算术平均。如果 6 只 A 股 5 年累计 ~0%、5 只海外 5 年累计 +50%：
- 11 池等权：6/11 × 0% + 5/11 × 50% = ~22.7% 5 年（CAGR ~4.2%）
- overseas 4 池：100% × 50% = 50% 5 年（CAGR ~8.4%）

实测 expanded_11 CAGR +6.36%，overseas_4 CAGR +11.87%（高于 8.4% 是因为黄金贡献 + 多元化降波动）。**和算术直觉一致**。

## 警惕：这不是新发现，是已知的资产配置定理

「过去 5 年最佳大类组合的等权配置」就是 Mebane Faber 一直推的 GTAA / "Permanent Portfolio" / "Permanent Portfolio of Trends" 等系列做法的一种特例。**S8 在文献上不是新东西**。

但它在本项目内是新数据点：
- 揭示了「6 池 / 11 池基线」本身有偏置
- 证明 V1 全套（S1-S7）在错误的池上做了大量"参数调优"
- 为后续 crypto 验证（V2）确定了"先做 universe sweep 再做策略 ablation"的正确顺序

## 与 S3 / S5v2 在 overseas_4 上的对比

`universe_sweep_demo` 同样跑了 S5v2 + overseas_4：
- S3 + overseas_4: NAV 171.3k / Sharpe 0.851 / MaxDD -20.9%
- S5v2 + overseas_4: NAV 120.5k / Sharpe 0.717 / MaxDD **-8.5%**

S5v2 的 vol-target sizing 在 overseas_4 上把 MaxDD 压到 -8.5%（迄今最低），但代价是 NAV 也低 50k。
**两个版本各自代表不同 risk profile**。如果未来出现「Sharpe 优先 vs MaxDD 优先」的 trade-off 决策，建议 ship 两个：
- S8 = 「追求 alpha」 → S3 + overseas_4
- S5v2 + overseas_4 = 「追求 capital preservation」

## v2 / v3 候选

1. **5 池版**：在 overseas_4 基础上加 511260 十年国债 ETF，看能否在保持 alpha 的同时 buffer 2022-style 全大类下跌
2. **逆向版（A 股 only）**：完全去掉海外 + 黄金，只用 A 股 6 池——验证「A 股 5y 平盘」的对照实验（如果 OOS A 股 outperform，可以反过来）
3. **滚动 risk parity**：在 overseas_4 上用 vol-target 替代等权（继承 S5v2 sizing 思路）

---
