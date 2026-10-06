from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from candidate_evaluator import openai_scoring
from candidate_evaluator.openai_scoring import ModelOutputFormatError, evaluate_candidate, evaluate_candidates
from candidate_evaluator.providers import (
    DEEPSEEK_PROVIDER_KEY,
    OPENAI_PROVIDER_KEY,
    get_provider,
    provider_options,
)
from candidate_evaluator.roles import get_role_profile


class _FakeEndpoint:
    def __init__(self, response: object | list[object]) -> None:
        self.responses = response if isinstance(response, list) else [response]
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses[min(len(self.calls) - 1, len(self.responses) - 1)]


class _FakeClient:
    def __init__(self, response_json: dict) -> None:
        content = json.dumps(response_json)
        self.responses = _FakeEndpoint(SimpleNamespace(output_text=content))
        self.chat = SimpleNamespace(
            completions=_FakeEndpoint(
                SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])
            )
        )


def _candidate() -> dict:
    return {
        "linkedin_profile_id": "person",
        "linkedin_url": "https://linkedin.com/in/person",
        "candidate_name": "Example Person",
        "headline": "Product Designer",
        "about": "Designs products.",
        "website": "",
        "education": [],
        "experiences": [],
    }


def _batch_response(grading: dict) -> dict:
    return {"evaluations": [{"candidate_number": 1, "grading": grading}]}


def test_provider_registry_exposes_current_deepseek_models() -> None:
    assert provider_options() == {"OpenAI": "openai", "DeepSeek": "deepseek"}
    deepseek = get_provider(DEEPSEEK_PROVIDER_KEY)
    assert deepseek.base_url == "https://api.deepseek.com"
    assert deepseek.default_model == "deepseek-flash"
    assert deepseek.model_options["DeepSeek V4 Pro"] == "deepseek-v4-pro"
    assert deepseek.default_reasoning_effort == "none"


def test_deepseek_uses_responses_json_schema_and_selected_reasoning(monkeypatch) -> None:
    clients: list[tuple[dict, _FakeClient]] = []

    def fake_openai(**kwargs):
        client = _FakeClient(_batch_response({"Total Score": 0}))
        clients.append((kwargs, client))
        return client

    monkeypatch.setattr(openai_scoring, "OpenAI", fake_openai)
    grading, _ = evaluate_candidate(
        api_key="deepseek-key",
        provider_key=DEEPSEEK_PROVIDER_KEY,
        model="deepseek-flash",
        reasoning_effort="low",
        rubric_text="A rubric",
        candidate=_candidate(),
        role_profile=get_role_profile("design"),
        max_retries=0,
    )

    client_args, client = clients[0]
    assert grading == {"Total Score": 0}
    assert client_args == {"api_key": "deepseek-key", "max_retries": 0, "base_url": "https://api.deepseek.com"}
    assert client.chat.completions.calls == []
    request = client.responses.calls[0]
    assert request["model"] == "deepseek-flash"
    assert request["reasoning"] == {"effort": "low"}
    assert request["max_output_tokens"] == 16000
    assert request["text"]["format"]["type"] == "json_schema"
    assert request["text"]["format"]["name"] == "candidate_evaluation_batch"
    assert request["text"]["format"]["schema"]["additionalProperties"] is False


def test_deepseek_high_reasoning_uses_larger_batch_output_allowance(monkeypatch) -> None:
    client = _FakeClient(_batch_response({"Total Score": 0}))
    monkeypatch.setattr(openai_scoring, "OpenAI", lambda **_kwargs: client)

    evaluate_candidate(
        api_key="deepseek-key",
        provider_key=DEEPSEEK_PROVIDER_KEY,
        model="deepseek-flash",
        reasoning_effort="high",
        rubric_text="A rubric",
        candidate=_candidate(),
        role_profile=get_role_profile("design"),
        max_retries=0,
    )

    request = client.responses.calls[0]
    assert request["reasoning"] == {"effort": "high"}
    assert request["max_output_tokens"] == 48000


def test_openai_keeps_strict_chat_completions_transport(monkeypatch) -> None:
    clients: list[tuple[dict, _FakeClient]] = []

    def fake_openai(**kwargs):
        client = _FakeClient(_batch_response({"Total Score": 0}))
        clients.append((kwargs, client))
        return client

    monkeypatch.setattr(openai_scoring, "OpenAI", fake_openai)
    evaluate_candidate(
        api_key="openai-key",
        provider_key=OPENAI_PROVIDER_KEY,
        model="gpt-5.5",
        rubric_text="A rubric",
        candidate=_candidate(),
        role_profile=get_role_profile("design"),
        max_retries=0,
    )

    client_args, client = clients[0]
    assert client_args == {"api_key": "openai-key", "max_retries": 0}
    assert client.responses.calls == []
    request = client.chat.completions.calls[0]
    assert request["response_format"]["type"] == "json_schema"
    assert request["response_format"]["json_schema"]["strict"] is True


def test_deepseek_batches_five_candidates_in_one_call(monkeypatch) -> None:
    batch = {
        "evaluations": [
            {"candidate_number": number, "grading": {"Total Score": number}}
            for number in range(1, 6)
        ]
    }
    client = _FakeClient(batch)
    monkeypatch.setattr(openai_scoring, "OpenAI", lambda **_kwargs: client)

    results = evaluate_candidates(
        api_key="deepseek-key",
        provider_key=DEEPSEEK_PROVIDER_KEY,
        model="deepseek-flash",
        rubric_text="Shared rubric",
        candidates=[{**_candidate(), "linkedin_profile_id": f"person-{number}"} for number in range(1, 6)],
        role_profile=get_role_profile("design"),
        max_retries=0,
    )

    assert len(results) == 5
    assert len(client.responses.calls) == 1
    request = client.responses.calls[0]
    assert "Shared rubric" in request["instructions"]
    assert len(json.loads(request["input"])["candidates"]) == 5
    assert request["text"]["format"]["name"] == "candidate_evaluation_batch"


def test_deepseek_accepts_valid_json_with_trailing_text_without_retry(monkeypatch) -> None:
    valid = json.dumps(_batch_response({"Total Score": 42}))
    client = _FakeClient(_batch_response({}))
    client.responses = _FakeEndpoint(SimpleNamespace(output_text=valid + "\nAdditional explanation"))
    monkeypatch.setattr(openai_scoring, "OpenAI", lambda **kwargs: client)

    grading, raw = evaluate_candidate(
        api_key="deepseek-key",
        provider_key=DEEPSEEK_PROVIDER_KEY,
        model="deepseek-flash",
        rubric_text="A rubric",
        candidate=_candidate(),
        role_profile=get_role_profile("design"),
        max_retries=0,
    )

    assert grading == {"Total Score": 42}
    assert raw == {"candidate_number": 1, "grading": {"Total Score": 42}}
    assert len(client.responses.calls) == 1


@pytest.mark.parametrize(
    "malformed",
    [
        '{"evaluations":[{"candidate_number":1 "grading":{"Total Score":42}}]}',
        '{"evaluations":[{"candidate_number":1,"grading":{"Total Score":42,}},]}',
        '{"evaluations":[{"candidate_number":1,"grading":{"Total Score":42}}]',
    ],
)
def test_deepseek_repairs_common_json_syntax_errors_locally_without_retry(monkeypatch, malformed: str) -> None:
    client = _FakeClient(_batch_response({}))
    client.responses = _FakeEndpoint(SimpleNamespace(output_text=malformed))
    monkeypatch.setattr(openai_scoring, "OpenAI", lambda **_kwargs: client)

    grading, raw = evaluate_candidate(
        api_key="deepseek-key",
        provider_key=DEEPSEEK_PROVIDER_KEY,
        model="deepseek-flash",
        rubric_text="A rubric",
        candidate=_candidate(),
        role_profile=get_role_profile("design"),
        max_retries=0,
    )

    assert grading == {"Total Score": 42}
    assert raw["_response_format_repaired"] is True
    assert len(client.responses.calls) == 1


def test_deepseek_repaired_json_still_requires_complete_batch(monkeypatch) -> None:
    malformed = '{"evaluations":[{"candidate_number":1,"grading":{"Total Score":42}},]}'
    client = _FakeClient(_batch_response({}))
    client.responses = _FakeEndpoint(SimpleNamespace(output_text=malformed))
    monkeypatch.setattr(openai_scoring, "OpenAI", lambda **_kwargs: client)

    with pytest.raises(ModelOutputFormatError, match="different number or order"):
        evaluate_candidates(
            api_key="deepseek-key",
            provider_key=DEEPSEEK_PROVIDER_KEY,
            model="deepseek-flash",
            rubric_text="A rubric",
            candidates=[_candidate(), {**_candidate(), "linkedin_profile_id": "person-2"}],
            role_profile=get_role_profile("design"),
            max_retries=0,
        )

    assert len(client.responses.calls) == 1


def test_deepseek_uses_first_complete_json_when_another_object_follows(monkeypatch) -> None:
    first = json.dumps(_batch_response({"Total Score": 42}))
    second = json.dumps(_batch_response({"Total Score": 99}))
    client = _FakeClient(_batch_response({}))
    client.responses = _FakeEndpoint(SimpleNamespace(output_text=first + second))
    monkeypatch.setattr(openai_scoring, "OpenAI", lambda **kwargs: client)

    grading, _ = evaluate_candidate(
        api_key="deepseek-key",
        provider_key=DEEPSEEK_PROVIDER_KEY,
        model="deepseek-flash",
        rubric_text="A rubric",
        candidate=_candidate(),
        role_profile=get_role_profile("design"),
        max_retries=0,
    )

    assert grading == {"Total Score": 42}
    assert len(client.responses.calls) == 1


def test_deepseek_accepts_json_surrounded_by_markdown_without_retry(monkeypatch) -> None:
    valid = json.dumps(_batch_response({"Total Score": 31}))
    client = _FakeClient(_batch_response({}))
    client.responses = _FakeEndpoint(SimpleNamespace(output_text=f"Result:\n```json\n{valid}\n```"))
    monkeypatch.setattr(openai_scoring, "OpenAI", lambda **kwargs: client)

    grading, _ = evaluate_candidate(
        api_key="deepseek-key",
        provider_key=DEEPSEEK_PROVIDER_KEY,
        model="deepseek-flash",
        rubric_text="A rubric",
        candidate=_candidate(),
        role_profile=get_role_profile("design"),
        max_retries=0,
    )

    assert grading == {"Total Score": 31}
    assert len(client.responses.calls) == 1


def test_malformed_deepseek_response_is_not_retried(monkeypatch) -> None:
    malformed = '{"grading": {"Total Score": 10,}}'
    client = _FakeClient(_batch_response({}))
    client.responses = _FakeEndpoint(
        [
            SimpleNamespace(output_text=malformed),
            SimpleNamespace(output_text=json.dumps(_batch_response({"Total Score": 10}))),
        ]
    )
    monkeypatch.setattr(openai_scoring, "OpenAI", lambda **kwargs: client)

    with pytest.raises(ModelOutputFormatError) as caught:
        evaluate_candidate(
            api_key="deepseek-key",
            provider_key=DEEPSEEK_PROVIDER_KEY,
            model="deepseek-flash",
            rubric_text="A rubric",
            candidate=_candidate(),
            role_profile=get_role_profile("design"),
            max_retries=0,
            max_format_retries=5,
        )

    assert caught.value.raw_content == malformed
    assert len(client.responses.calls) == 1


def test_empty_deepseek_response_is_not_retried(monkeypatch) -> None:
    valid = json.dumps(_batch_response({"Total Score": 0}))
    client = _FakeClient(_batch_response({}))
    client.responses = _FakeEndpoint(
        [
            SimpleNamespace(output_text=""),
            SimpleNamespace(output_text=valid),
        ]
    )
    monkeypatch.setattr(openai_scoring, "OpenAI", lambda **kwargs: client)

    with pytest.raises(ModelOutputFormatError):
        evaluate_candidate(
            api_key="deepseek-key",
            provider_key=DEEPSEEK_PROVIDER_KEY,
            model="deepseek-flash",
            rubric_text="A rubric",
            candidate=_candidate(),
            role_profile=get_role_profile("design"),
            max_retries=0,
            max_format_retries=1,
        )

    assert len(client.responses.calls) == 1
