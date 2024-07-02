#!/usr/bin/env python
import click

from . import Grid


@click.command()
@click.option("--local-store", required="true", help="local era5 zarr store path")
@click.option("--start", required="true", help="start datetime")
@click.option("--stop", required="true", help="stop datetime")
def main(local_store, start, stop):
    fmg = Grid(local_store=local_store)
    fmg.sync_local(start, stop)


if __name__ == "__main__":
    main()
