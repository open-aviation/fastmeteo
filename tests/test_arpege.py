from contextlib import contextmanager
from functools import partial
from io import BytesIO
from unittest.mock import Mock

import httpx
import pandas as pd
import pytest
import xarray as xr

from fastmeteo.source import Arpege, arpege


@pytest.fixture
def mock_http(monkeypatch):
    """Route both metadata requests and streamed downloads through a mock server."""
    handler = Mock(return_value=httpx.Response(404))
    client = partial(httpx.Client, transport=httpx.MockTransport(handler))
    monkeypatch.setattr(arpege.httpx, "Client", client)

    @contextmanager
    def stream(method, url, **kwargs):
        with client() as session, session.stream(method, url, **kwargs) as response:
            yield response

    monkeypatch.setattr(arpege.httpx, "stream", stream)
    return handler


@pytest.fixture
def fixed_clock(monkeypatch):
    clock = Mock(wraps=pd)
    clock.Timestamp.now.return_value = pd.Timestamp("2026-11-04T20:00:00Z")
    monkeypatch.setattr(arpege, "pd", clock)


@pytest.mark.parametrize("aware", [False, True])
def test_future_forecast_uses_published_run(mock_http, fixed_clock, aware):
    """A forecast after midnight must use an already published model run."""
    mock_http.side_effect = [httpx.Response(404), httpx.Response(200)]
    requested = pd.Timestamp("2026-11-05T02:00:00", tz="UTC" if aware else None)
    grid = Arpege(local_store="unused")

    runtime = grid.get_latest_run_time(requested)

    assert runtime == pd.Timestamp("2026-11-04T12:00:00Z")
    urls = [str(call.args[0].url) for call in mock_http.call_args_list]
    assert len(urls) == 2
    assert "2026-11-04T18:00:00Z" in urls[0]
    assert "2026-11-04T12:00:00Z" in urls[1]
    assert all("files.data.gouv.fr/meteofrance-pnt/pnt/" in url for url in urls)


def test_no_published_run_covers_forecast(mock_http, fixed_clock):
    grid = Arpege(local_store="unused")
    with pytest.raises(RuntimeError, match="No published ARPEGE"):
        grid.get_latest_run_time(pd.Timestamp("2026-11-05T02:00:00Z"))
    # Runs older than 24 forecast hours cannot satisfy this request.
    assert mock_http.call_count == 3


def test_forecast_beyond_range_does_not_request_future_run(mock_http, fixed_clock):
    grid = Arpege(local_store="unused")
    with pytest.raises(RuntimeError, match="No published ARPEGE"):
        grid.get_latest_run_time(pd.Timestamp("2026-11-07T02:00:00Z"))
    mock_http.assert_not_called()


def test_later_forecast_package(mock_http, fixed_clock):
    mock_http.return_value = httpx.Response(200)
    grid = Arpege(local_store="unused", time_range="025H048H")
    assert grid.get_latest_run_time(
        pd.Timestamp("2026-11-06T02:00:00Z")
    ) == pd.Timestamp("2026-11-04T18:00:00Z")


def test_server_error_is_not_treated_as_unpublished(mock_http, fixed_clock):
    mock_http.return_value = httpx.Response(503)
    with pytest.raises(httpx.HTTPStatusError):
        Arpege(local_store="unused").get_latest_run_time(
            pd.Timestamp("2026-11-05T02:00:00Z")
        )
    assert mock_http.call_count == 1


@pytest.mark.parametrize(
    ("status", "body", "headers", "error"),
    [
        (404, b"<?xml version='1.0'?><Error/>", {}, httpx.HTTPStatusError),
        (200, b"<?xml version='1.0'?><Error/>", {}, RuntimeError),
        (200, b"", {}, RuntimeError),
        (200, b"GRIBpartial", {"Content-Length": "100"}, RuntimeError),
    ],
)
def test_failed_download_does_not_create_cache(
    mock_http, tmp_path, status, body, headers, error
):
    mock_http.return_value = httpx.Response(status, content=body, headers=headers)
    file = tmp_path / "forecast.grib2"
    with pytest.raises(error):
        arpege.download_with_progress("https://example.test/forecast.grib2", file)
    assert list(tmp_path.iterdir()) == []


def test_successful_download(mock_http, tmp_path):
    body = b"GRIBtest7777"
    mock_http.return_value = httpx.Response(200, content=body)
    file = tmp_path / "forecast.grib2"
    assert (
        arpege.download_with_progress("https://example.test/forecast.grib2", file)
        is None
    )
    assert file.read_bytes() == body
    assert list(tmp_path.iterdir()) == [file]

    buffer = arpege.download_with_progress("https://example.test/forecast.grib2")
    assert isinstance(buffer, BytesIO)
    assert buffer.read() == body


@pytest.mark.parametrize("cached", [b"", b"<?xml error", b"GRIBpartial"])
def test_invalid_cached_download_is_replaced(monkeypatch, tmp_path, cached):
    monkeypatch.setattr(arpege, "tempdir", tmp_path)
    grid = Arpege(local_store="unused", levels=[500], features=["t"])
    runtime = pd.Timestamp("2026-11-04T12:00:00Z")
    monkeypatch.setattr(grid, "get_latest_run_time", lambda hour: runtime)
    file = tmp_path / grid._remote_url(runtime).rsplit("/", 1)[-1]
    file.write_bytes(cached)

    def download(url, destination):
        assert destination == file
        destination.write_bytes(b"GRIBtest7777")

    monkeypatch.setattr(arpege, "download_with_progress", download)
    dataset = xr.Dataset(
        {"t": (("step", "isobaricInhPa"), [[250.0], [252.0]])},
        coords={
            "time": runtime.tz_localize(None).to_datetime64(),
            "step": pd.to_timedelta([0, 1], unit="h"),
            "isobaricInhPa": [500],
        },
    )
    monkeypatch.setattr(arpege.xr, "open_dataset", lambda *args, **kwargs: dataset)

    result = grid.select_remote(runtime)

    assert file.read_bytes() == b"GRIBtest7777"
    assert result.time.values[1] == pd.Timestamp("2026-11-04T13:00:00").to_datetime64()
    assert list(result.data_vars) == ["t"]
