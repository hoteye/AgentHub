from __future__ import annotations

from cli.agent_cli import memory_retrieval_runtime as retrieval_runtime
from cli.agent_cli import memory_types


def test_normalized_ranking_weight_contract_merges_components_and_type_weights() -> None:
    contract = memory_types.normalized_ranking_weight_contract(
        {
            "components": {"tag": 9, "path": 1.5},
            "type_weights": {"project": 3.0, "unknown": 99},
        }
    )
    assert contract["components"]["tag"] == 9.0
    assert contract["components"]["path"] == 1.5
    assert "text" in contract["components"]
    assert contract["type_weights"]["project"] == 3.0
    assert "unknown" not in contract["type_weights"]


def test_recall_propagates_ranking_contract_and_breakdown_to_reference_metadata() -> None:
    memories = [
        {
            "memory_id": "mem_contract",
            "scope": "project",
            "memory_type": "project",
            "title": "Android contract",
            "summary": "android gradle",
            "body": "mobile app gradle constraints",
            "tags": ["android"],
            "paths": ["mobile/app/build.gradle"],
            "status": "active",
            "salience": 1.0,
            "updated_at": "2026-04-09T00:00:00+00:00",
        }
    ]
    recalled = retrieval_runtime.recall_memories_for_turn(
        memories,
        user_text="android gradle mobile/app",
        limit=1,
        ranking_weights={"components": {"tag": 5.0, "path": 6.0, "text": 2.0, "type": 1.0, "salience": 1.0}},
    )
    assert len(recalled) == 1
    assert "ranking_contract" in recalled[0]
    assert "score_breakdown" in recalled[0]
    assert "explainability" in recalled[0]
    metadata = dict(recalled[0]["reference_context_item"]["metadata"])
    assert metadata["ranking_contract"]["components"]["tag"] == 5.0
    assert "components" in metadata["score_breakdown"]
    assert metadata["score_breakdown"]["total_score"] == recalled[0]["score"]
    assert isinstance(metadata["explainability"], dict)
    assert isinstance(recalled[0]["explainability"]["rule_score"], float)
    assert isinstance(recalled[0]["explainability"]["semantic_score"], float)
    assert isinstance(recalled[0]["explainability"]["fusion_score"], float)
