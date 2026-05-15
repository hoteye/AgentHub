"""Background-task slash command spec catalog slice."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def background_slash_command_specs(
    SlashCommandSpec: type[Any],
    surface_usage_text: Callable[[str], str],
) -> tuple[Any, ...]:
    return (
        SlashCommandSpec(
            "workflows",
            surface_usage_text("workflows"),
            "list delegated agent workflows plus recent non-mirrored background tasks",
        ),
        SlashCommandSpec(
            "background_tasks",
            surface_usage_text("background_tasks"),
            "list recent background tasks and current queue status",
        ),
        SlashCommandSpec(
            "background_worker_status",
            "/background_worker_status",
            "show background worker health, heartbeat, and runtime state",
        ),
        SlashCommandSpec(
            "background_worker_start",
            surface_usage_text("background_worker_start"),
            "start one detached background worker process",
        ),
        SlashCommandSpec(
            "background_worker_stop",
            surface_usage_text("background_worker_stop"),
            "stop the detached background worker process recorded in worker state",
        ),
        SlashCommandSpec(
            "background_worker_run_once",
            surface_usage_text("background_worker_run_once"),
            "run one local worker maintenance and queue-consumption pass",
        ),
        SlashCommandSpec(
            "background_benchmark",
            surface_usage_text("background_benchmark"),
            "submit one benchmark_headless_models run to the background task layer",
        ),
        SlashCommandSpec(
            "background_smoke",
            surface_usage_text("background_smoke"),
            "submit one live smoke script run to the background task layer",
        ),
        SlashCommandSpec(
            "background_teammate",
            surface_usage_text("background_teammate"),
            "run one real headless teammate turn in the background task layer",
        ),
        SlashCommandSpec(
            "background_task_status",
            "/background_task_status <task_id>",
            "show one background task status, dispatch state, and artifact pointers",
        ),
        SlashCommandSpec(
            "background_task_cancel",
            "/background_task_cancel <task_id>",
            "request cancellation for one background task",
        ),
        SlashCommandSpec(
            "background_task_retry",
            "/background_task_retry <task_id>",
            "retry one failed or cancelled background task",
        ),
        SlashCommandSpec(
            "background_task_apply",
            "/background_task_apply <task_id>",
            "apply one reviewed staged background teammate diff to the live workspace",
        ),
        SlashCommandSpec(
            "background_task_reject",
            "/background_task_reject <task_id>",
            "reject one staged background teammate diff without applying it to the live workspace",
        ),
    )
