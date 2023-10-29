# %%
import numpy as np
import pandas as pd
import xarray as xr
from . import aero


class Grid:
    def __init__(self, local_store: str = None) -> None:
        self.remote = None
        self.local = None

        self.local_store = local_store

        self.features = [
            "u_component_of_wind",
            "v_component_of_wind",
            "temperature",
            "specific_humidity",
        ]

    def set_local_path(self, local_store: str) -> None:
        self.local_store = local_store

    def set_remote(self) -> None:
        # remote google era5 zarr cloud storage
        self.remote = xr.open_zarr(
            "gs://gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3/",
            chunks={"time": 48},
            consolidated=True,
        )

    def select_remote_hour(self, hour: np.datetime64) -> xr.Dataset:
        if self.remote is None:
            self.set_remote()

        features = [
            "u_component_of_wind",
            "v_component_of_wind",
            "temperature",
            "specific_humidity",
        ]

        selected = self.remote.sel(time=slice(hour, hour), level=slice(100, 700))[
            features
        ]

        return selected

    def sync_local(self, start: np.datetime64, stop: np.datetime64):
        # open local zarr storage, create if not exist
        try:
            self.local = xr.open_zarr(self.local_store, consolidated=True)
        except KeyError:
            print(f"init local zarr from google arco era5, hour: {start.floor('1h')}")
            selected = self.select_remote_hour(start.round("1h").to_datetime64())
            selected.to_zarr(self.local_store, mode="w", consolidated=True)
            self.local = xr.open_zarr(self.local_store, consolidated=True)

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
                    self.local_store, mode="a", append_dim="time", consolidated=True
                )

        # close to ensure the write is complete
        self.local.close()

    def interpolate(self, flight: pd.DataFrame) -> pd.DataFrame:
        times = pd.to_datetime(flight.timestamp)

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
            "time": (("points",), flight.timestamp.to_numpy(dtype="datetime64[ns]")),
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

        flight_new = pd.concat([flight, new_params], axis=1).drop(
            columns="longitude_360"
        )
        return flight_new
