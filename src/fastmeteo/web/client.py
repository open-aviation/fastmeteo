from typing import Any

import httpx
import pandas as pd


class Client:
    def __init__(
        self,
        server: str = "127.0.0.1",
        port: int = 9800,
        client: httpx.Client | None = None,
    ) -> None:
        self.server = server
        self.port = port
        self.client = client or httpx.Client()

    def serialize(self, df: pd.DataFrame) -> dict[str, Any]:
        return df.to_dict(orient="list")  # type: ignore

    def deserialize(self, data: dict[str, Any]) -> pd.DataFrame:
        return pd.DataFrame.from_dict(data)

    def submit_flight(self, flight: pd.DataFrame) -> pd.DataFrame:
        url = f"http://{self.server}:{self.port}/submit_flight/"

        flight_dict = self.serialize(flight)

        payload = {"data": flight_dict}

        response = self.client.post(url, json=payload)
        response.raise_for_status()

        data = response.json()
        flight_new = self.deserialize(data)

        return flight_new
