from __future__ import annotations

from typing import Any

ReferenceModelCapability = tuple[str, str | None, tuple[str, ...], bool, str | None]

# Frozen snapshot from codex_ref `codex debug models` on 2026-04-25.
# Keep runtime deterministic; refresh explicitly when codex_ref updates.
# Slugs absent from the snapshot must follow codex_ref unknown-model fallback
# metadata rather than being guessed into the table.
_DEFAULT_REFERENCE_INPUT_MODALITIES: tuple[str, ...] = ("text", "image")
_CODEX_REFERENCE_MODEL_CAPABILITIES: tuple[ReferenceModelCapability, ...] = (
    ("gpt-5.5", "freeform", ("text", "image"), True, "low"),
    ("gpt-5.4", "freeform", ("text", "image"), True, "low"),
    ("gpt-5.4-mini", "freeform", ("text", "image"), True, "medium"),
    ("gpt-5.3-codex", "freeform", ("text", "image"), True, "low"),
    ("gpt-5.2-codex", "freeform", ("text", "image"), False, None),
    ("gpt-5.1-codex-max", "freeform", ("text", "image"), False, None),
    ("gpt-5.1-codex", "freeform", ("text", "image"), False, None),
    ("gpt-5.2", "freeform", ("text", "image"), False, None),
    ("gpt-5.1", "freeform", ("text", "image"), False, None),
    ("gpt-5-codex", "freeform", ("text", "image"), False, None),
    ("gpt-5", None, ("text", "image"), False, None),
    ("gpt-oss-120b", "freeform", ("text",), False, None),
    ("gpt-oss-20b", "freeform", ("text",), False, None),
    ("gpt-5.1-codex-mini", "freeform", ("text", "image"), False, None),
    ("gpt-5-codex-mini", "freeform", ("text", "image"), False, None),
)
_VALID_REFERENCE_VERBOSITY = {"low", "medium", "high"}


def _reference_model_slug_candidates(model_slug: str) -> tuple[str, ...]:
    normalized = str(model_slug or "").strip().lower()
    if not normalized:
        return ()
    candidates = [normalized]
    if "/" in normalized:
        suffix = normalized.rsplit("/", 1)[-1].strip()
        if suffix and suffix != normalized:
            candidates.append(suffix)
    return tuple(candidates)


def _matches_reference_model_prefix(candidate: str, prefix: str) -> bool:
    if candidate == prefix:
        return True
    for separator in ("-", "."):
        if candidate.startswith(prefix + separator):
            return True
    return False


def normalized_input_modalities(value: Any) -> tuple[str, ...] | None:
    raw_values: list[str]
    if isinstance(value, str):
        raw_values = [part.strip().lower() for part in value.replace(",", " ").split()]
    elif isinstance(value, list | tuple | set):
        raw_values = [str(part or "").strip().lower() for part in value]
    else:
        return None
    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw_values:
        if item not in {"text", "image"} or item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return tuple(normalized)


def normalized_string_list(value: Any) -> tuple[str, ...] | None:
    raw_values: list[str]
    if isinstance(value, str):
        raw_values = [part.strip().lower() for part in value.replace(",", " ").split()]
    elif isinstance(value, list | tuple | set):
        raw_values = [str(part or "").strip().lower() for part in value]
    else:
        return None
    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw_values:
        if not item or item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return tuple(normalized)


def reference_model_capability_for_model(model_slug: str) -> ReferenceModelCapability | None:
    for candidate in _reference_model_slug_candidates(model_slug):
        for capability in _CODEX_REFERENCE_MODEL_CAPABILITIES:
            if _matches_reference_model_prefix(candidate, capability[0]):
                return capability
    return None


def reference_input_modalities_for_model(model_slug: str) -> tuple[str, ...]:
    capability = reference_model_capability_for_model(model_slug)
    if capability is None:
        return _DEFAULT_REFERENCE_INPUT_MODALITIES
    return capability[2]


def normalized_reference_verbosity(value: str | None) -> str | None:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in _VALID_REFERENCE_VERBOSITY else None


def reference_default_text_verbosity_for_model(model_slug: str) -> str | None:
    capability = reference_model_capability_for_model(model_slug)
    if capability is None:
        return None
    return normalized_reference_verbosity(capability[4])
