from __future__ import annotations

from pathlib import Path

from cli.agent_cli import agent_config_runtime, startup_debug
from cli.agent_cli.agent import RuleBasedAgent
from cli.agent_cli.runtime_facade_bindings_runtime import _build_default_agent


def test_startup_log_writes_claude_style_label(monkeypatch, tmp_path: Path) -> None:
    debug_file = tmp_path / "startup.debug.log"
    monkeypatch.setenv("AGENTHUB_START_DEBUG_LOG", str(debug_file))
    startup_debug._STARTUP_DEBUG_STREAM = None

    startup_debug.startup_log("main.enter argv=None")

    content = debug_file.read_text(encoding="utf-8")
    assert "[DEBUG] [STARTUP]" in content
    assert "main.enter argv=None" in content

    stream = startup_debug._STARTUP_DEBUG_STREAM
    if stream is not None and not stream.closed:
        stream.close()
    startup_debug._STARTUP_DEBUG_STREAM = None


def test_startup_timer_writes_elapsed_profile(monkeypatch, tmp_path: Path) -> None:
    debug_file = tmp_path / "startup.profile.log"
    monkeypatch.setenv("AGENTHUB_START_DEBUG_LOG", str(debug_file))
    startup_debug._STARTUP_DEBUG_STREAM = None

    with startup_debug.startup_timer("sample"):
        pass

    content = debug_file.read_text(encoding="utf-8")
    assert "profile.sample.begin" in content
    assert "profile.sample.end elapsed_ms=" in content

    stream = startup_debug._STARTUP_DEBUG_STREAM
    if stream is not None and not stream.closed:
        stream.close()
    startup_debug._STARTUP_DEBUG_STREAM = None


def test_default_runtime_agent_defers_initial_planner_build() -> None:
    class Agent:
        def __init__(self, *, build_initial_planner: bool = True) -> None:
            self.build_initial_planner = build_initial_planner

    agent = _build_default_agent(Agent, build_initial_planner=False)

    assert agent.build_initial_planner is False


def test_rule_based_agent_defer_planner_reload_coalesces_requests() -> None:
    agent = object.__new__(RuleBasedAgent)
    agent._planner_reload_defer_depth = 0
    agent._planner_reload_pending = False
    calls: list[str] = []
    agent._reload_planner = lambda: calls.append("reload")

    with RuleBasedAgent.defer_planner_reload(agent):
        agent._planner_reload_pending = True
        with RuleBasedAgent.defer_planner_reload(agent):
            agent._planner_reload_pending = True
        assert calls == []

    assert calls == ["reload"]


def test_lazy_rule_based_agent_reload_refreshes_pending_config_without_build(monkeypatch) -> None:
    agent = RuleBasedAgent(build_initial_planner=False)
    calls: list[str] = []

    def _prepare(agent_obj, **_kwargs):
        calls.append("prepare")
        agent_obj._planner_config = object()
        agent_obj._planner_build_pending = True

    def _reload(*_args, **_kwargs):
        calls.append("reload")

    monkeypatch.setattr(agent_config_runtime, "prepare_lazy_planner", _prepare)
    monkeypatch.setattr(agent_config_runtime, "reload_planner", _reload)

    agent._reload_planner()

    assert calls == ["prepare"]
    assert agent._planner is None
    assert agent._planner_build_pending is True
