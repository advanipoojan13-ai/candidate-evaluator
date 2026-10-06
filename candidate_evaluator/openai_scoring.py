from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any, Optional

from json_repair import repair_json
from openai import OpenAI

from .evidence import custom_evidence_payload
from .extractor import merge_duplicate_experiences
from .providers import DEEPSEEK_PROVIDER_KEY, DEFAULT_PROVIDER_KEY, ProviderProfile, get_provider
from .roles import RoleProfile, get_role_profile

BATCH_SIZE = 5
OPENAI_MAX_RETRIES = 2
DEEPSEEK_DEFAULT_MAX_OUTPUT_TOKENS = 16000
DEEPSEEK_HIGH_MAX_OUTPUT_TOKENS = 32000


class BatchEvaluationResults(list[tuple[dict[str, Any], dict[str, Any]]]):
    """Candidate results plus the provider-reported usage for this API response."""

    def __init__(
        self,
        values: list[tuple[dict[str, Any], dict[str, Any]]],
        usage: dict[str, int],
    ) -> None:
        super().__init__(values)
        self.usage = usage


def evaluate_candidate(
    *,
    api_key: str,
    model: str,
    rubric_text: str,
    candidate: dict[str, Any],
    role_key: str = "design",
    role_profile: Optional[RoleProfile] = None,
    provider_key: str = DEFAULT_PROVIDER_KEY,
    reasoning_effort: str = "none",
    max_retries: int = OPENAI_MAX_RETRIES,
    max_format_retries: int = 0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    # Kept for compatibility with older callers. Formatting failures are not
    # retried because that would resend the full rubric and candidate payload.
    del max_format_retries
    results = evaluate_candidates(
        api_key=api_key,
        model=model,
        rubric_text=rubric_text,
        candidates=[candidate],
        role_key=role_key,
        role_profile=role_profile,
        provider_key=provider_key,
        reasoning_effort=reasoning_effort,
        max_retries=max_retries,
    )
    return results[0]


def evaluate_candidates(
    *,
    api_key: str,
    model: str,
    rubric_text: str,
    candidates: list[dict[str, Any]],
    role_key: str = "design",
    role_profile: Optional[RoleProfile] = None,
    provider_key: str = DEFAULT_PROVIDER_KEY,
    reasoning_effort: str = "none",
    max_retries: int = OPENAI_MAX_RETRIES,
) -> BatchEvaluationResults:
    if not 1 <= len(candidates) <= BATCH_SIZE:
        raise ValueError(f"An evaluation batch must contain between 1 and {BATCH_SIZE} candidates.")

    provider = get_provider(provider_key)
    client_kwargs: dict[str, Any] = {"api_key": api_key, "max_retries": max_retries}
    if provider.base_url:
        client_kwargs["base_url"] = provider.base_url
    client = OpenAI(**client_kwargs)
    role = role_profile or get_role_profile(role_key)
    response = _create_response(client, provider, model, rubric_text, candidates, role, reasoning_effort)
    usage = _response_usage(response)

    content = ""
    try:
        content = _response_content(response, provider)
        raw = _parse_response_json(content, allow_surrounding_text=provider.key == DEEPSEEK_PROVIDER_KEY)
        format_repaired = bool(raw.pop("_response_format_repaired", False))
        evaluations = raw["evaluations"]
        if not isinstance(evaluations, list):
            raise TypeError("The evaluations field is not a JSON array.")
        expected_numbers = list(range(1, len(candidates) + 1))
        actual_numbers = [item.get("candidate_number") for item in evaluations]
        if len(evaluations) != len(candidates) or actual_numbers != expected_numbers:
            raise ValueError(
                f"{provider.label} returned a different number or order of candidate evaluations "
                f"(expected {expected_numbers}, received {actual_numbers})."
            )
        results = []
        for item in evaluations:
            grading = item.get("grading")
            if not isinstance(grading, dict):
                raise TypeError("An evaluation grading field is not a JSON object.")
            if format_repaired:
                item = {**item, "_response_format_repaired": True}
            results.append((grading, item))
        return BatchEvaluationResults(results, usage)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise ModelOutputFormatError(str(exc), content, usage) from exc


class ModelOutputFormatError(ValueError):
    """Preserve unreadable provider output for diagnostics without retrying it."""

    def __init__(self, message: str, raw_content: str, usage: Optional[dict[str, int]] = None) -> None:
        super().__init__(message)
        self.raw_content = raw_content
        self.usage = usage or _empty_usage()


def _response_usage(response: Any) -> dict[str, int]:
    """Normalize usage returned by Chat Completions or Responses-style providers."""
    usage = _field(response, "usage")
    if usage is None:
        return _empty_usage()

    input_tokens = _integer_field(usage, "prompt_tokens", "input_tokens")
    output_tokens = _integer_field(usage, "completion_tokens", "output_tokens")
    total_tokens = _integer_field(usage, "total_tokens") or input_tokens + output_tokens
    input_details = _field(usage, "prompt_tokens_details") or _field(usage, "input_tokens_details")
    output_details = _field(usage, "completion_tokens_details") or _field(usage, "output_tokens_details")
    return {
        "api_calls": 1,
        "input_tokens": input_tokens,
        "cached_input_tokens": _integer_field(input_details, "cached_tokens"),
        "cache_write_tokens": _integer_field(input_details, "cache_write_tokens"),
        "output_tokens": output_tokens,
        "reasoning_tokens": _integer_field(output_details, "reasoning_tokens"),
        "total_tokens": total_tokens,
    }


def _empty_usage() -> dict[str, int]:
    return {
        "api_calls": 0,
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "cache_write_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "total_tokens": 0,
    }


def _field(value: Any, name: str) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def _integer_field(value: Any, *names: str) -> int:
    for name in names:
        item = _field(value, name)
        if item is not None:
            try:
                return int(item)
            except (TypeError, ValueError):
                return 0
    return 0


def _parse_response_json(content: str, *, allow_surrounding_text: bool) -> dict[str, Any]:
    repaired = False
    if not allow_surrounding_text:
        parsed = json.loads(content)
    else:
        stripped = content.lstrip()
        object_start = stripped.find("{")
        if object_start < 0:
            raise json.JSONDecodeError("No JSON object found", content, 0)
        candidate_json = stripped[object_start:]
        try:
            parsed, _ = json.JSONDecoder().raw_decode(candidate_json)
        except json.JSONDecodeError as original_error:
            try:
                parsed = repair_json(
                    candidate_json,
                    return_objects=True,
                    skip_json_loads=True,
                    ensure_ascii=False,
                )
            except (TypeError, ValueError, IndexError) as repair_error:
                raise original_error from repair_error
            if parsed in (None, ""):
                raise original_error
            repaired = True
    if not isinstance(parsed, dict):
        raise TypeError("The candidate evaluation response is not a JSON object.")
    if repaired:
        parsed["_response_format_repaired"] = True
    return parsed


def _create_response(
    client: OpenAI,
    provider: ProviderProfile,
    model: str,
    rubric_text: str,
    candidates: list[dict[str, Any]],
    role: RoleProfile,
    reasoning_effort: str,
) -> Any:
    fixed_prompt = _fixed_prompt(role, rubric_text)
    request_input = json.dumps(
        {
            "candidates": [
                {
                    "candidate_number": index,
                    "candidate": _candidate_payload(candidate, role),
                }
                for index, candidate in enumerate(candidates, start=1)
            ]
        },
        ensure_ascii=False,
    )
    schema = _batch_response_schema(role)
    if provider.transport == "responses":
        return client.responses.create(
            model=model,
            instructions=fixed_prompt,
            input=request_input,
            reasoning={"effort": reasoning_effort or provider.default_reasoning_effort},
            max_output_tokens=_deepseek_max_output_tokens(reasoning_effort),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "candidate_evaluation_batch",
                    "schema": schema,
                }
            },
        )
    return client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": fixed_prompt},
            {"role": "user", "content": request_input},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "candidate_evaluation_batch",
                "strict": True,
                "schema": schema,
            },
        },
        prompt_cache_key=_prompt_cache_key(model, fixed_prompt),
    )


def _deepseek_max_output_tokens(reasoning_effort: str) -> int:
    """Give high-effort batches room to finish without raising cheaper runs' ceiling."""
    if reasoning_effort in {"high", "max", "xhigh", "ultra"}:
        return DEEPSEEK_HIGH_MAX_OUTPUT_TOKENS
    return DEEPSEEK_DEFAULT_MAX_OUTPUT_TOKENS


def _response_content(response: Any, provider: ProviderProfile) -> str:
    if provider.transport == "responses":
        content = getattr(response, "output_text", "") or ""
    else:
        content = response.choices[0].message.content or ""
    if not content.strip():
        raise ValueError(f"{provider.label} returned an empty response.")
    return content


def _candidate_payload(candidate: dict[str, Any], role: RoleProfile) -> dict[str, Any]:
    experiences = candidate.get("experiences") or []
    if role.key in {"backend", "ai_engineer_trj", "head_sales"}:
        experiences = merge_duplicate_experiences(experiences)
    candidate = {**candidate, "experiences": experiences}
    payload = {
        "LinkedIn Profile ID": candidate.get("linkedin_profile_id", ""),
        "LinkedIn URL": candidate.get("linkedin_url", ""),
        "Candidate Name": candidate.get("candidate_name", ""),
        "Headline": candidate.get("headline", ""),
        "About": candidate.get("about", ""),
        "Website": candidate.get("website", ""),
        "Education 0": (candidate.get("education") or [""])[0] if candidate.get("education") else "",
        "Education 1": (candidate.get("education") or ["", ""])[1]
        if len(candidate.get("education") or []) > 1
        else "",
        "experiences": experiences,
    }
    if role.evidence_sources is None:
        return payload
    filtered_payload = {
        "LinkedIn Profile ID": candidate.get("linkedin_profile_id", ""),
        "LinkedIn URL": candidate.get("linkedin_url", ""),
        "Candidate Name": candidate.get("candidate_name", ""),
        **custom_evidence_payload(candidate, role.evidence_sources),
    }
    if role.experience_fields and filtered_payload.get("experiences"):
        filtered_payload["experiences"] = [
            {field: experience.get(field) for field in role.experience_fields if field in experience}
            for experience in filtered_payload["experiences"]
        ]
    return filtered_payload


def _system_prompt(role: RoleProfile) -> str:
    return f"{role.system_prompt} Evaluation date: {date.today().isoformat()}."


def _fixed_prompt(role: RoleProfile, rubric_text: str) -> str:
    role_instructions = "\n".join(f"- {instruction}" for instruction in role.instructions)
    prompt = (
        f"{_system_prompt(role)}\n\n"
        "UNIVERSAL EVALUATION RULES\n"
        "- Apply the supplied rubric using only the supplied candidate evidence; do not use external information or invent missing facts.\n"
        "- Ignore profile-platform metadata such as images, logos, followers, connections, internal IDs, and scraper metadata if present.\n"
        "- Evaluate every candidate independently; do not compare candidates with one another.\n"
        "- Return exactly one evaluation per candidate, in the supplied order, using consecutive candidate_number values starting at 1.\n"
        "- Return only fields required by the JSON schema."
    )
    if role_instructions:
        prompt += f"\n\nROLE-SPECIFIC SAFEGUARDS\n{role_instructions}"
    return f"{prompt}\n\nRUBRIC\n{rubric_text}"


def _prompt_cache_key(model: str, fixed_prompt: str) -> str:
    digest = hashlib.sha256(f"{model}\0{fixed_prompt}".encode("utf-8")).hexdigest()[:32]
    return f"candidate-evaluator-{digest}"


def _batch_response_schema(role: RoleProfile) -> dict[str, Any]:
    candidate_schema = _response_schema(role)
    candidate_schema["required"] = ["candidate_number", *candidate_schema["required"]]
    candidate_schema["properties"] = {
        "candidate_number": {"type": "integer", "minimum": 1, "maximum": BATCH_SIZE},
        **candidate_schema["properties"],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["evaluations"],
        "properties": {
            "evaluations": {
                "type": "array",
                "minItems": 1,
                "maxItems": BATCH_SIZE,
                "items": candidate_schema,
            }
        },
    }


def _response_schema(role: RoleProfile) -> dict[str, Any]:
    model_columns = role.model_grading_columns
    grading_props = _grading_properties(role, model_columns)
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["grading"],
        "properties": {
            "grading": {
                "type": "object",
                "additionalProperties": False,
                "required": model_columns,
                "properties": grading_props,
            }
        },
    }


def _grading_properties(role: RoleProfile, columns: list[str]) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    for column in columns:
        if column in role.component_score_maxima:
            properties[column] = {
                "type": "integer",
                "minimum": 0,
                "maximum": role.component_score_maxima[column],
            }
        elif column in role.category_scores:
            schema: dict[str, Any] = {
                "type": "number" if role.numeric_scores else "integer",
                "minimum": 0,
                "maximum": role.category_scores[column],
            }
            if column in role.allowed_scores:
                schema["enum"] = sorted(role.allowed_scores[column])
            properties[column] = schema
        elif column == role.total_column:
            properties[column] = {
                "type": "number" if role.numeric_scores else "integer",
                "minimum": 0,
                "maximum": role.total_max,
            }
        elif column == role.outcome_column and role.outcome_bands:
            properties[column] = {"type": "string", "enum": [band[2] for band in role.outcome_bands]}
        elif column == "Evidence Confidence":
            properties[column] = {"type": "string", "enum": role.evidence_confidence_values}
        elif role.column_enums and column in role.column_enums:
            properties[column] = {"type": "string", "enum": role.column_enums[column]}
        elif column in (role.ranking_tiebreaker_columns or []):
            properties[column] = {"type": "number", "minimum": 0}
        elif column.endswith("— Months"):
            properties[column] = {"type": "integer", "minimum": 0}
        else:
            properties[column] = {"type": "string"}
    return properties
