from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from app import _default_rubric_path, _evaluate_candidate_for_run
from candidate_evaluator.extractor import candidate_input_issue, normalize_candidate
from candidate_evaluator.openai_scoring import _candidate_payload, _response_schema
from candidate_evaluator.progress import init_run, role_for_run, run_dir
from candidate_evaluator.roles import get_role_profile, prepare_output_rows, role_options
from candidate_evaluator.validation import apply_calculated_fields, coerce_fixed_row, validate_output_row


COMPONENT_VALUES = {
    "Dealer / Distributor Network Building — Evidence Points": 4,
    "Dealer / Distributor Network Building — Impact Points": 3,
    "Dealer / Distributor Network Building — Evidenced Duration Points": 2,
    "Revenue Responsibility & Growth — Evidence Points": 4,
    "Revenue Responsibility & Growth — Impact Points": 4,
    "Revenue Responsibility & Growth — Evidenced Duration Points": 2,
    "Geographic / Channel Expansion — Evidence Points": 3,
    "Geographic / Channel Expansion — Impact Points": 3,
    "Geographic / Channel Expansion — Evidenced Duration Points": 1,
    "Sales Organisation Building & Leadership — Evidence Points": 4,
    "Sales Organisation Building & Leadership — Impact Points": 2,
    "Sales Organisation Building & Leadership — Evidenced Duration Points": 2,
    "P&L & Commercial Ownership — Evidence Points": 3,
    "P&L & Commercial Ownership — Impact Points": 2,
    "P&L & Commercial Ownership — Evidenced Duration Points": 1,
    "Sales Strategy & Operating Systems — Evidence Points": 4,
    "Sales Strategy & Operating Systems — Impact Points": 4,
    "Sales Strategy & Operating Systems — Evidenced Duration Points": 2,
}


def _candidate() -> dict:
    return {
        "linkedin_profile_id": "sales-leader",
        "linkedin_url": "https://www.linkedin.com/in/sales-leader/",
        "candidate_name": "Sales Leader",
        "source_index": 0,
        "headline": "Head of Sales",
        "about": "Builds dealer networks and leads revenue growth.",
        "location": "Delhi",
        "experiences": [
            {
                "index": 0,
                "company_name": "Example Ltd",
                "position_or_title": "Head of Sales",
                "description": "",
                "employment_type": "Full-time",
                "start_date": "2023-01",
                "end_date": "Present",
                "is_current": True,
                "duration": "3 years",
                "experience_skills": ["Sales"],
            }
        ],
        "source_row": {},
    }


def _model_grading() -> dict:
    return {
        **COMPONENT_VALUES,
        "Dealer / Distributor Building Unverified": "No",
        "Revenue Ownership Unverified": "No",
        "Date-Quality Warning": "No",
        "Strongest Evidence": "Built a dealer network | Owned monthly revenue growth | Led a national sales team",
        "Missing or Unclear Information": "P&L scope is only partly stated.",
        "Score Rationale": "Strong explicit network, revenue and leadership evidence is supported by dated roles. P&L ownership is less complete.",
    }


def _calculated_row(grading: dict | None = None) -> dict:
    role = get_role_profile("head_sales")
    candidate = _candidate()
    row = {
        "Candidate": candidate["candidate_name"],
        "Profile URL": candidate["linkedin_url"],
        "Rank Number": "",
        **(grading or _model_grading()),
    }
    return coerce_fixed_row(apply_calculated_fields(row, candidate, role), role)


def test_head_sales_role_is_dedicated_but_has_no_bundled_default_rubric() -> None:
    role = get_role_profile("head_sales")

    assert role_options()["Head Sales"] == "head_sales"
    assert _default_rubric_path("head_sales") == ""
    assert role.total_column == "Final Score (/60)"
    assert role.total_max == 60
    assert role.ranked is True
    assert sum(role.category_scores.values()) == 60
    assert len(role.component_score_maxima) == 18
    assert role.rationale_max_words == 50
    assert role.output_columns[0:5] == [
        "Rank Number",
        "Candidate",
        "Profile URL",
        "Current Company",
        "Current Title",
    ]
    assert set(role.component_score_maxima).isdisjoint(role.output_columns)


def test_head_sales_run_saves_uploaded_rubric_and_restores_dedicated_role(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    candidate = _candidate()

    init_run(
        "head-sales-run",
        [candidate],
        "# User-uploaded Head Sales rubric",
        "test-model",
        role_key="head_sales",
    )

    assert role_for_run("head-sales-run").key == "head_sales"
    assert (run_dir("head-sales-run") / "rubric.md").read_text(encoding="utf-8") == "# User-uploaded Head Sales rubric"


def test_head_sales_schema_requests_components_not_mechanical_scores() -> None:
    role = get_role_profile("head_sales")
    grading = _response_schema(role)["properties"]["grading"]
    requested = set(grading["required"])

    assert set(role.component_score_maxima) <= requested
    assert set(role.category_scores).isdisjoint(requested)
    assert {
        "Current Company",
        "Current Title",
        "Final Score (/60)",
        "Rank Number",
    }.isdisjoint(requested)
    assert grading["properties"]["Dealer / Distributor Network Building — Evidence Points"] == {
        "type": "integer",
        "minimum": 0,
        "maximum": 4,
    }
    assert grading["properties"]["Dealer / Distributor Network Building — Evidenced Duration Points"]["maximum"] == 2


def test_python_calculates_all_weighted_scores_and_total() -> None:
    row = _calculated_row()

    assert row["Dealer / Distributor Network Building Score (/15)"] == 13.5
    assert row["Revenue Responsibility & Growth Score (/12)"] == 12.0
    assert row["Geographic / Channel Expansion Score (/9)"] == 6.3
    assert row["Sales Organisation Building & Leadership Score (/9)"] == 7.2
    assert row["P&L & Commercial Ownership Score (/9)"] == 5.4
    assert row["Sales Strategy & Operating Systems Score (/6)"] == 6.0
    assert row["Final Score (/60)"] == 50.4
    assert row["Current Company"] == "Example Ltd"
    assert row["Current Title"] == "Head of Sales"
    assert validate_output_row(row, "head_sales") == []


def test_python_calculates_zero_and_maximum_score_boundaries() -> None:
    role = get_role_profile("head_sales")
    zero = _model_grading()
    maximum = _model_grading()
    for component, cap in role.component_score_maxima.items():
        zero[component] = 0
        maximum[component] = cap

    assert _calculated_row(zero)["Final Score (/60)"] == 0
    assert _calculated_row(maximum)["Final Score (/60)"] == 60


def test_python_overwrites_any_model_supplied_weighted_scores_or_total() -> None:
    grading = _model_grading()
    grading.update({column: 0 for column in get_role_profile("head_sales").category_scores})
    grading["Final Score (/60)"] = 0

    row = _calculated_row(grading)

    assert row["Dealer / Distributor Network Building Score (/15)"] == 13.5
    assert row["Final Score (/60)"] == 50.4


def test_validation_rejects_missing_out_of_range_and_fractional_components() -> None:
    missing = _calculated_row()
    missing["Revenue Responsibility & Growth — Impact Points"] = ""
    errors = validate_output_row(missing, "head_sales")
    assert any("Revenue Responsibility & Growth — Impact Points must be a whole number" in error for error in errors)

    excessive = _calculated_row()
    excessive["P&L & Commercial Ownership — Impact Points"] = 5
    errors = validate_output_row(excessive, "head_sales")
    assert any("must be between 0 and 4" in error for error in errors)

    fractional = _calculated_row()
    fractional["Sales Strategy & Operating Systems — Evidence Points"] = 2.5
    errors = validate_output_row(fractional, "head_sales")
    assert any("must be a whole number" in error for error in errors)


def test_validation_enforces_warnings_evidence_count_and_rationale_limit() -> None:
    row = _calculated_row()
    row["Date-Quality Warning"] = "Maybe"
    row["Strongest Evidence"] = "One | Two | Three | Four"
    row["Score Rationale"] = "word " * 51

    errors = validate_output_row(row, "head_sales")

    assert any("Date-Quality Warning must be one of" in error for error in errors)
    assert any("Strongest Evidence has more than three items" in error for error in errors)
    assert any("no longer than 50 words" in error for error in errors)


def test_head_sales_ranking_uses_capability_order_then_candidate_name() -> None:
    base = _calculated_row()
    higher_dealer = {
        **base,
        "Candidate": "Zulu",
        "Dealer / Distributor Network Building Score (/15)": 14.0,
        "Revenue Responsibility & Growth Score (/12)": 11.5,
    }
    higher_revenue = {
        **base,
        "Candidate": "Alpha",
        "Dealer / Distributor Network Building Score (/15)": 13.5,
        "Revenue Responsibility & Growth Score (/12)": 12.0,
    }
    higher_dealer["Final Score (/60)"] = 50.4
    higher_revenue["Final Score (/60)"] = 50.4

    ranked = prepare_output_rows([higher_revenue, higher_dealer], "head_sales")
    assert [row["Candidate"] for row in ranked] == ["Zulu", "Alpha"]
    assert [row["Rank Number"] for row in ranked] == [1, 2]

    same_a = {**base, "Candidate": "Alpha"}
    same_b = {**base, "Candidate": "Beta"}
    ranked = prepare_output_rows([same_b, same_a], "head_sales")
    assert [row["Candidate"] for row in ranked] == ["Alpha", "Beta"]


def test_payload_merges_duplicates_and_sends_only_permitted_experience_fields() -> None:
    candidate = normalize_candidate(
        {
            "publicIdentifier": "sales-leader",
            "linkedinUrl": "https://www.linkedin.com/in/sales-leader/",
            "fullName": "Sales Leader",
            "headline": "Head of Sales",
            "about": "Builds dealer networks.",
            "location": "Delhi",
            "education": [{"schoolName": "Unscored University"}],
            "skills": ["Unscored global skill"],
            "experience": [
                {
                    "companyName": "Example Ltd",
                    "title": "Head of Sales",
                    "startDate": "2023",
                    "endDate": "Present",
                    "description": "Built dealer networks.",
                    "employmentType": "Full-time",
                    "skills": ["Unscored role skill"],
                },
                {
                    "companyName": "Example Ltd",
                    "title": "Head of Sales",
                    "startDate": "2023",
                    "endDate": "Present",
                    "description": "Owned monthly revenue growth.",
                    "employmentType": "Full-time",
                    "skills": ["Another unscored skill"],
                },
            ],
        },
        0,
    )

    payload = _candidate_payload(candidate, get_role_profile("head_sales"))

    assert payload["Location"] == "Delhi"
    assert payload["Headline"] == "Head of Sales"
    assert len(payload["experiences"]) == 1
    assert payload["experiences"][0]["description"] == "Built dealer networks. | Owned monthly revenue growth."
    assert "experience_skills" not in payload["experiences"][0]
    assert "employment_type" not in payload["experiences"][0]
    assert "Education" not in payload
    assert "Skills" not in payload


def test_title_only_and_sparse_profiles_are_sent_for_scoring() -> None:
    title_only = normalize_candidate(
        {
            "publicIdentifier": "title-only",
            "linkedinUrl": "https://www.linkedin.com/in/title-only/",
            "fullName": "Title Only",
            "experience": [
                {
                    "companyName": "Example",
                    "title": "Head of Sales",
                    "startDate": "2022",
                    "endDate": "Present",
                    "description": "",
                }
            ],
        },
        0,
    )
    role = get_role_profile("head_sales")
    payload = _candidate_payload(title_only, role)

    assert payload["experiences"][0]["position_or_title"] == "Head of Sales"
    assert payload["experiences"][0]["start_date"] == "2022"
    assert candidate_input_issue(
        title_only,
        role.key,
        role.evidence_sources,
        role.require_experience,
        role.skip_if_no_evidence,
    ) == ""

    sparse = normalize_candidate(
        {
            "publicIdentifier": "sparse",
            "linkedinUrl": "https://www.linkedin.com/in/sparse/",
            "fullName": "Sparse",
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


def test_full_evaluation_flow_calculates_scores_and_accepts_valid_model_output(monkeypatch) -> None:
    grading = _model_grading()

    def fake_evaluate_candidate(**_kwargs):
        return deepcopy(grading), {"grading": deepcopy(grading)}

    monkeypatch.setattr("candidate_evaluator.openai_scoring.evaluate_candidate", fake_evaluate_candidate)

    result = _evaluate_candidate_for_run(
        "unused-api-key",
        "unused-model",
        "uploaded-rubric",
        _candidate(),
        get_role_profile("head_sales"),
    )

    assert result["state"] == "completed"
    assert result["row"]["Final Score (/60)"] == 50.4
    assert result["row"]["Current Title"] == "Head of Sales"
