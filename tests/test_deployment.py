from http.client import RemoteDisconnected
from io import BytesIO
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

import pytest

from scripts import check_deployment


@pytest.mark.parametrize(
    "error",
    [
        ConnectionResetError("Connection reset by peer"),
        ConnectionRefusedError("Connection refused"),
        TimeoutError("Timed out"),
        RemoteDisconnected("Connection closed before response"),
        URLError("Connection refused"),
        HTTPError("http://127.0.0.1:8080/healthz", 503, "Starting", {}, None),
    ],
)
def test_health_retries_transport_errors_until_ready(monkeypatch, error):
    request = Mock(side_effect=[error, BytesIO(b'{"status":"ok"}')])
    sleep = Mock()
    monkeypatch.setattr(check_deployment, "urlopen", request)
    monkeypatch.setattr(check_deployment.time, "sleep", sleep)

    check_deployment.wait_for_health("http://127.0.0.1:8080")

    assert request.call_count == 2
    request.assert_called_with("http://127.0.0.1:8080/healthz", timeout=2)
    sleep.assert_called_once_with(1)


def test_health_failure_still_fails_after_bounded_retries(monkeypatch):
    error = ConnectionResetError("Connection reset by peer")
    request = Mock(side_effect=error)
    sleep = Mock()
    monkeypatch.setattr(check_deployment, "urlopen", request)
    monkeypatch.setattr(check_deployment.time, "sleep", sleep)

    with pytest.raises(ConnectionResetError):
        check_deployment.wait_for_health("http://127.0.0.1:8080")

    assert request.call_count == 30
    assert sleep.call_count == 29


def test_health_does_not_accept_invalid_response(monkeypatch):
    request = Mock(return_value=BytesIO(b'{"status":"failed"}'))
    monkeypatch.setattr(check_deployment, "urlopen", request)

    with pytest.raises(AssertionError):
        check_deployment.wait_for_health("http://127.0.0.1:8080")

    request.assert_called_once()
