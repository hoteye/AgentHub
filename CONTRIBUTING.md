# Contributing

Thanks for your interest in AgentHub.

## Development Setup

```bash
python -m pip install -r requirements.txt -r cli/requirements.txt -r requirements-dev.txt
python -m cli.agent_cli --help
```

## Before Opening a Pull Request

Run the focused checks first:

```bash
python -m pytest -q \
  cli/tests/test_provider_config_boundary_guard.py \
  cli/tests/test_permission_mode_mapping.py \
  cli/tests/test_provider_catalog_paths_runtime.py
```

For broader changes, run the relevant tests under `cli/tests` or `tests`.

## Contribution Guidelines

- Keep provider credentials out of source code, tests, logs, and examples.
- Prefer small, focused pull requests.
- Include tests for behavior changes.
- Keep public documentation user-facing; avoid local machine paths or private deployment details.
- Do not commit build artifacts, caches, local runtime state, or generated logs.

## Reporting Issues

When reporting a bug, include:

- Operating system and Python version
- AgentHub command used
- Provider type, without API keys
- Expected behavior and actual behavior
- Minimal reproduction steps
