import pandas as pd

from metmesh import Client

if __name__ == "__main__":
    flight = pd.DataFrame(
        {
            "timestamp": ["2021-10-12T01:10:00", "2021-10-12T01:20:00"],
            "icao24": ["abc123", "abc123"],
            "latitude": [40.3, 42.5],
            "longitude": [4.2, 6.6],
            "altitude": [25_000, 30_000],
        }
    )

    client = Client()

    print(flight)

    # send the flight and receive the new DataFrame
    flight_new = client.submit_flight(flight)

    print(flight_new)
