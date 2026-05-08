"""绩效指标提取：从 vectorbt Portfolio 抽取关键指标到 dict。"""

from __future__ import annotations

import numpy as np


def portfolio_metrics(pf) -> dict:
    """vectorbt Portfolio -> 关键指标 dict。"""
    try:
        total_return = float(pf.total_return().mean())
        sharpe = float(pf.sharpe_ratio().mean())
        max_dd = float(pf.max_drawdown().mean())
        win_rate = float(pf.trades.win_rate().mean()) if pf.trades.count().sum() else np.nan
        n_trades = int(pf.trades.count().sum())
    except Exception:  # noqa: BLE001
        # 单 asset 时的标量
        total_return = float(pf.total_return())
        sharpe = float(pf.sharpe_ratio())
        max_dd = float(pf.max_drawdown())
        win_rate = float(pf.trades.win_rate()) if pf.trades.count() else np.nan
        n_trades = int(pf.trades.count())

    return {
        "total_return": total_return,
        "sharpe": sharpe,
        "max_drawdown": max_dd,
        "win_rate": win_rate,
        "n_trades": n_trades,
        "calmar": total_return / abs(max_dd) if max_dd else np.nan,
    }
