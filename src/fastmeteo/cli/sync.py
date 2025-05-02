#!/usr/bin/env python
import click

from ..source import ArcoEra5


@click.command()
@click.option("--local-store", required="true", help="local era5 zarr store path")
@click.option("--start", required="true", help="start datetime")
@click.option("--stop", required="true", help="stop datetime")
def main(local_store: str, start: str, stop: str) -> None:
    fmg = ArcoEra5(local_store=local_store)
    fmg.sync_local(start, stop)
