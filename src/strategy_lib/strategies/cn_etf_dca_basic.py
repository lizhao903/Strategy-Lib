"""Strategy 1 — 基础 DCA（cn_etf_dca_basic）。

货币基金（511990）作为现金池 + 风险资产池（6 只 ETF 等权）。
每月第 1 个交易日从货币池等额转入风险池，不做主动调仓。

设计要点：
- 权重驱动而非信号驱动，**不**继承 BaseStrategy（base 是 entries/exits 信号语义，不匹配）。
- 自包含 `run(panel, ...)`，纯 numpy/pandas 模拟净值，不依赖 vectorbt。
- 输出 `StrategyResult` 同款 dataclass（reuse base 中的定义）以保持 metrics dict 接口一致。
- `target_weights(date, prices)` 暴露给上层做调试 / 可视化。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# 默认参数（与 docs/benchmark_suite_v1.md 共享基线对齐）
DEFAULT_CASH_SYMBOL = "511990"
DEFAULT_RISK_POOL = ("510300", "510500", "159915", "512100", "512880", "512170")
DEFAULT_DCA_AMOUNT = 5_000.0
DEFAULT_INIT_CASH = 100_000.0
DEFAULT_FEES = 0.00005   # 万 0.5
DEFAULT_SLIPPAGE = 0.0005  # 万 5


@dataclass
class DCAResult:
    """DCA 策略回测结果（结构兼容 BaseStrategy 的 StrategyResult.metrics）。"""

    equity: pd.Series        # 组合净值（含现金 + 风险持仓）
    cash: pd.Series          # 货币池余额（RMB）
    holdings: pd.DataFrame   # 各风险 ETF 持有股数
    weights: pd.DataFrame    # 各风险 ETF 占组合净值权重
    trades: pd.DataFrame     # 交易流水（date, symbol, side, qty, price, notional, fee）
    metrics: dict            # 关键绩效指标
    portfolio: object = None  # 兼容字段，留给后续接 vectorbt
    factor_values: pd.DataFrame = field(default_factory=pd.DataFrame)
    signals: pd.DataFrame = field(default_factory=pd.DataFrame)


class DCABasicStrategy:
    """基础 DCA 策略：货币池 → 6 只风险 ETF 等额定投，无再平衡。

    Parameters
    ----------
    cash_symbol : str
        现金池标的（默认 "511990" 华宝添益）。
    risk_symbols : list[str]
        风险资产池标的列表（默认 6 只行业/宽基 ETF）。
    dca_amount : float
        每次 DCA 转入风险池的金额（RMB）。默认 5_000。
    dca_frequency : {"M", "W"}
        DCA 频率。"M" 每月第 1 个交易日，"W" 每周第 1 个交易日。默认 "M"。
    risk_allocation : {"equal", "inverse_price"}
        每次 DCA 在风险池内部如何分配。"equal"：金额均分；
        "inverse_price"：按当日收盘价倒数加权（低吸）。默认 "equal"。
    name : str
        策略实例名（用于日志/图表）。
    """

    def __init__(
        self,
        cash_symbol: str = DEFAULT_CASH_SYMBOL,
        risk_symbols: list[str] | tuple[str, ...] = DEFAULT_RISK_POOL,
        *,
        dca_amount: float = DEFAULT_DCA_AMOUNT,
        dca_frequency: str = "M",
        risk_allocation: str = "equal",
        name: str = "cn_etf_dca_basic",
    ) -> None:
        if dca_frequency not in ("M", "W"):
            raise ValueError(f"dca_frequency must be 'M' or 'W', got {dca_frequency}")
        if risk_allocation not in ("equal", "inverse_price"):
            raise ValueError(
                f"risk_allocation must be 'equal' or 'inverse_price', got {risk_allocation}"
            )
        self.cash_symbol = cash_symbol
        self.risk_symbols = list(risk_symbols)
        self.dca_amount = float(dca_amount)
        self.dca_frequency = dca_frequency
        self.risk_allocation = risk_allocation
        self.name = name

    # ------------------------------------------------------------------ helpers

    def _build_close_panel(self, panel: dict[str, pd.DataFrame]) -> pd.DataFrame:
        """组装一个仅含 close 的宽表，行 = 日期，列 = 全部 symbol（cash + risk）。"""
        all_syms = [self.cash_symbol] + self.risk_symbols
        missing = [s for s in all_syms if s not in panel]
        if missing:
            raise KeyError(f"panel 缺少 symbol：{missing}")
        close = pd.DataFrame(
            {s: panel[s]["close"] for s in all_syms}
        ).sort_index()
        # 前向填充，保险（停牌/早期数据缺失时维持上一日价格）
        close = close.ffill()
        return close

    def _dca_trigger_dates(self, idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
        """根据 dca_frequency 找出每月（每周）第 1 个交易日。

        实现说明：用 pd.Series(range(n)) 在 idx 上分组取第 1 个 **位置**，
        再用 idx[positions] 还原 Timestamp，避免 groupby + .values 把 tz 信息丢掉。
        """
        if self.dca_frequency == "M":
            grouper = [idx.year, idx.month]
        else:  # "W"
            iso = idx.isocalendar()
            grouper = [iso.year.values, iso.week.values]
        positions = pd.Series(np.arange(len(idx)), index=idx).groupby(grouper).first()
        first_positions = sorted(positions.tolist())
        return idx[first_positions]

    def target_weights(
        self, date: pd.Timestamp, prices: pd.Series
    ) -> dict[str, float]:
        """暴露：在 DCA 日，单次买入金额在风险池内部的权重分配。

        注意：这是"DCA 动作的内部权重"，**不是**组合的目标权重（组合权重随价格漂移）。
        """
        if self.risk_allocation == "equal":
            n = len(self.risk_symbols)
            return {s: 1.0 / n for s in self.risk_symbols}
        # inverse_price
        p = prices.reindex(self.risk_symbols).astype(float)
        if (p <= 0).any() or p.isna().any():
            # 兜底：若有价格异常，退回 equal
            n = len(self.risk_symbols)
            return {s: 1.0 / n for s in self.risk_symbols}
        inv = 1.0 / p
        w = inv / inv.sum()
        return w.to_dict()

    # ------------------------------------------------------------------ core run

    def run(
        self,
        panel: dict[str, pd.DataFrame],
        *,
        init_cash: float = DEFAULT_INIT_CASH,
        fees: float = DEFAULT_FEES,
        slippage: float = DEFAULT_SLIPPAGE,
        since: str | pd.Timestamp | None = None,
        until: str | pd.Timestamp | None = None,
    ) -> DCAResult:
        """跑回测。返回 DCAResult。

        簿记规则
        --------
        - 起始：cash = init_cash 全部进入 511990 货币池，risk holdings 全为 0。
        - 每日：cash 随 511990 价格变动而变动（货币池 = 货币ETF 持仓数 × 当日 close）。
          实现上把 cash 折算成"货币 ETF 股数 × 价格"，与风险池簿记一致。
        - DCA 日（每月第 1 个交易日）：从货币池卖出 `dca_amount` RMB，
          按 `target_weights` 分配给风险池，按当日收盘价 +/- 滑点 + 佣金成交。
          若货币池余额 < dca_amount，则转出全部余额。
        - 不做再平衡：风险池买入后持有到结束。
        """
        close = self._build_close_panel(panel)
        # 处理 tz：close.index 一般来自 loader（tz-aware UTC），
        # since/until 由用户传入可能是 naive；按 close.index 的 tz 对齐
        idx_tz = close.index.tz
        if since is not None:
            ts = pd.Timestamp(since)
            if idx_tz is not None and ts.tz is None:
                ts = ts.tz_localize(idx_tz)
            elif idx_tz is None and ts.tz is not None:
                ts = ts.tz_convert(None)
            close = close.loc[close.index >= ts]
        if until is not None:
            ts = pd.Timestamp(until)
            if idx_tz is not None and ts.tz is None:
                ts = ts.tz_localize(idx_tz)
            elif idx_tz is None and ts.tz is not None:
                ts = ts.tz_convert(None)
            close = close.loc[close.index <= ts]
        if close.empty:
            raise ValueError("panel 切片后为空，检查 since/until 与数据范围")

        dates = close.index
        cash_sym = self.cash_symbol
        risk_syms = self.risk_symbols

        # 起始：全部 init_cash 折算成货币 ETF 股数（不扣手续费，"开户入金"语义）
        first_cash_price = float(close.iloc[0][cash_sym])
        if first_cash_price <= 0 or np.isnan(first_cash_price):
            raise ValueError(f"{cash_sym} 起始价格异常：{first_cash_price}")
        cash_units = init_cash / first_cash_price  # 货币 ETF 持有"股数"

        # 风险池持有股数（初始 0）
        risk_units = pd.Series(0.0, index=risk_syms)

        dca_dates = set(self._dca_trigger_dates(dates).tolist())

        # 簿记数组
        equity_arr = np.empty(len(dates))
        cash_value_arr = np.empty(len(dates))
        holdings_arr = np.zeros((len(dates), len(risk_syms)))
        trades_records: list[dict] = []

        for i, date in enumerate(dates):
            row = close.iloc[i]
            cash_price = float(row[cash_sym])

            # —— DCA 触发 ——
            if date in dca_dates:
                cash_value = cash_units * cash_price
                # 本次能转出的金额（货币池余额不足时降级）
                spend = min(self.dca_amount, max(cash_value, 0.0))
                if spend > 0:
                    weights = self.target_weights(date, row[risk_syms])
                    # 卖货币 ETF：扣手续费（少量）
                    sell_units = spend / cash_price
                    sell_fee = spend * fees
                    cash_units -= sell_units
                    # 净流入风险池的金额（卖出货币 ETF 的钱减去卖出手续费）
                    risk_budget = spend - sell_fee
                    trades_records.append({
                        "date": date,
                        "symbol": cash_sym,
                        "side": "sell",
                        "qty": sell_units,
                        "price": cash_price,
                        "notional": spend,
                        "fee": sell_fee,
                    })
                    # 买入风险 ETF：考虑滑点与买入手续费
                    for sym in risk_syms:
                        alloc = risk_budget * weights[sym]
                        if alloc <= 0:
                            continue
                        px = float(row[sym])
                        if np.isnan(px) or px <= 0:
                            # 数据缺失，跳过该 symbol（其他份额仍买）
                            continue
                        buy_px = px * (1.0 + slippage)
                        # 把 alloc 当作"打算花的钱"，扣掉手续费后实际买入金额
                        buy_fee = alloc * fees
                        buy_notional = alloc - buy_fee
                        if buy_notional <= 0:
                            continue
                        units = buy_notional / buy_px
                        risk_units[sym] += units
                        trades_records.append({
                            "date": date,
                            "symbol": sym,
                            "side": "buy",
                            "qty": units,
                            "price": buy_px,
                            "notional": alloc,
                            "fee": buy_fee,
                        })

            # —— 当日收盘簿记 ——
            cash_value = cash_units * cash_price
            risk_prices = row[risk_syms].astype(float).values
            risk_value = float((risk_units.values * risk_prices).sum())
            equity = cash_value + risk_value

            equity_arr[i] = equity
            cash_value_arr[i] = cash_value
            holdings_arr[i, :] = risk_units.values

        equity = pd.Series(equity_arr, index=dates, name="equity")
        cash_series = pd.Series(cash_value_arr, index=dates, name="cash")
        holdings = pd.DataFrame(holdings_arr, index=dates, columns=risk_syms)

        # 实时权重（占组合净值）
        weights_df = pd.DataFrame(
            {sym: holdings[sym] * close[sym] / equity for sym in risk_syms}
        )
        weights_df["__cash__"] = cash_series / equity

        trades = pd.DataFrame(trades_records)

        metrics = self._compute_metrics(equity, trades, init_cash)

        return DCAResult(
            equity=equity,
            cash=cash_series,
            holdings=holdings,
            weights=weights_df,
            trades=trades,
            metrics=metrics,
        )

    # ------------------------------------------------------------------ metrics

    @staticmethod
    def _compute_metrics(
        equity: pd.Series, trades: pd.DataFrame, init_cash: float
    ) -> dict:
        """关键绩效指标（与 backtest.metrics.portfolio_metrics 字段对齐）。"""
        if equity.empty:
            return {}

        rets = equity.pct_change().fillna(0.0)
        n = len(equity)
        # 假设日线 252 交易日年化
        ann_factor = 252.0
        total_return = float(equity.iloc[-1] / init_cash - 1.0)
        # CAGR
        years = max(n / ann_factor, 1e-9)
        cagr = float((equity.iloc[-1] / init_cash) ** (1 / years) - 1.0)
        ann_vol = float(rets.std(ddof=0) * np.sqrt(ann_factor))
        sharpe = float(rets.mean() / rets.std(ddof=0) * np.sqrt(ann_factor)) if rets.std(ddof=0) > 0 else float("nan")
        # 最大回撤
        cummax = equity.cummax()
        dd = equity / cummax - 1.0
        max_dd = float(dd.min())
        calmar = float(cagr / abs(max_dd)) if max_dd < 0 else float("nan")

        # 换手率：年化换手 = 累计买入金额 / 平均净值 / 年数
        if not trades.empty:
            buy_notional = trades.loc[trades["side"] == "buy", "notional"].sum()
            avg_equity = float(equity.mean())
            annual_turnover = float(buy_notional / avg_equity / years) if avg_equity > 0 else float("nan")
            n_trades = int(len(trades))
        else:
            annual_turnover = 0.0
            n_trades = 0

        return {
            "total_return": total_return,
            "cagr": cagr,
            "ann_vol": ann_vol,
            "sharpe": sharpe,
            "max_drawdown": max_dd,
            "calmar": calmar,
            "annual_turnover": annual_turnover,
            "n_trades": n_trades,
            # base.portfolio_metrics 兼容字段
            "win_rate": float("nan"),  # DCA 无"交易胜率"语义
        }
