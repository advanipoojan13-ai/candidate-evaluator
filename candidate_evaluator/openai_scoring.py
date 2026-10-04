from __future__ import annotations

import json
import random
import time
from datetime import date
from typing import Any, Optional

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, RateLimitError

from .evidence import custom_evidence_payload
from .extractor import merge_duplicate_experiences
from .providers import DEFAULT_PROVIDER_KEY, ProviderProfile, get_provider
from .roles import RoleProfile, get_role_profile


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
    max_retries: int = 5,
    max_format_retries: int = 2,
) -> tuple[dict[str, Any], dict[str, Any]]:
    provider = get_provider(provider_key)
    client_kwargs: dict[str, Any] = {"api_key": api_key}
    if provider.base_url:
        client_kwargs["base_url"] = provider.base_url
    client = OpenAI(**client_kwargs)
    role = role_profile or get_role_profile(role_key)
    for format_attempt in range(max_format_retries + 1):
        response = _call_with_backoff(
            client,
            provider,
            model,
            rubric_text,
            candidate,
            role,
            reasoning_effort=reasoning_effort,
            max_retries=max_retries,
        )
        try:
            content = _response_content(response, provider)
            raw = json.loads(content)
            grading = raw["grading"]
            if not isinstance(grading, dict):
                raise ValueError("The grading field is not a JSON object.")
            return grading, raw
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            if format_attempt >= max_format_retries:
                raise
            time.sleep(0.5 * (format_attempt + 1))
    raise RuntimeError(f"{provider.label} returned unreadable output after retries.")


def _call_with_backoff(
    client: OpenAI,
    provider: ProviderProfile,
    model: str,
    rubric_text: str,
    candidate: dict[str, Any],
    role: RoleProfile,
    reasoning_effort: str,
    max_retries: int,
) -> Any:
    for attempt in range(max_retries + 1):
        try:
            return _create_response(client, provider, model, rubric_text, candidate, role, reasoning_effort)
        except (RateLimitError, APIConnectionError, APITimeoutError, APIStatusError) as exc:
            if attempt >= max_retries or not _is_retryable(exc):
                raise
            time.sleep(_retry_delay_seconds(exc, attempt))
    raise RuntimeError(f"{provider.label} request failed after retries.")


def _create_response(
    client: OpenAI,
    provider: ProviderProfile,
    model: str,
    rubric_text: str,
    candidate: dict[str, Any],
    role: RoleProfile,
    reasoning_effort: str,
) -> Any:
    request_input = json.dumps(
        {
            "rubric": rubric_text,
            "candidate": _candidate_payload(candidate, role),
            "instructions": role.instructions,
            "output_requirement": "Return JSON that exactly matches the supplied candidate evaluation schema.",
        },
        ensure_ascii=False,
    )
    schema = _response_schema(role)
    if provider.transport == "responses":
        return client.responses.create(
            model=model,
            instructions=_system_prompt(role),
            input=request_input,
            reasoning={"effort": reasoning_effort or provider.default_reasoning_effort},
            max_output_tokens=16000,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "candidate_evaluation",
                    "schema": schema,
                }
            },
        )
    return client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _system_prompt(role)},
            {"role": "user", "content": request_input},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "candidate_evaluation",
                "strict": True,
                "schema": schema,
            },
        },
    )


def _response_content(response: Any, provider: ProviderProfile) -> str:
    if provider.transport == "responses":
        content = getattr(response, "output_text", "") or ""
    else:
        content = response.choices[0].message.content or ""
    if not content.strip():
        raise ValueError(f"{provider.label} returned an empty response.")
    return content


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, (RateLimitError, APIConnectionError, APITimeoutError)):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code >= 500 or exc.status_code == 429
    return False


def _retry_delay_seconds(exc: Exception, attempt: int) -> float:
    retry_after = _retry_after_seconds(exc)
    if retry_after is not None:
        return min(retry_after, 60.0)
    base_delay = min(2**attempt, 30)
    return base_delay + random.uniform(0, 0.75)


def _retry_after_seconds(exc: Exception) -> Optional[float]:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    value = headers.get("retry-after") or headers.get("Retry-After")
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def _candidate_payload(candidate: dict[str, Any], role: RoleProfile) -> dict[str, Any]:
    experiences = candidate.get("experiences") or []
    if role.key in {"backend", "ai_engineer_trj"}:
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
        "Education 1": (candidate.get("education") or ["", ""])[1] if len(candidate.get("education") or []) > 1 else "",
        "experiences": experiences,
    }
    if role.evidence_sources is None:
        return payload
    return {
        "LinkedIn Profile ID": candidate.get("linkedin_profile_id", ""),
        "LinkedIn URL": candidate.get("linkedin_url", ""),
        "Candidate Name": candidate.get("candidate_name", ""),
        **custom_evidence_payload(candidate, role.evidence_sources),
    }


def _system_prompt(role: RoleProfile) -> str:
    maxima_text = ", ".join(f"{name}: {maximum}" for name, maximum in role.category_scores.items())
    allowed_text = "; ".join(f"{name}: {sorted(values)}" for name, values in role.allowed_scores.items())
    prompt = f"{role.system_prompt} Evaluation date: {date.today().isoformat()}. Category maxima: {maxima_text}."
    if allowed_text:
        prompt += f" Allowed discrete score values: {allowed_text}."
    return prompt


def _response_schema(role: RoleProfile) -> dict[str, Any]:
    grading_props = _grading_properties(role)
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["grading", "internal_role_summaries", "internal_category_justifications"],
        "properties": {
            "grading": {
                "type": "object",
                "additionalProperties": False,
                "required": role.grading_columns,
                "properties": grading_props,
            },
            "internal_role_summaries": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "experience_index",
                        "company",
                        "title",
                        "employment_type",
                        "actual_duration_months",
                        "employment_type_weight",
                        "weighted_duration_months",
                        role.internal_role_flag_name,
                        "reason",
                        role.internal_role_evidence_name,
                    ],
                    "properties": {
                        "experience_index": {"type": "integer"},
                        "company": {"type": "string"},
                        "title": {"type": "string"},
                        "employment_type": {"type": "string"},
                        "actual_duration_months": {"type": "number"},
                        "employment_type_weight": {"type": "number"},
                        "weighted_duration_months": {"type": "number"},
                        role.internal_role_flag_name: {"type": "boolean"},
                        "reason": {"type": "string"},
                        role.internal_role_evidence_name: {"type": "string"},
                    },
                },
            },
            "internal_category_justifications": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "category",
                        "assigned_score",
                        "evidence_used",
                        "relevant_experience_indexes",
                        "applicable_score_band",
                        "score_cap_applied",
                        "brief_justification",
                    ],
                    "properties": {
                        "category": {"type": "string"},
                        "assigned_score": {"type": "number" if role.numeric_scores else "integer"},
                        "evidence_used": {"type": "string"},
                        "relevant_experience_indexes": {"type": "array", "items": {"type": "integer"}},
                        "applicable_score_band": {"type": "string"},
                        "score_cap_applied": {"type": "string"},
                        "brief_justification": {"type": "string"},
                    },
                },
            },
        },
    }


def _grading_properties(role: RoleProfile) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    for column in role.grading_columns:
        if column in role.category_scores:
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
