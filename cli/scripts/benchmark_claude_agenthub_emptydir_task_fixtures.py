from __future__ import annotations

import textwrap
from typing import Any


def _task_prompt(body: str) -> str:
    return textwrap.dedent(
        f"""
        You are running unattended in an empty directory.
        Do not ask follow-up questions. Make reasonable assumptions and finish the task end-to-end.

        {body.strip()}
        """
    ).strip()


def build_default_tasks(
    *, benchmark_task_cls: type[Any], validation_spec_cls: type[Any]
) -> list[Any]:
    BenchmarkTask = benchmark_task_cls
    ValidationSpec = validation_spec_cls
    return [
        BenchmarkTask(
            task_id="ranges_cli",
            title="Normalize ranges library and CLI",
            prompt=_task_prompt(
                """
                Create a small Python project with these exact files:
                - src/range_tools.py
                - normalize_ranges.py
                - tests/test_range_tools.py
                - README.md

                Requirements:
                - Implement normalize_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]
                - Merge overlapping or adjacent ranges
                - Accept unsorted input
                - Raise ValueError if a range has start > end
                - The CLI must read a JSON array of pairs from stdin and print normalized JSON to stdout
                - Use only the Python standard library plus pytest for tests
                - Run the tests yourself before finishing

                Final response:
                - 2 to 4 short lines
                - State what you built
                - State the test command you ran
                """
            ),
            validations=(
                ValidationSpec(name="pytest", command="python -m pytest -q"),
                ValidationSpec(
                    name="hidden_checks",
                    command=textwrap.dedent(
                        """
                        python - <<'PY'
                        import json
                        import pathlib
                        import subprocess
                        import sys

                        root = pathlib.Path.cwd()
                        sys.path.insert(0, str(root / "src"))
                        from range_tools import normalize_ranges

                        assert normalize_ranges([(5, 6), (1, 3), (4, 4)]) == [(1, 6)]
                        assert normalize_ranges([(8, 9), (1, 1)]) == [(1, 1), (8, 9)]
                        try:
                            normalize_ranges([(3, 1)])
                        except ValueError:
                            pass
                        else:
                            raise AssertionError("normalize_ranges must raise ValueError when start > end")

                        proc = subprocess.run(
                            [sys.executable, "normalize_ranges.py"],
                            input="[[5, 6], [1, 3], [4, 4]]",
                            text=True,
                            capture_output=True,
                            check=True,
                        )
                        assert json.loads(proc.stdout) == [[1, 6]], proc.stdout
                        print("ok")
                        PY
                        """
                    ).strip(),
                ),
            ),
            expected_files=(
                "src/range_tools.py",
                "normalize_ranges.py",
                "tests/test_range_tools.py",
                "README.md",
            ),
        ),
        BenchmarkTask(
            task_id="expense_report",
            title="Expense CSV summarizer CLI",
            prompt=_task_prompt(
                """
                Create a small Python project with these exact files:
                - expense_report.py
                - tests/test_expense_report.py
                - README.md

                Requirements:
                - Build a CLI: python expense_report.py <csv_path>
                - Input CSV columns are: date, category, amount
                - Output a JSON object with keys:
                  - total
                  - by_category
                  - largest_expense
                - Round monetary values to 2 decimal places
                - Ignore blank lines
                - Invalid rows must produce a clear error message and a non-zero exit code
                - Use only the Python standard library plus pytest for tests
                - Run the tests yourself before finishing

                Final response:
                - 2 to 4 short lines
                - State what you built
                - State the test command you ran
                """
            ),
            validations=(
                ValidationSpec(name="pytest", command="python -m pytest -q"),
                ValidationSpec(
                    name="hidden_checks",
                    command=textwrap.dedent(
                        """
                        python - <<'PY'
                        import json
                        import pathlib
                        import subprocess
                        import sys

                        root = pathlib.Path.cwd()
                        good = root / "sample.csv"
                        good.write_text(
                            "date,category,amount\\n"
                            "2026-04-01,food,12.5\\n"
                            "2026-04-01,transport,8\\n"
                            "2026-04-02,food,7.25\\n",
                            encoding="utf-8",
                        )
                        proc = subprocess.run(
                            [sys.executable, "expense_report.py", str(good)],
                            text=True,
                            capture_output=True,
                            check=True,
                        )
                        payload = json.loads(proc.stdout)
                        assert payload["total"] == 27.75, payload
                        assert payload["by_category"] == {"food": 19.75, "transport": 8.0}, payload
                        assert payload["largest_expense"] == {
                            "date": "2026-04-01",
                            "category": "food",
                            "amount": 12.5,
                        }, payload

                        bad = root / "bad.csv"
                        bad.write_text("date,category,amount\\n2026-04-01,food,abc\\n", encoding="utf-8")
                        bad_proc = subprocess.run(
                            [sys.executable, "expense_report.py", str(bad)],
                            text=True,
                            capture_output=True,
                        )
                        assert bad_proc.returncode != 0, bad_proc.returncode
                        error_text = f"{bad_proc.stdout}\\n{bad_proc.stderr}".lower()
                        assert "amount" in error_text, error_text
                        print("ok")
                        PY
                        """
                    ).strip(),
                ),
            ),
            expected_files=("expense_report.py", "tests/test_expense_report.py", "README.md"),
        ),
        BenchmarkTask(
            task_id="notes_server",
            title="Minimal notes HTTP server",
            prompt=_task_prompt(
                """
                Create a small Python project with these exact files:
                - notes_server.py
                - tests/test_notes_server.py
                - README.md

                Requirements:
                - Implement a small HTTP server using only the Python standard library
                - Run with: python notes_server.py --port <port>
                - GET /health returns {"status": "ok"}
                - GET /notes returns the full list of notes as JSON
                - POST /notes accepts JSON {"title": "...", "body": "..."}
                - POST /notes returns the created note with an integer id starting from 1
                - Invalid JSON or missing fields must return HTTP 400 with a JSON error body
                - Keep notes in memory only
                - Use only the Python standard library plus pytest for tests
                - Run the tests yourself before finishing

                Final response:
                - 2 to 4 short lines
                - State what you built
                - State the test command you ran
                """
            ),
            validations=(
                ValidationSpec(name="pytest", command="python -m pytest -q"),
                ValidationSpec(
                    name="hidden_checks",
                    command=textwrap.dedent(
                        """
                        python - <<'PY'
                        import json
                        import socket
                        import subprocess
                        import sys
                        import time
                        import urllib.error
                        import urllib.request

                        def free_port() -> int:
                            sock = socket.socket()
                            sock.bind(("127.0.0.1", 0))
                            port = sock.getsockname()[1]
                            sock.close()
                            return port

                        port = free_port()
                        proc = subprocess.Popen(
                            [sys.executable, "notes_server.py", "--port", str(port)],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            text=True,
                        )
                        base = f"http://127.0.0.1:{port}"
                        try:
                            deadline = time.time() + 20
                            while True:
                                try:
                                    with urllib.request.urlopen(base + "/health", timeout=1.0) as response:
                                        payload = json.loads(response.read().decode("utf-8"))
                                    assert payload == {"status": "ok"}, payload
                                    break
                                except Exception:
                                    if time.time() >= deadline:
                                        raise
                                    time.sleep(0.2)

                            create_req = urllib.request.Request(
                                base + "/notes",
                                data=json.dumps({"title": "t1", "body": "b1"}).encode("utf-8"),
                                headers={"Content-Type": "application/json"},
                                method="POST",
                            )
                            with urllib.request.urlopen(create_req, timeout=2.0) as response:
                                created = json.loads(response.read().decode("utf-8"))
                            assert created == {"id": 1, "title": "t1", "body": "b1"}, created

                            with urllib.request.urlopen(base + "/notes", timeout=2.0) as response:
                                notes = json.loads(response.read().decode("utf-8"))
                            assert notes == [created], notes

                            bad_req = urllib.request.Request(
                                base + "/notes",
                                data=b'{"title": "x"}',
                                headers={"Content-Type": "application/json"},
                                method="POST",
                            )
                            try:
                                urllib.request.urlopen(bad_req, timeout=2.0)
                            except urllib.error.HTTPError as exc:
                                assert exc.code == 400, exc.code
                                error_payload = json.loads(exc.read().decode("utf-8"))
                                assert "error" in error_payload, error_payload
                            else:
                                raise AssertionError("expected HTTP 400 for invalid payload")
                            print("ok")
                        finally:
                            proc.terminate()
                            try:
                                proc.wait(timeout=5)
                            except subprocess.TimeoutExpired:
                                proc.kill()
                                proc.wait(timeout=5)
                        PY
                        """
                    ).strip(),
                ),
            ),
            expected_files=("notes_server.py", "tests/test_notes_server.py", "README.md"),
        ),
    ]
