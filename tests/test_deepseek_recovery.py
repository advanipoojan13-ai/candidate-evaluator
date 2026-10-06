from __future__ import annotations

from typing import Any

import app
from candidate_evaluator.openai_scoring import BatchEvaluationResults, ModelOutputFormatError
from candidate_evaluator.providers import DEEPSEEK_PROVIDER_KEY, OPENAI_PROVIDER_KEY
from candidate_evaluator.roles import get_role_profile


def _candidate(number: int) -> dict[str, Any]:
    return {
        "linkedin_profile_id": f"candidate-{number}",
        "linkedin_url": f"https://linkedin.com/in/candidate-{number}",
        "candidate_name": f"Candidate {number}",
        "source_row": {},
    }


def _usage(api_calls: int = 1, output_tokens: int = 10) -> dict[str, int]:
    return {
        "api_calls": api_calls,
        "input_tokens": 5,
        "cached_input_tokens": 3,
        "cache_write_tokens": 0,
        "output_tokens": output_tokens,
        "reasoning_tokens": output_tokens - 1,
        "total_tokens": output_tokens + 5,
    }


def _accept_all_rows(monkeypatch) -> None:
    monkeypatch.setattr(app, "apply_calculated_fields", lambda row, _candidate, _role: row)
    monkeypatch.setattr(app, "coerce_fixed_row", lambda row, _role: row)
    monkeypatch.setattr(app, "validate_output_row", lambda _row, _role: [])


def test_failed_deepseek_batch_is_split_and_all_candidates_are_recovered(monkeypatch) -> None:
    calls: list[int] = []

    def fake_evaluate_candidates(*, candidates, **_kwargs):
        calls.append(len(candidates))
        if len(candidates) > 1:
            raise ModelOutputFormatError("output limit reached", "", _usage(output_tokens=20))
        return BatchEvaluationResults(
            [({"Total Score": 1}, {"candidate_number": 1, "grading": {"Total Score": 1}})],
            _usage(output_tokens=2),
        )

    monkeypatch.setattr("candidate_evaluator.openai_scoring.evaluate_candidates", fake_evaluate_candidates)
    _accept_all_rows(monkeypatch)

    result = app._evaluate_candidate_batch_for_run(
        "key",
        "deepseek-flash",
        "rubric",
        [_candidate(1), _candidate(2)],
        get_role_profile("design"),
        DEEPSEEK_PROVIDER_KEY,
        "low",
    )

    assert calls == [2, 1, 1]
    assert [item["state"] for item in result["results"]] == ["completed", "completed"]
    assert result["usage"]["api_calls"] == 3
    assert result["usage"]["output_tokens"] == 24


def test_deepseek_split_isolates_a_candidate_that_still_cannot_complete(monkeypatch) -> None:
    def fake_evaluate_candidates(*, candidates, **_kwargs):
        if len(candidates) > 1 or candidates[0]["linkedin_profile_id"] == "candidate-2":
            raise ModelOutputFormatError("output limit reached", "", _usage())
        return BatchEvaluationResults(
            [({"Total Score": 1}, {"candidate_number": 1, "grading": {"Total Score": 1}})],
            _usage(output_tokens=2),
        )

    monkeypatch.setattr("candidate_evaluator.openai_scoring.evaluate_candidates", fake_evaluate_candidates)
    _accept_all_rows(monkeypatch)

    result = app._evaluate_candidate_batch_for_run(
        "key",
        "deepseek-flash",
        "rubric",
        [_candidate(1), _candidate(2)],
        get_role_profile("design"),
        DEEPSEEK_PROVIDER_KEY,
        "max",
    )

    assert [item["state"] for item in result["results"]] == ["completed", "skipped"]
    assert "candidate output" in result["results"][1]["error"]
    assert result["usage"]["api_calls"] == 3


def test_openai_format_failure_is_not_split(monkeypatch) -> None:
    calls: list[int] = []

    def fake_evaluate_candidates(*, candidates, **_kwargs):
        calls.append(len(candidates))
        raise ModelOutputFormatError("unreadable", "", _usage())

    monkeypatch.setattr("candidate_evaluator.openai_scoring.evaluate_candidates", fake_evaluate_candidates)

    result = app._evaluate_candidate_batch_for_run(
        "key",
        "gpt-5.5",
        "rubric",
        [_candidate(1), _candidate(2)],
        get_role_profile("design"),
        OPENAI_PROVIDER_KEY,
        "none",
    )

    assert calls == [2]
    assert [item["state"] for item in result["results"]] == ["skipped", "skipped"]
