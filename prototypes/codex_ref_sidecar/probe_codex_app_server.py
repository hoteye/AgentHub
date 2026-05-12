#!/usr/bin/env python3
"""Probe Codex ref app-server as an AgentHub sidecar.

The script intentionally avoids importing AgentHub runtime code. It validates
the external process/protocol boundary that AgentHub can later wrap.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_CODEX_BIN = Path(
    "/home/lyc/project/AgentHubRef/codex_ref/codex-rs/target/release/codex-app-server"
)
DEFAULT_CWD = Path("/home/lyc/project/AgentHub")


class SidecarError(RuntimeError):
    pass


@dataclass
class JsonRpcEvent:
    payload: dict[str, Any]
    received_at: float = field(default_factory=time.monotonic)


class CodexAppServerSidecar:
    def __init__(
        self,
        *,
        codex_bin: Path,
        extra_args: Iterable[str] = (),
        timeout: float = 30.0,
        verbose: bool = False,
    ) -> None:
        self.codex_bin = codex_bin
        self.extra_args = list(extra_args)
        self.timeout = timeout
        self.verbose = verbose
        self._proc: subprocess.Popen[str] | None = None
        self._events: queue.Queue[JsonRpcEvent] = queue.Queue()
        self._stderr_lines: queue.Queue[str] = queue.Queue()
        self._request_id = 0
        self.notifications: list[dict[str, Any]] = []

    def start(self) -> None:
        if not self.codex_bin.exists():
            raise SidecarError(f"codex binary not found: {self.codex_bin}")

        command = [
            str(self.codex_bin),
            "--listen",
            "stdio://",
            *self.extra_args,
        ]
        if self.verbose:
            print(f"$ {' '.join(command)}", file=sys.stderr)

        self._proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()

    def close(self) -> None:
        proc = self._proc
        if proc is None:
            return
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._request_id += 1
        request_id = self._request_id
        message: dict[str, Any] = {"id": request_id, "method": method}
        if params is not None:
            message["params"] = params
        self._send(message)
        return self._wait_for_response(request_id)

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        message: dict[str, Any] = {"method": method}
        if params is not None:
            message["params"] = params
        self._send(message)

    def stderr_tail(self, limit: int = 20) -> list[str]:
        lines: list[str] = []
        while True:
            try:
                lines.append(self._stderr_lines.get_nowait())
            except queue.Empty:
                break
        return lines[-limit:]

    def drain_notifications(self, duration: float = 0.25) -> list[dict[str, Any]]:
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            try:
                event = self._events.get(timeout=max(0.01, deadline - time.monotonic()))
            except queue.Empty:
                break
            payload = event.payload
            if "method" in payload and "id" not in payload:
                self.notifications.append(payload)
            else:
                self._events.put(event)
                break
        return list(self.notifications)

    def _send(self, message: dict[str, Any]) -> None:
        proc = self._require_proc()
        if proc.stdin is None:
            raise SidecarError("sidecar stdin is unavailable")
        if proc.poll() is not None:
            raise SidecarError(
                f"sidecar exited before send: code={proc.returncode}, stderr={self.stderr_tail()}"
            )
        line = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
        if self.verbose:
            print(f"> {line}", file=sys.stderr)
        proc.stdin.write(line + "\n")
        proc.stdin.flush()

    def _wait_for_response(self, request_id: int) -> dict[str, Any]:
        deadline = time.monotonic() + self.timeout
        while True:
            proc = self._require_proc()
            if proc.poll() is not None and self._events.empty():
                raise SidecarError(
                    f"sidecar exited while waiting for id={request_id}: "
                    f"code={proc.returncode}, stderr={self.stderr_tail()}"
                )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SidecarError(
                    f"timeout waiting for id={request_id}; stderr={self.stderr_tail()}"
                )
            try:
                event = self._events.get(timeout=min(0.25, remaining))
            except queue.Empty:
                continue

            payload = event.payload
            if self.verbose:
                print(f"< {json.dumps(payload, ensure_ascii=False)}", file=sys.stderr)
            if "method" in payload and "id" not in payload:
                self.notifications.append(payload)
                continue
            if payload.get("id") != request_id:
                self.notifications.append(payload)
                continue
            if "error" in payload:
                raise SidecarError(
                    f"{payload.get('error', {}).get('message', 'JSON-RPC error')}: "
                    f"{json.dumps(payload.get('error'), ensure_ascii=False)}"
                )
            return payload.get("result", {})

    def _read_stdout(self) -> None:
        proc = self._require_proc()
        assert proc.stdout is not None
        for line in proc.stdout:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                self._events.put(
                    JsonRpcEvent(
                        {
                            "method": "$agenthub/protocolError",
                            "params": {
                                "error": str(exc),
                                "line": stripped,
                            },
                        }
                    )
                )
                continue
            if isinstance(payload, dict):
                self._events.put(JsonRpcEvent(payload))
            else:
                self._events.put(
                    JsonRpcEvent(
                        {
                            "method": "$agenthub/protocolError",
                            "params": {
                                "error": "non-object JSON-RPC payload",
                                "value": payload,
                            },
                        }
                    )
                )

    def _read_stderr(self) -> None:
        proc = self._require_proc()
        assert proc.stderr is not None
        for line in proc.stderr:
            stripped = line.rstrip("\n")
            if self.verbose and stripped:
                print(f"! {stripped}", file=sys.stderr)
            self._stderr_lines.put(stripped)

    def _require_proc(self) -> subprocess.Popen[str]:
        if self._proc is None:
            raise SidecarError("sidecar is not started")
        return self._proc


def initialize(sidecar: CodexAppServerSidecar) -> dict[str, Any]:
    result = sidecar.request(
        "initialize",
        {
            "clientInfo": {
                "name": "agenthub_sidecar_probe",
                "title": "AgentHub Sidecar Probe",
                "version": "0.1.0",
            },
            "capabilities": {
                "experimentalApi": True,
            },
        },
    )
    sidecar.notify("initialized")
    return result


def start_thread(args: argparse.Namespace, sidecar: CodexAppServerSidecar) -> dict[str, Any]:
    params: dict[str, Any] = {
        "cwd": str(args.cwd),
        "approvalPolicy": args.approval_policy,
        "sandbox": args.sandbox,
        "persistExtendedHistory": True,
    }
    if args.model_provider:
        params["modelProvider"] = args.model_provider
    if args.model:
        params["model"] = args.model
    return sidecar.request("thread/start", params)


def start_turn(
    args: argparse.Namespace,
    sidecar: CodexAppServerSidecar,
    thread_response: dict[str, Any],
) -> dict[str, Any]:
    thread_id = thread_response["thread"]["id"]
    return sidecar.request(
        "turn/start",
        {
            "threadId": thread_id,
            "input": [
                {
                    "type": "text",
                    "text": args.turn,
                    "textElements": [],
                }
            ],
        },
    )


def fork_thread(
    args: argparse.Namespace,
    sidecar: CodexAppServerSidecar,
    thread_response: dict[str, Any],
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "threadId": thread_response["thread"]["id"],
        "approvalPolicy": args.approval_policy,
        "sandbox": args.sandbox,
        "persistExtendedHistory": True,
    }
    if args.cwd:
        params["cwd"] = str(args.cwd)
    if args.model_provider:
        params["modelProvider"] = args.model_provider
    if args.model:
        params["model"] = args.model
    return sidecar.request("thread/fork", params)


def wait_for_turn_completion(
    sidecar: CodexAppServerSidecar,
    *,
    timeout: float,
) -> dict[str, Any] | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            event = sidecar._events.get(timeout=min(0.25, deadline - time.monotonic()))
        except queue.Empty:
            continue
        payload = event.payload
        if "method" in payload and "id" not in payload:
            sidecar.notifications.append(payload)
            if payload.get("method") == "turn/completed":
                return payload
            continue
        sidecar.notifications.append(payload)
    return None


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--codex-bin",
        type=Path,
        default=Path(os.environ.get("CODEX_REF_BIN", DEFAULT_CODEX_BIN)),
        help="Path to the Codex ref codex-app-server binary.",
    )
    parser.add_argument(
        "--cwd",
        type=Path,
        default=DEFAULT_CWD,
        help="Thread working directory passed to Codex ref.",
    )
    parser.add_argument(
        "--model-provider",
        default=None,
        help="Optional model provider override. Omit to use Codex ref config.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Optional model override. Omit to use Codex ref config/catalog.",
    )
    parser.add_argument(
        "--approval-policy",
        default="never",
        choices=["untrusted", "on-failure", "on-request", "never"],
    )
    parser.add_argument(
        "--sandbox",
        default="danger-full-access",
        choices=["read-only", "workspace-write", "danger-full-access"],
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="JSON-RPC request timeout in seconds.",
    )
    parser.add_argument(
        "--turn",
        default=None,
        help="Optional live prompt. If omitted, no provider turn is started.",
    )
    parser.add_argument(
        "--turn-timeout",
        type=float,
        default=120.0,
        help="How long to wait for turn/completed when --turn is used.",
    )
    parser.add_argument(
        "--fork",
        action="store_true",
        help="After thread/start, call thread/fork and print the forked thread id.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print raw JSON-RPC traffic and sidecar stderr.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    sidecar = CodexAppServerSidecar(
        codex_bin=args.codex_bin,
        timeout=args.timeout,
        verbose=args.verbose,
    )

    try:
        sidecar.start()
        init = initialize(sidecar)
        print("initialize: ok")
        print(f"  userAgent: {init.get('userAgent')}")
        print(f"  codexHome: {init.get('codexHome')}")
        print(f"  platform: {init.get('platformFamily')}/{init.get('platformOs')}")

        thread = start_thread(args, sidecar)
        thread_info = thread.get("thread", {})
        print("thread/start: ok")
        print(f"  threadId: {thread_info.get('id')}")
        print(f"  model: {thread.get('model')}")
        print(f"  modelProvider: {thread.get('modelProvider')}")
        print(f"  cwd: {thread.get('cwd')}")
        print(f"  approvalPolicy: {thread.get('approvalPolicy')}")
        print(f"  sandbox: {json.dumps(thread.get('sandbox'), ensure_ascii=False)}")

        sidecar.drain_notifications()
        if args.turn:
            turn = start_turn(args, sidecar, thread)
            print("turn/start: ok")
            print(f"  turnId: {turn.get('turn', {}).get('id')}")
            completed = wait_for_turn_completion(sidecar, timeout=args.turn_timeout)
            if completed is None:
                print("turn/completed: timeout")
                return 2
            print("turn/completed: ok")

        if args.fork:
            forked = fork_thread(args, sidecar, thread)
            forked_info = forked.get("thread", {})
            print("thread/fork: ok")
            print(f"  forkedThreadId: {forked_info.get('id')}")
            print(f"  forkedFromId: {forked_info.get('forkedFromId')}")
            print(f"  model: {forked.get('model')}")
            print(f"  modelProvider: {forked.get('modelProvider')}")

        notification_methods = [
            payload.get("method") for payload in sidecar.notifications if payload.get("method")
        ]
        if notification_methods:
            print("notifications:")
            for method in notification_methods[-20:]:
                print(f"  - {method}")
        return 0
    except SidecarError as exc:
        print(f"sidecar probe failed: {exc}", file=sys.stderr)
        for line in sidecar.stderr_tail():
            print(f"stderr: {line}", file=sys.stderr)
        return 1
    finally:
        sidecar.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
