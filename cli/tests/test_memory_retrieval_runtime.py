from __future__ import annotations

from cli.agent_cli import memory_retrieval_runtime as retrieval_runtime


def _memory(
    memory_id: str,
    *,
    memory_type: str = "project",
    title: str = "",
    summary: str = "",
    body: str = "",
    tags: list[str] | None = None,
    paths: list[str] | None = None,
    salience: float = 0.0,
    updated_at: str = "2026-04-09T00:00:00+00:00",
) -> dict:
    return {
        "memory_id": memory_id,
        "scope": "project",
        "memory_type": memory_type,
        "title": title,
        "summary": summary,
        "body": body,
        "tags": list(tags or []),
        "paths": list(paths or []),
        "status": "active",
        "salience": salience,
        "updated_at": updated_at,
    }


def test_recall_scoring_considers_tag_path_keyword_type_and_salience() -> None:
    memories = [
        _memory(
            "mem_strong",
            memory_type="project",
            title="Android build constraints",
            summary="mobile app uses gradle and minSdk 26",
            body="Keep minSdk aligned when building mobile client",
            tags=["android", "mobile"],
            paths=["mobile/app/build.gradle"],
            salience=2.0,
        ),
        _memory(
            "mem_weak",
            memory_type="reference",
            title="Database migration note",
            summary="postgres extension details",
            body="No mobile context here",
            tags=["database"],
            paths=["db/migrations"],
            salience=0.0,
        ),
    ]
    recalled = retrieval_runtime.recall_memories_for_turn(
        memories,
        user_text="请在 mobile/app 修 Android minSdk，gradle 构建报错",
        cwd="/repo/mobile/app",
        limit=2,
    )
    assert recalled
    assert recalled[0]["memory"]["memory_id"] == "mem_strong"
    reasons = " ".join(recalled[0]["reasons"])
    assert "tag_overlap" in reasons
    assert "path_overlap" in reasons
    assert "keyword_overlap" in reasons
    assert "type_weight" in reasons
    assert "salience" in reasons


def test_recall_respects_top_n_and_score_threshold() -> None:
    memories = [
        _memory("mem_1", title="alpha", summary="android mobile app", tags=["android"], salience=0.5),
        _memory("mem_2", title="beta", summary="android mobile app", tags=["android"], salience=0.4),
        _memory("mem_3", title="gamma", summary="android mobile app", tags=["android"], salience=0.3),
    ]
    recalled = retrieval_runtime.recall_memories_for_turn(
        memories,
        user_text="android mobile",
        limit=2,
        min_score=0.1,
    )
    assert len(recalled) == 2
    assert [item["memory"]["memory_id"] for item in recalled] == ["mem_1", "mem_2"]


def test_recall_excerpt_truncation_and_total_budget() -> None:
    long_body = "A" * 300
    memories = [
        _memory("mem_a", summary="alpha", body=long_body, tags=["alpha"], salience=1.0),
        _memory("mem_b", summary="alpha", body=long_body, tags=["alpha"], salience=0.8),
    ]
    recalled = retrieval_runtime.recall_memories_for_turn(
        memories,
        user_text="alpha",
        limit=5,
        max_excerpt_chars=120,
        max_total_chars=150,
    )
    assert recalled
    assert len(recalled[0]["excerpt"]) <= 120
    assert sum(len(item["excerpt"]) for item in recalled) <= 150


def test_recall_projection_contains_reference_context_contract() -> None:
    memories = [
        _memory(
            "mem_contract",
            memory_type="reference",
            title="Docs entry",
            summary="internal doc link",
            body="Use desk.pressget.cn docs for latest runbook",
            tags=["docs"],
            paths=["docs/runbook.md"],
            salience=0.5,
        )
    ]
    recalled = retrieval_runtime.recall_memories_for_turn(
        memories,
        user_text="找 docs runbook",
        limit=1,
    )
    assert len(recalled) == 1
    item = recalled[0]["reference_context_item"]
    assert item["item_type"] == "memory"
    assert item["source"] == "runtime:memory_store"
    assert item["label"] == "reference_memory"
    assert item["path"] == "memory://mem_contract"
    metadata = dict(item.get("metadata") or {})
    assert metadata.get("memory_id") == "mem_contract"
    assert metadata.get("memory_type") == "reference"
    assert isinstance(metadata.get("score"), float)
    assert isinstance(metadata.get("score_breakdown"), dict)
    assert isinstance(metadata.get("ranking_contract"), dict)
    assert isinstance(metadata.get("reasons"), list)
    assert isinstance(metadata.get("excerpt"), str)


def test_recall_ranking_weights_are_configurable() -> None:
    memory = _memory(
        "mem_android",
        memory_type="project",
        title="Android note",
        summary="android mobile app",
        tags=["android"],
        paths=["mobile/app/build.gradle"],
        salience=1.0,
    )
    baseline = retrieval_runtime.recall_memories_for_turn(
        [memory],
        user_text="android mobile app",
        limit=1,
    )
    tuned = retrieval_runtime.recall_memories_for_turn(
        [memory],
        user_text="android mobile app",
        limit=1,
        ranking_weights={"components": {"text": 8.0, "tag": 1.0, "path": 1.0, "type": 1.0, "salience": 0.5}},
    )
    assert baseline and tuned
    assert tuned[0]["score"] != baseline[0]["score"]
    assert tuned[0]["ranking_contract"]["components"]["text"] == 8.0


def test_recall_returns_score_breakdown_with_hits() -> None:
    recalled = retrieval_runtime.recall_memories_for_turn(
        [
            _memory(
                "mem_breakdown",
                summary="android gradle setup",
                tags=["android"],
                paths=["mobile/app/build.gradle"],
                salience=1.0,
            )
        ],
        user_text="android gradle mobile/app",
        limit=1,
    )
    assert len(recalled) == 1
    breakdown = recalled[0]["score_breakdown"]
    assert isinstance(breakdown, dict)
    assert breakdown.get("total_score", 0) > 0
    components = dict(breakdown.get("components") or {})
    assert "tag" in components
    assert "path" in components
    assert "text" in components
    assert isinstance(components["tag"].get("hits"), list)


def test_hybrid_disabled_or_backend_missing_keeps_rule_compatibility() -> None:
    memories = [
        _memory("mem_1", title="alpha", summary="android mobile app", tags=["android"], salience=0.5),
        _memory("mem_2", title="beta", summary="android mobile app", tags=["android"], salience=0.4),
    ]
    baseline = retrieval_runtime.recall_memories_for_turn(
        memories,
        user_text="android mobile",
        limit=2,
    )
    degraded = retrieval_runtime.recall_memories_for_turn(
        memories,
        user_text="android mobile",
        limit=2,
        enable_hybrid=True,
        ranking_weights={"semantic_weight": 3.0, "rule_weight": 1.0},
        semantic_backend=None,
    )
    assert [item["memory"]["memory_id"] for item in degraded] == [item["memory"]["memory_id"] for item in baseline]
    assert [item["score"] for item in degraded] == [item["score"] for item in baseline]
    for item in degraded:
        explainability = item["explainability"]
        assert isinstance(explainability.get("rule_score"), float)
        assert isinstance(explainability.get("semantic_score"), float)
        assert isinstance(explainability.get("fusion_score"), float)
        assert explainability["semantic_score"] == 0.0
        assert explainability["fusion_score"] == item["score"]


def test_hybrid_semantic_weight_can_change_ranking_order() -> None:
    memories = [
        _memory("mem_rule_high", summary="android mobile app gradle", tags=["android"], salience=1.0),
        _memory("mem_rule_low", summary="db cache", tags=["infra"], salience=0.0),
    ]

    def semantic_backend(*, user_text: str, query_terms: list[str], query_paths: list[str], candidates: list[dict]) -> dict:
        del user_text, query_terms, query_paths, candidates
        return {"mem_rule_high": 0.1, "mem_rule_low": 10.0}

    baseline = retrieval_runtime.recall_memories_for_turn(
        memories,
        user_text="android gradle mobile",
        limit=2,
        min_score=0.0,
    )
    hybrid = retrieval_runtime.recall_memories_for_turn(
        memories,
        user_text="android gradle mobile",
        limit=2,
        min_score=0.0,
        enable_hybrid=True,
        ranking_weights={"semantic_weight": 2.0, "rule_weight": 0.2},
        semantic_backend=semantic_backend,
    )
    assert baseline[0]["memory"]["memory_id"] == "mem_rule_high"
    assert hybrid[0]["memory"]["memory_id"] == "mem_rule_low"
