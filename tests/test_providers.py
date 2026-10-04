from __future__ import annotations

import json
from types import SimpleNamespace

from candidate_evaluator import openai_scoring
from candidate_evaluator.openai_scoring import evaluate_candidate
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
        client = _FakeClient({"grading": {"Total Score": 0}})
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
    assert client_args == {"api_key": "deepseek-key", "base_url": "https://api.deepseek.com"}
    assert client.chat.completions.calls == []
    request = client.responses.calls[0]
    assert request["model"] == "deepseek-flash"
    assert request["reasoning"] == {"effort": "low"}
    assert request["text"]["format"]["type"] == "json_schema"
    assert request["text"]["format"]["name"] == "candidate_evaluation"
    assert request["text"]["format"]["schema"]["additionalProperties"] is False


def test_openai_keeps_strict_chat_completions_transport(monkeypatch) -> None:
    clients: list[tuple[dict, _FakeClient]] = []

    def fake_openai(**kwargs):
        client = _FakeClient({"grading": {"Total Score": 0}})
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
    assert client_args == {"api_key": "openai-key"}
    assert client.responses.calls == []
    request = client.chat.completions.calls[0]
    assert request["response_format"]["type"] == "json_schema"
    assert request["response_format"]["json_schema"]["strict"] is True


def test_empty_deepseek_response_is_retried_before_candidate_is_skipped(monkeypatch) -> None:
    valid = json.dumps({"grading": {"Total Score": 0}})
    client = _FakeClient({"grading": {}})
    client.responses = _FakeEndpoint(
        [
            SimpleNamespace(output_text=""),
            SimpleNamespace(output_text=valid),
        ]
    )
    monkeypatch.setattr(openai_scoring, "OpenAI", lambda **kwargs: client)
    monkeypatch.setattr(openai_scoring.time, "sleep", lambda seconds: None)

    grading, _ = evaluate_candidate(
        api_key="deepseek-key",
        provider_key=DEEPSEEK_PROVIDER_KEY,
        model="deepseek-flash",
        rubric_text="A rubric",
        candidate=_candidate(),
        role_profile=get_role_profile("design"),
        max_retries=0,
        max_format_retries=1,
    )

    assert grading == {"Total Score": 0}
    assert len(client.responses.calls) == 2
