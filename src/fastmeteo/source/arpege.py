import tempfile
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Annotated, Any, Literal

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

# fmt:off
DEFAULT_LEVELS_37 = [
    100, 125, 150, 175, 200, 225, 250, 300, 350, 400, 450,
    500, 550, 600, 650, 700, 750, 800, 850, 900, 950, 1000,
]
DEFAULT_IP1_FEATURES = ['u', 'v', 't', 'r']
# fmt:on


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
    ARPEGE is a global numerical weather prediction model developed by
    Météo-France.  It is used for medium-range weather forecasting and provides
    data on various atmospheric parameters, including temperature, humidity,
    wind speed, and direction. The model is run four times a day and provides
    forecasts up to 10 days ahead. The data is available at a resolution of 0.1
    degree (over 72N 20N 32W 42E, i.e. roughly Europe) and 0.25 degrees.

    The data is made available on the data.gouv.fr platform, which is a French
    government initiative to provide open data to the public, without
    authentication.

    The features depend on the package:

    **Surface parameters**:

    - SP1: P(mer), U(10m), V(10m), DD(10m), FF(10m), FF_RAF(10m), U_RAF(10m),
        V_RAF (10m), T(2m), HU (2m), NEBUL, PRECIP, NEIGE, FLSOLAIRE_D
    - SP2: ALTITUDE, P(sol) , T(sol), COLONNE_VAPO, NEBBAS, NEBHAU, NEBMOY,
        CAPE_INS, H_COULIM, FLEVAP, FLLAT, FLSEN, FLTHERM_D, FLSOLAIRE, FLTHERM,
        USTR, VSTR, TMIN(2m), TMAX(2m), TD(2m), Q(2m)

    **Isobaric parameters**:

    - IP1: T, HU, U, V, Z on 34 levels (1 to 1000 hPa)
    - IP2: TD, Q, DD, FF, VV on 34 levels (1 to 1000 hPa)
    - IP3: CLD_WATER , CIWC, CLD_FRACT, TKE on 24 levels (100 to 1000 hPa)
    - IP4: U, V, Z; TP, TA, TB, THETAPW (various levels)

    **Height parameters**::

    - HP1: T, HU, U, V, DD, FF, P on 24 levels (20m à 3000 m)
    - HP2: TD, Q, Z, CLD_FRACT, TKE, CLD_WATER, CIWC on 24 levels (20m à 3000 m)


    """

    def __init__(
        self,
        local_store: str,
        levels: None | list[int] = None,
        features: None | list[str] = None,
        resolution: Literal["025", "01"] = "025",
        package: Literal[
            "SP1", "SP2", "IP1", "IP2", "IP3", "IP4", "HP1", "HP2"
        ] = "IP1",
        time_range: Literal[
            "000H024H",  # on the 0.25 degree grid
            "025H048H",  # on the 0.25 degree grid
            "049H072H",  # on the 0.25 degree grid
            "073H102H",  # on the 0.25 degree grid
            "000H012H",  # on the 0.1 degree grid
            "013H024H",  # on the 0.1 degree grid
            "025H036H",  # on the 0.1 degree grid
            "037H048H",  # on the 0.1 degree grid
            "049H060H",  # on the 0.1 degree grid
            "061H072H",  # on the 0.1 degree grid
            "073H084H",  # on the 0.1 degree grid
            "085H096H",  # on the 0.1 degree grid
            "097H102H",  # on the 0.1 degree grid
        ] = "000H024H",
    ) -> None:
        self.local_store = local_store
        self.model = "ARPEGE"
        self.resolution = resolution
        self.package = package
        self.time_range = time_range
        self.run_date = [0, 6, 12, 18]
        self.features = features or DEFAULT_IP1_FEATURES
        self.levels = levels or DEFAULT_LEVELS_37

    def get_latest_run_time(self, time: np.datetime64) -> datetime:
        # TODO

        # The challenge here is to ensure we select a unique and consistent
        # timestamp for each data point. Multiple files may contain forecasts
        # for the same timestamp (from different model runs or forecast ranges),
        # especially when considering different grids and time ranges.
        #
        # For the moment, we will consider that we stick to the 0.25 degree grid
        # with only one file per day (time range 000H024H), and get only one
        # file per day.

        now = pd.to_datetime(time).tz_localize("UTC")
        run_time = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        return run_time

    def select_remote(self, hour: pd.DatetimeIndex) -> xr.Dataset:
        runtime = self.get_latest_run_time(hour)

        url = f"{bare_url}{runtime.isoformat()}/"
        url += f"{self.model.lower()}/{self.resolution}/{self.package}/"
        filename = f"{self.model.lower()}__{self.resolution}__{self.package}__"
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

        return ds.sel(isobaricInhPa=self.levels)[self.features].compute()

    # @impunity
    def coords(self, flight: pd.DataFrame) -> dict[str, Any]:
        times = pd.to_datetime(flight.timestamp).dt.tz_localize(None)
        altitude: Annotated[pd.Series, "ft"] = flight.altitude
        # hPa: Annotated[Any, "hPa"] = pressure(altitude)
        hPa: Annotated[Any, "hPa"] = pressure(altitude * 0.3048) / 100

        coords = {
            "time": (("points",), times.to_numpy(dtype="datetime64[ns]")),
            "latitude": (("points",), flight.latitude.values),
            "longitude": (("points",), flight.longitude_360.values),
            "isobaricInhPa": (("points",), hPa),
        }
        return coords
