# Fast Meteo

A super-fast Python package to obtain meteorological parameters for your flight trajectories.

```
import pandas as pd
from fastmeteo import Grid

# define the location for local store
mmg = Grid(local_store="/tmp/era5-zarr")

flight = pd.DataFrame(
    {
        "timestamp": ["2021-10-12T01:10:00", "2021-10-12T01:20:00"],
        "latitude": [40.3, 42.5],
        "longitude": [4.2, 6.6],
        "altitude": [25_000, 30_000],
    }
)

# obtain weather information
flight_new = mmg.interpolate(flight)
```

When running the tool in a server-client mode. The following script can be used to start a FastAPI service on the server, which handles the flight date request, obtaining Google ARCO data if the partition is not on the server, perform the interpolation of weather data, and return the final data to the client.

```
fastmeteo-serve --local-store /tmp/era5-zarr
```

At the client side, the following code can be used to submit and get the process flight with meteorology data.

```
from fastmeteo import Client

client = Client()

# send the flight and receive the new DataFrame
flight_new = client.submit_flight(flight)
```
