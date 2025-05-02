import pandas as pd

from fastmeteo.source import ArcoEra5, Arpege

arco_fmg = ArcoEra5(local_store="/tmp/era5-zarr", model_levels=37)
arpege_fmg = Arpege(local_store="/tmp/arpege-zarr")


def test_interpolate() -> None:
    flight = pd.DataFrame(
        {
            "timestamp": ["2024-10-12T01:10:00", "2024-10-12T01:20:00"],
            "icao24": ["abc123", "abc123"],
            "latitude": [40.3, 42.5],
            "longitude": [4.2, 6.6],
            "altitude": [25_000, 30_000],
        }
    )

    flight_new = arco_fmg.interpolate(flight)
    assert "u_component_of_wind" in flight_new.columns


def test_arpege() -> None:
    now = pd.Timestamp("now", tz="UTC")
    flight = pd.DataFrame(
        {
            "timestamp": [now, now],
            "icao24": ["abc123", "abc123"],
            "latitude": [40.3, 42.5],
            "longitude": [4.2, 6.6],
            "altitude": [25_000, 30_000],
        }
    )

    flight_new = arpege_fmg.interpolate(flight)
    assert "u" in flight_new.columns
