import pandas as pd
import xarray as xr

from . import aero

# fmt:off
DEFAULT_LEVELS = [
    100, 125, 150, 175, 200, 225, 250, 300, 350, 400, 450,
    500, 550, 600, 650, 700, 750, 800, 850, 900, 950, 1000
]
# fmt:on

DEFAULT_FEATURES = [
    "u_component_of_wind",
    "v_component_of_wind",
    "temperature",
    "specific_humidity",
]


class Grid:
    def __init__(
        self,
        local_store: str = None,
        features: list = DEFAULT_FEATURES,
        levels: list = DEFAULT_LEVELS,
    ) -> None:
        self.remote = None
        self.local = None
        self.local_store = local_store
        self.features = features
        self.levels = levels

    def set_local_path(self, local_store: str) -> None:
        self.local_store = local_store

    def set_remote(self) -> None:
        # remote google era5 zarr cloud storage
        self.remote = xr.open_zarr(
            "gs://gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3/",
            chunks={"time": 48},
            consolidated=True,
        )

    def select_remote_hour(self, hour: pd.DatetimeIndex) -> xr.Dataset:
        if self.remote is None:
            self.set_remote()

        selected = self.remote.sel(time=slice(hour, hour))[self.features].compute()

        # must process level selection locally
        selected = selected.sel(level=DEFAULT_LEVELS)

        return selected

    def sync_local(self, start: str or pd.DatetimeIndex, stop: str or pd.DatetimeIndex):
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

        coords = {
            "time": (("points",), times.to_numpy(dtype="datetime64[ns]")),
            "latitude": (("points",), flight.latitude.values),
            "longitude": (("points",), flight.longitude_360.values),
            "level": (
                ("points",),
                aero.pressure(flight.altitude * aero.ft) / 100,
            ),
        }

        ds = xr.Dataset(coords=coords)

        new_params = era5_cropped.interp(
            ds.coords, method="linear", assume_sorted=False
        ).to_dataframe()[self.features]

        flight_new = (
            pd.concat([flight, new_params], axis=1)
            .drop(columns="longitude_360")
            .set_index(index)
        )

        return flight_new
