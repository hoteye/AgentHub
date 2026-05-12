from __future__ import annotations

import socket
import threading
import time
import urllib.request

from cli.agent_cli.providers.oauth_pkce_callback_runtime import (
    ERROR_CALLBACK_TIMEOUT,
    ERROR_INVALID_REDIRECT_URI,
    wait_for_pkce_callback,
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_wait_for_pkce_callback_captures_code_and_state() -> None:
    port = _free_port()
    redirect_uri = f"http://127.0.0.1:{port}/callback"
    result_holder: dict[str, dict[str, object]] = {}

    def _runner() -> None:
        result_holder["result"] = wait_for_pkce_callback(redirect_uri=redirect_uri, timeout_seconds=3)

    worker = threading.Thread(target=_runner, daemon=True)
    worker.start()
    callback_url = f"http://127.0.0.1:{port}/callback?code=auth-code-1&state=state-1"
    deadline = time.time() + 2.0
    delivered = False
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(callback_url, timeout=1) as response:
                _ = response.read()
            delivered = True
            break
        except Exception:
            time.sleep(0.05)
    assert delivered is True
    worker.join(timeout=4.0)
    assert worker.is_alive() is False
    result = dict(result_holder.get("result") or {})
    assert result.get("status") == "ok"
    assert result.get("code") == "auth-code-1"
    assert result.get("state") == "state-1"


def test_wait_for_pkce_callback_timeout() -> None:
    port = _free_port()
    redirect_uri = f"http://127.0.0.1:{port}/callback"
    result = wait_for_pkce_callback(redirect_uri=redirect_uri, timeout_seconds=1)
    assert result.get("status") == "timeout"
    assert result.get("error_code") == ERROR_CALLBACK_TIMEOUT


def test_wait_for_pkce_callback_rejects_invalid_redirect_uri() -> None:
    result = wait_for_pkce_callback(redirect_uri="https://issuer.example/callback", timeout_seconds=1)
    assert result.get("status") == "error"
    assert result.get("error_code") == ERROR_INVALID_REDIRECT_URI
