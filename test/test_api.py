import pandas as pd
from fastmeteo import Grid


flight = pd.DataFrame(
    {
        "timestamp": ["2021-10-12T01:10:00", "2021-10-12T01:20:00"],
        "icao24": ["abc123", "abc123"],
        "latitude": [40.3, 42.5],
        "longitude": [4.2, 6.6],
        "altitude": [25_000, 30_000],
    }
)

# define the location for local store
fmg = Grid(local_store="/tmp/era5-zarr")

# obtain weather information
flight_new = fmg.interpolate(flight)

print(flight)
print(flight_new)
