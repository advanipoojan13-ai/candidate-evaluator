from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from candidate_evaluator.openai_scoring import (
    BATCH_SIZE,
    OPENAI_MAX_RETRIES,
    _batch_response_schema,
    _fixed_prompt,
    _prompt_cache_key,
    evaluate_candidates,
)
from candidate_evaluator.roles import get_role_profile


def _candidate(number: int) -> dict:
    return {
        "linkedin_profile_id": f"candidate-{number}",
        "linkedin_url": f"https://linkedin.com/in/candidate-{number}",
        "candidate_name": f"Candidate {number}",
        "headline": "Product designer",
        "about": "Designs useful products.",
        "education": [],
        "experiences": [],
    }


def _response(count: int) -> SimpleNamespace:
    evaluations = [
        {
            "candidate_number": number,
            "grading": {"Total Score": number},
        }
        for number in range(1, count + 1)
    ]
    message = SimpleNamespace(content=json.dumps({"evaluations": evaluations}))
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


@patch("candidate_evaluator.openai_scoring.OpenAI")
def test_five_candidates_use_one_api_call_and_keep_rubric_in_fixed_prefix(mock_openai) -> None:
    create = mock_openai.return_value.chat.completions.create
    create.return_value = _response(BATCH_SIZE)
    candidates = [_candidate(number) for number in range(1, BATCH_SIZE + 1)]

    results = evaluate_candidates(
        api_key="test-key",
        model="gpt-5.5",
        rubric_text="Use this unchanged rubric.",
        candidates=candidates,
    )

    assert len(results) == BATCH_SIZE
    mock_openai.assert_called_once_with(api_key="test-key", max_retries=OPENAI_MAX_RETRIES)
    create.assert_called_once()
    request = create.call_args.kwargs
    assert "Use this unchanged rubric." in request["messages"][0]["content"]
    assert "Use this unchanged rubric." not in request["messages"][1]["content"]
    sent = json.loads(request["messages"][1]["content"])
    assert len(sent["candidates"]) == BATCH_SIZE
    assert [item["candidate_number"] for item in sent["candidates"]] == [1, 2, 3, 4, 5]
    assert request["prompt_cache_key"].startswith("candidate-evaluator-")
    candidate_schema = request["response_format"]["json_schema"]["schema"]["properties"]["evaluations"]["items"]
    assert candidate_schema["required"] == ["candidate_number", "grading"]
    assert set(candidate_schema["properties"]) == {"candidate_number", "grading"}
    schema_text = json.dumps(candidate_schema)
    assert "internal_role_summaries" not in schema_text
    assert "internal_category_justifications" not in schema_text


def test_cache_key_is_stable_for_same_rubric_and_changes_with_rubric() -> None:
    role = get_role_profile("design")
    first_prompt = _fixed_prompt(role, "Rubric A")

    assert _prompt_cache_key("gpt-5.5", first_prompt) == _prompt_cache_key("gpt-5.5", first_prompt)
    assert _prompt_cache_key("gpt-5.5", first_prompt) != _prompt_cache_key(
        "gpt-5.5", _fixed_prompt(role, "Rubric B")
    )


@pytest.mark.parametrize("role_key", ["design", "qa", "backend"])
def test_fixed_prompt_keeps_each_universal_safeguard_once(role_key) -> None:
    prompt = _fixed_prompt(get_role_profile(role_key), "Unique rubric body.")

    assert prompt.count("UNIVERSAL EVALUATION RULES") == 1
    assert prompt.count("ROLE-SPECIFIC SAFEGUARDS") == 1
    assert prompt.count("RUBRIC\nUnique rubric body.") == 1
    assert prompt.count("images, logos, followers, connections, internal IDs, and scraper metadata") == 1
    assert prompt.count("do not use external information or invent missing facts") == 1
    assert prompt.count("do not compare candidates with one another") == 1
    assert prompt.count("Return only fields required by the JSON schema") == 1


def test_prompt_does_not_repeat_schema_or_python_owned_rules() -> None:
    role = get_role_profile("qa")
    prompt = _fixed_prompt(role, "Unique rubric body.")

    assert "Category maxima:" not in prompt
    assert "Allowed discrete score values:" not in prompt
    assert "Total Score must equal" not in prompt
    assert "Decision bands are" not in prompt


@patch("candidate_evaluator.openai_scoring.OpenAI")
def test_short_final_batch_is_supported(mock_openai) -> None:
    create = mock_openai.return_value.chat.completions.create
    create.return_value = _response(2)

    results = evaluate_candidates(
        api_key="test-key",
        model="gpt-5.5",
        rubric_text="Rubric",
        candidates=[_candidate(1), _candidate(2)],
    )

    assert len(results) == 2
    assert create.call_count == 1


@patch("candidate_evaluator.openai_scoring.OpenAI")
def test_mismatched_batch_output_is_rejected(mock_openai) -> None:
    create = mock_openai.return_value.chat.completions.create
    create.return_value = _response(1)

    with pytest.raises(ValueError, match="different number or order"):
        evaluate_candidates(
            api_key="test-key",
            model="gpt-5.5",
            rubric_text="Rubric",
            candidates=[_candidate(1), _candidate(2)],
        )

    create.assert_called_once()


@patch("candidate_evaluator.openai_scoring.OpenAI")
def test_malformed_model_output_is_not_retried_by_application(mock_openai) -> None:
    create = mock_openai.return_value.chat.completions.create
    message = SimpleNamespace(content="{not valid JSON")
    create.return_value = SimpleNamespace(choices=[SimpleNamespace(message=message)])

    with pytest.raises(ValueError):
        evaluate_candidates(
            api_key="test-key",
            model="gpt-5.5",
            rubric_text="Rubric",
            candidates=[_candidate(1)],
        )

    create.assert_called_once()


@patch("candidate_evaluator.openai_scoring.OpenAI")
def test_request_error_is_not_retried_by_application(mock_openai) -> None:
    create = mock_openai.return_value.chat.completions.create
    create.side_effect = RuntimeError("permanent request error")

    with pytest.raises(RuntimeError, match="permanent request error"):
        evaluate_candidates(
            api_key="test-key",
            model="gpt-5.5",
            rubric_text="Rubric",
            candidates=[_candidate(1)],
        )

    create.assert_called_once()


@patch("candidate_evaluator.openai_scoring.OpenAI")
def test_retry_limit_is_owned_by_openai_client(mock_openai) -> None:
    mock_openai.return_value.chat.completions.create.return_value = _response(1)

    evaluate_candidates(
        api_key="test-key",
        model="gpt-5.5",
        rubric_text="Rubric",
        candidates=[_candidate(1)],
        max_retries=1,
    )

    mock_openai.assert_called_once_with(api_key="test-key", max_retries=1)
    mock_openai.return_value.chat.completions.create.assert_called_once()


def test_more_than_five_candidates_must_be_split_before_api_call() -> None:
    with pytest.raises(ValueError, match="between 1 and 5"):
        evaluate_candidates(
            api_key="test-key",
            model="gpt-5.5",
            rubric_text="Rubric",
            candidates=[_candidate(number) for number in range(1, 7)],
        )


@pytest.mark.parametrize(
    ("role_key", "calculated_fields"),
    [
        (
            "design",
            {
                "Total Score",
                "Ranking",
                "Total Relevant Design Experience — Years and Months",
                "Total Weighted Relevant Design Experience — Years and Months",
                "Weighted Design-Agency Experience — Years and Months",
            },
        ),
        (
            "qa",
            {
                "Total Score",
                "Decision",
                "Total Relevant QA Experience — Years and Months",
                "Total Weighted Relevant QA Experience — Years and Months",
            },
        ),
        ("backend", {"Current Company", "Current Title", "Final Score (/60)", "Rank Number"}),
    ],
)
def test_mechanical_fields_are_not_requested_from_model(role_key, calculated_fields) -> None:
    schema = _batch_response_schema(get_role_profile(role_key))
    grading = schema["properties"]["evaluations"]["items"]["properties"]["grading"]

    assert calculated_fields.isdisjoint(grading["required"])
    assert calculated_fields.isdisjoint(grading["properties"])
