# Fast Meteo

A super-fast Python package to obtain meteorological parameters for your flight trajectories.

## Data

`fastmeteo` make the interpolation of meteorological parameters for your flight trajectories super fast and easy. Currently, it supports the following data sources:

- [ARCO ERA5](https://cloud.google.com/storage/docs/public-datasets/era5) reanalysis data from ECMWF and Google (beware this data has delay of months)
- [ARPEGE](https://www.umr-cnrm.fr/spip.php?article121&lang=en) weather forecast data from Météo-France.



## Checklist

Here are a few things you should know first:

- Synchronization of the data from the Google ARCO ERA5 store can be a little slow.

- Once the data is available locally, the code is blazing fast.

- To share access for your group, a good practice is to set up fastmeteo on a server and use it in Server-Client mode.

- You can pre-sync the data using `fastmeteo-sync` command

## Install

### stable version

```
pip install fastmeteo
```

### development version

```
pip install git+https://github.com/open-aviation/fastmeteo
```

## Usage

### ARCO ERA5 reanalysis data

You can get the weather information for a given flight or position with the following code. Basic information on time, latitude, longitude, and altitude is needed.

```python

import pandas as pd

from fastmeteo.source import ArcoEra5

flight = pd.DataFrame(
    {
        "timestamp": ["2021-10-12T01:10:00", "2021-10-12T01:20:00"],
        "latitude": [40.3, 42.5],
        "longitude": [4.2, 6.6],
        "altitude": [25_000, 30_000],
    }
)

# Obtain ERA5 reanalysis information.
arco_grid = ArcoEra5(local_store="/tmp/era5-zarr")
flight_new = arco_grid.interpolate(flight)
```

### ARPEGE weather forecast data

```python
import pandas as pd

from fastmeteo.source import Arpege

six_hours_later = pd.Timestamp("now", tz="UTC") + pd.Timedelta("6h")

flight = pd.DataFrame(
    {
        "timestamp": [six_hours_later, six_hours_later],
        "latitude": [40.3, 42.5],
        "longitude": [4.2, 6.6],
        "altitude": [25_000, 30_000],
    }
)

# Obtain Arpege forecast information.
arpege_grid = Arpege(local_store="/tmp/arpege-zarr")
flight_new = arpege_grid.interpolate(flight)
```

## Server-client mode

When running the tool in a server-client mode. The following script can be used to start a FastAPI service on the server. It handles the flight date request and obtains Google ARCO data if the partition is not on the server. After that, it will perform the interpolation of weather data and return the final data to the client.

```bash
fastmeteo-server --local-store /tmp/era5-zarr
```

At the client side, the following code can be used to submit and get the process flight with meteorology data.

```python
import pandas as pd
from fastmeteo.network import Client

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

Note: The default server address is `http://localhost:9800`. You can run the server remotely, and use a different port if needed. For example:

```bash
fastmeteo-server --local-store /tmp/era5-zarr --port 8080
```

Then update the client code to point to the new server address: 

```python
server_address = "192.168.1.123"  # or:
server_address = "my.server.example.com"

client = Client(server=server_address, port=8080)
```

## Pre-sync your data

You can use the following command to pre-sync the data (only available for ARCO ERA5 data):

```bash
fastmeteo-sync --local-store /path/to/era5-zarr/ --start 2022-01-01 --stop 2022-02-01
```

Above example will download the data for January 2022 to your `/path/to/era5-zarr/` folder.

## Options

### Differen meteorological features

If you want more or different meteorological features than wind, temperature and humidity, specify the desired feature list as follows:

```python
features = [
    "u_component_of_wind",
    "v_component_of_wind",
    "convective_available_potential_energy",
]

era5_grid = ArcoEra5(local_store="/tmp/era5-zarr", features=features)

flight_new = era5_grid.interpolate(flight)
```

> [!CAUTION]
> If you get a `RuntimeError: Requested features not in local zarr`, it means you have initialized the `local_store` path with different features. Choose a different path or delete the old folder first.

There are 273 variables from ARCO ERA5, which can be listed with the following code:

```python
import xarray

ds = xarray.open_zarr(
    "gs://gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3",
    chunks=None,
    storage_options=dict(token="anon"),
)
print(ds.variables)
```


### Use 137 model levels

By default, `fastmeteo` uses the 37-pressure-level version of the ARCO ERA5 data. If you want to use the 137 model level version of the data, you can do so by specifying the `model_levels` parameter as follows:

```python
era5_grid = ArcoEra5(local_store="/tmp/era5-zarr", model_levels=137)
```

Note that not all levels are used. Only the following levels are used for the construction of the interpolation grid:

```
DEFAULT_LEVELS_37 = [
    100, 125, 150, 175, 200, 225, 250, 300, 350, 400, 450,
    500, 550, 600, 650, 700, 750, 800, 850, 900, 950, 1000
]

DEFAULT_LEVELS_137 = [
    67,  68,  69,  70,  71,  72,  73,  74,  75,  76,  77,  78,  79,  80,
    81,  82,  83,  84,  85,  86,  88,  89,  90,  91,  92,  93,  94,  95,
    96,  97,  98,  99,  100, 101, 103, 104, 105, 107, 108, 110, 112, 114,
    116, 119, 122, 128, 132, 137
]
```

> [!WARNING]
> The list of features is different in the 137 model-level dataset. Only the following are available in 137 model-level dataset:
> ```
> divergence
> fraction_of_cloud_cover
> geopotential
> ozone_mass_mixing_ratio
> specific_cloud_ice_water_content
> specific_cloud_liquid_water_content
> specific_humidity
> specific_rain_water_content
> specific_snow_water_content
> temperature
> u_component_of_wind
> v_component_of_wind
> vertical_velocity
> vorticity
> ```

### Check the property of the ARCO ERA5 data

You can discover the properties of the data as:

```python
import xarray
from fastmeteo.grid import arco_era5_url_level_37

ds = xarray.open_zarr(
    arco_era5_url_level_37, chunks=None, storage_options=dict(token="anon")
)
ds
```
