import warnings
from abc import abstractmethod
from typing import Any, cast

import numpy as np
import pandas as pd
import xarray as xr
from numpy.typing import NDArray


def to_grid_frame(lon: Any, grid_lon: Any) -> NDArray[np.float64]:
    """Express longitudes in the dataset's own frame ``[lon0, lon0 + 360)``.

    Datasets use different conventions (ARCO ERA5: 0..359.75; ARPEGE 0.1 deg:
    -32..42), so ``lon % 360`` is only correct for grids starting at 0.
    """
    lon0 = float(np.min(np.asarray(grid_lon)))
    return lon0 + np.mod(np.asarray(lon, dtype=float) - lon0, 360.0)


def close_longitude(cropped: xr.Dataset, full: xr.Dataset) -> xr.Dataset:
    """Append the first longitude, shifted by +360 deg, to a crop of a global grid.

    Without it, points between the last grid longitude and 360 deg (e.g.
    359.75..360 on a 0.25 deg grid) are extrapolated instead of interpolated
    towards 0 deg. Only needed when the crop reaches the last column of a global
    grid; regional grids and other crops are returned unchanged. Works on the
    crop only, so a lazily opened dataset is never loaded as a whole.
    """
    lon = np.asarray(full.longitude.values, dtype=float)
    if lon.size < 2 or cropped.longitude.size == 0:
        return cropped
    step = float(np.min(np.abs(np.diff(np.sort(lon)))))
    if abs(float(lon.max() - lon.min()) + step - 360.0) > 1e-6:
        return cropped
    if float(cropped.longitude.max()) < float(lon.max()):
        return cropped
    first = full.isel(longitude=[int(np.argmin(lon))]).sel(
        time=cropped.time, latitude=cropped.latitude
    )
    first = first.assign_coords(longitude=first.longitude + 360.0)
    return xr.concat([cropped, first], dim="longitude")


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
                warnings.warn(
                    f"data from {start} to {stop} is not available remotely",
                    RuntimeWarning,
                    stacklevel=2,
                )
            else:
                selected.to_zarr(
                    self.local_store, mode="a", append_dim="time", consolidated=True
                )

        # close stale handle and re-open to include appended data
        local_dataset.close()
        return cast(xr.Dataset, xr.open_zarr(self.local_store, consolidated=True))

    def interpolate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Interpolate data on a grid."""
        times = pd.to_datetime(df.timestamp).dt.tz_localize(None)
        index = df.index

        df = (
            df.reset_index(drop=True)
            # remove features if exist
            .drop(self.features, axis=1, errors="ignore")
            # prevent pyarrow error
            .assign(latitude=lambda x: x.latitude.astype(float))
            .assign(longitude=lambda x: x.longitude.astype(float))
            .assign(altitude=lambda x: x.altitude.astype(float))
        )
        start = times.min()
        stop = times.max()

        local_dataset = self.sync_local(start, stop)
        df = df.assign(
            longitude_360=to_grid_frame(df.longitude, local_dataset.longitude)
        )
        interval = pd.date_range(start.floor("1h"), stop.ceil("1h"), freq="1h")

        data_cropped = local_dataset.sel(
            time=local_dataset.time.isin(interval.to_numpy(dtype="datetime64")),
            latitude=slice(df.latitude.max() + 1, df.latitude.min() - 1),
            longitude=slice(df.longitude_360.min() - 1, df.longitude_360.max() + 1),
        )
        data_cropped = close_longitude(data_cropped, local_dataset)

        if data_cropped.time.size == 0:
            msg = f"data from {start} to {stop} is not available."
            warnings.warn(
                msg,
                RuntimeWarning,
                stacklevel=2,
            )
            raise RuntimeError(msg)

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
