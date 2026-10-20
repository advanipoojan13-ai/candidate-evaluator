from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app import _default_rubric_path, _evaluate_candidate_batch_for_run, _evaluate_candidate_for_run
from candidate_evaluator.extractor import candidate_input_issue, normalize_candidate
from candidate_evaluator.openai_scoring import (
    ModelOutputFormatError,
    _candidate_payload,
    _response_schema,
    evaluate_candidates,
)
from candidate_evaluator.progress import init_run, role_for_run, run_dir
from candidate_evaluator.providers import DEEPSEEK_PROVIDER_KEY
from candidate_evaluator.roles import get_role_profile, prepare_output_rows, role_options
from candidate_evaluator.validation import apply_calculated_fields, coerce_fixed_row, validate_output_row


CAPABILITIES = [
    "Shipped AI Agent / Agent-Chatbot Delivery",
    "FastAPI / Django",
    "Backend / System Architecture",
    "AI Solution Breadth & Judgment",
]


def _candidate() -> dict:
    return normalize_candidate(
        {
            "publicIdentifier": "agent-engineer",
            "linkedinUrl": "https://www.linkedin.com/in/agent-engineer/",
            "fullName": "Agent Engineer",
            "headline": "Backend and GenAI Engineer",
            "about": "Builds agentic systems and scalable backends.",
            "location": "Bengaluru",
            "skills": ["Global skill that must not be sent"],
            "education": [{"schoolName": "Unscored University"}],
            "projects": [
                {
                    "name": "Support Agent",
                    "description": "Deployed an LLM support agent for internal users.",
                    "technologies": ["LangGraph", "FastAPI"],
                }
            ],
            "experience": [
                {
                    "companyName": "Current Co",
                    "title": "Software Engineer",
                    "description": "Built and deployed an AI agent using LangGraph and FastAPI.",
                    "location": "Bengaluru",
                    "employmentType": "Full-time",
                    "startDate": "2025-01",
                    "endDate": "Present",
                    "duration": "1 year 9 months",
                    "skills": ["FastAPI", "LangGraph"],
                }
            ],
        },
        0,
    )


def _model_grading(value: int = 2) -> dict:
    role = get_role_profile("sde3")
    grading = {column: value for column in role.component_score_maxima}
    grading.update(
        {
            "Shipped AI Agent / Agent-Chatbot Unverified": "No",
            "FastAPI / Django Unverified": "No",
            "Backend / System Architecture Unverified": "No",
            "Date-Quality Warning": "No",
            "Strongest Evidence": "Current Co: deployed AI agent | Current Co: FastAPI delivery | Support Agent: deployed LLM system",
            "Missing or Unclear Information": "Sustained ownership duration is not fully stated.",
            "Score Rationale": (
                "Shipped AI Agent / Agent-Chatbot Delivery: Current Co explicitly states that the candidate built and deployed an AI agent, while sustained ownership beyond the current role is not established. "
                "FastAPI / Django: The same current experience explicitly connects FastAPI to the delivered agent, but no earlier framework use is stated. "
                "Backend / System Architecture: The current role shows backend implementation, although broader architecture ownership and longer-term responsibility remain unclear. "
                "AI Solution Breadth & Judgment: LangGraph and retrieval work support applied AI breadth, but evaluation and model-selection decisions are not described. "
                "Overall: Strong current agent and FastAPI evidence is moderated by limited duration and architecture detail."
            ),
        }
    )
    return grading


def _calculated_row(grading: dict | None = None) -> dict:
    role = get_role_profile("sde3")
    candidate = _candidate()
    row = {
        "Candidate": candidate["candidate_name"],
        "Profile URL": candidate["linkedin_url"],
        "Rank Number": "",
        **(grading or _model_grading()),
    }
    return coerce_fixed_row(apply_calculated_fields(row, candidate, role), role)


def test_sde3_is_a_dedicated_selectable_role_with_bundled_rubric() -> None:
    role = get_role_profile("sde3")

    assert role_options()["SDE3"] == "sde3"
    assert role.role_name == "SDE3 - Agentic AI Technical Lead"
    assert role.total_column == "Final Score (/62)"
    assert role.total_max == 62
    assert sum(role.category_scores.values()) == 62
    assert len(role.component_score_maxima) == 12
    assert set(role.component_score_maxima).isdisjoint(role.output_columns)
    assert role.rationale_max_words == 200
    assert role.rationale_required_sections == [
        "Shipped AI Agent / Agent-Chatbot Delivery:",
        "FastAPI / Django:",
        "Backend / System Architecture:",
        "AI Solution Breadth & Judgment:",
    ]
    assert any("no more than 200 words" in instruction for instruction in role.instructions)
    assert Path(_default_rubric_path("sde3")).name == "sde3.md"
    assert Path(_default_rubric_path("sde3")).is_file()


def test_saved_run_restores_sde3_role_and_rubric(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init_run("sde3-run", [_candidate()], "# SDE3 rubric", "test-model", role_key="sde3")

    assert role_for_run("sde3-run").key == "sde3"
    assert (run_dir("sde3-run") / "rubric.md").read_text(encoding="utf-8") == "# SDE3 rubric"


def test_schema_requests_only_ai_judgments_with_exact_component_limits() -> None:
    role = get_role_profile("sde3")
    grading = _response_schema(role)["properties"]["grading"]
    requested = set(grading["required"])

    assert set(role.component_score_maxima) <= requested
    assert set(role.category_scores).isdisjoint(requested)
    assert {"Current Company", "Current Title", "Final Score (/62)", "Rank Number"}.isdisjoint(requested)
    for capability in CAPABILITIES:
        assert grading["properties"][f"{capability} — Evidence Points"] == {
            "type": "integer",
            "minimum": 0,
            "maximum": 4,
        }
        assert grading["properties"][f"{capability} — Recency Points"]["maximum"] == 3
        assert grading["properties"][f"{capability} — Evidenced Duration Points"]["maximum"] == 3


def test_python_calculates_weighted_scores_total_and_current_role() -> None:
    row = _calculated_row()

    assert row["Shipped AI Agent / Agent-Chatbot Delivery Score (/20)"] == 12.0
    assert row["FastAPI / Django Score (/18)"] == 10.8
    assert row["Backend / System Architecture Score (/14)"] == 8.4
    assert row["AI Solution Breadth & Judgment Score (/10)"] == 6.0
    assert row["Final Score (/62)"] == 37.2
    assert row["Current Company"] == "Current Co"
    assert row["Current Title"] == "Software Engineer"
    assert validate_output_row(row, "sde3") == []


def test_python_calculates_zero_and_maximum_boundaries() -> None:
    role = get_role_profile("sde3")
    zero = _model_grading()
    maximum = _model_grading()
    for component, cap in role.component_score_maxima.items():
        zero[component] = 0
        maximum[component] = cap

    assert _calculated_row(zero)["Final Score (/62)"] == 0
    assert _calculated_row(maximum)["Final Score (/62)"] == 62


def test_python_overwrites_model_supplied_scores_total_and_ranking_overwrites_rank() -> None:
    role = get_role_profile("sde3")
    grading = _model_grading()
    grading.update({column: 0 for column in role.category_scores})
    grading["Final Score (/62)"] = 0
    grading["Rank Number"] = 99

    row = _calculated_row(grading)

    assert row["Shipped AI Agent / Agent-Chatbot Delivery Score (/20)"] == 12.0
    assert row["Final Score (/62)"] == 37.2
    assert prepare_output_rows([row], "sde3")[0]["Rank Number"] == 1


def test_validation_rejects_missing_fractional_and_out_of_range_components() -> None:
    missing = _calculated_row()
    missing["FastAPI / Django — Recency Points"] = ""
    assert any("must be a whole number" in error for error in validate_output_row(missing, "sde3"))

    fractional = _calculated_row()
    fractional["Backend / System Architecture — Evidence Points"] = 2.5
    assert any("must be a whole number" in error for error in validate_output_row(fractional, "sde3"))

    excessive = _calculated_row()
    excessive["AI Solution Breadth & Judgment — Evidenced Duration Points"] = 4
    assert any("must be between 0 and 3" in error for error in validate_output_row(excessive, "sde3"))


def test_validation_enforces_warnings_evidence_count_and_rationale_limit() -> None:
    row = _calculated_row()
    row["Date-Quality Warning"] = "Maybe"
    row["Strongest Evidence"] = "One | Two | Three | Four"
    row["Score Rationale"] = "word " * 201

    errors = validate_output_row(row, "sde3")

    assert any("Date-Quality Warning must be one of" in error for error in errors)
    assert any("Strongest Evidence has more than three items" in error for error in errors)
    assert any("no longer than 200 words" in error for error in errors)


def test_validation_requires_all_rationale_sections_in_order() -> None:
    missing = _calculated_row()
    missing["Score Rationale"] = missing["Score Rationale"].replace(
        "FastAPI / Django:", "Framework experience:"
    )
    assert any(
        "must cover all required sections" in error for error in validate_output_row(missing, "sde3")
    )

    out_of_order = _calculated_row()
    out_of_order["Score Rationale"] = (
        "FastAPI / Django: Current experience supports the framework. "
        "Shipped AI Agent / Agent-Chatbot Delivery: Current experience supports delivery. "
        "Backend / System Architecture: Current experience supports backend work. "
        "AI Solution Breadth & Judgment: Current experience supports applied AI work. "
        "Overall: Evidence is current but duration is limited."
    )
    assert any(
        "sections must appear in the required order" in error
        for error in validate_output_row(out_of_order, "sde3")
    )


def test_validation_accepts_detailed_rationale_above_old_limit() -> None:
    row = _calculated_row()
    assert len(row["Score Rationale"].split()) > 50
    assert validate_output_row(row, "sde3") == []


def test_validation_accepts_overall_conclusion_without_exact_heading() -> None:
    row = _calculated_row()
    row["Score Rationale"] = row["Score Rationale"].replace(
        "Overall:", "In summary,"
    )

    assert validate_output_row(row, "sde3") == []


def test_ranking_uses_sde3_capability_order_then_candidate_name() -> None:
    base = _calculated_row()
    higher_agent = {
        **base,
        "Candidate": "Zulu",
        "Shipped AI Agent / Agent-Chatbot Delivery Score (/20)": 13.0,
        "FastAPI / Django Score (/18)": 9.8,
    }
    higher_fastapi = {
        **base,
        "Candidate": "Alpha",
        "Shipped AI Agent / Agent-Chatbot Delivery Score (/20)": 12.0,
        "FastAPI / Django Score (/18)": 10.8,
    }
    higher_agent["Final Score (/62)"] = higher_fastapi["Final Score (/62)"] = 37.2

    ranked = prepare_output_rows([higher_fastapi, higher_agent], "sde3")
    assert [row["Candidate"] for row in ranked] == ["Zulu", "Alpha"]
    assert [row["Rank Number"] for row in ranked] == [1, 2]

    alphabetical = prepare_output_rows(
        [{**base, "Candidate": "Beta"}, {**base, "Candidate": "Alpha"}],
        "sde3",
    )
    assert [row["Candidate"] for row in alphabetical] == ["Alpha", "Beta"]


def test_payload_is_cleaned_merged_and_filtered_before_ai() -> None:
    candidate = normalize_candidate(
        {
            "publicIdentifier": "clean-me",
            "linkedinUrl": "https://www.linkedin.com/in/clean-me/",
            "fullName": "Clean Me",
            "headline": "Agent Engineer",
            "about": "Builds AI agents.",
            "location": "Must not be sent",
            "skills": ["Global skill must not be sent"],
            "education": [{"schoolName": "Must not be sent"}],
            "websites": ["https://must-not-be-sent.example"],
            "projects": [{"title": "Agent", "summary": "Deployed agent", "techStack": ["LangGraph"]}],
            "experience": [
                {
                    "companyName": "Example",
                    "title": "Engineer",
                    "description": "Built an AI agent.",
                    "location": "Must not be sent",
                    "employmentType": "Full-time",
                    "startDate": "2024",
                    "endDate": "Present",
                    "duration": "2 years",
                    "skills": ["FastAPI"],
                },
                {
                    "companyName": "Example",
                    "title": "Engineer",
                    "description": "Designed its retrieval architecture.",
                    "startDate": "2024",
                    "endDate": "Present",
                    "duration": "2 years",
                    "skills": ["LangGraph"],
                },
            ],
        },
        0,
    )

    payload = _candidate_payload(candidate, get_role_profile("sde3"))

    assert set(payload) == {
        "LinkedIn Profile ID",
        "LinkedIn URL",
        "Candidate Name",
        "Headline",
        "About",
        "Projects",
        "experiences",
    }
    assert len(payload["experiences"]) == 1
    experience = payload["experiences"][0]
    assert experience["description"] == "Built an AI agent. | Designed its retrieval architecture."
    assert experience["experience_skills"] == ["FastAPI", "LangGraph"]
    assert set(experience) == {
        "index",
        "company_name",
        "position_or_title",
        "description",
        "start_date",
        "end_date",
        "is_current",
        "duration",
        "experience_skills",
    }
    assert payload["Projects"] == [
        {"name": "Agent", "description": "Deployed agent", "technologies": ["LangGraph"]}
    ]
    assert "Location" not in payload and "Skills" not in payload and "Education" not in payload


def test_sparse_valid_profiles_continue_but_invalid_identity_and_post_urls_skip() -> None:
    role = get_role_profile("sde3")
    sparse = normalize_candidate(
        {
            "publicIdentifier": "sparse",
            "linkedinUrl": "https://www.linkedin.com/in/sparse/",
            "fullName": "Sparse Candidate",
        },
        0,
    )
    assert role.skip_if_no_evidence is False
    assert candidate_input_issue(
        sparse,
        role.key,
        role.evidence_sources,
        role.require_experience,
        role.skip_if_no_evidence,
    ) == ""

    missing_name = {**sparse, "candidate_name": ""}
    missing_url = {**sparse, "linkedin_url": ""}
    post_url = {**sparse, "linkedin_url": "https://www.linkedin.com/posts/not-a-profile"}
    assert "candidate name is empty" in candidate_input_issue(
        missing_name, role.key, role.evidence_sources, False, False
    )
    assert "LinkedIn profile URL is empty" in candidate_input_issue(
        missing_url, role.key, role.evidence_sources, False, False
    )
    assert "post/activity" in candidate_input_issue(post_url, role.key, role.evidence_sources, False, False)


@patch("candidate_evaluator.openai_scoring.OpenAI")
def test_sde3_batch_uses_one_ai_request_with_cleaned_candidates(mock_openai) -> None:
    role = get_role_profile("sde3")
    evaluations = [
        {"candidate_number": number, "grading": _model_grading()}
        for number in (1, 2)
    ]
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({"evaluations": evaluations})))],
        usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50, total_tokens=150),
    )
    create = mock_openai.return_value.chat.completions.create
    create.return_value = response

    results = evaluate_candidates(
        api_key="test-key",
        model="test-model",
        rubric_text="SDE3 rubric",
        candidates=[_candidate(), _candidate()],
        role_profile=role,
    )

    assert len(results) == 2
    mock_openai.assert_called_once_with(api_key="test-key", max_retries=0)
    create.assert_called_once()
    request_payload = json.loads(create.call_args.kwargs["messages"][1]["content"])
    for item in request_payload["candidates"]:
        sent = item["candidate"]
        assert "Location" not in sent and "Education" not in sent and "Skills" not in sent
        assert set(sent["experiences"][0]) <= set(role.experience_fields)


def test_sde3_unreadable_deepseek_batch_is_not_resent_or_split(monkeypatch) -> None:
    calls = 0

    def unreadable_batch(**_kwargs):
        nonlocal calls
        calls += 1
        raise ModelOutputFormatError(
            "invalid batch response",
            "not-json",
            {"api_calls": 1, "input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
        )

    monkeypatch.setattr("candidate_evaluator.openai_scoring.evaluate_candidates", unreadable_batch)
    result = _evaluate_candidate_batch_for_run(
        "key",
        "model",
        "rubric",
        [_candidate(), _candidate()],
        get_role_profile("sde3"),
        provider_key=DEEPSEEK_PROVIDER_KEY,
    )

    assert calls == 1
    assert [item["state"] for item in result["results"]] == ["skipped", "skipped"]
    assert result["usage"]["api_calls"] == 1


def test_full_flow_completes_valid_output_skips_invalid_output_and_marks_request_failure(monkeypatch) -> None:
    role = get_role_profile("sde3")
    grading = _model_grading()

    def valid_evaluation(**_kwargs):
        return deepcopy(grading), {"grading": deepcopy(grading)}

    monkeypatch.setattr("candidate_evaluator.openai_scoring.evaluate_candidate", valid_evaluation)
    completed = _evaluate_candidate_for_run("key", "model", "rubric", _candidate(), role)
    assert completed["state"] == "completed"
    assert completed["row"]["Final Score (/62)"] == 37.2

    def invalid_evaluation(**_kwargs):
        invalid = deepcopy(grading)
        invalid.pop("FastAPI / Django — Evidence Points")
        return invalid, {"grading": invalid}

    monkeypatch.setattr("candidate_evaluator.openai_scoring.evaluate_candidate", invalid_evaluation)
    skipped = _evaluate_candidate_for_run("key", "model", "rubric", _candidate(), role)
    assert skipped["state"] == "skipped"
    assert "incomplete or invalid" in skipped["error"]

    def failed_evaluation(**_kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr("candidate_evaluator.openai_scoring.evaluate_candidate", failed_evaluation)
    failed = _evaluate_candidate_for_run("key", "model", "rubric", _candidate(), role)
    assert failed["state"] == "failed"
    assert failed["error"] == "provider unavailable"
