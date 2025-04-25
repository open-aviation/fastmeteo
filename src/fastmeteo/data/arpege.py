import tempfile
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Annotated, Any

import httpx
import numpy as np
import pandas as pd
import xarray as xr
from impunity import impunity
from pitot.isa import pressure
from tqdm.auto import tqdm

from ..core.grid import Grid

tempdir = Path(tempfile.gettempdir())

bare_url = "https://object.data.gouv.fr/meteofrance-pnt/pnt/"


def download_with_progress(url: str) -> BytesIO:
    with httpx.stream("GET", url) as r:
        total_size = int(r.headers.get("Content-Length", 0))
        buffer = BytesIO()
        with tqdm(
            total=total_size, unit="B", unit_scale=True, desc=url.split("/")[-1]
        ) as progress_bar:
            for chunk in r.iter_bytes():
                buffer.write(chunk)
                progress_bar.update(len(chunk))
        buffer.seek(0)
        return buffer


class Arpege(Grid):
    """
    Class to handle the ARPEGE data.
    """

    def __init__(self, local_store: str) -> None:
        self.local_store = local_store
        self.model = "ARPEGE"
        self.grib = "025"
        self.package = "IP1"
        self.time_range = "000H024H"
        self.run_date = [0, 6, 12, 18]
        self.features = ["r", "t", "u", "v", "z"]

    def get_latest_run_time(self, time: np.datetime64) -> datetime:
        utc_now = pd.to_datetime(time).tz_localize("UTC")
        candidate = datetime(
            utc_now.year,
            utc_now.month,
            utc_now.day,
            utc_now.hour,
            tzinfo=timezone.utc,
        )
        run_time = datetime(
            candidate.year,
            candidate.month,
            candidate.day,
            tzinfo=timezone.utc,
        )
        for hour in self.run_date:
            if candidate.hour >= hour:
                run_time += timedelta(hours=int(hour))
                break

        return run_time

    def select_remote(self, hour: pd.DatetimeIndex) -> xr.Dataset:
        runtime = self.get_latest_run_time(hour)

        url = f"{bare_url}{runtime.isoformat()}/"
        url += f"{self.model.lower()}/{self.grib}/{self.package}/"
        filename = f"{self.model.lower()}__{self.grib}__{self.package}__"
        filename += f"{self.time_range}__{runtime.isoformat()}.grib2"
        filename = filename.replace("+00:00", "Z")
        url += filename
        url = url.replace("+00:00", "Z")

        if not (tempdir / filename).exists():
            buffer = download_with_progress(url)
            value = buffer.getvalue()
            if value.startswith(b"<?xml"):
                raise RuntimeError(
                    f"Error downloading data from {url}. "
                    "Check if the requested data is available."
                )
            # Save BytesIO to temporary file
            # cfgrib engine can't work directly with BytesIO
            (tempdir / filename).write_bytes(value)

        # Open the dataset using cfgrib engine from the temp file
        ds = xr.open_dataset(tempdir / filename, engine="cfgrib")
        ds = ds.assign(step=ds.time + ds.step).drop("time")
        ds = ds.rename(step="time")

        return ds

    @impunity
    def coords(self, flight: pd.DataFrame) -> dict[str, Any]:
        times = pd.to_datetime(flight.timestamp).dt.tz_localize(None)
        altitude: Annotated[pd.Series, "ft"] = flight.altitude

        coords = {
            "time": (("points",), times.to_numpy(dtype="datetime64[ns]")),
            "latitude": (("points",), flight.latitude.values),
            "longitude": (("points",), flight.longitude_360.values),
            "isobaricInhPa": (("points",), pressure(altitude) // 100),
        }
        return coords
