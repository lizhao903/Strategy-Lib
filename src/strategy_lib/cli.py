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


if __name__ == "__main__":
    main()
