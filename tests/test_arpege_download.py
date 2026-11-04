"""ARPEGE download: new data.gouv.fr entry point, redirects and failed downloads.

No network: httpx's transport is replaced by a fake data.gouv.fr (302 redirect)
and a fake object storage behind it.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from fastmeteo.source import arpege
from fastmeteo.source.arpege import download_with_progress

STORAGE = "https://storage.example/pnt/"
GRIB = b"GRIB" + b"\x00" * 1000 + b"7777"


@pytest.fixture
def serve(monkeypatch: pytest.MonkeyPatch) -> Callable[[int, bytes], None]:
    """Route every httpx request to a fake data.gouv.fr + object storage."""

    def install(status: int = 200, body: bytes = GRIB) -> None:
        def handle(self: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if url.startswith(arpege.bare_url):
                path = url[len(arpege.bare_url) :]
                return httpx.Response(302, headers={"location": STORAGE + path})
            return httpx.Response(status, content=body)

        monkeypatch.setattr(httpx.HTTPTransport, "handle_request", handle)

    return install


def test_entry_point_is_the_current_data_gouv_host() -> None:
    assert arpege.bare_url.startswith("https://files.data.gouv.fr/meteofrance-pnt/pnt/")


def test_redirect_is_followed_to_the_grib_file(serve, tmp_path: Path) -> None:
    serve(200, GRIB)
    target = tmp_path / "file.grib2"
    download_with_progress(arpege.bare_url + "run/file.grib2", target)
    assert target.read_bytes() == GRIB


def test_http_error_raises_and_leaves_no_file(serve, tmp_path: Path) -> None:
    serve(404, b"<html>Not Found</html>")
    target = tmp_path / "file.grib2"
    with pytest.raises(httpx.HTTPStatusError, match="404"):
        download_with_progress(arpege.bare_url + "run/file.grib2", target)
    assert list(tmp_path.iterdir()) == []


def test_error_page_served_with_200_leaves_no_file(serve, tmp_path: Path) -> None:
    serve(200, b"<?xml version='1.0'?><Error/>")
    target = tmp_path / "file.grib2"
    with pytest.raises(RuntimeError, match="Check if the requested data is available"):
        download_with_progress(arpege.bare_url + "run/file.grib2", target)
    assert list(tmp_path.iterdir()) == []  # no truncated file reused by the next call


def test_in_memory_download_still_works(serve) -> None:
    serve(200, GRIB)
    buffer = download_with_progress(arpege.bare_url + "run/file.grib2")
    assert buffer is not None and buffer.read() == GRIB
