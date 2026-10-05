from __future__ import annotations

from pathlib import Path

import pytest

from candidate_evaluator.constants import MODEL_OPTIONS
from candidate_evaluator.extractor import (
    candidate_input_issues,
    load_profiles,
    merge_duplicate_experiences,
    normalize_candidates,
    preview_candidates,
)
from candidate_evaluator.roles import get_role_profile, prepare_output_rows
from candidate_evaluator.validation import apply_calculated_fields, expected_outcome, validate_output_row


SAMPLE_PATH = Path("/Users/sehermehta/Documents/Documents - Seher’s MacBook Air/Codex/candidate-evaluator/sample.json")


@pytest.mark.skipif(not SAMPLE_PATH.exists(), reason="sample JSON is outside this workspace")
def test_sample_extraction_uses_all_experiences() -> None:
    candidates = normalize_candidates(load_profiles(SAMPLE_PATH))
    assert len(candidates) == 5
    assert candidates[0]["linkedin_profile_id"] == "aditi-bhattacharjee-343b39208"
    assert candidates[1]["candidate_name"] == "Vaishali Jaiswal"
    assert len(candidates[1]["experiences"]) == 7
    assert candidates[1]["experiences"][6]["company_name"] == "Yellow Fishes"
    assert any(exp["experience_skills"] for candidate in candidates for exp in candidate["experiences"])


@pytest.mark.skipif(not SAMPLE_PATH.exists(), reason="sample JSON is outside this workspace")
def test_preview_includes_every_experience_index() -> None:
    candidates = normalize_candidates(load_profiles(SAMPLE_PATH))
    preview = preview_candidates(candidates, limit=5)
    assert len(preview) == 5
    assert preview[0]["Experience Entries Detected"] == 3
    assert preview[1]["Experience Entries Detected"] == 7
    assert "experience/6" in preview[1]
    assert "experience/6" in preview[4]
    assert "experience/3" not in preview[0]


def test_model_selector_options_include_default_and_thinking() -> None:
    assert MODEL_OPTIONS["GPT-5.5"] == "gpt-5.5"
    assert MODEL_OPTIONS["GPT-5.5 Thinking"] == "gpt-5.5-thinking"
    assert MODEL_OPTIONS["GPT-5.5 Mini"] == "gpt-5.5-mini"
    assert MODEL_OPTIONS["GPT-5.3"] == "gpt-5.3"
    assert MODEL_OPTIONS["GPT-5.3 Thinking"] == "gpt-5.3-thinking"
    assert MODEL_OPTIONS["GPT-5.3 Mini"] == "gpt-5.3-mini"
    assert MODEL_OPTIONS["GPT-4.1"] == "gpt-4.1"
    assert MODEL_OPTIONS["GPT-4.1 Mini"] == "gpt-4.1-mini"
    assert MODEL_OPTIONS["GPT-4o Mini"] == "gpt-4o-mini"
    assert MODEL_OPTIONS["O3 Mini"] == "o3-mini"
    assert "Custom" in MODEL_OPTIONS


def test_custom_model_parser_splits_lines_and_commas() -> None:
    from app import _parse_custom_models

    assert _parse_custom_models("gpt-4o-mini\ngpt-4.1-mini, gpt-4o-mini") == [
        "gpt-4o-mini",
        "gpt-4.1-mini",
    ]


def test_valid_output_row_passes() -> None:
    role = get_role_profile("design")
    row = {column: "" for column in role.output_columns}
    scores = {
        "UX/Product Design Experience and Career Depth — Score": 10,
        "User Research, Insight and Synthesis — Score": 8,
        "UX Craft and Complex Workflow Design — Score": 7,
        "Product Thinking, UX Strategy and Ownership — Score": 6,
        "Validation, Behavioural Data and Outcomes — Score": 3,
        "Design Systems, Engineering and Accessibility — Score": 2,
        "Design-Agency Experience and Breadth — Score": 3,
    }
    row.update(scores)
    row["Total Score"] = sum(scores.values())
    row["Ranking"] = expected_outcome(row["Total Score"], role)
    row["Evidence Confidence"] = "High"
    row["Score Rationale"] = "Recent full-time UX roles show weighted design depth, research, workflow craft, ownership, validation, systems collaboration, and agency breadth across relevant product contexts."
    assert validate_output_row(row, "design") == []


def test_validation_catches_caps_total_ranking_and_rationale() -> None:
    role = get_role_profile("design")
    row = {column: "" for column in role.output_columns}
    for column in role.category_scores:
        row[column] = 0
    row["UX/Product Design Experience and Career Depth — Score"] = 16
    row["Total Score"] = 20
    row["Ranking"] = "Strong relevance"
    row["Score Rationale"] = "word " * 76
    errors = validate_output_row(row, "design")
    assert any("between 0 and 15" in error for error in errors)
    assert any("must equal category score sum" in error for error in errors)
    assert any("Ranking must be" in error for error in errors)


def test_role_profiles_expose_design_qa_and_backend_columns() -> None:
    design = get_role_profile("design")
    qa = get_role_profile("qa")
    backend = get_role_profile("backend")
    assert "UX/Product Design Experience and Career Depth — Score" in design.output_columns
    assert "Ranking" in design.output_columns
    assert "Rest Assured / API Automation — Score" in qa.output_columns
    assert "Decision" in qa.output_columns
    assert "UX/Product Design Experience and Career Depth — Score" not in qa.output_columns
    assert backend.output_columns[0] == "Rank Number"
    assert len(backend.output_columns) == 18
    assert backend.output_columns[-1] == "Score Rationale"
    assert "PHP Score (/20)" in backend.output_columns
    assert "Final Score (/60)" in backend.output_columns
    assert "Experience 0" not in backend.output_columns


def test_qa_validation_enforces_allowed_scores_total_and_decision() -> None:
    role = get_role_profile("qa")
    row = {column: "" for column in role.output_columns}
    scores = {
        "Rest Assured / API Automation — Score": 26,
        "Manual API / Postman — Score": 10,
        "Python Automation — Score": 5,
        "Java Proficiency — Score": 10,
        "Selenium UI Automation — Score": 5,
        "SQL and Data Validation — Score": 3,
        "CI/CD and Pipelines — Score": 2,
    }
    row.update(scores)
    row["Total Score"] = sum(scores.values())
    row["Decision"] = "Hold"
    row["Evidence Confidence"] = "Medium"
    row["Score Rationale"] = "Recent QA roles show weighted automation experience with visible API testing, Java automation, some Selenium, SQL checks and CI exposure, though ownership depth is only partly clear."
    assert validate_output_row(row, "qa") == []

    row["Python Automation — Score"] = 7
    row["Total Score"] = sum(v for v in row.values() if isinstance(v, int))
    row["Score Rationale"] = "word " * 76
    errors = validate_output_row(row, "qa")
    assert any("Python Automation" in error and "one of" in error for error in errors)
    assert any("Score Rationale" in error for error in errors)


def test_backend_validation_accepts_decimals_and_enforces_warnings_and_total() -> None:
    role = get_role_profile("backend")
    row = {column: "" for column in set(role.output_columns + role.grading_columns)}
    row.update(
        {
            "Candidate": "A Candidate",
            "Profile URL": "https://linkedin.com/in/a",
            "PHP Score (/20)": 15.0,
            "Python Score (/20)": 13.0,
            "Laravel Score (/12)": 6.6,
            "AWS Score (/8)": 4.4,
            "Final Score (/60)": 39.0,
            "PHP Unverified": "No",
            "Python Unverified": "No",
            "Backend Relevance Unverified": "No",
            "Seniority Unverified": "No",
            "Date-Quality Warning": "No",
            "Strongest Evidence": "Built PHP APIs | Maintained Python services | Deployed workloads on AWS",
            "Score Rationale": "Explicit recent backend experience provides dated evidence of PHP, Python, Laravel, and AWS engineering work. Strong descriptions support technology evidence and meaningful duration across relevant roles, while the supplied employment dates support recency calculations without contradictions. The strongest verified evidence is concentrated in PHP and Python, with additional framework and cloud exposure supporting the final score.",
        }
    )
    assert validate_output_row(row, "backend") == []

    row["Date-Quality Warning"] = "Maybe"
    row["Final Score (/60)"] = 40
    errors = validate_output_row(row, "backend")
    assert any("Date-Quality Warning must be one of" in error for error in errors)
    assert any("must equal category score sum" in error for error in errors)

    row["Date-Quality Warning"] = "No"
    row["Final Score (/60)"] = 39
    row["Strongest Evidence"] = "One | Two | Three | Four"
    row["Score Rationale"] = "Too short."
    errors = validate_output_row(row, "backend")
    assert any("Strongest Evidence has more than three" in error for error in errors)
    assert any("at least 50 words" in error for error in errors)


def test_backend_output_ranking_uses_documented_tie_break_order() -> None:
    rows = [
        {
            "Candidate": "Beta",
            "Profile URL": "b",
            "PHP Score (/20)": 10,
            "Python Score (/20)": 12,
            "Laravel Score (/12)": 4,
            "AWS Score (/8)": 4,
            "Final Score (/60)": 30,
            "Weighted Recency Subtotal": 8,
            "Weighted Duration Subtotal": 6,
            "Weighted Evidence Subtotal": 16,
        },
        {
            "Candidate": "Alpha",
            "Profile URL": "a",
            "PHP Score (/20)": 12,
            "Python Score (/20)": 10,
            "Laravel Score (/12)": 4,
            "AWS Score (/8)": 4,
            "Final Score (/60)": 30,
            "Weighted Recency Subtotal": 8,
            "Weighted Duration Subtotal": 6,
            "Weighted Evidence Subtotal": 16,
        },
    ]
    ranked = prepare_output_rows(rows, "backend")
    assert [row["Candidate"] for row in ranked] == ["Alpha", "Beta"]
    assert [row["Rank Number"] for row in ranked] == [1, 2]


def test_python_calculates_design_total_band_and_duration_labels() -> None:
    role = get_role_profile("design")
    row = {
        **{column: 0 for column in role.category_scores},
        "UX/Product Design Experience and Career Depth — Score": 15,
        "User Research, Insight and Synthesis — Score": 12,
        "UX Craft and Complex Workflow Design — Score": 10,
        "Product Thinking, UX Strategy and Ownership — Score": 8,
        "Total Relevant Design Experience — Months": 25,
        "Total Weighted Relevant Design Experience — Months": 12,
        "Weighted Design-Agency Experience — Months": 0,
    }

    calculated = apply_calculated_fields(row, {"experiences": []}, role)

    assert calculated["Total Score"] == 45
    assert calculated["Ranking"] == "Strong relevance"
    assert calculated["Total Relevant Design Experience — Years and Months"] == "2 years 1 month"
    assert calculated["Total Weighted Relevant Design Experience — Years and Months"] == "1 year"
    assert calculated["Weighted Design-Agency Experience — Years and Months"] == "0 months"


def test_python_calculates_qa_decision_boundaries() -> None:
    role = get_role_profile("qa")
    row = {column: 0 for column in role.category_scores}
    row.update(
        {
            "Rest Assured / API Automation — Score": 35,
            "Manual API / Postman — Score": 15,
            "Python Automation — Score": 5,
        }
    )

    calculated = apply_calculated_fields(row, {"experiences": []}, role)

    assert calculated["Total Score"] == 55
    assert calculated["Decision"] == "Hold"


def test_python_calculates_backend_total_and_current_role() -> None:
    role = get_role_profile("backend")
    row = {
        "PHP Score (/20)": 15.0,
        "Python Score (/20)": 13.0,
        "Laravel Score (/12)": 6.6,
        "AWS Score (/8)": 4.4,
    }
    candidate = {
        "experiences": [
            {"company_name": "Previous Ltd", "position_or_title": "Backend Engineer", "is_current": False},
            {"company_name": "Example Ltd", "position_or_title": "Senior Backend Engineer", "is_current": True},
        ]
    }

    calculated = apply_calculated_fields(row, candidate, role)

    assert calculated["Final Score (/60)"] == 39.0
    assert calculated["Current Company"] == "Example Ltd"
    assert calculated["Current Title"] == "Senior Backend Engineer"


def test_backend_duplicate_merge_preserves_distinct_roles() -> None:
    duplicate = {
        "index": 0,
        "company_name": "Example",
        "position_or_title": "Backend Engineer",
        "start_date": "2024",
        "end_date": "Present",
        "duration": "2 years",
        "description": "Built PHP APIs",
        "experience_skills": ["PHP"],
    }
    records = [
        duplicate,
        {**duplicate, "index": 1, "description": "Deployed on AWS", "experience_skills": ["AWS"]},
        {**duplicate, "index": 2, "position_or_title": "Engineering Manager"},
    ]
    merged = merge_duplicate_experiences(records)
    assert len(merged) == 2
    assert merged[0]["description"] == "Built PHP APIs | Deployed on AWS"
    assert merged[0]["experience_skills"] == ["PHP", "AWS"]


def test_candidate_input_issues_blocks_post_data_without_profile_evidence() -> None:
    candidates = normalize_candidates(
        [
            {
                "id": "activity-123",
                "linkedinUrl": "https://www.linkedin.com/posts/example_activity-123",
            }
        ]
    )
    issues = candidate_input_issues(candidates)
    assert any("post/activity URLs" in issue for issue in issues)
    assert any("no headline, About text, or experience entries" in issue for issue in issues)


def test_candidate_input_issues_accepts_sparse_but_scorable_profile() -> None:
    candidates = normalize_candidates(
        [
            {
                "publicIdentifier": "example-person",
                "linkedinUrl": "https://www.linkedin.com/in/example-person/",
                "headline": "Backend Engineer using PHP and Python",
                "experience": [],
            }
        ]
    )
    assert candidate_input_issues(candidates) == []
