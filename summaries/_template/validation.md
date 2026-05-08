---
slug: <strategy_slug>
updated: YYYY-MM-DD
---

# Validation — <策略名称>

> 每次新一轮回测/验证就追加一个 `## YYYY-MM-DD <轮次主题>` 小节，不要覆盖。

---

## YYYY-MM-DD 初版验证

### 配置 & 数据
- 配置：`configs/<...>.yaml` @ commit `<sha>`
- 数据范围：YYYY-MM-DD ~ YYYY-MM-DD
- 训练/样本外切分：

### 因子层（IC 分析）
| 因子 | IC 均值 | ICIR | Rank IC | 5d 衰减后 IC |
|---|---|---|---|---|
| factor_a | 0.0xx | 0.xx | 0.0xx | 0.0xx |

> 关键观察：

### 分位数分组
- Q1~Qn 累计收益：
- 多空（Qn-Q1）Sharpe：
- 单调性：（是否单调？哪一组反常？）

### 回测绩效
| 指标 | 值 |
|---|---|
| 年化收益 | |
| Sharpe | |
| 最大回撤 | |
| Calmar | |
| 换手率 | |
| 胜率 | |

### 关键图表
> 导出到 `artifacts/`，这里只放路径

- ![equity_curve](artifacts/equity_curve.png)
- ![ic_decay](artifacts/ic_decay.png)

### 解读 & 问题
- <这个轮次最大的发现>
- <让人疑惑的地方>

### 下一步
- [ ] <调整什么参数>
- [ ] <验证什么假设>

---
