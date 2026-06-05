"""Tests for Grid base class — AXM-490 regression tests.

Bug 1: sync_local() returns a stale zarr handle (opened before appends).
Bug 2: RuntimeWarning(...) instantiated but never raised/warned.
"""

from __future__ import annotations

import tempfile
import warnings
from typing import Any, ClassVar
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from fastmeteo.core.grid import Grid


class StubGrid(Grid):
    """Minimal concrete Grid for testing sync_local / interpolate logic."""

    features: ClassVar[list[str]] = ["temperature"]

    def __init__(self, local_store: str) -> None:
        self.local_store = local_store

    def select_remote(self, hour: pd.DatetimeIndex) -> xr.Dataset:
        """Return a 1-hour dataset with a 'temperature' variable."""
        time = pd.DatetimeIndex([hour])
        ds = xr.Dataset(
            {
                "temperature": (
                    ["time", "latitude", "longitude"],
                    np.full((1, 3, 3), 288.0),
                )
            },
            coords={
                "time": time,
                "latitude": [39.0, 41.0, 43.0],
                "longitude": [3.0, 5.0, 7.0],
            },
        )
        # Explicit encoding so zarr append handles sub-day offsets correctly
        ds.time.encoding["units"] = "hours since 2024-01-01"
        ds.time.encoding["dtype"] = "int64"
        return ds

    def coords(self, flight: pd.DataFrame) -> dict[str, Any]:
        return {
            "time": ("points", pd.to_datetime(flight.timestamp).values),
            "latitude": ("points", flight.latitude.values),
            "longitude": ("points", (flight.longitude % 360).values),
        }


def _make_flight(
    start: str = "2024-06-01T01:30:00",
    stop: str = "2024-06-01T02:30:00",
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": [start, stop],
            "latitude": [40.0, 42.0],
            "longitude": [4.0, 6.0],
            "altitude": [30_000.0, 32_000.0],
        }
    )


# ---------- Bug 1: stale zarr handle -----------------------------------


class TestSyncLocalFreshHandle:
    """sync_local must return a dataset that includes newly appended hours."""

    def test_sync_local_returns_fresh_handle(self) -> None:
        """Create zarr with 1 hour, then sync_local for a wider range.

        The returned dataset must contain ALL hours — including those
        appended during the sync, not just the initial one.
        """
        with tempfile.TemporaryDirectory() as tmp:
            grid = StubGrid(local_store=tmp + "/test.zarr")

            # Seed the cache with hour 01:00
            seed_hour = pd.Timestamp("2024-06-01 01:00")
            init_ds = grid.select_remote(seed_hour.to_datetime64())
            init_ds.to_zarr(grid.local_store, mode="w", consolidated=True)

            # Ask sync_local for 01:00 → 03:00  (should append 02:00 and 03:00)
            result = grid.sync_local(
                start="2024-06-01 01:00",
                stop="2024-06-01 03:00",
            )

            result_times = pd.DatetimeIndex(result.time.values)
            assert pd.Timestamp("2024-06-01 02:00") in result_times, (
                "sync_local returned stale handle — missing appended hour 02:00"
            )
            assert pd.Timestamp("2024-06-01 03:00") in result_times, (
                "sync_local returned stale handle — missing appended hour 03:00"
            )
            result.close()


# ---------- Bug 2: silent RuntimeWarning --------------------------------


class TestRuntimeWarningRaised:
    """RuntimeWarning must actually be emitted, not silently discarded."""

    def test_sync_local_warns_on_missing_remote_data(self) -> None:
        """When select_remote returns an empty dataset, a warning must fire."""
        with tempfile.TemporaryDirectory() as tmp:
            grid = StubGrid(local_store=tmp + "/test.zarr")

            # Seed cache with hour 01:00
            seed_hour = pd.Timestamp("2024-06-01 01:00")
            init_ds = grid.select_remote(seed_hour.to_datetime64())
            init_ds.to_zarr(grid.local_store, mode="w", consolidated=True)

            # Make select_remote return empty for the missing hour
            def _empty_remote(hour: Any) -> xr.Dataset:
                dims = ["time", "latitude", "longitude"]
                return xr.Dataset(
                    {"temperature": (dims, np.empty((0, 3, 3)))},
                    coords={
                        "time": pd.DatetimeIndex(
                            [], dtype="datetime64[ns]"
                        ),
                        "latitude": [39.0, 41.0, 43.0],
                        "longitude": [3.0, 5.0, 7.0],
                    },
                )

            with patch.object(grid, "select_remote", side_effect=_empty_remote):
                with warnings.catch_warnings(record=True) as w:
                    warnings.simplefilter("always")
                    grid.sync_local(
                        start="2024-06-01 02:00",
                        stop="2024-06-01 02:00",
                    )

            runtime_warnings = [
                x for x in w
                if issubclass(x.category, RuntimeWarning)
            ]
            assert len(runtime_warnings) >= 1, (
                "RuntimeWarning not emitted (missing warnings.warn)"
            )

    def test_interpolate_raises_on_empty_cropped_data(self) -> None:
        """When no local data covers the request, fail before returning input."""
        with tempfile.TemporaryDirectory() as tmp:
            grid = StubGrid(local_store=tmp + "/test.zarr")

            # Seed cache with hour 01:00 only
            seed_hour = pd.Timestamp("2024-06-01 01:00")
            init_ds = grid.select_remote(seed_hour.to_datetime64())
            init_ds.to_zarr(grid.local_store, mode="w", consolidated=True)

            # Request flight at 10:00 — completely outside cache
            flight = _make_flight(
                start="2024-06-01 10:30:00",
                stop="2024-06-01 11:30:00",
            )

            # Make select_remote return empty so sync_local can't fill the gap
            def _empty_remote(hour: Any) -> xr.Dataset:
                dims = ["time", "latitude", "longitude"]
                return xr.Dataset(
                    {"temperature": (dims, np.empty((0, 3, 3)))},
                    coords={
                        "time": pd.DatetimeIndex(
                            [], dtype="datetime64[ns]"
                        ),
                        "latitude": [39.0, 41.0, 43.0],
                        "longitude": [3.0, 5.0, 7.0],
                    },
                )

            with patch.object(grid, "select_remote", side_effect=_empty_remote):
                with warnings.catch_warnings(record=True) as w:
                    warnings.simplefilter("always")
                    with pytest.raises(RuntimeError, match="is not available"):
                        grid.interpolate(flight)

            runtime_warnings = [
                x for x in w
                if issubclass(x.category, RuntimeWarning)
            ]
            assert len(runtime_warnings) >= 1, (
                "RuntimeWarning not emitted (missing warnings.warn)"
            )
