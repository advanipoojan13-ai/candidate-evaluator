from __future__ import annotations

from pathlib import Path

import pytest

from app import _default_rubric_path, _evaluate_candidate_for_run
from candidate_evaluator.extractor import candidate_input_issue, normalize_candidate
from candidate_evaluator.openai_scoring import _candidate_payload, _response_schema
from candidate_evaluator.roles import get_role_profile, prepare_output_rows, role_options
from candidate_evaluator.validation import validate_output_row


def _valid_ai_row() -> dict:
    role = get_role_profile("ai_engineer_trj")
    row = {column: "" for column in set(role.output_columns + role.grading_columns)}
    row.update(
        {
            "Candidate": "Ada Example",
            "Profile URL": "https://www.linkedin.com/in/ada-example/",
            "Current Company": "Example Labs",
            "Current Title": "Senior AI Engineer",
            "AI / LLM / Agentic Systems Score (/30)": 24.0,
            "Python Score (/25)": 20.0,
            "API & System Integration Score (/20)": 16.0,
            "Workflow Automation Score (/15)": 10.5,
            "TypeScript / Node.js Score (/5)": 3.5,
            "Ownership / Production Maturity Score (/5)": 4.0,
            "Final Score (/100)": 78.0,
            "AI / LLM / Agentic Systems Unverified": "No",
            "Python Unverified": "No",
            "API & System Integration Unverified": "No",
            "Seniority Unverified": "No",
            "Date-Quality Warning": "No",
            "Evidence Confidence": "High",
            "Strongest Evidence 1": "Built and deployed a dated RAG application using Python.",
            "Strongest Evidence 2": "Integrated production APIs and business systems.",
            "Strongest Evidence 3": "Owned monitoring and reliability improvements.",
            "Missing or Unclear Information": "TypeScript duration is only partly evidenced.",
            "Score Rationale": (
                "Recent dated experience provides concrete evidence of building and deploying LLM applications with Python, APIs, "
                "and multi-system business workflows. Descriptions also support end-to-end delivery, monitoring, and production "
                "operation. The strongest depth is in AI, Python, and integration work, while TypeScript duration is less fully "
                "documented and therefore receives a more conservative score."
            ),
        }
    )
    return row


def test_ai_engineer_role_exposes_exact_ranked_output_contract() -> None:
    role = get_role_profile("ai_engineer_trj")
    assert role_options()["AI Engineer TRJ"] == "ai_engineer_trj"
    assert role.output_columns[0:5] == [
        "Rank Number",
        "Candidate",
        "Profile URL",
        "Current Company",
        "Current Title",
    ]
    assert role.output_columns[-1] == "Score Rationale"
    assert role.total_column == "Final Score (/100)"
    assert role.total_max == 100
    assert role.ranked is True
    assert sum(role.category_scores.values()) == 100


def test_ai_engineer_validation_accepts_decimals_and_enforces_contract() -> None:
    row = _valid_ai_row()
    assert validate_output_row(row, "ai_engineer_trj") == []

    row["Final Score (/100)"] = 79
    row["Date-Quality Warning"] = "Maybe"
    errors = validate_output_row(row, "ai_engineer_trj")
    assert any("must equal category score sum" in error for error in errors)
    assert any("Date-Quality Warning must be one of" in error for error in errors)


def test_ai_engineer_validation_does_not_reject_rationale_word_count() -> None:
    row = _valid_ai_row()
    row["Score Rationale"] = "Brief rationale."
    assert validate_output_row(row, "ai_engineer_trj") == []

    row["Score Rationale"] = "word " * 100
    assert validate_output_row(row, "ai_engineer_trj") == []


@pytest.mark.parametrize("rationale", ["Brief rationale.", "word " * 100])
def test_ai_engineer_full_evaluation_flow_accepts_any_rationale_length(monkeypatch, rationale: str) -> None:
    grading = _valid_ai_row()
    grading["Score Rationale"] = rationale

    def fake_evaluate_candidate(**_kwargs):
        return grading, {"grading": grading}

    monkeypatch.setattr("candidate_evaluator.openai_scoring.evaluate_candidate", fake_evaluate_candidate)
    candidate = {
        "linkedin_profile_id": "ada-example",
        "linkedin_url": "https://www.linkedin.com/in/ada-example/",
        "candidate_name": "Ada Example",
        "source_row": {},
    }

    result = _evaluate_candidate_for_run(
        "unused-api-key",
        "unused-model",
        "unused-rubric",
        candidate,
        get_role_profile("ai_engineer_trj"),
    )

    assert result["state"] == "completed"


def test_ai_engineer_full_evaluation_flow_still_skips_invalid_scores(monkeypatch) -> None:
    grading = _valid_ai_row()
    grading["Final Score (/100)"] = 79

    def fake_evaluate_candidate(**_kwargs):
        return grading, {"grading": grading}

    monkeypatch.setattr("candidate_evaluator.openai_scoring.evaluate_candidate", fake_evaluate_candidate)
    candidate = {
        "linkedin_profile_id": "ada-example",
        "linkedin_url": "https://www.linkedin.com/in/ada-example/",
        "candidate_name": "Ada Example",
        "source_row": {},
    }

    result = _evaluate_candidate_for_run(
        "unused-api-key",
        "unused-model",
        "unused-rubric",
        candidate,
        get_role_profile("ai_engineer_trj"),
    )

    assert result["state"] == "skipped"
    assert "must equal category score sum" in result["error"]


def test_ai_engineer_ranking_uses_documented_capability_order() -> None:
    base = _valid_ai_row()
    alpha = {
        **base,
        "Candidate": "Alpha",
        "Profile URL": "alpha",
        "AI / LLM / Agentic Systems Score (/30)": 25,
        "Python Score (/25)": 19,
    }
    beta = {
        **base,
        "Candidate": "Beta",
        "Profile URL": "beta",
        "AI / LLM / Agentic Systems Score (/30)": 24,
        "Python Score (/25)": 20,
    }
    ranked = prepare_output_rows([beta, alpha], "ai_engineer_trj")
    assert [row["Candidate"] for row in ranked] == ["Alpha", "Beta"]
    assert [row["Rank Number"] for row in ranked] == [1, 2]

    ownership_first = {
        **base,
        "Candidate": "Ownership First",
        "Profile URL": "ownership",
        "Ownership / Production Maturity Score (/5)": 5,
        "TypeScript / Node.js Score (/5)": 2.5,
    }
    typescript_first = {
        **base,
        "Candidate": "TypeScript First",
        "Profile URL": "typescript",
        "Ownership / Production Maturity Score (/5)": 3,
        "TypeScript / Node.js Score (/5)": 4.5,
    }
    ranked = prepare_output_rows([typescript_first, ownership_first], "ai_engineer_trj")
    assert [row["Candidate"] for row in ranked] == ["Ownership First", "TypeScript First"]


def test_ai_engineer_payload_includes_only_permitted_evidence_and_merges_duplicates() -> None:
    profile = {
        "publicIdentifier": "ada-example",
        "linkedinUrl": "https://www.linkedin.com/in/ada-example/",
        "fullName": "Ada Example",
        "headline": "AI Engineer",
        "about": "Builds agentic systems.",
        "location": "Bengaluru",
        "skills": ["Unscored global skill"],
        "education": [{"schoolName": "Example University"}],
        "projects": [
            {
                "title": "Support agent",
                "description": "Built a tool-using support agent.",
                "technologies": ["LangGraph", {"name": "Python"}],
            }
        ],
        "experience": [
            {
                "companyName": "Example Labs",
                "title": "AI Engineer",
                "startDate": "2024",
                "endDate": "Present",
                "duration": "2 years",
                "description": "Built RAG APIs.",
                "skills": ["Python"],
            },
            {
                "companyName": "Example Labs",
                "title": "AI Engineer",
                "startDate": "2024",
                "endDate": "Present",
                "duration": "2 years",
                "description": "Deployed agent workflows.",
                "skills": ["LangGraph"],
            },
        ],
    }
    candidate = normalize_candidate(profile, 0)
    payload = _candidate_payload(candidate, get_role_profile("ai_engineer_trj"))

    assert payload["Location"] == "Bengaluru"
    assert payload["Projects"] == [
        {
            "name": "Support agent",
            "description": "Built a tool-using support agent.",
            "technologies": ["LangGraph", "Python"],
        }
    ]
    assert len(payload["experiences"]) == 1
    assert payload["experiences"][0]["description"] == "Built RAG APIs. | Deployed agent workflows."
    assert "Skills" not in payload
    assert "Education" not in payload


def test_ai_engineer_project_only_profile_is_scorable() -> None:
    candidate = normalize_candidate(
        {
            "publicIdentifier": "project-person",
            "linkedinUrl": "https://www.linkedin.com/in/project-person/",
            "fullName": "Project Person",
            "projects": [{"title": "RAG prototype", "description": "Built a RAG prototype."}],
        },
        0,
    )
    role = get_role_profile("ai_engineer_trj")
    assert candidate_input_issue(
        candidate,
        role.key,
        role.evidence_sources,
        role.require_experience,
        role.skip_if_no_evidence,
    ) == ""


def test_ai_engineer_sparse_profile_is_scored_instead_of_excluded() -> None:
    candidate = normalize_candidate(
        {
            "publicIdentifier": "sparse-person",
            "linkedinUrl": "https://www.linkedin.com/in/sparse-person/",
            "fullName": "Sparse Person",
            "education": [{"schoolName": "Example University"}],
        },
        0,
    )
    role = get_role_profile("ai_engineer_trj")

    assert role.skip_if_no_evidence is False
    assert candidate_input_issue(
        candidate,
        role.key,
        role.evidence_sources,
        role.require_experience,
        role.skip_if_no_evidence,
    ) == ""
    assert _candidate_payload(candidate, role) == {
        "LinkedIn Profile ID": "sparse-person",
        "LinkedIn URL": "https://www.linkedin.com/in/sparse-person/",
        "Candidate Name": "Sparse Person",
    }


def test_ai_engineer_schema_and_bundled_rubric_exclude_rank_from_model_response() -> None:
    role = get_role_profile("ai_engineer_trj")
    schema = _response_schema(role)
    grading = schema["properties"]["grading"]
    assert "Rank Number" not in grading["required"]
    assert grading["properties"]["Final Score (/100)"]["type"] == "number"

    rubric_path = Path(_default_rubric_path("ai_engineer_trj"))
    assert rubric_path.name == "ai_engineer_trj.md"
    assert rubric_path.exists()
    assert "Rank Number: [Rank]" in rubric_path.read_text(encoding="utf-8")
