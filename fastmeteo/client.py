import requests
import pandas as pd
from typing import Dict


class Client:
    def __init__(self, server="127.0.0.1", port=9800) -> None:
        self.server = server
        self.port = port

    def serialize(self, df: pd.DataFrame) -> Dict:
        return df.to_dict(orient="list")

    def deserialize(self, data: Dict) -> pd.DataFrame:
        return pd.DataFrame.from_dict(data)

    def submit_flight(self, flight: pd.DataFrame):
        url = f"http://{self.server}:{self.port}/submit_flight/"

        flight_dict = self.serialize(flight)

        payload = {"data": flight_dict}

        response = requests.post(url, json=payload)

        if response.status_code == 200:
            # Deserialize the received data back into a DataFrame
            data = response.json()
            flight_new = self.deserialize(data)

            return flight_new
        else:
            print(f"Error: {response.content}")
