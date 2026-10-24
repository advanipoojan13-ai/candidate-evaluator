from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from openai import APIStatusError

from candidate_evaluator.extractor import normalize_candidate
from candidate_evaluator.openai_scoring import evaluate_candidate, evaluate_candidates
from candidate_evaluator.roles import get_role_profile


COMPONENTS = {
    "agent_evidence": "Shipped AI Agent / Agent-Chatbot Delivery — Evidence Points",
    "agent_recency": "Shipped AI Agent / Agent-Chatbot Delivery — Recency Points",
    "agent_duration": "Shipped AI Agent / Agent-Chatbot Delivery — Evidenced Duration Points",
    "framework_evidence": "FastAPI / Django — Evidence Points",
    "framework_recency": "FastAPI / Django — Recency Points",
    "framework_duration": "FastAPI / Django — Evidenced Duration Points",
    "architecture_evidence": "Backend / System Architecture — Evidence Points",
    "architecture_recency": "Backend / System Architecture — Recency Points",
    "architecture_duration": "Backend / System Architecture — Evidenced Duration Points",
    "breadth_evidence": "AI Solution Breadth & Judgment — Evidence Points",
    "breadth_recency": "AI Solution Breadth & Judgment — Recency Points",
    "breadth_duration": "AI Solution Breadth & Judgment — Evidenced Duration Points",
}


def _candidate(number: int) -> dict:
    return normalize_candidate(
        {
            "publicIdentifier": f"engineer-{number}",
            "linkedinUrl": f"https://linkedin.com/in/engineer-{number}/",
            "fullName": f"Engineer {number}",
            "headline": "Backend and AI engineer",
            "about": "Builds AI agents and backends.",
            "experience": [
                {
                    "companyName": f"Company {number}",
                    "title": "Software Engineer",
                    "description": "Developed and deployed agents using FastAPI.",
                    "startDate": "2022-01",
                    "endDate": "2025-01",
                    # Dates, rather than this stale scraped value, own duration.
                    "duration": "99 years",
                }
            ],
        },
        number - 1,
    )


def _scores(value: int = 2) -> dict:
    return {
        **{alias: value for alias in COMPONENTS},
        "Shipped AI Agent / Agent-Chatbot Unverified": "No",
        "FastAPI / Django Unverified": "No",
        "Backend / System Architecture Unverified": "No",
        "Date-Quality Warning": "No",
        "Strongest Evidence": "Deployed agents at Company | FastAPI delivery in role",
        "Missing or Unclear Information": "Architecture ownership is unverified.",
    }


def _record(number: int, grading: dict | None = None) -> dict:
    return {"candidate_number": number, "grading": _scores() if grading is None else grading}


def _explanation(number: int, text: str | None = None, **extra) -> dict:
    return _record(number, {"Score Rationale": text or f"Validated explanation for {number}.", **extra})


def _response(*records: dict, tokens: int = 1, raw: str | None = None, **metadata) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=raw if raw is not None else json.dumps({"evaluations": records})),
                finish_reason=metadata.pop("finish_reason", "stop"),
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=10 * tokens,
            completion_tokens=5 * tokens,
            total_tokens=15 * tokens,
            prompt_tokens_details=SimpleNamespace(cached_tokens=3 * tokens, cache_write_tokens=2 * tokens),
            completion_tokens_details=SimpleNamespace(reasoning_tokens=tokens),
        ),
        **metadata,
    )


@pytest.fixture
def model(monkeypatch):
    client = MagicMock()
    factory = MagicMock(return_value=client)
    monkeypatch.setattr("candidate_evaluator.openai_scoring.OpenAI", factory)
    return client.chat.completions.create


def _evaluate(count: int = 1):
    return evaluate_candidates(
        api_key="mock-key",
        model="mock-model",
        rubric_text="A fixed SDE3 rubric.",
        candidates=[_candidate(n) for n in range(1, count + 1)],
        role_key="sde3",
    )


def _request(model, index: int) -> tuple[dict, dict, dict]:
    request = model.call_args_list[index].kwargs
    payload = json.loads(request["messages"][1]["content"])
    schema = request["response_format"]["json_schema"]["schema"]
    return request, payload, schema


def _numbers(model, index: int) -> list[int]:
    return [item["candidate_number"] for item in _request(model, index)[1]["candidates"]]


def test_dates_are_calculated_before_the_compact_scoring_request(model, monkeypatch) -> None:
    class EvaluationDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 10, 24)

    monkeypatch.setattr("candidate_evaluator.openai_scoring.date", EvaluationDate)
    model.side_effect = [_response(_record(1)), _response(_explanation(1))]

    results = _evaluate()

    assert model.call_count == 2
    request, payload, schema = _request(model, 0)
    facts = payload["candidates"][0]["candidate"]["experiences"][0]["calculated_dates"]
    assert facts["duration_months"] == 36
    assert facts["months_since_end"] == 21
    assert facts["start_month"] == "2022-01"
    assert facts["end_month"] == "2025-01"
    assert facts["date_quality_warning"] is True
    assert results[0][0]["Date-Quality Warning"] == "Yes"
    grading_schema = schema["properties"]["evaluations"]["items"]["properties"]["grading"]
    integer_fields = {key for key, value in grading_schema["properties"].items() if value["type"] == "integer"}
    assert integer_fields == set(COMPONENTS)
    assert set(COMPONENTS) <= set(grading_schema["required"])
    assert set(COMPONENTS.values()).isdisjoint(grading_schema["properties"])
    assert "Score Rationale" not in grading_schema["properties"]
    assert "SCORING ONLY" in request["messages"][0]["content"]


def test_explanations_receive_fixed_python_scores_and_cannot_overwrite_them(model) -> None:
    poisoned = {
        "Final Score (/62)": 999,
        "Shipped AI Agent / Agent-Chatbot Delivery Score (/20)": 0,
        COMPONENTS["agent_evidence"]: 4,
        "agent_evidence": 4,
    }
    model.side_effect = [_response(_record(1)), _response(_explanation(1, **poisoned))]

    grading, raw = evaluate_candidate(
        api_key="mock-key", model="mock-model", rubric_text="Rubric",
        candidate=_candidate(1), role_key="sde3",
    )

    _, payload, schema = _request(model, 1)
    fixed = payload["candidates"][0]["fixed_scores"]
    assert fixed["Shipped AI Agent / Agent-Chatbot Delivery Score (/20)"] == 12.0
    assert fixed["FastAPI / Django Score (/18)"] == 10.8
    assert fixed["Backend / System Architecture Score (/14)"] == 8.4
    assert fixed["AI Solution Breadth & Judgment Score (/10)"] == 6.0
    assert fixed["Final Score (/62)"] == 37.2
    assert all(fixed[column] == 2 for column in COMPONENTS.values())
    explanation_schema = schema["properties"]["evaluations"]["items"]["properties"]["grading"]
    assert set(explanation_schema["properties"]) == {"Score Rationale"}
    assert grading["Final Score (/62)"] == 37.2
    assert grading[COMPONENTS["agent_evidence"]] == 2
    assert grading["Score Rationale"] == "Validated explanation for 1."
    assert raw["explanation_status"] == "generated"


def test_explicit_zero_components_are_valid_and_do_not_trigger_recovery(model) -> None:
    model.side_effect = [_response(_record(1, _scores(0))), _response(_explanation(1))]

    results = _evaluate()

    assert model.call_count == 2
    assert results[0][0]["Final Score (/62)"] == 0
    assert all(results[0][0][column] == 0 for column in COMPONENTS.values())


@pytest.mark.parametrize("bad_value", [None, True, "2", 2.5, -1, 5])
def test_invalid_components_are_recovered_once_for_only_the_affected_candidate(model, bad_value) -> None:
    broken = _scores()
    broken["agent_evidence"] = bad_value
    model.side_effect = [
        _response(_record(1, _scores(1)), _record(2, broken)),
        _response(_record(2)),
        _response(_explanation(1), _explanation(2)),
    ]

    results = _evaluate(2)

    assert [_numbers(model, index) for index in range(3)] == [[1, 2], [2], [1, 2]]
    assert results[0][0]["Final Score (/62)"] == 18.6
    assert results[1][0]["Final Score (/62)"] == 37.2
    assert results[0][0][COMPONENTS["agent_evidence"]] == 1
    assert results[1][0][COMPONENTS["agent_evidence"]] == 2


@pytest.mark.parametrize("problem", ["missing_component", "missing_record", "duplicate_record"])
def test_missing_or_duplicate_scores_preserve_other_candidates_during_recovery(model, problem) -> None:
    broken = _scores()
    broken.pop("framework_duration")
    records = [_record(1, _scores(1))]
    if problem == "missing_component":
        records.append(_record(2, broken))
    elif problem == "duplicate_record":
        records.extend([_record(2), _record(2, _scores(0))])
    model.side_effect = [
        _response(*records),
        _response(_record(2)),
        _response(_explanation(2), _explanation(1)),
    ]

    results = _evaluate(2)

    assert [_numbers(model, index) for index in range(3)] == [[1, 2], [2], [1, 2]]
    assert [grading["Final Score (/62)"] for grading, _ in results] == [18.6, 37.2]
    assert [grading["Score Rationale"] for grading, _ in results] == [
        "Validated explanation for 1.", "Validated explanation for 2.",
    ]


def test_a_second_invalid_score_response_fails_only_that_candidate_without_fabricating_zero(model) -> None:
    broken = _scores()
    broken.pop("agent_evidence")
    model.side_effect = [
        _response(_record(1), _record(2, broken)),
        _response(_record(2, broken)),
        _response(_explanation(1)),
    ]

    results = _evaluate(2)

    assert [_numbers(model, index) for index in range(3)] == [[1, 2], [2], [1]]
    assert results[0][0]["Final Score (/62)"] == 37.2
    assert results[1][0] == {}
    assert "agent_evidence" in results[1][1]["evaluation_error"]
    assert results[1][1]["candidate_number"] == 2


def test_out_of_order_score_and_explanation_records_match_candidate_numbers(model) -> None:
    model.side_effect = [
        _response(_record(2, _scores(1)), _record(1)),
        _response(_explanation(2, "Second candidate."), _explanation(1, "First candidate.")),
    ]

    results = _evaluate(2)

    assert [grading["Candidate"] for grading, _ in results] == ["Engineer 1", "Engineer 2"]
    assert [grading["Final Score (/62)"] for grading, _ in results] == [37.2, 18.6]
    assert [grading["Score Rationale"] for grading, _ in results] == ["First candidate.", "Second candidate."]


def test_explanation_failure_preserves_calculated_scores_with_explicit_fallback(model) -> None:
    model.side_effect = [_response(_record(1)), RuntimeError("explanation provider unavailable")]

    results = _evaluate()

    grading, raw = results[0]
    assert model.call_count == 2
    assert grading["Final Score (/62)"] == 37.2
    assert raw["explanation_status"] == "calculated_summary"
    assert raw["explanation_error"] == "explanation provider unavailable"
    assert "provider explanation was unavailable" in grading["Score Rationale"]
    assert "validated scoring decisions" in grading["Score Rationale"]
    assert "37.2/62" in grading["Score Rationale"]
    for category in get_role_profile("sde3").category_scores:
        assert category.rsplit(" Score (/", 1)[0] in grading["Score Rationale"]


def test_partial_explanations_fall_back_only_for_missing_or_duplicate_candidates(model) -> None:
    model.side_effect = [
        _response(_record(1), _record(2), _record(3)),
        _response(_explanation(1), _explanation(2), _explanation(2, "Duplicate.")),
    ]

    results = _evaluate(3)

    assert model.call_count == 2
    assert results[0][0]["Score Rationale"] == "Validated explanation for 1."
    assert results[0][1]["explanation_status"] == "generated"
    assert [raw["explanation_status"] for _, raw in results[1:]] == ["calculated_summary", "calculated_summary"]
    assert all(grading["Final Score (/62)"] == 37.2 for grading, _ in results)


def test_usage_includes_initial_scores_targeted_recovery_and_explanations(model) -> None:
    model.side_effect = [
        _response(_record(1), tokens=1),
        _response(_record(2), tokens=2),
        _response(_explanation(1), _explanation(2), tokens=3),
    ]

    results = _evaluate(2)

    assert results.usage == {
        "api_calls": 3,
        "input_tokens": 60,
        "cached_input_tokens": 18,
        "cache_write_tokens": 12,
        "output_tokens": 30,
        "reasoning_tokens": 6,
        "total_tokens": 90,
    }


def test_incomplete_provider_response_keeps_raw_text_and_diagnostics_after_recovery(model) -> None:
    truncated_text = '{"evaluations": [{"candidate_number": 1, "grading": {"agent_evidence":'
    model.side_effect = [
        _response(raw=truncated_text, finish_reason="length", id="truncated-1", model="mock-model", _request_id="req-1"),
        _response(_record(1)),
        _response(_explanation(1)),
    ]

    results = _evaluate()

    diagnostics = results[0][1]["provider_diagnostics"]
    first = diagnostics[0]
    assert first["stage"] == "sde3_component_scores"
    assert first["finish_reason"] == "length"
    assert first["unparsed_content"] == truncated_text
    assert first["response_id"] == "truncated-1"
    assert first["request_id"] == "req-1"
    assert first["expected_candidate_numbers"] == [1]
    assert "incomplete" in first["error"]
    assert results[0][0]["Final Score (/62)"] == 37.2
    assert results.usage["api_calls"] == 3


def test_deepseek_incomplete_response_preserves_raw_output_and_usage(model, monkeypatch) -> None:
    client = MagicMock()
    monkeypatch.setattr("candidate_evaluator.openai_scoring.OpenAI", MagicMock(return_value=client))
    truncated = '{"evaluations": ['

    def responses_response(text: str, **metadata):
        return SimpleNamespace(
            output_text=text,
            usage=SimpleNamespace(input_tokens=10, output_tokens=5, total_tokens=15),
            **metadata,
        )

    client.responses.create.side_effect = [
        responses_response(truncated, status="incomplete", incomplete_details=SimpleNamespace(reason="max_output_tokens")),
        responses_response(json.dumps({"evaluations": [_record(1)]}), status="completed"),
        responses_response(json.dumps({"evaluations": [_explanation(1)]}), status="completed"),
    ]

    results = evaluate_candidates(
        api_key="mock-key", model="deepseek-flash", rubric_text="Rubric",
        candidates=[_candidate(1)], role_key="sde3", provider_key="deepseek",
    )

    first = results[0][1]["provider_diagnostics"][0]
    assert first["status"] == "incomplete"
    assert first["incomplete_reason"] == "max_output_tokens"
    assert first["unparsed_content"] == truncated
    assert results[0][0]["Final Score (/62)"] == 37.2
    assert results.usage["api_calls"] == 3
    assert results.usage["total_tokens"] == 45


def _transport_error() -> APIStatusError:
    return APIStatusError(
        "upstream unavailable",
        response=httpx.Response(
            503,
            request=httpx.Request("POST", "https://provider.example.test/evaluations"),
            headers={"x-request-id": "request-503"},
        ),
        body={"error": "upstream unavailable"},
    )


def test_api_calls_count_completed_stage_requests_even_when_usage_is_absent(model) -> None:
    score_response = _response(_record(1))
    explanation_response = _response(_explanation(1))
    score_response.usage = explanation_response.usage = None
    model.side_effect = [score_response, explanation_response]

    results = _evaluate()

    assert model.call_count == 2
    assert results.usage["api_calls"] == 2
    assert results.usage["input_tokens"] == 0
    assert results.usage["output_tokens"] == 0
    assert results.usage["total_tokens"] == 0
    assert results[0][0]["Final Score (/62)"] == 37.2


def test_scoring_transport_failure_records_one_attempt_without_candidate_fan_out(model) -> None:
    model.side_effect = _transport_error()

    results = _evaluate(3)

    assert model.call_count == 1
    assert results.usage["api_calls"] == 1
    assert results.usage["total_tokens"] == 0
    assert all(grading == {} for grading, _ in results)
    for _, raw in results:
        assert raw["evaluation_error"] == "upstream unavailable"
        assert len(raw["provider_diagnostics"]) == 1
        receipt = raw["provider_diagnostics"][0]
        assert receipt["stage"] == "sde3_component_scores"
        assert receipt["expected_candidate_numbers"] == [1, 2, 3]
        assert receipt["request_failed"] is True
        assert receipt["status_code"] == 503
        assert receipt["request_id"] == "request-503"
        assert receipt["error"] == "upstream unavailable"


def test_explanation_transport_failure_counts_attempt_and_preserves_numeric_result(model) -> None:
    model.side_effect = [_response(_record(1)), _transport_error()]

    results = _evaluate()

    assert model.call_count == 2
    assert results.usage["api_calls"] == 2
    assert results.usage["total_tokens"] == 15
    grading, raw = results[0]
    assert grading["Final Score (/62)"] == 37.2
    assert raw["explanation_status"] == "calculated_summary"
    assert raw["explanation_error"] == "upstream unavailable"
    receipt = raw["provider_diagnostics"][1]
    assert receipt["stage"] == "sde3_score_explanations"
    assert receipt["request_failed"] is True
    assert receipt["status_code"] == 503
    assert receipt["request_id"] == "request-503"


def test_single_candidate_run_preserves_provider_diagnostics_when_scores_remain_invalid(model) -> None:
    from app import _evaluate_candidate_for_run

    broken = _scores()
    broken.pop("agent_evidence")
    model.side_effect = [_response(_record(1, broken)), _response(_record(1, broken))]

    result = _evaluate_candidate_for_run(
        "mock-key", "mock-model", "Rubric", _candidate(1), get_role_profile("sde3"),
    )

    assert model.call_count == 2
    assert result["state"] == "failed"
    assert "agent_evidence" in result["error"]
    assert "agent_evidence" in result["raw"]["evaluation_error"]
    diagnostics = result["raw"]["provider_diagnostics"]
    assert len(diagnostics) == 2
    assert all(receipt["expected_candidate_numbers"] == [1] for receipt in diagnostics)
    assert all("1" in receipt["invalid_candidates"] for receipt in diagnostics)


def test_batch_run_completes_valid_candidate_and_keeps_invalid_candidate_failure_isolated(model) -> None:
    from app import _evaluate_candidate_batch_for_run

    broken = _scores()
    broken["framework_duration"] = None
    model.side_effect = [
        _response(_record(1), _record(2, broken)),
        _response(_record(2, broken)),
        _response(_explanation(1)),
    ]

    run_result = _evaluate_candidate_batch_for_run(
        "mock-key", "mock-model", "Rubric", [_candidate(1), _candidate(2)], get_role_profile("sde3"),
    )

    assert [_numbers(model, index) for index in range(3)] == [[1, 2], [2], [1]]
    completed, failed = run_result["results"]
    assert completed["state"] == "completed"
    assert completed["row"]["Candidate"] == "Engineer 1"
    assert completed["row"]["Final Score (/62)"] == 37.2
    assert completed["row"]["Score Rationale"] == "Validated explanation for 1."
    assert failed["state"] == "failed"
    assert "framework_duration" in failed["error"]
    assert "row" not in failed
    assert failed["raw"]["candidate_number"] == 2
    assert len(failed["raw"]["provider_diagnostics"]) == 3
    assert run_result["usage"]["api_calls"] == 3
    assert run_result["usage"]["total_tokens"] == 45
