import io
import urllib.error
from email.message import Message
from unittest.mock import patch

import pytest

from famly_fetch.api_client import urlopen_with_backoff


def _http_error(code, retry_after=None):
    headers = Message()
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return urllib.error.HTTPError(
        url="https://app.famly.co/api", code=code, msg="err", hdrs=headers, fp=io.BytesIO(b"")
    )


def test_retries_on_429_then_succeeds():
    sentinel = object()
    calls = {"n": 0}

    def fake_urlopen(req):
        calls["n"] += 1
        if calls["n"] < 3:
            raise _http_error(429)
        return sentinel

    sleeps = []
    with (
        patch("famly_fetch.api_client.urllib.request.urlopen", fake_urlopen),
        patch("famly_fetch.api_client.time.sleep", sleeps.append),
    ):
        assert urlopen_with_backoff("req") is sentinel
    assert calls["n"] == 3
    assert sleeps == [2.0, 4.0]  # exponential: base_delay * 2^attempt


def test_honors_retry_after_header():
    calls = {"n": 0}

    def fake_urlopen(req):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _http_error(429, retry_after=7)
        return "ok"

    sleeps = []
    with (
        patch("famly_fetch.api_client.urllib.request.urlopen", fake_urlopen),
        patch("famly_fetch.api_client.time.sleep", sleeps.append),
    ):
        assert urlopen_with_backoff("req") == "ok"
    assert sleeps == [7.0]


def test_does_not_retry_client_errors():
    def fake_urlopen(req):
        raise _http_error(400)

    with (
        patch("famly_fetch.api_client.urllib.request.urlopen", fake_urlopen),
        patch("famly_fetch.api_client.time.sleep") as sleep,
    ):
        with pytest.raises(urllib.error.HTTPError):
            urlopen_with_backoff("req")
    sleep.assert_not_called()


def test_raises_after_exhausting_attempts():
    calls = {"n": 0}

    def fake_urlopen(req):
        calls["n"] += 1
        raise urllib.error.URLError("connection reset")

    sleeps = []
    with (
        patch("famly_fetch.api_client.urllib.request.urlopen", fake_urlopen),
        patch("famly_fetch.api_client.time.sleep", sleeps.append),
    ):
        with pytest.raises(urllib.error.URLError):
            urlopen_with_backoff("req", attempts=3)
    assert calls["n"] == 3
    assert sleeps == [2.0, 4.0]
