---
slug: cn_etf_market_ma_filter
status: shelved  # 避险命题部分兑现（2022 单年最佳）但总收益跑输 S3；保留代码 + lag=1 sweep 作为 v2 起点
finalized: 2026-05-08
---

# Conclusion — A股 ETF 大盘 MA 过滤 (S7 v1)

## 一句话结论

**避险命题部分兑现：搁置（shelved）**。在 2020-2024 样本期 S7（MA=200, lag=2）NAV 108.1k vs S3 110.8k vs S5v1 120.3k vs S5v2 112.9k vs BH 104.2k —— 跑输 S3 与 S5v1/v2，**但 2022 单年回撤 ≈ 0%（5 个策略中最佳）证明了"市场代理 timing 在熊市能避险"**。然而代价是 2024 单边行情完全错过（-3.6% vs S5v1 +28.1%/BH +18.4%），且 Sharpe 0.18 < S5 的 0.28。**lag=1 sweep 档位（NAV 119.1k / Sharpe 0.30）才是真正的 v1 最佳设置**，但 200MA 是唯一 work 的长度（100/150/250 全部 CAGR 为负），有单点过拟合嫌疑。

## 关键数据（2020-01-02 ~ 2024-12-31）

### 主跑（MA=200, lag=2）

| 指标 | S7 (MA200, lag=2) | S5v1 | S5v2 | S3 | 510300 BH |
|---|---:|---:|---:|---:|---:|
| NAV (100k) | 108.1k | **120.3k** | 112.9k | 110.8k | 104.2k |
| CAGR | +1.64% | **+3.92%** | +2.57% | +2.16% | +0.86% |
| Sharpe | 0.18 | **0.28** | **0.28** | 0.21 | 0.15 |
| Vol(ann) | 15.92% | 22.01% | **11.07%** | 23.78% | 21.77% |
| MaxDD | -30.25% | -47.80% | **-20.52%** | -45.18% | -44.75% |
| Calmar | 0.05 | 0.08 | **0.13** | 0.05 | 0.02 |
| **2022 单年** | **-0.02%** | -21.61% | -7.58% | -23.47% | -21.68% |
| 2023 单年 | -12.38% | -18.91% | -8.01% | -10.17% | -10.43% |
| 2024 单年 | -3.61% | **+28.09%** | +0.47% | +8.82% | +18.39% |
| 切换次数 | 25 | (高频, 60+ 评估) | (中, 连续) | 0 | 0 |
| 空仓占比 | 60.2% | 18.2%（双峰） | 70%（连续） | 0% | 0% |
| OFF↔BH 跌相关性 | **0.052** | 0.033 | 0.031 | — | — |

### lag=1 sweep（实际上的 v1 最佳档）

| 指标 | S7 (MA200, **lag=1**) |
|---|---:|
| NAV (100k) | **119.1k** |
| CAGR | +3.71% |
| Sharpe | **0.30**（持平/略胜 S5） |
| MaxDD | -27.26% |
| 2022 单年 | -0.01% |
| 2024 单年 | -1.6% (估) |
| 切换次数 | 31 |
| OFF↔BH 跌相关性 | **0.099**（接近 S5 三倍） |

### MA 长度敏感性结果

唯一 CAGR 为正的档位是 **MA=200**：

| MA | NAV | CAGR | 备注 |
|---:|---:|---:|---|
| 100 | 67.9k | -7.77% | 太短，假突破吃光 |
| 150 | 73.8k | -6.15% | 仍太短 |
| **200** | **108.1k** | **+1.64%** | **唯一 work 档** |
| 250 | 77.9k | -5.08% | 太长，2024/2020 反弹错过 |

⚠️ **过拟合警告**：单一参数 work + 邻近档位都不 work → 在 OOS 上很可能失效。
但 200 是 Faber 给定的先验默认，不算后验调参。

## 在什么情况下有效，什么情况下失效

- ✅ **极端下跌年（2022）**：完美避开，整年 0% 收益（5 个策略最佳，胜过 S5v2 -7.6%）
- ✅ **持续单边趋势上升后 + 持续单边下行后**：信号能稳定捕捉 regime
- ✅ **信号稳定性**：5 年 25 次切换、平均 ON 段 37 天、OFF 段 56 天，与"市场 regime"节奏吻合
- ❌ **快速反转**：2020-Q1 疫情急跌后的 V 型反弹，200MA 太慢、4-12 月反弹错过
- ❌ **结构性单边牛市启动早期**：2024 9-10 月行情前 510300 还在 MA200 下方，整段错过 +18% BH 收益
- ❌ **震荡市**：2023 -12.4% 跑输 S3 -10.2%（频繁假突破吃成本）
- ❌ **风险调整收益**：Sharpe 0.18 < S3 0.21 < S5 0.28（lag=2 主跑）
- ⚠️ **lag>1 越大越差**：lag=1→3→5 NAV 119k→108k→99k→91k，过滤反而损害收益

## 这个策略教会我什么（可迁移的经验）

1. **A 股 ETF 池上"避险 timing"的下限**：S5v1/v2 的 cash↔down corr 0.03 不是
   逐标的趋势的局限，而是**所有滞后型 MA 信号在 A 股 ETF 池上的共性**。
   200MA 也只能做到 0.05-0.10，远低于 V1 baseline 命题假设的 0.20+。
   **教训**：想要真正的 timing 类避险，必须用更快的信号（ATR、价格突破带宽、
   vol-of-vol），而不是任何形式的 MA。

2. **市场代理 vs 逐标的趋势的差距是"信号稳定性"，不是"timing 准确性"**：
   - S7 切换 25 次 vs S5v1 (60+ 评估机会)
   - S7 OFF↔down corr 0.052 vs S5 0.033（小幅改善）
   - **S7 的优势是"少假信号、避免成本耗损"**，不是"更早识别下跌"
   - 教训：当 6 标的高度同源时，1 个市场代理 ≈ 1.5 倍信噪比的 6 个独立信号，
     不是质变。如果想要质变，需要跨资产类别（股+债+商品）或跨市场（A+港+美）

3. **滞后过滤是事前合理、事后无效的"保险机制"**：
   - 设计时认为 N=2 能过滤假突破
   - 实测 lag=1 反而最佳（NAV +10% / Sharpe +0.12 / corr +0.05）
   - 200MA 本身的低通滤波已经够（窗口 199 天的平均），再加 N=2 是过度平滑
   - 教训：**长 MA + 短 lag** 优于 **短 MA + 长 lag**；过滤层次越多越糟糕

4. **"避险命题兑现"和"shipped"是两个概念**：
   - 2022 单年 0% 是 5 个策略最佳 → 命题在那一年完美兑现
   - 但 5 年总 NAV 跑输 S3 → 不能 ship 取代 S3
   - 教训：**defense-only strategy 的成立标准应当是"在熊年提供保护、其他年不显著拖后腿"**，
     S7 在 2024 牛市的 -3.6% 损失太大（比 S5v2 +0.47% 还差），所以 shelved
   - 解决方向：v2 用更快信号（再次回到上一条）

5. **回测的 lag 选择应当跑 sensitivity 再决定主参数**：
   - 事前以 lag=2 为主跑、lag=1 作"消融"
   - 事后发现 lag=1 是真正的最佳
   - 教训：**任何超参的"事前默认"都应当被 sensitivity 推翻**；如果 sensitivity
     里的某档位明显胜过事前默认，要把那档作为新主参数（v2 直接采用）

## 后续动作

- [x] 真实回测出结果，决定 status = **shelved**（避险命题部分兑现但跑输 S3，主参数 lag=2 失败；lag=1 sweep 是 v2 的起点）
- [ ] **v2 候选**：
  - **v2.1**（直接 v1 微调）：主参数改 `lag_days=1`，重测 NAV/Sharpe/2024 损失能否被接受
  - **v2.2**（双 MA）：close > MA50 进场、close < MA200 出场（金叉/死叉）—— 抓 2024 单边的同时保留 2022 避险
  - **v2.3**（信号源升级）：用等权 6 池合成净值替代 510300 作为信号资产（更纯净的"我们持仓的市场"）
  - **v2.4**（叠加扩池）：risky pool 改 11 池（继承 S4v2 alpha），看 alpha 是否能盖住 timing 损失
- [ ] OOS：等 2025 H1 数据后跑一次（特别检验 2024 末/2025 初的反弹捕捉能力）
- [ ] 不再继续 v3：如果 v2.1-v2.4 都不能让 NAV ≥ S5v1 120.3k，说明"MA 类信号在 A 股 ETF 池"已无 alpha 空间，结案

## 相关链接

- Idea：`ideas/S7_cn_etf_market_ma_filter/v1/idea.md`
- Notes：`ideas/S7_cn_etf_market_ma_filter/v1/notes.md`
- 实现：`summaries/S7_cn_etf_market_ma_filter/v1/implementation.md`
- 验证记录：`summaries/S7_cn_etf_market_ma_filter/v1/validation.md`
- 验证脚本：`summaries/S7_cn_etf_market_ma_filter/v1/validate.py`（`smoke` / `real` / `all`）
- Artifacts：`summaries/S7_cn_etf_market_ma_filter/v1/artifacts/`
  - `equity_curve.png`、`drawdown.png`（含 2022 特写）
  - `signal_overlay.png`（**核心可视化**：510300 close + MA200 + ON/OFF 色块）
  - `regime_periods.png`（切换日 + ON/OFF 段时长直方图）
  - `ma_length_sensitivity.csv`、`lag_sensitivity.csv`
- 配置：`configs/S7_cn_etf_market_ma_filter_v1.yaml`
- 实现代码：`src/strategy_lib/strategies/cn_etf_market_ma_filter.py`
- 兄弟策略对照：
  - S3 baseline：`src/strategy_lib/strategies/cn_etf_equal_rebalance.py`
  - S5v1（逐标的趋势）：`src/strategy_lib/strategies/cn_etf_trend_tilt.py`
  - S5v2（连续 + vol filter + bond）：`src/strategy_lib/strategies/cn_etf_trend_tilt_v2.py`
- 命题来源：`docs/benchmark_suite_v1.md` v3 候选：「换大盘 200MA 二元过滤」
