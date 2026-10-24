"""SDE3: prepared date inputs -> rubric judgments -> Python scores -> explanation."""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable

from .roles import RoleProfile
from .validation import apply_calculated_fields, coerce_fixed_row, validate_output_row


def _score_fields(role: RoleProfile) -> dict[str, str]:
    fields: dict[str, str] = {}
    for prefix, rule in zip(("agent", "framework", "architecture", "breadth"), role.component_scoring.values()):
        fields.update(zip((f"{prefix}_evidence", f"{prefix}_recency", f"{prefix}_duration"), rule.columns))
    for column in role.model_grading_columns:
        if column not in role.component_score_maxima and column != "Score Rationale":
            fields[column] = column
    return fields


def _stage_schema(properties: dict[str, Any], numbers: list[int]) -> dict[str, Any]:
    return {
        "type": "object", "additionalProperties": False, "required": ["evaluations"],
        "properties": {"evaluations": {
            "type": "array", "minItems": len(numbers), "maxItems": len(numbers),
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["candidate_number", "grading"],
                "properties": {
                    "candidate_number": {"type": "integer", "enum": numbers},
                    "grading": {
                        "type": "object", "additionalProperties": False,
                        "required": list(properties), "properties": properties,
                    },
                },
            },
        }},
    }


def _validated_scores(model_grading: Any, candidate: dict, payload: dict, role: RoleProfile) -> dict:
    if not isinstance(model_grading, dict):
        raise ValueError("The scoring stage did not return a grading object.")
    grading = {}
    for internal, column in _score_fields(role).items():
        # Accept the existing long names for saved fixtures/providers during the
        # transition; outgoing requests use only the shorter schema keys.
        if internal in model_grading and column in model_grading and model_grading[internal] != model_grading[column]:
            raise ValueError(f"Conflicting score keys for {column}.")
        value = model_grading.get(internal, model_grading.get(column))
        if column in role.component_score_maxima:
            if type(value) is not int or not 0 <= value <= role.component_score_maxima[column]:
                raise ValueError(f"{internal} must be an explicit integer from 0 to {role.component_score_maxima[column]}; got {value!r}.")
        elif not isinstance(value, str):
            raise ValueError(f"Missing or invalid text field: {column}.")
        grading[column] = value
    if any(exp["calculated_dates"]["date_quality_warning"] for exp in payload.get("experiences", [])):
        grading["Date-Quality Warning"] = "Yes"
    row = apply_calculated_fields({
        "Candidate": candidate.get("candidate_name", ""),
        "Profile URL": candidate.get("linkedin_url", ""),
        "Rank Number": "", "Score Rationale": "", **grading,
    }, candidate, role)
    # Numeric fields were checked above, before any coercion. Keep existing
    # harmless prose normalization (for example, at most three evidence items).
    row = coerce_fixed_row(row, role)
    errors = validate_output_row(row, role)
    if errors:
        raise ValueError("; ".join(errors))
    return row


def _fallback_explanation(grading: dict, role: RoleProfile) -> str:
    recency = ("undated or more than five years ago", "37–60 months ago", "13–36 months ago", "current or within 12 months")
    duration = ("under one year or not reliably established", "one to under two years", "two to under three years", "at least three years")
    evidence = ("not stated in permitted sources", "a limited keyword or role-attached skill", "an explicit headline or About mention", "role-specific or project evidence", "explicit delivery or actual-use experience")
    parts = ["The provider explanation was unavailable. This summary uses the validated scoring decisions."]
    for category, rule in role.component_scoring.items():
        name = category.rsplit(" Score (/", 1)[0]
        parts.append(
            f"{name}: evidence was assessed as {evidence[grading[rule.evidence_column]]}; "
            f"qualifying use was assessed as {recency[grading[rule.impact_column]]}; "
            f"supported duration was assessed as {duration[grading[rule.duration_column]]}."
        )
    parts.append(f"The weighted total is {grading[role.total_column]:g}/{role.total_max:g}.")
    if grading.get("Missing or Unclear Information"):
        parts.append(f"Unverified information: {grading['Missing or Unclear Information']}")
    return " ".join(parts)


def evaluate_sde3_candidates(
    *, candidates: list[dict], payloads: list[dict], role: RoleProfile,
    rubric_text: str, provider: Any, request: Callable,
):
    # Import lazily: the provider adapter dispatches here after creating a client.
    from .openai_scoring import (
        BatchEvaluationResults, _empty_usage, _field, _fixed_prompt,
        _grading_properties, _parse_response_json, _response_content, _response_usage,
    )

    usage = _empty_usage()
    diagnostics: list[dict] = []
    columns = _score_fields(role)
    source_properties = _grading_properties(role, list(columns.values()))
    score_properties = {key: source_properties[column] for key, column in columns.items()}
    numbers = list(range(1, len(candidates) + 1))
    valid: dict[int, tuple[dict, dict]] = {}
    failures: dict[int, str] = {}
    request_failures: set[int] = set()
    # The rubric's explanations are a separate task, never part of the score
    # response. Temporal point assignment still needs capability-specific
    # judgment: total employment duration alone does not establish actual use.
    score_role = replace(role, instructions=[
        "Assign all 12 component decisions using the supplied rubric. Return integer 0 when qualifying evidence is absent; never omit a score.",
        "calculated_dates contains application-calculated role duration and recency inputs, including uncertainty. Use those inputs; do not invent missing months.",
        "Role duration is an upper bound, not automatic capability duration. Use full tenure only for explicit ongoing use; one-time achievements need an explicit supported period. Count overlapping qualifying months once and apply the rubric's source caps.",
        "Judge recency separately per capability using qualifying dated experiences; an unrelated current role does not refresh old evidence.",
        "Return no weighted scores, total, rank, or Score Rationale. Python calculates scores and a later stage writes the explanation.",
        "Return at most three strongest evidence points separated by ' | '. Warnings never change scores; describe missing evidence as unverified.",
    ])
    score_prompt = _fixed_prompt(score_role, rubric_text, preserve_candidate_numbers=True) + (
        "\n\nCURRENT STAGE: SCORING ONLY. The supplied schema defines this stage's output; "
        "defer the rubric's Score Rationale and final-output prose requirements until the explanation stage."
    )

    def call_stage(prompt: str, payload: dict, schema: dict, name: str) -> dict:
        info = {
            "stage": name,
            "expected_candidate_numbers": [item["candidate_number"] for item in payload["candidates"]],
        }
        diagnostics.append(info)
        usage["api_calls"] += 1
        try:
            response = request(prompt, payload, schema, name)
        except Exception as exc:
            info.update(error=str(exc), request_failed=True, request_id=_field(exc, "request_id"), status_code=_field(exc, "status_code"))
            raise
        receipt = _response_usage(response)
        for key in usage:
            if key != "api_calls":
                usage[key] += receipt.get(key, 0)
        choices = _field(response, "choices") or []
        info.update({
            "response_id": _field(response, "id"),
            "request_id": _field(response, "_request_id"), "model": _field(response, "model"),
            "status": _field(response, "status"),
            "incomplete_reason": _field(_field(response, "incomplete_details"), "reason"),
            "finish_reason": _field(choices[0], "finish_reason") if choices else None,
            "usage": receipt,
        })
        # Preserve text even if completion status rejects it before parsing.
        content = _field(response, "output_text") if provider.transport == "responses" else _field(_field(choices[0], "message"), "content") if choices else ""
        try:
            content = _response_content(response, provider)
            info["response_content"] = content
            parsed = _parse_response_json(content, allow_surrounding_text=provider.key == "deepseek")
            info["format_repaired"] = bool(parsed.pop("_response_format_repaired", False))
            return parsed
        except (ValueError, TypeError, KeyError, IndexError, AttributeError) as exc:
            info["error"] = str(exc)
            info["unparsed_content"] = content or ""
            raise

    def score_group(group: list[int]) -> None:
        try:
            parsed = call_stage(score_prompt, {
                "candidates": [{"candidate_number": n, "candidate": payloads[n - 1]} for n in group],
            }, _stage_schema(score_properties, group), "sde3_component_scores")
            items = parsed.get("evaluations")
            if not isinstance(items, list):
                raise ValueError("The scoring response is missing its evaluations array.")
            by_number: dict[int, list] = {}
            for item in items:
                number = item.get("candidate_number") if isinstance(item, dict) else None
                if type(number) is not int or number not in group:
                    diagnostics[-1].setdefault("unexpected_candidate_numbers", []).append(number)
                    continue
                by_number.setdefault(number, []).append(item)
            diagnostics[-1]["received_candidate_numbers"] = [item.get("candidate_number") for item in items if isinstance(item, dict)]
            for n in group:
                try:
                    matches = by_number.get(n, [])
                    if len(matches) != 1:
                        raise ValueError(f"Expected exactly one scoring record for candidate {n}; received {len(matches)}.")
                    raw = matches[0]
                    grading = _validated_scores(raw.get("grading"), candidates[n - 1], payloads[n - 1], role)
                    valid[n] = (grading, {**raw, "calculated_inputs": payloads[n - 1].get("experiences", [])})
                    failures.pop(n, None)
                except (ValueError, TypeError, KeyError) as exc:
                    failures[n] = str(exc)
                    diagnostics[-1].setdefault("invalid_candidates", {})[str(n)] = str(exc)
        except Exception as exc:
            for n in group:
                failures[n] = str(exc)
                if diagnostics[-1].get("request_failed"):
                    request_failures.add(n)

    score_group(numbers)
    # One targeted recovery request per invalid/missing candidate. Successful
    # candidates are never rescored because another member of the batch failed.
    for n in numbers:
        if n not in valid and n not in request_failures:
            score_group([n])

    if valid:
        explanation_properties = {"Score Rationale": {"type": "string"}}
        valid_numbers = sorted(valid)
        explain_prompt = (
            "Write an evidence-based explanation of an already completed SDE3 evaluation. "
            "The validated component points, weighted capability scores, and final score are fixed inputs: "
            "do not rescore, alter, or return numeric fields. Explain the relevant work and sources, "
            "capability-specific recency, supported duration, and missing evidence for all four capabilities, "
            "then conclude why the overall score follows. Follow the supplied rubric's prose and length guidance. "
            "Use only the supplied permitted profile evidence, calculated date inputs, rubric, and fixed scores. "
            "Never claim that missing evidence proves a lack of ability. Return exactly the supplied candidate numbers.\n\nRUBRIC\n"
            + rubric_text
            + "\n\nCURRENT STAGE: EXPLANATION ONLY. Return only Score Rationale inside grading, per the supplied schema."
        )
        try:
            parsed = call_stage(explain_prompt, {"candidates": [
                {"candidate_number": n, "candidate": payloads[n - 1], "fixed_scores": valid[n][0]}
                for n in valid_numbers
            ]}, _stage_schema(explanation_properties, valid_numbers), "sde3_score_explanations")
            explanation_items = parsed.get("evaluations")
            if not isinstance(explanation_items, list):
                raise ValueError("The explanation response is missing its evaluations array.")
            by_number: dict[int, list] = {}
            for item in explanation_items:
                n = item.get("candidate_number") if isinstance(item, dict) else None
                if type(n) is not int or n not in valid:
                    diagnostics[-1].setdefault("unexpected_candidate_numbers", []).append(n)
                    continue
                by_number.setdefault(n, []).append(item)
            for n in valid_numbers:
                matches = by_number.get(n, [])
                explanation = matches[0].get("grading", {}) if len(matches) == 1 else {}
                text = explanation.get("Score Rationale") if isinstance(explanation, dict) else None
                # Numeric fields in this response are never merged into scores.
                if isinstance(text, str) and text.strip():
                    valid[n][0]["Score Rationale"] = text.strip()
                    valid[n][1]["explanation_status"] = "generated"
        except Exception as exc:
            for _, raw in valid.values():
                raw["explanation_error"] = str(exc)

    results = []
    for n in numbers:
        if n in valid:
            grading, raw = valid[n]
            if not grading.get("Score Rationale"):
                grading["Score Rationale"] = _fallback_explanation(grading, role)
                raw["explanation_status"] = "calculated_summary"
                raw.setdefault("explanation_error", "Missing, duplicate, or empty explanation record.")
            raw = {**raw, "grading": dict(grading), "provider_diagnostics": diagnostics}
            results.append((grading, raw))
        else:
            results.append(({}, {
                "candidate_number": n, "evaluation_error": failures.get(n, "Missing score decisions."),
                "provider_diagnostics": diagnostics,
            }))
    return BatchEvaluationResults(results, usage)
