from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any, Optional

from openai import OpenAI

from .evidence import custom_evidence_payload
from .extractor import merge_duplicate_experiences
from .providers import DEEPSEEK_PROVIDER_KEY, DEFAULT_PROVIDER_KEY, ProviderProfile, get_provider
from .roles import RoleProfile, get_role_profile

BATCH_SIZE = 5
OPENAI_MAX_RETRIES = 2


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
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    if not 1 <= len(candidates) <= BATCH_SIZE:
        raise ValueError(f"An evaluation batch must contain between 1 and {BATCH_SIZE} candidates.")

    provider = get_provider(provider_key)
    client_kwargs: dict[str, Any] = {"api_key": api_key, "max_retries": max_retries}
    if provider.base_url:
        client_kwargs["base_url"] = provider.base_url
    client = OpenAI(**client_kwargs)
    role = role_profile or get_role_profile(role_key)
    response = _create_response(client, provider, model, rubric_text, candidates, role, reasoning_effort)

    content = ""
    try:
        content = _response_content(response, provider)
        raw = _parse_response_json(content, allow_surrounding_text=provider.key == DEEPSEEK_PROVIDER_KEY)
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
            results.append((grading, item))
        return results
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise ModelOutputFormatError(str(exc), content) from exc


class ModelOutputFormatError(ValueError):
    """Preserve unreadable provider output for diagnostics without retrying it."""

    def __init__(self, message: str, raw_content: str) -> None:
        super().__init__(message)
        self.raw_content = raw_content


def _parse_response_json(content: str, *, allow_surrounding_text: bool) -> dict[str, Any]:
    if not allow_surrounding_text:
        parsed = json.loads(content)
    else:
        stripped = content.lstrip()
        object_start = stripped.find("{")
        if object_start < 0:
            raise json.JSONDecodeError("No JSON object found", content, 0)
        parsed, _ = json.JSONDecoder().raw_decode(stripped[object_start:])
    if not isinstance(parsed, dict):
        raise TypeError("The candidate evaluation response is not a JSON object.")
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
            max_output_tokens=16000,
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
        "Education 1": (candidate.get("education") or ["", ""])[1]
        if len(candidate.get("education") or []) > 1
        else "",
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
