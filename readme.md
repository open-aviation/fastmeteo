# Fast Meteo

A super-fast Python package to obtain meteorological parameters for your flight trajectories.

## Install

### stable version

```
pip install fastmeteo

```

### development version

```
pip install git+https://github.com/junzis/fastmeteo
```

or, if you prefer `poetry`:

```
git clone https://github.com/junzis/fastmeteo
cd fastmeteo
poetry install
```

## Usage

### Local mode

You can get the weather information for a given flight or position with the following code. Basic information on time, latitude, longitude, and altitude is needed.

```python

import pandas as pd
from fastmeteo import Grid

flight = pd.DataFrame(
    {
        "timestamp": ["2021-10-12T01:10:00", "2021-10-12T01:20:00"],
        "latitude": [40.3, 42.5],
        "longitude": [4.2, 6.6],
        "altitude": [25_000, 30_000],
    }
)

# define the location for local store
fmg = Grid(local_store="/tmp/era5-zarr")

# obtain weather information
flight_new = fmg.interpolate(flight)

```

### Server-client mode

When running the tool in a server-client mode. The following script can be used to start a FastAPI service on the server. It handles the flight date request and obtains Google ARCO data if the partition is not on the server. After that, it will perform the interpolation of weather data and return the final data to the client.

```
fastmeteo-serve --local-store /tmp/era5-zarr
```

At the client side, the following code can be used to submit and get the process flight with meteorology data.

```python
import pandas as pd
from fastmeteo import Client

flight = pd.DataFrame(
    {
        "timestamp": ["2021-10-12T01:10:00", "2021-10-12T01:20:00"],
        "latitude": [40.3, 42.5],
        "longitude": [4.2, 6.6],
        "altitude": [25_000, 30_000],
    }
)

# define the client object
client = Client()

# send the flight and receive the new DataFrame
flight_new = client.submit_flight(flight)
```
