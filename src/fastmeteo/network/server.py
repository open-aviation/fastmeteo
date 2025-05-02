#!/usr/bin/env python
from typing import Any, Dict

import click
import pandas as pd
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

from ..source import ArcoEra5

fmg = ArcoEra5("/tmp/era5-zarr")
app = FastAPI()


class FlightRequest(BaseModel):
    data: Dict[str, Any]


def deserialize(flight_dict: dict[str, Any]) -> pd.DataFrame:
    df = pd.DataFrame.from_dict(flight_dict)
    return df


def serialize(flight_df: pd.DataFrame) -> dict[str, Any]:
    return flight_df.to_dict(orient="list")  # type: ignore


@app.post("/submit_flight/", response_model=Dict)
async def submit_flight(flight_request: FlightRequest) -> dict[str, Any]:
    flight = deserialize(flight_request.data)
    flight_new = fmg.interpolate(flight)
    return serialize(flight_new)


@click.command()
@click.option("--local-store", required="true", help="local era5 zarr store path")
@click.option("--port", default=9800, help="listening on port")
def main(local_store: str, port: int) -> None:
    fmg.local_store = local_store
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
