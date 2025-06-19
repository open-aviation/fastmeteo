#!/usr/bin/env python
from typing import Literal

import click

from ..source import ArcoEra5


@click.command()
@click.option("--local-store", required="true", help="local era5 zarr store path")
@click.option("--model-levels", default=37, help="levels 37 or 137")
@click.option("--start", required="true", help="start datetime")
@click.option("--stop", required="true", help="stop datetime")
def main(
    local_store: str,
    start: str,
    stop: str,
    model_levels: Literal[37, 137],
) -> None:
    fmg = ArcoEra5(local_store=local_store, model_levels=model_levels)
    fmg.sync_local(start, stop)
