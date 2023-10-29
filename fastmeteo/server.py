#!/usr/bin/env python
import click
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any, Dict
import pandas as pd
from . import Grid

mmg = Grid()
app = FastAPI()


class FlightRequest(BaseModel):
    data: Dict[str, Any]


def deserialize(flight_dict: Dict) -> pd.DataFrame:
    df = pd.DataFrame.from_dict(flight_dict)
    return df


def serialize(flight_df: pd.DataFrame) -> dict:
    return flight_df.to_dict()


@app.post("/submit_flight/", response_model=Dict)
async def submit_flight(flight_request: FlightRequest):
    flight = deserialize(flight_request.data)
    flight_new = mmg.interpolate(flight)
    return serialize(flight_new)


@click.command()
@click.option("--local-store", required="true", help="local era5 zarr store path")
@click.option("--port", default=9800, help="listening on port")
def main(local_store, port):
    mmg.set_local_path(local_store)
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
