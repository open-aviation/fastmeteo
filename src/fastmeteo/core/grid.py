from abc import abstractmethod
from typing import Any

import pandas as pd
import xarray as xr


class Grid:
    """
    Base class for all grid data sources.

    This class provides a common interface for all grid data sources, including
    methods for selecting remote data, synchronizing local data, and
    interpolating data to match flight data. The class is designed to be
    subclassed by specific grid data sources, such as Arpege or Arco-Era5.

    """

    # Data collected remotely
    remote_dataset: xr.Dataset
    # Local storage path for a copy of the data
    local_store: str
    # Features we want to keep in the dataset
    features: list[str]

    @abstractmethod
    def select_remote(self, hour: pd.DatetimeIndex) -> xr.Dataset: ...

    @abstractmethod
    def coords(self, flight: pd.DataFrame) -> dict[str, Any]: ...

    def get_local(self, start: str | pd.DatetimeIndex) -> xr.Dataset:
        """Get the local dataset, if it exists.
        If not, create it from the remote source."""
        start = pd.to_datetime(start)
        try:
            local_dataset = xr.open_zarr(self.local_store, consolidated=True)
        except KeyError:
            print(f"init local zarr from remote, hour: {start.floor('1h')}")
            selected = self.select_remote(start.floor("1h").to_datetime64())
            selected.to_zarr(self.local_store, mode="w", consolidated=True)
            local_dataset = xr.open_zarr(self.local_store, consolidated=True)

        return local_dataset  # type: ignore

    def sync_local(
        self,
        start: str | pd.DatetimeIndex,
        stop: str | pd.DatetimeIndex,
    ) -> xr.Dataset:
        """Ensure you get the data from the remote source and save it locally."""
        start = pd.to_datetime(start)
        stop = pd.to_datetime(stop)

        local_dataset = self.get_local(start)

        # ensure existing and requested features are matching
        missing_features = [
            feature
            for feature in self.features
            if feature not in local_dataset.data_vars
        ]
        if missing_features:
            raise RuntimeError(
                "Requested features not in local zarr, create a new folder for this."
            )

        # ensure the data is available locally
        for hour_dt in pd.date_range(start.floor("1h"), stop.ceil("1h"), freq="1h"):
            hour = hour_dt.to_datetime64()
            if local_dataset.sel(time=local_dataset.time.isin(hour)).time.size > 0:
                continue

            print(f"syncing from remote, hour: {hour_dt}")
            selected = self.select_remote(hour)

            if selected.time.size == 0:
                RuntimeWarning(f"data from {start} to {stop} is not available remotely")
            else:
                selected.to_zarr(
                    self.local_store, mode="a", append_dim="time", consolidated=True
                )

        # close to ensure the write is complete
        local_dataset.close()
        return local_dataset

    def interpolate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Interpolate data on a grid."""
        times = pd.to_datetime(df.timestamp).dt.tz_localize(None)
        index = df.index

        df = df.reset_index(drop=True).assign(longitude_360=lambda d: d.longitude % 360)
        start = times.min()
        stop = times.max()

        local_dataset = self.sync_local(start, stop)
        interval = pd.date_range(start.floor("1h"), stop.ceil("1h"), freq="1h")

        data_cropped = local_dataset.sel(
            time=local_dataset.time.isin(interval.to_numpy(dtype="datetime64")),
            latitude=slice(df.latitude.max() + 1, df.latitude.min() - 1),
            longitude=slice(df.longitude_360.min() - 1, df.longitude_360.max() + 1),
        )

        if data_cropped.time.size == 0:
            RuntimeWarning(f"data from {start} to {stop} is not available.")
            return df

        coords = self.coords(df)
        ds = xr.Dataset(coords=coords)

        new_params = data_cropped.interp(
            ds.coords,
            method="linear",
            assume_sorted=False,
            kwargs={"fill_value": None},
        ).to_dataframe()[self.features]

        flight_new = (
            pd.concat([df, new_params], axis=1)
            .drop(columns="longitude_360")
            .set_index(index)
        )

        return flight_new
