import os

import numpy as np
import pandas as pd
import xarray as xr

from . import aero

curr_path = os.path.dirname(os.path.realpath(__file__))
datadir = os.path.join(curr_path, "data/")


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


class Grid:
    remote: xr.Dataset
    local: xr.Dataset

    def __init__(
        self,
        local_store: None | str = None,
        model_levels: int = 37,
        features: list = DEFAULT_FEATURES,
    ) -> None:
        assert model_levels in [37, 137], "model_level must be 37 or 137"

        self.local_store = local_store
        self.features = features
        self.model_levels = model_levels

        if model_levels == 37:
            self.set_remote(arco_era5_url_level_37)
            self.levels = DEFAULT_LEVELS_37
        elif model_levels == 137:
            self.set_remote(arco_era5_url_level_137)
            self.levels = DEFAULT_LEVELS_137
            self.level_data = pd.read_csv(f"{datadir}/level_137.csv").sort_values(
                "altitude"
            )

    def set_local_path(self, local_store: str) -> None:
        self.local_store = local_store

    def set_remote(self, url) -> None:
        # remote google era5 zarr cloud storage
        self.remote = xr.open_zarr(
            url,
            chunks=None,
            # https://gcsfs.readthedocs.io/en/latest/#proxy
            storage_options=dict(token="anon", session_kwargs={"trust_env": True}),
        )

    def select_remote_hour(self, hour: pd.DatetimeIndex) -> xr.Dataset:
        selected = self.remote.sel(time=slice(hour, hour))[self.features].compute()

        # must process level selection locally
        if self.model_levels == 37:
            selected = selected.sel(level=self.levels)
        elif self.model_levels == 137:
            selected = selected.sel(hybrid=self.levels)

        return selected

    def sync_local(
        self, start: str | pd.DatetimeIndex, stop: str | pd.DatetimeIndex
    ) -> None:
        # sync local zarr storage, create if not exist

        start = pd.to_datetime(start)
        stop = pd.to_datetime(stop)

        try:
            self.local = xr.open_zarr(self.local_store, consolidated=True)
        except KeyError:
            print(f"init local zarr from google arco era5, hour: {start.floor('1h')}")
            selected = self.select_remote_hour(start.round("1h").to_datetime64())
            selected.to_zarr(self.local_store, mode="w", consolidated=True)
            self.local = xr.open_zarr(self.local_store, consolidated=True)

        # ensure existing and requested features are matching
        missing_features = [
            feature for feature in self.features if feature not in self.local.data_vars
        ]
        if missing_features:
            raise RuntimeError(
                "Requested features not in local zarr, create a new folder for this."
            )

        # ensure the data is available locally
        for hour_dt in pd.date_range(start.floor("1h"), stop.ceil("1h"), freq="1h"):
            hour = hour_dt.to_datetime64()
            if self.local.sel(time=self.local.time.isin(hour)).time.size > 0:
                continue

            print(f"syncing zarr from google arco-era5, hour: {hour_dt}")
            selected = self.select_remote_hour(hour)

            if selected.time.size == 0:
                RuntimeWarning(
                    f"data from {start} to {stop} is not available from google arco-era5."
                )
            else:
                selected.to_zarr(
                    self.local_store,
                    mode="a",
                    append_dim="time",
                    consolidated=True,
                )

        # close to ensure the write is complete
        self.local.close()

    def interpolate(self, flight: pd.DataFrame) -> pd.DataFrame:
        times = pd.to_datetime(flight.timestamp).dt.tz_localize(None)
        index = flight.index

        flight = flight.reset_index(drop=True).assign(
            longitude_360=lambda d: d.longitude % 360
        )
        start = times.min()
        stop = times.max()

        self.sync_local(start, stop)
        self.local = xr.open_zarr(self.local_store, consolidated=True)

        era5_cropped = self.local.sel(
            time=self.local.time.isin(
                pd.date_range(start.floor("1h"), stop.ceil("1h"), freq="1h").to_numpy(
                    dtype="datetime64"
                )
            ),
            latitude=slice(flight.latitude.max() + 1, flight.latitude.min() - 1),
            longitude=slice(
                flight.longitude_360.min() - 1, flight.longitude_360.max() + 1
            ),
        )

        if era5_cropped.time.size == 0:
            RuntimeWarning(f"data from {start} to {stop} is not available.")
            return flight

        if self.model_levels == 37:
            coords = {
                "time": (("points",), times.to_numpy(dtype="datetime64[ns]")),
                "latitude": (("points",), flight.latitude.values),
                "longitude": (("points",), flight.longitude_360.values),
                "level": (
                    ("points",),
                    aero.pressure(flight.altitude * aero.ft) / 100,
                ),
            }
        elif self.model_levels == 137:
            coords = {
                "time": (("points",), times.to_numpy(dtype="datetime64[ns]")),
                "latitude": (("points",), flight.latitude.values),
                "longitude": (("points",), flight.longitude_360.values),
                "hybrid": (
                    ("points",),
                    np.interp(
                        flight.altitude, self.level_data.altitude, self.level_data.level
                    ),
                ),
            }

        ds = xr.Dataset(coords=coords)

        new_params = era5_cropped.interp(
            ds.coords,
            method="linear",
            assume_sorted=False,
            kwargs={"fill_value": None},
        ).to_dataframe()[self.features]

        flight_new = (
            pd.concat([flight, new_params], axis=1)
            .drop(columns="longitude_360")
            .set_index(index)
        )

        return flight_new
