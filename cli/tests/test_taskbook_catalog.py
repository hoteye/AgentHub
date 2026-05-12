from __future__ import annotations

from pathlib import Path
import sqlite3
import hashlib

from cli.agent_cli.orchestration.taskbook_catalog import TaskbookCatalog
from cli.agent_cli.orchestration.taskbook_models import (
    CardAcceptance,
    CardResult,
    ComplexTaskRun,
    OrchestrationEvent,
    TaskCard,
    TaskCardState,
    TaskbookSnapshot,
)
from cli.agent_cli.orchestration.taskbook_state import (
    CardAcceptanceDecision,
    CardResultStatus,
    ComplexTaskRunStatus,
    TaskCardKind,
    TaskCardStatus,
    TaskCardDependencyStatus,
)
from cli.agent_cli.orchestration.taskbook_storage import TaskbookStorage


def _storage(tmp_path: Path) -> TaskbookStorage:
    return TaskbookStorage(base_dir=tmp_path / "orchestration")


def _catalog(tmp_path: Path) -> TaskbookCatalog:
    return TaskbookCatalog(db_path=tmp_path / "orchestration" / "orchestration_catalog.sqlite3")


def test_taskbook_catalog_schema_init(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    catalog.ensure_ready()

    with sqlite3.connect(catalog.db_path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}

    assert "orchestration_runs" in tables
    assert "orchestration_cards" in tables
    assert "orchestration_results" in tables
    assert "orchestration_acceptance" in tables
    assert "orchestration_events" in tables


def test_taskbook_catalog_indexes_run_card_result_and_path_queries(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    catalog = _catalog(tmp_path)

    run = ComplexTaskRun(
        run_id="ctrun_123",
        thread_id="thread_abc",
        objective="build orchestrator",
        status=ComplexTaskRunStatus.RUNNING,
        taskbook_version_current=2,
        updated_at="2026-04-05T09:30:00Z",
    )
    taskbook = TaskbookSnapshot(
        taskbook_id="tb_1",
        run_id=run.run_id,
        version=2,
        goal="ship orchestration",
        success_definition=["taskbook persists"],
        critical_path=["CARD-001"],
    )
    card = TaskCard(
        card_id="CARD-001",
        taskbook_version=2,
        title="taskbook storage",
        goal="persist files",
        kind=TaskCardKind.WORKSPACE_MUTATING,
        owned_files=["cli/agent_cli/orchestration/taskbook_models.py"],
    )
    state = TaskCardState(
        card_id=card.card_id,
        status=TaskCardStatus.RUNNING,
        attempt=1,
        dependency_status=TaskCardDependencyStatus.SATISFIED,
        updated_at="2026-04-05T09:31:00Z",
    )
    result = CardResult(
        result_id="result_0001",
        run_id=run.run_id,
        card_id=card.card_id,
        status=CardResultStatus.COMPLETED,
        summary="done",
        modified_files=["cli/agent_cli/orchestration/taskbook_models.py"],
        reported_at="2026-04-05T09:32:00Z",
    )
    acceptance = CardAcceptance(
        acceptance_id="accept_0001",
        run_id=run.run_id,
        card_id=card.card_id,
        result_id=result.result_id,
        decision=CardAcceptanceDecision.ACCEPT,
        reviewed_at="2026-04-05T09:33:00Z",
    )
    event = OrchestrationEvent(
        seq=1,
        run_id=run.run_id,
        card_id=card.card_id,
        event_type="card_result_reported",
        actor_type="background_task",
        created_at="2026-04-05T09:32:00Z",
    )

    storage.write_run(run)
    storage.append_taskbook(taskbook)
    storage.write_card_spec(run.run_id, card)
    storage.write_card_state(run.run_id, state)
    storage.append_card_result(result)
    storage.append_card_acceptance(acceptance)
    storage.append_event(event)
    projection_path = storage.run_dir(run.run_id) / "projections" / "taskbook.md"
    projection_path.parent.mkdir(parents=True, exist_ok=True)
    projection_path.write_text("# Taskbook\n", encoding="utf-8")
    card_projection_path = storage.run_dir(run.run_id) / "projections" / "cards" / f"{card.card_id}.md"
    card_projection_path.parent.mkdir(parents=True, exist_ok=True)
    card_projection_path.write_text("## CARD-001\n", encoding="utf-8")

    counts = catalog.rebuild_run_index(storage, run.run_id)

    assert counts == {
        "runs": 1,
        "taskbooks": 1,
        "cards": 1,
        "results": 1,
        "acceptance": 1,
        "events": 1,
    }
    runs = catalog.list_runs(thread_id="thread_abc", status="running")
    cards = catalog.list_cards(run.run_id, status="running")
    results = catalog.list_results(run.run_id, card_id=card.card_id, status="completed")
    owned = catalog.find_cards_by_owned_file("taskbook_models.py")
    documents = catalog.list_documents(run.run_id)

    assert [item["run_id"] for item in runs] == [run.run_id]
    assert [item["card_id"] for item in cards] == [card.card_id]
    assert [item["result_id"] for item in results] == [result.result_id]
    assert [item["card_id"] for item in owned] == [card.card_id]
    assert len(documents) == 2
    docs_by_type = {item["doc_type"]: item for item in documents}
    assert "projection_taskbook" in docs_by_type
    assert "projection_card" in docs_by_type

    taskbook_doc = docs_by_type["projection_taskbook"]
    card_doc = docs_by_type["projection_card"]
    assert taskbook_doc["title"] == "taskbook"
    assert taskbook_doc["version"] == 2
    assert taskbook_doc["path"].endswith("/projections/taskbook.md")
    assert taskbook_doc["checksum"] == hashlib.sha256(projection_path.read_bytes()).hexdigest()
    assert card_doc["card_id"] == card.card_id
    assert card_doc["title"] == card.title
    assert card_doc["version"] == 2
    assert card_doc["path"].endswith(f"/projections/cards/{card.card_id}.md")
    assert card_doc["checksum"] == hashlib.sha256(card_projection_path.read_bytes()).hexdigest()


def test_taskbook_catalog_upsert_methods_work_without_rebuild(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    run = ComplexTaskRun(run_id="ctrun_direct", status=ComplexTaskRunStatus.READY)
    taskbook = TaskbookSnapshot(taskbook_id="tb_direct", run_id=run.run_id, version=1)
    card = TaskCard(card_id="CARD-001", taskbook_version=1, title="schema")
    state = TaskCardState(card_id=card.card_id, status=TaskCardStatus.READY)

    catalog.upsert_run(run, path="run.json")
    catalog.upsert_taskbook(taskbook, path="taskbooks/taskbook_v001.json")
    catalog.upsert_card(run.run_id, card, state=state, spec_path="cards/CARD-001/spec.json", state_path="cards/CARD-001/state.json")

    run_rows = catalog.list_runs(status="ready")
    card_row = catalog.get_card(run.run_id, card.card_id)

    assert [item["run_id"] for item in run_rows] == [run.run_id]
    assert card_row is not None
    assert card_row["spec_path"] == "cards/CARD-001/spec.json"


def test_taskbook_catalog_query_filters_and_ordering_contract(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)

    run_old = ComplexTaskRun(
        run_id="ctrun_query_old",
        thread_id="thread_query",
        objective="orchestration older run",
        status=ComplexTaskRunStatus.RUNNING,
        updated_at="2026-04-06T09:00:00Z",
    )
    run_new = ComplexTaskRun(
        run_id="ctrun_query_new",
        thread_id="thread_query",
        objective="orchestration latest run",
        status=ComplexTaskRunStatus.RUNNING,
        updated_at="2026-04-06T10:00:00Z",
    )
    run_exact = ComplexTaskRun(
        run_id="ctrun_query_exact",
        thread_id="thread_query",
        objective="latest",
        status=ComplexTaskRunStatus.RUNNING,
        updated_at="2026-04-06T08:00:00Z",
    )
    catalog.upsert_run(run_old, path="runs/old.json")
    catalog.upsert_run(run_new, path="runs/new.json")
    catalog.upsert_run(run_exact, path="runs/exact.json")

    latest_only = catalog.list_runs(
        thread_id="thread_query",
        status="running",
        objective_query="latest",
        limit=1,
    )
    assert [item["run_id"] for item in latest_only] == [run_exact.run_id]
    assert latest_only[0]["objective_match_rank"] == 0
    assert latest_only[0]["objective_match_kind"] == "exact"
    assert latest_only[0]["ranking_query_text"] == "latest"
    assert latest_only[0]["ranking_query_scope"] == "objective"
    assert latest_only[0]["ranking_result_index"] == 1
    assert latest_only[0]["ranking_result_total"] == 1
    assert latest_only[0]["ranking_effective_limit"] == 1
    assert latest_only[0]["ranking_primary_match_kind"] == "exact"
    assert latest_only[0]["ranking_primary_match_kind_count"] == 1
    assert latest_only[0]["ranking_match_kind_counts"] == "exact:1"
    assert latest_only[0]["ranking_kind_position"] == 1
    assert latest_only[0]["ranking_kind_result_index"] == 1
    assert latest_only[0]["ranking_query_token_count"] == 1
    assert latest_only[0]["ranking_primary_match_rank"] == 0
    assert latest_only[0]["ranking_weight_profile"] == "v1"
    assert latest_only[0]["ranking_quality_score"] == 120.0
    assert latest_only[0]["ranking_analytics_version"] == "v1"
    assert latest_only[0]["ranking_analytics_rank_bucket"] == "high"
    assert "scope=objective;" in latest_only[0]["ranking_analytics_summary"]
    assert "version=v1;" in latest_only[0]["ranking_analytics_summary"]
    assert "rank_bucket=high;" in latest_only[0]["ranking_analytics_summary"]
    assert "weight_profile=v1" in latest_only[0]["ranking_analytics_summary"]
    assert "scope=objective;" in latest_only[0]["ranking_scope_summary"]
    assert "query=present;" in latest_only[0]["ranking_scope_summary"]

    card_exact = TaskCard(
        card_id="CARD-001",
        taskbook_version=1,
        title="exact path card",
        goal="exact file path lookup",
        kind=TaskCardKind.WORKSPACE_MUTATING,
        owned_files=["cli/agent_cli/orchestration/taskbook_models.py"],
    )
    state_exact = TaskCardState(
        card_id=card_exact.card_id,
        status=TaskCardStatus.READY,
        dependency_status=TaskCardDependencyStatus.SATISFIED,
        updated_at="2026-04-06T10:01:00Z",
    )
    card_suffix = TaskCard(
        card_id="CARD-002",
        taskbook_version=1,
        title="suffix path card",
        goal="suffix file path lookup",
        kind=TaskCardKind.READ_ONLY,
        owned_files=["docs/taskbook_models.py"],
    )
    state_suffix = TaskCardState(
        card_id=card_suffix.card_id,
        status=TaskCardStatus.BLOCKED,
        dependency_status=TaskCardDependencyStatus.SATISFIED,
        updated_at="2026-04-06T10:02:00Z",
    )
    catalog.upsert_card(run_new.run_id, card_exact, state=state_exact)
    catalog.upsert_card(run_new.run_id, card_suffix, state=state_suffix)

    exact_hits = catalog.find_cards_by_owned_file(
        "cli/agent_cli/orchestration/taskbook_models.py",
        run_id=run_new.run_id,
    )
    assert [item["card_id"] for item in exact_hits] == ["CARD-001"]
    assert exact_hits[0]["file_match_rank"] == 0
    assert exact_hits[0]["file_match_kind"] == "exact"
    assert exact_hits[0]["matched_file_path"] == "cli/agent_cli/orchestration/taskbook_models.py"
    assert exact_hits[0]["ranking_query_text"] == "cli/agent_cli/orchestration/taskbook_models.py"
    assert exact_hits[0]["ranking_query_scope"] == "owned_file"
    assert exact_hits[0]["ranking_result_index"] == 1
    assert exact_hits[0]["ranking_result_total"] == 1
    assert exact_hits[0]["ranking_effective_limit"] == 200
    assert exact_hits[0]["ranking_match_kind_counts"] == "exact:1"
    assert exact_hits[0]["ranking_kind_position"] == 1
    assert exact_hits[0]["ranking_kind_result_index"] == 1
    assert exact_hits[0]["ranking_query_token_count"] == 1
    assert exact_hits[0]["ranking_primary_match_rank"] == 0
    assert exact_hits[0]["ranking_weight_profile"] == "v1"
    assert exact_hits[0]["ranking_quality_score"] == 100.0
    assert "scope=owned_file;" in exact_hits[0]["ranking_scope_summary"]

    ready_hits = catalog.find_cards_by_owned_file(
        "taskbook_models.py",
        run_id=run_new.run_id,
        status="ready",
    )
    assert [item["card_id"] for item in ready_hits] == ["CARD-001"]
    assert ready_hits[0]["file_match_rank"] == 1
    assert ready_hits[0]["file_match_kind"] == "suffix"
    assert ready_hits[0]["ranking_primary_match_kind"] == "suffix"
    assert ready_hits[0]["ranking_primary_match_kind_count"] == 1
    assert ready_hits[0]["ranking_primary_match_rank"] == 1

    limited_hits = catalog.find_cards_by_owned_file(
        "taskbook_models.py",
        run_id=run_new.run_id,
        limit=1,
    )
    assert [item["card_id"] for item in limited_hits] == ["CARD-002"]
    assert limited_hits[0]["file_match_rank"] == 1
    assert limited_hits[0]["file_match_kind"] == "suffix"
    assert limited_hits[0]["ranking_result_total"] == 1
    assert limited_hits[0]["ranking_effective_limit"] == 1
    assert limited_hits[0]["ranking_match_kind_counts"] == "suffix:1"
    assert limited_hits[0]["ranking_scope_summary"].startswith("scope=owned_file;")

    catalog.upsert_document(
        document_id=f"{run_new.run_id}:projection:taskbook",
        run_id=run_new.run_id,
        doc_type="projection_taskbook",
        title="taskbook",
        path="projections/taskbook.md",
        version=1,
        updated_at="2026-04-06T10:03:00Z",
    )
    catalog.upsert_document(
        document_id=f"{run_new.run_id}:projection:CARD-001",
        run_id=run_new.run_id,
        card_id="CARD-001",
        doc_type="projection_card",
        title="runtime card detail",
        path="projections/cards/CARD-001.md",
        version=1,
        updated_at="2026-04-06T10:04:00Z",
    )
    catalog.upsert_document(
        document_id=f"{run_new.run_id}:projection:CARD-002",
        run_id=run_new.run_id,
        card_id="CARD-002",
        doc_type="projection_card",
        title="notes card detail",
        path="projections/cards/CARD-002.md",
        version=1,
        updated_at="2026-04-06T10:05:00Z",
    )

    latest_doc = catalog.list_documents(run_new.run_id, limit=1)
    assert [item["document_id"] for item in latest_doc] == [f"{run_new.run_id}:projection:CARD-002"]

    runtime_docs = catalog.list_documents(
        run_new.run_id,
        card_id="CARD-001",
        doc_type="projection_card",
        query="runtime",
    )
    assert [item["document_id"] for item in runtime_docs] == [f"{run_new.run_id}:projection:CARD-001"]
    assert runtime_docs[0]["query_match_rank"] == 1
    assert runtime_docs[0]["query_match_kind"] == "prefix"
    assert runtime_docs[0]["ranking_query_text"] == "runtime"
    assert runtime_docs[0]["ranking_query_scope"] == "document_query"
    assert runtime_docs[0]["ranking_result_index"] == 1
    assert runtime_docs[0]["ranking_result_total"] == 1
    assert runtime_docs[0]["ranking_effective_limit"] == 200
    assert runtime_docs[0]["ranking_primary_match_kind"] == "prefix"
    assert runtime_docs[0]["ranking_primary_match_kind_count"] == 1
    assert runtime_docs[0]["ranking_match_kind_counts"] == "prefix:1"
    assert runtime_docs[0]["ranking_kind_position"] == 1
    assert runtime_docs[0]["ranking_kind_result_index"] == 1
    assert runtime_docs[0]["ranking_query_token_count"] == 1
    assert runtime_docs[0]["ranking_primary_match_rank"] == 1
    assert runtime_docs[0]["ranking_weight_profile"] == "v1"
    assert runtime_docs[0]["ranking_quality_score"] == 110.0
    assert "scope=document_query;" in runtime_docs[0]["ranking_scope_summary"]

    exact_docs = catalog.list_documents(
        run_new.run_id,
        card_id="CARD-001",
        doc_type="projection_card",
        query="runtime card detail",
    )
    assert [item["document_id"] for item in exact_docs] == [f"{run_new.run_id}:projection:CARD-001"]
    assert exact_docs[0]["query_match_rank"] == 0
    assert exact_docs[0]["query_match_kind"] == "exact"
    assert exact_docs[0]["ranking_primary_match_kind"] == "exact"
    assert exact_docs[0]["ranking_primary_match_rank"] == 0


def test_taskbook_catalog_run_query_supports_token_contains_recall(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    run = ComplexTaskRun(
        run_id="ctrun_tokenized",
        thread_id="thread_query",
        objective="ship orchestration pipeline",
        status=ComplexTaskRunStatus.RUNNING,
        updated_at="2026-04-07T10:00:00Z",
    )
    catalog.upsert_run(run, path="runs/tokenized.json")

    hits = catalog.list_runs(thread_id="thread_query", status="running", objective_query="ship pipeline")
    assert [item["run_id"] for item in hits] == [run.run_id]
    assert hits[0]["objective_match_kind"] == "token_all"
    assert hits[0]["objective_match_rank"] == 3
    assert hits[0]["ranking_primary_match_kind"] == "token_all"
    assert hits[0]["ranking_query_token_count"] == 2
    assert hits[0]["ranking_token_match_count"] == 2
    assert hits[0]["ranking_token_coverage_ratio"] == 1.0
    assert hits[0]["ranking_weight_profile"] == "v1"
    assert hits[0]["ranking_quality_score"] == 80.0
    assert hits[0]["ranking_analytics_version"] == "v1"
    assert hits[0]["ranking_analytics_rank_bucket"] == "medium"
    assert "rank_bucket=medium;" in hits[0]["ranking_analytics_summary"]
    assert "version=v1;" in hits[0]["ranking_analytics_summary"]
    assert "weight_profile=v1" in hits[0]["ranking_analytics_summary"]
    assert "token_matches=2;" in hits[0]["ranking_analytics_summary"]
    assert "tokens=2;" in hits[0]["ranking_scope_summary"]


def test_taskbook_catalog_document_query_supports_token_contains_recall(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    run_id = "ctrun_doc_tokens"
    catalog.upsert_document(
        document_id=f"{run_id}:projection:CARD-100",
        run_id=run_id,
        card_id="CARD-100",
        doc_type="projection_card",
        title="runtime detail card",
        path="projections/cards/CARD-100-runtime.md",
        version=1,
        updated_at="2026-04-07T10:10:00Z",
    )

    hits = catalog.list_documents(run_id, doc_type="projection_card", query="runtime CARD-100")
    assert [item["document_id"] for item in hits] == [f"{run_id}:projection:CARD-100"]
    assert hits[0]["query_match_kind"] == "token_all"
    assert hits[0]["query_match_rank"] == 3
    assert hits[0]["ranking_primary_match_kind"] == "token_all"
    assert hits[0]["ranking_query_token_count"] == 2
    assert hits[0]["ranking_token_match_count"] == 2
    assert hits[0]["ranking_token_coverage_ratio"] == 1.0
    assert hits[0]["ranking_weight_profile"] == "v1"
    assert hits[0]["ranking_quality_score"] == 80.0


def test_taskbook_catalog_run_query_supports_current_phase_multi_field_recall(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    run = ComplexTaskRun(
        run_id="ctrun_phase_query",
        thread_id="thread_query",
        objective="ship orchestration pipeline",
        status=ComplexTaskRunStatus.RUNNING,
        current_phase="review_pending",
        updated_at="2026-04-07T10:20:00Z",
    )
    catalog.upsert_run(run, path="runs/phase_query.json")

    hits = catalog.list_runs(thread_id="thread_query", status="running", objective_query="review pending")
    assert [item["run_id"] for item in hits] == [run.run_id]
    assert hits[0]["objective_match_kind"] == "token_all"
    assert hits[0]["objective_match_rank"] == 3
    assert hits[0]["ranking_primary_match_kind"] == "token_all"
    assert hits[0]["ranking_token_match_count"] == 2
    assert hits[0]["ranking_token_coverage_ratio"] == 1.0
    assert hits[0]["ranking_weight_profile"] == "v1"
    assert hits[0]["ranking_quality_score"] == 80.0
