from __future__ import annotations

from typing import Any, Dict, Sequence

from tools.psbc_audit_case_eval_model_helpers import _shorten


SECTION_DIVIDER = "-" * 72


def _summary(results: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    live_title_hits = sum(1 for item in results if item["live"]["policy_title_hit"])
    oracle_scores = [float(item["oracle"]["answer_evaluation"]["score"]) for item in results]
    live_scores = [float(item["live"]["answer_evaluation"]["score"]) for item in results]
    return {
        "case_count": len(results),
        "live_title_hit_cases": live_title_hits,
        "live_title_hit_rate": round(live_title_hits / len(results), 4) if results else 0.0,
        "live_answer_score_avg": round(sum(live_scores) / len(live_scores), 4) if live_scores else 0.0,
        "oracle_answer_score_avg": round(sum(oracle_scores) / len(oracle_scores), 4) if oracle_scores else 0.0,
    }


def _print_human(results: Sequence[Dict[str, Any]]) -> None:
    summary = _summary(results)
    print("PSBC 审计案例验证")
    print(SECTION_DIVIDER)
    print(f"案例数: {summary['case_count']}")
    print(f"live retrieval 命中审计制度标题: {summary['live_title_hit_cases']}/{summary['case_count']}")
    print(f"live answer 平均得分: {summary['live_answer_score_avg']:.2%}")
    print(f"oracle answer 平均得分: {summary['oracle_answer_score_avg']:.2%}")
    for item in results:
        print(SECTION_DIVIDER)
        print(f"[{item['case_id']}] {item['case_name']}")
        print(f"审计发现: {_shorten(item['finding'], 200)}")
        print(f"live query: {item['live']['query']}")
        print(f"live draft mode: {item['live'].get('draft_mode')}")
        if item["live"].get("draft_fallback_reason"):
            print(f"live draft fallback: {item['live']['draft_fallback_reason']}")
        print("live top titles:")
        for title in item["live"]["top_titles"]:
            print(f"- {title}")
        print(f"live title hit: {item['live']['policy_title_hit']}")
        print(f"live answer score: {item['live']['answer_evaluation']['score']:.2%}")
        print(item["live"]["answer"]["answer_text"])
        print(f"oracle answer score: {item['oracle']['answer_evaluation']['score']:.2%}")
        print(f"oracle draft mode: {item['oracle'].get('draft_mode')}")
        if item["oracle"].get("draft_fallback_reason"):
            print(f"oracle draft fallback: {item['oracle']['draft_fallback_reason']}")
        print(item["oracle"]["answer"]["answer_text"])
