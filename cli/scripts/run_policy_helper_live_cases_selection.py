from __future__ import annotations

from cli.scripts.run_policy_helper_live_cases_catalog import (
    CASES,
    POLICY_HELPER_COMBO_CATALOG,
    POLICY_HELPER_PROFILE_MATRIX,
    PolicyHelperCase,
    PolicyHelperCombo,
)


def _selected_cases(names: list[str] | None) -> list[PolicyHelperCase]:
    if not names:
        return list(CASES)
    requested = {str(name or "").strip() for name in list(names or []) if str(name or "").strip()}
    return [case for case in CASES if case.name in requested]


def _combo_catalog_index() -> dict[str, PolicyHelperCombo]:
    return {combo.combo_id: combo for combo in POLICY_HELPER_COMBO_CATALOG}


def _combo_token(text: str) -> str:
    normalized = "".join(ch if ch.isalnum() else "_" for ch in str(text or "").strip().lower())
    normalized = normalized.strip("_")
    return normalized or "default"


def _manual_helper_combo(
    *,
    provider: str,
    model: str,
    reasoning_effort: str,
    timeout: int,
) -> PolicyHelperCombo:
    provider_name = str(provider or "").strip()
    model_name = str(model or "").strip()
    effort = str(reasoning_effort or "").strip() or "low"
    timeout_value = max(0, int(timeout or 0))
    if provider_name or model_name:
        combo_id = (
            f"manual_{_combo_token(provider_name or 'provider')}_"
            f"{_combo_token(model_name or 'model')}_"
            f"{_combo_token(effort)}_t{timeout_value}"
        )
        source = "manual_override"
        description = "Single-run helper override from command line flags."
    else:
        combo_id = f"single_main_route_{_combo_token(effort)}_t{timeout_value}"
        source = "main_route"
        description = "Single-run helper route follows main model route."
    return PolicyHelperCombo(
        combo_id=combo_id,
        provider=provider_name,
        model=model_name,
        reasoning_effort=effort,
        timeout=timeout_value,
        source=source,
        description=description,
    )


def _selected_helper_combos(
    *,
    profile: str,
    helper_combos: list[str] | None,
    policy_helper_provider: str,
    policy_helper_model: str,
    policy_helper_reasoning_effort: str,
    policy_helper_timeout: int,
) -> list[PolicyHelperCombo]:
    normalized_profile = str(profile or "single").strip() or "single"
    requested_combo_ids = [
        str(item or "").strip() for item in list(helper_combos or []) if str(item or "").strip()
    ]
    if normalized_profile == "single":
        if requested_combo_ids:
            raise ValueError(
                "--helper-combo requires --profile policy_helper_regression or policy_helper_matrix"
            )
        return [
            _manual_helper_combo(
                provider=policy_helper_provider,
                model=policy_helper_model,
                reasoning_effort=policy_helper_reasoning_effort,
                timeout=policy_helper_timeout,
            )
        ]

    if str(policy_helper_provider or "").strip() or str(policy_helper_model or "").strip():
        raise ValueError(
            "--policy-helper-provider/--policy-helper-model cannot be combined with profile matrix runs; "
            "use --helper-combo to pick profile combos"
        )

    combo_index = _combo_catalog_index()
    profile_combo_ids = list(POLICY_HELPER_PROFILE_MATRIX.get(normalized_profile) or ())
    if not profile_combo_ids:
        raise ValueError(f"unsupported --profile {normalized_profile!r}")
    if requested_combo_ids:
        unknown_ids = [combo_id for combo_id in requested_combo_ids if combo_id not in combo_index]
        if unknown_ids:
            joined = ", ".join(sorted(set(unknown_ids)))
            raise ValueError(f"unknown --helper-combo ids: {joined}")
        filtered_ids = [
            combo_id for combo_id in profile_combo_ids if combo_id in set(requested_combo_ids)
        ]
        if not filtered_ids:
            raise ValueError(
                f"requested --helper-combo not in profile {normalized_profile}: "
                f"{', '.join(requested_combo_ids)}"
            )
        profile_combo_ids = filtered_ids
    return [combo_index[combo_id] for combo_id in profile_combo_ids]
