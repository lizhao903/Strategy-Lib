"""命令行入口。`slib data fetch` / `slib backtest run`。"""

from __future__ import annotations

import click

from strategy_lib.data import get_loader
from strategy_lib.utils.logging import logger


@click.group()
def main() -> None:
    """Strategy-Lib CLI."""


@main.group()
def data() -> None:
    """数据相关命令。"""


@data.command("fetch")
@click.option("--market", required=True, type=click.Choice(["crypto", "cn_stock", "cn_etf", "hk_stock", "us_stock"]))
@click.option("--symbol", required=True, help="symbol，如 BTC/USDT, 600519, AAPL")
@click.option("--tf", "timeframe", default="1d", help="时间周期：1d/1h/1m...")
@click.option("--since", default=None, help="起始日期 YYYY-MM-DD")
@click.option("--until", default=None, help="结束日期 YYYY-MM-DD")
@click.option("--refresh", is_flag=True, help="忽略缓存重新拉取")
def data_fetch(market: str, symbol: str, timeframe: str, since: str, until: str, refresh: bool) -> None:
    loader = get_loader(market, refresh=refresh)
    df = loader.load(symbol, timeframe, since, until)
    logger.info(f"fetched {len(df)} bars: {df.index.min()} ~ {df.index.max()}")
    click.echo(df.tail(10))


@main.group()
def backtest() -> None:
    """回测相关命令。"""


@backtest.command("run")
@click.argument("config_path", type=click.Path(exists=True))
def backtest_run(config_path: str) -> None:
    from strategy_lib.backtest.runner import run_config

    run_config(config_path)


@main.command("quickrun")
@click.option("--symbols", required=True,
              help="逗号分隔的标的列表，如 'BTC/USDT,ETH/USDT' 或 '510300,510500,159915'")
@click.option("--strategies", default="S3",
              help="逗号分隔的策略名（S1/S2/S2v2/S3/S4/S4v2/S5/S5v2/S6/S7/S7v2）；默认 S3")
@click.option("--market", default=None,
              type=click.Choice(["crypto", "cn_stock", "cn_etf", "hk_stock", "us_stock"]),
              help="不传则自动推断")
@click.option("--cash", "cash_proxy", default=None, help="现金代理；默认按 market 推断")
@click.option("--benchmark", default=None, help="基准标的；默认按 market 推断")
@click.option("--since", default=None, help="起始日期 YYYY-MM-DD；默认按 market 推断")
@click.option("--until", default="2024-12-31", help="结束日期 YYYY-MM-DD")
@click.option("--init-cash", default=100_000, type=float, help="初始资金")
@click.option("--no-save", is_flag=True, help="不保存 artifacts，只打印")
def quickrun_cli(symbols, strategies, market, cash_proxy, benchmark,
                 since, until, init_cash, no_save):
    """无脑跑任意标的池：自动推断 market / cash / benchmark + 标准报告。

    示例：
        slib quickrun --symbols 'BTC/USDT,ETH/USDT,SOL/USDT'
        slib quickrun --symbols '510300,510500' --strategies 'S3,S4v2'
        slib quickrun --symbols 'AAPL,MSFT,GOOG' --benchmark SPY
    """
    from strategy_lib.quickrun import quickrun

    strategies_list = [s.strip() for s in strategies.split(",") if s.strip()]
    quickrun(
        symbols=symbols,
        strategies=strategies_list,
        market=market,
        cash_proxy=cash_proxy,
        benchmark=benchmark,
        since=since,
        until=until,
        init_cash=init_cash,
        save_artifacts=not no_save,
    )


if __name__ == "__main__":
    main()
