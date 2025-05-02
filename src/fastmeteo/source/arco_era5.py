import os
from typing import Annotated, Any, Literal, TypedDict

import numpy as np
import pandas as pd
import xarray as xr
from impunity import impunity
from pitot.isa import pressure

from ..core.grid import Grid

curr_path = os.path.dirname(os.path.realpath(__file__))

arco_era5_url_level_37 = (
    "gs://gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3/"
)
arco_era5_url_level_137 = (
    "gs://gcp-public-data-arco-era5/ar/model-level-1h-0p25deg.zarr-v1/"
)

# fmt:off
DEFAULT_LEVELS_37 = [
    100, 125, 150, 175, 200, 225, 250, 300, 350, 400, 450,
    500, 550, 600, 650, 700, 750, 800, 850, 900, 950, 1000
]

DEFAULT_LEVELS_137 = [
    67,  68,  69,  70,  71,  72,  73,  74,  75,  76,  77,  78,  79,  80,
    81,  82,  83,  84,  85,  86,  88,  89,  90,  91,  92,  93,  94,  95,
    96,  97,  98,  99,  100, 101, 103, 104, 105, 107, 108, 110, 112, 114,
    116, 119, 122, 128, 132, 137
]
# fmt:on

DEFAULT_FEATURES = [
    "u_component_of_wind",
    "v_component_of_wind",
    "temperature",
    "specific_humidity",
]


class ArcoEra5(Grid):
    """
    ARCO ERA5 data is made available by the European Centre for Medium-Range
    Weather Forecasts (ECMWF) and is accessible via Google Cloud Storage. The
    data is stored in Zarr format, which is a cloud-optimized format for storing
    large datasets.

    The data is available at a resolution of 0.25 degrees and is updated every
    hour. The data is available for the entire globe and is available for the
    years 1979 to present. The data is available in a variety of formats,
    including NetCDF, GRIB, and Zarr. The data is available for a variety of
    variables, including temperature, humidity, wind speed, and wind direction.

    """

    def __init__(
        self,
        local_store: str,
        model_levels: Literal[37, 137] = 37,
        features: None | list[str] = None,
    ) -> None:
        assert model_levels in [37, 137], "model_level must be 37 or 137"

        self.local_store = local_store
        self.features = features if features else DEFAULT_FEATURES
        self.model_levels = model_levels

        if model_levels == 37:
            self.set_remote(arco_era5_url_level_37)
            self.levels = DEFAULT_LEVELS_37
        else:
            self.set_remote(arco_era5_url_level_137)
            self.levels = DEFAULT_LEVELS_137
            level_137_csv = pd.read_csv(f"{curr_path}/level_137.csv")
            self.level_data = level_137_csv.sort_values("altitude")

    def set_remote(self, url: str) -> None:
        # Remote Google ERA5 Zarr cloud storage
        self.remote_dataset = xr.open_zarr(
            url,
            chunks=None,
            storage_options=dict(
                token="anon",
                # https://gcsfs.readthedocs.io/en/latest/#proxy
                session_kwargs={"trust_env": True},
            ),
        )

    def select_remote(self, hour: pd.DatetimeIndex) -> xr.Dataset:
        selected = self.remote_dataset.sel(time=slice(hour, hour))
        selected = selected[self.features].compute()

        # must process level selection locally
        if self.model_levels == 37:
            selected = selected.sel(level=self.levels)
        elif self.model_levels == 137:
            selected = selected.sel(hybrid=self.levels)

        return selected

    # @impunity
    def coords(self, df: pd.DataFrame) -> dict[str, Any]:
        times = pd.to_datetime(df.timestamp).dt.tz_localize(None)

        if self.model_levels == 37:
            altitude: Annotated[Any, "ft"] = df.altitude
            # hPa: Annotated[Any, "hPa"] = pressure(altitude)
            hPa: Annotated[Any, "hPa"] = pressure(altitude * 0.3048) / 100
            _coords = {
                "time": (("points",), times.to_numpy(dtype="datetime64[ns]")),
                "latitude": (("points",), df.latitude.values),
                "longitude": (("points",), df.longitude_360.values),
                "level": (("points",), hPa),
            }
        elif self.model_levels == 137:
            _coords = {
                "time": (("points",), times.to_numpy(dtype="datetime64[ns]")),
                "latitude": (("points",), df.latitude.values),
                "longitude": (("points",), df.longitude_360.values),
                "hybrid": (
                    ("points",),
                    np.interp(
                        df.altitude,
                        self.level_data.altitude,
                        self.level_data.level,
                    ),
                ),
            }
        else:
            raise ValueError("model_levels must be 37 or 137")

        return _coords
