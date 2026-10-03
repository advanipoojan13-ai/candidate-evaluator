from __future__ import annotations

from pathlib import Path

from candidate_evaluator.evidence import CUSTOM_EVIDENCE_SOURCES
from candidate_evaluator.extractor import candidate_input_issue, normalize_candidate
from candidate_evaluator.openai_scoring import _candidate_payload
from candidate_evaluator.progress import init_run, load_status, role_for_run
from candidate_evaluator.roles import (
    CUSTOM_ROLE_KEY,
    get_role_profile,
    validate_custom_role_config,
)
from candidate_evaluator.validation import validate_output_row


def valid_custom_config() -> dict:
    return {
        "role_name": "Data Engineer",
        "categories": [
            {"name": "Data Modelling", "max_score": 20, "allowed_scores": [0, 10, 20]},
            {"name": "Pipelines", "max_score": 30, "allowed_scores": []},
        ],
        "outcome_column": "Decision",
        "outcome_bands": [
            {"minimum": 0, "maximum": 24, "label": "Reject"},
            {"minimum": 25, "maximum": 39, "label": "Hold"},
            {"minimum": 40, "maximum": 50, "label": "Shortlist"},
        ],
        "evidence_sources": ["About", "All experiences"],
        "require_experience": True,
    }


def test_custom_role_builds_machine_validated_contract() -> None:
    config = valid_custom_config()
    assert validate_custom_role_config(config) == []

    role = get_role_profile(CUSTOM_ROLE_KEY, config)
    assert role.label == "Custom: Data Engineer"
    assert role.total_max == 50
    assert role.category_scores == {
        "Data Modelling — Score": 20,
        "Pipelines — Score": 30,
    }
    assert role.allowed_scores["Data Modelling — Score"] == {0, 10, 20}
    assert role.output_columns[-8:] == [
        "Total Score",
        "Decision",
        "Evidence Confidence",
        "Strongest Evidence 1",
        "Strongest Evidence 2",
        "Strongest Evidence 3",
        "Missing or Unclear Information",
        "Score Rationale",
    ]


def test_custom_role_rejects_ambiguous_or_incomplete_setup() -> None:
    config = valid_custom_config()
    config["categories"][0]["allowed_scores"] = [0, 21]
    config["categories"][1]["name"] = "Data Modelling"
    config["outcome_bands"][1]["minimum"] = 30
    config["evidence_sources"] = []

    errors = validate_custom_role_config(config)
    assert any("allowed scores must be between" in error for error in errors)
    assert any("Category names must be unique" in error for error in errors)
    assert any("without gaps or overlaps" in error for error in errors)
    assert any("Select at least one" in error for error in errors)


def test_custom_result_validation_checks_scores_total_and_outcome() -> None:
    role = get_role_profile(CUSTOM_ROLE_KEY, valid_custom_config())
    row = {column: "" for column in role.output_columns}
    row.update(
        {
            "Data Modelling — Score": 20,
            "Pipelines — Score": 22,
            "Total Score": 42,
            "Decision": "Shortlist",
            "Evidence Confidence": "High",
        }
    )
    assert validate_output_row(row, role) == []

    row["Data Modelling — Score"] = 11
    row["Total Score"] = 40
    row["Decision"] = "Hold"
    errors = validate_output_row(row, role)
    assert any("must be one of" in error for error in errors)
    assert any("must equal category score sum" in error for error in errors)
    assert any("Decision must be" in error for error in errors)


def test_custom_role_uses_only_selected_evidence_and_skips_missing_profiles() -> None:
    role = get_role_profile(CUSTOM_ROLE_KEY, valid_custom_config())
    candidate = {
        "linkedin_profile_id": "person",
        "linkedin_url": "https://linkedin.com/in/person",
        "candidate_name": "Person",
        "headline": "This must be hidden",
        "about": "Data engineer",
        "website": "https://example.com",
        "education": ["Example University"],
        "experiences": [
            {
                "company_name": "Example",
                "position_or_title": "Data Engineer",
                "description": "Built pipelines",
                "experience_skills": ["Python"],
            }
        ],
    }
    payload = _candidate_payload(candidate, role)
    assert "Headline" not in payload
    assert "Website" not in payload
    assert "Education" not in payload
    assert payload["About"] == "Data engineer"
    assert payload["experiences"][0]["description"] == "Built pipelines"
    assert payload["experiences"][0]["experience_skills"] == ["Python"]
    assert candidate_input_issue(
        {**candidate, "experiences": []},
        CUSTOM_ROLE_KEY,
        evidence_sources=role.evidence_sources,
        require_experience=role.require_experience,
    ) == "no experience entries are available for this custom role"


def test_exhaustive_linkedin_evidence_sources_are_normalized_and_filtered() -> None:
    assert {
        "Location",
        "Experience 0",
        "Experience 4",
        "All experiences",
        "Current company (Experience 0 company name)",
        "Experience role titles",
        "Experience durations",
        "Skills",
        "Education",
        "Open-to-work signal",
        "All open-to signals",
    }.issubset(CUSTOM_EVIDENCE_SOURCES)

    raw_profile = {
        "publicIdentifier": "person",
        "linkedinUrl": "https://linkedin.com/in/person",
        "firstName": "Example",
        "lastName": "Person",
        "headline": "Hidden headline",
        "about": "Hidden about",
        "location": {"linkedinText": "Mumbai, Maharashtra, India"},
        "skills": [{"name": "Python"}, {"name": "SQL"}],
        "topSkills": ["Python", "Data Modelling"],
        "openToWork": False,
        "hiring": True,
        "services": ["Data engineering"],
        "education": [{"schoolName": "Example University", "degree": "BTech"}],
        "experience": [
            {
                "companyName": "Current Co",
                "position": "Senior Data Engineer",
                "startDate": {"text": "Jan 2024"},
                "endDate": {"text": "Present"},
                "duration": "2 yrs",
                "description": "Current role details",
            },
            {
                "companyName": "Earlier Co",
                "position": "Data Engineer",
                "startDate": {"text": "Jan 2022"},
                "endDate": {"text": "Dec 2023"},
                "duration": "2 yrs",
                "description": "Built batch pipelines",
            },
            {
                "companyName": "Old Co",
                "position": "Analyst",
                "duration": "1 yr",
                "description": "Should be hidden",
            },
        ],
    }
    candidate = normalize_candidate(raw_profile, 0)
    config = valid_custom_config()
    config["evidence_sources"] = [
        "Location",
        "Experience 1",
        "Current company (Experience 0 company name)",
        "Experience role titles",
        "Experience durations",
        "Skills",
        "Education",
        "All open-to signals",
    ]
    role = get_role_profile(CUSTOM_ROLE_KEY, config)
    payload = _candidate_payload(candidate, role)

    assert payload["Location"] == "Mumbai, Maharashtra, India"
    assert payload["Skills"] == ["Python", "SQL", "Data Modelling"]
    assert payload["Education"] == ["Example University | BTech"]
    assert payload["Open-to signals"] == {
        "open_to_work": False,
        "hiring": True,
        "services": ["Data engineering"],
    }
    assert payload["experiences"][0] == {
        "index": 0,
        "company_name": "Current Co",
        "position_or_title": "Senior Data Engineer",
        "start_date": "Jan 2024",
        "end_date": "Present",
        "is_current": True,
        "duration": "2 yrs",
    }
    assert payload["experiences"][1]["description"] == "Built batch pipelines"
    assert payload["experiences"][2] == {
        "index": 2,
        "position_or_title": "Analyst",
        "is_current": True,
        "duration": "1 yr",
    }


def test_legacy_experience_source_remains_valid_for_saved_runs() -> None:
    config = valid_custom_config()
    config["evidence_sources"] = ["Experience entries"]
    assert validate_custom_role_config(config) == []


def test_custom_role_configuration_is_saved_with_run(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    config = valid_custom_config()
    candidates = [
        {
            "source_index": 0,
            "linkedin_profile_id": "person",
            "candidate_name": "Person",
            "source_row": {"Candidate Name": "Person"},
        }
    ]
    init_run("custom-run", candidates, "rubric", "model", CUSTOM_ROLE_KEY, custom_role_config=config)

    assert load_status("custom-run")["custom_role_config"] == config
    restored = role_for_run("custom-run")
    assert restored.role_name == "Data Engineer"
    assert restored.total_max == 50
