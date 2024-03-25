# Fast Meteo

A fast Python package to obtain meteorological parameters for your flight trajectories.


## Checklist

Here are a few things you should know first:

- Synchronization of the data from the Google ARCO ERA5 store can be slow, as each hour of data is about 250MB.

- You should also have a good amount of computer RAM to sync the Zarr Store. I recommend having at least **32 GB of RAM**.

- Once the data is available locally, the code is super-fast, and you don't need much RAM to run it.

- To share access for your group, a good practice is to set up fastmeteo on a server and use it in Server-Client mode.


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

fmg = Grid(local_store="/tmp/era5-zarr")

# Obtain weather information.
flight_new = fmg.interpolate(flight)
```

### Server-client mode

When running the tool in a server-client mode. The following script can be used to start a FastAPI service on the server. It handles the flight date request and obtains Google ARCO data if the partition is not on the server. After that, it will perform the interpolation of weather data and return the final data to the client.

```bash
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

## Options

### Meteorological features

If you want more or different meteorological features than wind, temperature and humidity, specify the desired feature list as follows:

```python
features = [
    "u_component_of_wind",
    "v_component_of_wind",
    "convective_available_potential_energy",
]

fmg = Grid(local_store="/tmp/era5-zarr", features=features)

flight_new = fmg.interpolate(flight)
```

All available parameters can be found at: https://codes.ecmwf.int/grib/param-db/

You should use feature names in **lower case** with **underscores** for the list of features in `fastmeteo`.

### Pressure levels

By default, `fastmeteo` extracts features for the following pressure levels (hPa), out of all available levels:

```
100, 125, 150, 175, 200, 225, 250, 300, 350, 400, 450,
500, 550, 600, 650, 700, 750, 800, 850, 900, 950, 1000
```

You can also customize the desired levels (sorted), for example, as follows:

```python
levels = [500, 600, 700, 800, 900, 1000]
fmg = Grid(local_store="/tmp/era5-zarr", levels=levels)

flight_new = fmg.interpolate(flight)
```
