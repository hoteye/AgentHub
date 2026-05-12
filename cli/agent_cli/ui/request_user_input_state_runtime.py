from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from cli.agent_cli.runtime_core.request_user_input_contract_runtime import (
    normalize_request_user_input_questions,
)


OTHER_OPTION_VALUE = "__other__"
PHASE_QUESTIONS = "questions"
PHASE_REVIEW = "review"


@dataclass(frozen=True, slots=True)
class RequestUserInputOption:
    label: str
    description: str
    value: str
    is_other: bool = False


@dataclass(frozen=True, slots=True)
class RequestUserInputQuestion:
    question_id: str
    header: str
    prompt: str
    options: tuple[RequestUserInputOption, ...]


@dataclass(frozen=True, slots=True)
class RequestUserInputSpec:
    questions: tuple[RequestUserInputQuestion, ...]


@dataclass(frozen=True, slots=True)
class RequestUserInputState:
    spec: RequestUserInputSpec
    phase: str = PHASE_QUESTIONS
    question_index: int = 0
    cursor_index: int = 0
    selected_option_by_question: dict[str, str] | None = None
    other_text_by_question: dict[str, str] | None = None
    notice: str = ""

    def selected_option(self, question_id: str) -> str:
        return str((self.selected_option_by_question or {}).get(question_id) or "")

    def other_text(self, question_id: str) -> str:
        return str((self.other_text_by_question or {}).get(question_id) or "")


def parse_request_user_input_spec(payload: dict[str, Any], *, max_questions: int = 3) -> RequestUserInputSpec:
    normalized_input_questions = normalize_request_user_input_questions(payload.get("questions"))
    normalized_questions: list[RequestUserInputQuestion] = []
    for raw_question in normalized_input_questions:
        question_id = str(raw_question.get("id") or "").strip()
        header = str(raw_question.get("header") or "").strip()
        prompt = str(raw_question.get("question") or "").strip()
        raw_options = list(raw_question.get("options") or [])
        options: list[RequestUserInputOption] = []
        for raw_option in raw_options:
            label = str(raw_option.get("label") or "").strip()
            description = str(raw_option.get("description") or "").strip()
            options.append(
                RequestUserInputOption(
                    label=label,
                    description=description,
                    value=label,
                    is_other=False,
                )
            )
        options.append(
            RequestUserInputOption(
                label="Other",
                description="Provide a custom answer.",
                value=OTHER_OPTION_VALUE,
                is_other=True,
            )
        )
        normalized_questions.append(
            RequestUserInputQuestion(
                question_id=question_id,
                header=header,
                prompt=prompt,
                options=tuple(options),
            )
        )
    if not normalized_questions:
        raise ValueError("request_user_input payload must include at least one question")
    if len(normalized_questions) > max_questions:
        raise ValueError(f"request_user_input payload supports at most {max_questions} questions in TUI mode")
    return RequestUserInputSpec(questions=tuple(normalized_questions))


def request_user_input_initial_state(spec: RequestUserInputSpec) -> RequestUserInputState:
    return RequestUserInputState(
        spec=spec,
        phase=PHASE_QUESTIONS,
        question_index=0,
        cursor_index=0,
        selected_option_by_question={},
        other_text_by_question={},
        notice="",
    )


def active_question(state: RequestUserInputState) -> RequestUserInputQuestion:
    index = max(0, min(state.question_index, len(state.spec.questions) - 1))
    return state.spec.questions[index]


def review_actions() -> tuple[str, ...]:
    return ("Submit answers", "Edit answers", "Cancel")


def max_cursor_index(state: RequestUserInputState) -> int:
    if state.phase == PHASE_REVIEW:
        return len(review_actions()) - 1
    return len(active_question(state).options) - 1


def with_cursor_delta(state: RequestUserInputState, delta: int) -> RequestUserInputState:
    upper = max_cursor_index(state)
    cursor = max(0, min(upper, state.cursor_index + int(delta)))
    return replace(state, cursor_index=cursor, notice="")


def with_notice(state: RequestUserInputState, notice: str) -> RequestUserInputState:
    return replace(state, notice=str(notice or ""))


def _copy_selected(state: RequestUserInputState) -> dict[str, str]:
    return dict(state.selected_option_by_question or {})


def _copy_other_text(state: RequestUserInputState) -> dict[str, str]:
    return dict(state.other_text_by_question or {})


def with_selected_current_option(state: RequestUserInputState) -> RequestUserInputState:
    question = active_question(state)
    option = question.options[state.cursor_index]
    selected = _copy_selected(state)
    selected[question.question_id] = option.value
    updated = replace(state, selected_option_by_question=selected, notice="")
    if option.is_other:
        return updated
    return with_move_next(updated)


def with_move_next(state: RequestUserInputState) -> RequestUserInputState:
    if state.phase == PHASE_REVIEW:
        return state
    next_index = state.question_index + 1
    if next_index >= len(state.spec.questions):
        return replace(state, phase=PHASE_REVIEW, cursor_index=0, notice="")
    next_question = state.spec.questions[next_index]
    selected_value = str((state.selected_option_by_question or {}).get(next_question.question_id) or "")
    cursor_index = option_index_for_value(next_question, selected_value)
    return replace(state, question_index=next_index, cursor_index=cursor_index, notice="")


def with_move_previous(state: RequestUserInputState) -> RequestUserInputState:
    if state.phase == PHASE_REVIEW:
        last_index = len(state.spec.questions) - 1
        question = state.spec.questions[last_index]
        selected_value = str((state.selected_option_by_question or {}).get(question.question_id) or "")
        return replace(
            state,
            phase=PHASE_QUESTIONS,
            question_index=last_index,
            cursor_index=option_index_for_value(question, selected_value),
            notice="",
        )
    prev_index = max(0, state.question_index - 1)
    question = state.spec.questions[prev_index]
    selected_value = str((state.selected_option_by_question or {}).get(question.question_id) or "")
    return replace(
        state,
        question_index=prev_index,
        cursor_index=option_index_for_value(question, selected_value),
        notice="",
    )


def with_other_text(state: RequestUserInputState, text: str) -> RequestUserInputState:
    question = active_question(state)
    other_text = _copy_other_text(state)
    other_text[question.question_id] = str(text or "")
    return replace(state, other_text_by_question=other_text, notice="")


def with_other_text_append(state: RequestUserInputState, char: str) -> RequestUserInputState:
    question = active_question(state)
    if selected_option_value_for_question(state, question.question_id) != OTHER_OPTION_VALUE:
        return state
    current = str((state.other_text_by_question or {}).get(question.question_id) or "")
    return with_other_text(state, current + str(char or ""))


def with_other_text_backspace(state: RequestUserInputState) -> RequestUserInputState:
    question = active_question(state)
    if selected_option_value_for_question(state, question.question_id) != OTHER_OPTION_VALUE:
        return state
    current = str((state.other_text_by_question or {}).get(question.question_id) or "")
    if not current:
        return state
    return with_other_text(state, current[:-1])


def question_answer_text(state: RequestUserInputState, question: RequestUserInputQuestion) -> str:
    selected = selected_option_value_for_question(state, question.question_id)
    if selected == OTHER_OPTION_VALUE:
        return str((state.other_text_by_question or {}).get(question.question_id) or "").strip()
    return selected


def selected_option_value_for_question(state: RequestUserInputState, question_id: str) -> str:
    return str((state.selected_option_by_question or {}).get(question_id) or "")


def question_is_answered(state: RequestUserInputState, question: RequestUserInputQuestion) -> bool:
    selected = selected_option_value_for_question(state, question.question_id)
    if not selected:
        return False
    if selected != OTHER_OPTION_VALUE:
        return True
    return bool(str((state.other_text_by_question or {}).get(question.question_id) or "").strip())


def all_questions_answered(state: RequestUserInputState) -> bool:
    return all(question_is_answered(state, question) for question in state.spec.questions)


def first_unanswered_question_index(state: RequestUserInputState) -> int | None:
    for index, question in enumerate(state.spec.questions):
        if not question_is_answered(state, question):
            return index
    return None


def with_return_to_unanswered(state: RequestUserInputState) -> RequestUserInputState:
    unresolved = first_unanswered_question_index(state)
    if unresolved is None:
        unresolved = 0
    question = state.spec.questions[unresolved]
    selected_value = selected_option_value_for_question(state, question.question_id)
    return replace(
        state,
        phase=PHASE_QUESTIONS,
        question_index=unresolved,
        cursor_index=option_index_for_value(question, selected_value),
        notice="",
    )


def option_index_for_value(question: RequestUserInputQuestion, value: str) -> int:
    target = str(value or "")
    if not target:
        return 0
    for index, option in enumerate(question.options):
        if option.value == target:
            return index
    return 0


def review_answer_rows(state: RequestUserInputState) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for question in state.spec.questions:
        answer = question_answer_text(state, question)
        rows.append((question.prompt, answer or "<unanswered>"))
    return rows


def response_payload(state: RequestUserInputState) -> dict[str, Any]:
    answers: dict[str, dict[str, list[str]]] = {}
    for question in state.spec.questions:
        answer_text = question_answer_text(state, question)
        if not answer_text:
            continue
        answers[question.question_id] = {"answers": [answer_text]}
    return {"answers": answers}
