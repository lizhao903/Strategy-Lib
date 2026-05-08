# S8 · cn_etf_overseas_equal — 版本索引

港股 + 海外 + 黄金 4 只 CN-listed ETF 等权（**无 A 股**）。复用 `EqualRebalanceStrategy`，无新策略类。

| Version | 池组成 | NAV (100k) | CAGR | Sharpe | MaxDD | vs BH | 数据来源 | Status |
|---|---|---:|---:|---:|---:|---:|---|---|
| [v1](v1/) | 159920/513100/513500/518880 | **★171.3k** | **★+11.87%** | **★0.851** | -20.9% | **★+11.01%** | universe_sweep_demo | validating (no dedicated run) |

★ = 截至 2026-05-08 全套（S1-S7 含 v2）实测中**所有维度第一**。

## 起源
2026-05-08 实现 `Universe + sweep` 工具后，第一次跑 4 strategies × 4 universes grid，发现 overseas_4 池在所有 4 个策略上都暴揍其他 universe，且 S3 等权在 overseas_4 上 Sharpe 0.851 直接刷新全套记录。

## 关键警告
**窗口偶然性**：2020-2024 是「A 股最弱 + 美股最强 + 黄金牛市」组合。事后选 4 个最强大类做等权，本质是 lookback bias。**OOS（2025+）必须验证**才能 ship。

## 当前 status：`validating (no dedicated run)`
- ✅ 在 sweep grid 中跑过 in-sample（与其他 7 策略可横向对比）
- ❌ 没有专门的 validate.py 跑分年度 / vs BH 详细 / 滚动窗口
- ❌ OOS 数据未到

## v2 候选
- 5 池版：+ 511260 十年国债 ETF（buffer 2022-style 全大类下跌）
- vol-target 版：在 overseas_4 上用 sizing 替代等权（继承 S5v2 思路）—— 已知 S5v2 + overseas_4 MaxDD -8.5% 是另一个亮点
