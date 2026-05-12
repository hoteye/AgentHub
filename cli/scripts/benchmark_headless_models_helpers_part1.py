from __future__ import annotations

SOURCE_PART = r'''#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from script_runtime_helpers import (
    apply_provider_home_override_env,
    normalize_optional_provider_home_override,
    resolve_effective_script_provider_home_dir,
    resolve_script_provider_home_dir,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
DEFAULT_PROMPT = "你好"
DEFAULT_TIMEOUT_SECONDS = 35.0
DEFAULT_ABILITY_TIMEOUT_SECONDS = 75.0
DEFAULT_MULTI_LLM_TIMEOUT_SECONDS = 240.0
DEFAULT_RUNS = 2
DEFAULT_FIRST_PROMPT = "今天几号？"
DEFAULT_SECOND_PROMPT = "明天呢？"
DEFAULT_TIMEZONE = "Asia/Shanghai"
DEFAULT_MAX_WORKERS = 4
DEFAULT_SCENARIO = "single_turn_headless"
DEFAULT_PROVIDER_HOME = resolve_script_provider_home_dir(cwd=REPO_ROOT)
DEFAULT_MULTI_LLM_CASES = (
    ("openai", "gpt_54"),
)
DEFAULT_POLICY_HELPER_CASES = (
    ("glm", "glm_5"),
)
DEFAULT_POLICY_HELPER_PROFILE = "policy_helper_regression"
POLICY_HELPER_PROFILE_CHOICES = ("single", "policy_helper_regression", "policy_helper_matrix")
ABILITY_TEST_NORMALIZE_RANGES_PROMPT = """你在进行 AgentHub benchmark 的编程能力测试。
不要调用工具，不要依赖外部文件。
直接回答，并严格按顺序包含以下三个一级标题：

# Implementation
使用 Python 3.11 实现函数：
def normalize_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]

规则：
1. 输入是闭区间 [start, end]。
2. 允许乱序、重复、相邻、嵌套。
3. 重叠或相邻区间必须合并，例如 (1, 3) 和 (4, 6) 要合并成 (1, 6)。
4. 若某个区间 start > end，必须抛出 ValueError，不能静默交换。
5. 目标时间复杂度 O(n log n)。

# Tests
给出 pytest 风格测试，至少覆盖：
- 空输入
- 单区间
- 乱序输入
- 重叠合并
- 相邻合并
- 嵌套区间
- 重复区间
- 非法区间

# Analysis
用 3 到 6 句话解释：
- 合并策略
- 为什么非法区间要抛错
- 时间复杂度为什么是 O(n log n)

要求：
- 必须包含至少一个 ```python 代码块
- 不要省略测试
- 不要输出与题目无关的寒暄
"""
ABILITY_TEST_STABLE_TOPO_PROMPT = """你在进行 AgentHub benchmark 的编程能力测试。
不要调用工具，不要依赖外部文件。
直接回答，并严格按顺序包含以下三个一级标题：

# Implementation
使用 Python 3.11 实现函数：
def stable_topological_sort(nodes: list[str], edges: list[tuple[str, str]]) -> list[str]

规则：
1. 返回一个合法拓扑序。
2. 如果同时有多个入度为 0 的节点，必须优先选择字典序最小的节点，保证结果稳定可重复。
3. nodes 里可能包含孤立节点，结果中不能丢失。
4. edges 里可能有重复边，重复边不能重复累计入度。
5. 如果边里引用了不在 nodes 中的节点，必须抛出 KeyError。
6. 如果出现自环或一般环，必须抛出 ValueError。
7. 目标时间复杂度 O((V + E) log V)。

# Tests
给出 pytest 风格测试，至少覆盖：
- 空图
- 孤立节点
- 多个可选节点时的稳定字典序
- 重复边
- 自环
- 一般环
- unknown node

# Analysis
用 3 到 6 句话解释：
- 为什么要用稳定 tie-break
- 如何检测 cycle / self-loop
- 复杂度为什么是 O((V + E) log V)

要求：
- 必须包含至少一个 ```python 代码块
- 不要省略测试
- 不要输出与题目无关的寒暄
"""
CI_REUSE_RECOMMENDED_COMMANDS = {
    "multi_llm_live_cases": (
        "python cli/scripts/benchmark_headless_models.py "
        "--scenario multi_llm_live_cases --case openai:gpt_54 --json "
        "--out /tmp/agenthub_benchmark_multi_llm_ci.json"
    ),
    "policy_helper_live_cases": (
        "python cli/scripts/benchmark_headless_models.py "
        "--scenario policy_helper_live_cases --case glm:glm_5 --json "
        "--out /tmp/agenthub_benchmark_policy_helper_ci.json"
    ),
}
DEFAULT_FIXED_PROVIDER_MATRIX = (
    {
        "capability": "main+subagent+teammate orchestration smoke",
        "scenario": "multi_llm_live_cases",
        "provider": "openai",
        "model": "gpt_54",
        "covers": ("main", "subagent", "teammate"),
    },
    {
        "capability": "policy helper rewrite/rerank/extract",
        "scenario": "policy_helper_live_cases",
        "provider": "glm",
        "model": "glm_5",
        "covers": ("helper",),
        "default_helper_profile": DEFAULT_POLICY_HELPER_PROFILE,
        "helper_combos": ("glm_low_latency", "deepseek_low_latency"),
    },
)
DEFAULT_CASES = (
    ("claude", "claude-sonnet-4-6"),
    ("claude", "claude-haiku-4-5-20251001"),
    ("deepseek", "deepseek-chat"),
    ("glm", "glm-5"),
    ("glm-claude-mode", "glm-5"),
    ("openai", "gpt-5.4"),
    ("openai", "gpt-5.3-reference"),
)


@dataclass(frozen=True)
class BenchmarkCase:
    provider: str
    model: str

    @property
    def label(self) -> str:
        return self.model

    def env_overrides(self, *, provider_home: str = "") -> dict[str, str]:
        env = {
            "AGENT_CLI_PROVIDER": self.provider,
            "AGENT_CLI_MODEL": self.model,
        }
        return apply_provider_home_override_env(env, provider_home=provider_home)


def _provider_home_report_fields(provider_home: str) -> dict[str, Any]:
    normalized_provider_home = normalize_optional_provider_home_override(provider_home)
    return {
        "provider_home": str(
            resolve_effective_script_provider_home_dir(
                cwd=REPO_ROOT,
                provider_home=normalized_provider_home,
            )
        ),
        "provider_home_override": normalized_provider_home,
        "provider_home_source": "explicit_override" if normalized_provider_home else "runtime_default",
    }


@dataclass(frozen=True)
class PolicyHelperCombo:
    combo_id: str
    provider: str = ""
    model: str = ""
    reasoning_effort: str = "low"
    timeout: int = 20
    source: str = "profile"
    description: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "combo_id": self.combo_id,
            "provider": self.provider,
            "model": self.model,
            "reasoning_effort": self.reasoning_effort,
            "timeout": int(self.timeout),
            "source": self.source,
            "description": self.description,
        }


@dataclass(frozen=True)
class AbilityTestDefinition:
    test_id: str
    title: str
    prompt: str
    max_score: int = 10
    pass_score: int = 7

    def as_dict(self) -> dict[str, Any]:
        return {
            "test_id": self.test_id,
            "title": self.title,
            "max_score": int(self.max_score),
            "pass_score": int(self.pass_score),
            "prompt": self.prompt,
        }


@dataclass(frozen=True)
class AbilitySuiteDefinition:
    suite_id: str
    title: str
    test_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "suite_id": self.suite_id,
            "title": self.title,
            "test_ids": list(self.test_ids),
        }


POLICY_HELPER_COMBO_CATALOG: tuple[PolicyHelperCombo, ...] = (
    PolicyHelperCombo(
        combo_id="main_route_default",
        provider="",
        model="",
        reasoning_effort="low",
        timeout=20,
        source="main_route",
        description="Follow main provider/model route and enforce helper low-effort timeout guard.",
    ),
    PolicyHelperCombo(
        combo_id="glm_low_latency",
        provider="glm",
        model="glm_5",
        reasoning_effort="low",
        timeout=20,
        source="override",
        description="Pin helper route to glm_5 for baseline regression.",
    ),
    PolicyHelperCombo(
        combo_id="deepseek_low_latency",
        provider="deepseek",
        model="deepseek_chat",
        reasoning_effort="low",
        timeout=20,
        source="override",
        description="Pin helper route to deepseek_chat for alternate regression lane.",
    ),
)

POLICY_HELPER_PROFILE_MATRIX: dict[str, tuple[str, ...]] = {
    "policy_helper_regression": ("glm_low_latency", "deepseek_low_latency"),
    "policy_helper_matrix": ("main_route_default", "glm_low_latency", "deepseek_low_latency"),
}
ABILITY_TEST_CATALOG: tuple[AbilityTestDefinition, ...] = (
    AbilityTestDefinition(
        test_id="normalize_ranges_py",
        title="Normalize Closed Integer Ranges",
        prompt=ABILITY_TEST_NORMALIZE_RANGES_PROMPT,
        max_score=11,
        pass_score=8,
    ),
    AbilityTestDefinition(
        test_id="stable_topological_sort_py",
        title="Stable Topological Sort With Validation",
        prompt=ABILITY_TEST_STABLE_TOPO_PROMPT,
        max_score=13,
        pass_score=9,
    ),
)
ABILITY_TEST_CHOICES = tuple(item.test_id for item in ABILITY_TEST_CATALOG)
ABILITY_SUITE_CATALOG: tuple[AbilitySuiteDefinition, ...] = (
    AbilitySuiteDefinition(
        suite_id="coding_pair",
        title="Two hard coding questions: range merge + stable topo sort",
        test_ids=("normalize_ranges_py", "stable_topological_sort_py"),
    ),
)
ABILITY_SUITE_CHOICES = tuple(item.suite_id for item in ABILITY_SUITE_CATALOG)


def _parse_case(value: str) -> BenchmarkCase:
    text = str(value or "").strip()
    provider, sep, model = text.partition(":")
    if not sep or not provider.strip() or not model.strip():
        raise argparse.ArgumentTypeError(
            f"invalid --case {value!r}; expected provider:model"
        )
    return BenchmarkCase(provider=provider.strip(), model=model.strip())


def _default_cases() -> list[BenchmarkCase]:
    return [BenchmarkCase(provider=provider, model=model) for provider, model in DEFAULT_CASES]


def _default_multi_llm_cases() -> list[BenchmarkCase]:
    return [BenchmarkCase(provider=provider, model=model) for provider, model in DEFAULT_MULTI_LLM_CASES]


def _default_policy_helper_cases() -> list[BenchmarkCase]:
    return [BenchmarkCase(provider=provider, model=model) for provider, model in DEFAULT_POLICY_HELPER_CASES]


def _combo_token(text: str) -> str:
    normalized = "".join(ch if ch.isalnum() else "_" for ch in str(text or "").strip().lower())
    normalized = normalized.strip("_")
    return normalized or "default"


def _policy_helper_combo_index() -> dict[str, PolicyHelperCombo]:
    return {combo.combo_id: combo for combo in POLICY_HELPER_COMBO_CATALOG}


def _ability_test_index() -> dict[str, AbilityTestDefinition]:
    return {item.test_id: item for item in ABILITY_TEST_CATALOG}


def _ability_suite_index() -> dict[str, AbilitySuiteDefinition]:
    return {item.suite_id: item for item in ABILITY_SUITE_CATALOG}


def _selected_ability_test(test_id: str) -> AbilityTestDefinition:
    normalized = str(test_id or "").strip()
    index = _ability_test_index()
    if normalized not in index:
        raise argparse.ArgumentTypeError(f"unsupported --ability-test {test_id!r}")
    return index[normalized]


def _selected_ability_suite(suite_id: str) -> AbilitySuiteDefinition:
    normalized = str(suite_id or "").strip()
    index = _ability_suite_index()
    if normalized not in index:
        raise argparse.ArgumentTypeError(f"unsupported --ability-suite {suite_id!r}")
    return index[normalized]


def _selected_ability_tests(*, ability_test_id: str, ability_suite_id: str) -> tuple[AbilitySuiteDefinition | None, list[AbilityTestDefinition]]:
    test_id = str(ability_test_id or "").strip()
    suite_id = str(ability_suite_id or "").strip()
    if test_id and suite_id:
        raise argparse.ArgumentTypeError("--ability-test cannot be combined with --ability-suite")
    if suite_id:
        suite = _selected_ability_suite(suite_id)
        test_index = _ability_test_index()
        return suite, [test_index[item] for item in suite.test_ids]
    if test_id:
        return None, [_selected_ability_test(test_id)]
    return None, []


def _manual_policy_helper_combo(
    *,
    provider: str,
    model: str,
'''
