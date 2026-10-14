from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from app import _default_rubric_path, _evaluate_candidate_for_run
from candidate_evaluator.extractor import candidate_input_issue, normalize_candidate
from candidate_evaluator.openai_scoring import _candidate_payload, _response_schema
from candidate_evaluator.progress import init_run, role_for_run, run_dir
from candidate_evaluator.roles import get_role_profile, prepare_output_rows, role_options
from candidate_evaluator.validation import apply_calculated_fields, coerce_fixed_row, validate_output_row


CAPABILITIES = [
    "International Market Sales Experience",
    "Lead Generation and New Business Prospecting",
    "Sales Pipeline Management and Conversion",
    "Key Account Management and Account Growth",
    "Customer Success and Consultative Selling",
    "Cross-Functional Coordination and Operational Execution",
]


def _candidate() -> dict:
    return {
        "linkedin_profile_id": "account-executive",
        "linkedin_url": "https://www.linkedin.com/in/account-executive/",
        "candidate_name": "Account Executive",
        "source_index": 0,
        "headline": "US Account Executive",
        "about": "Builds pipeline and grows key accounts.",
        "experiences": [
            {
                "index": 0,
                "company_name": "Current Co",
                "position_or_title": "Operations Manager",
                "description": "Runs internal operations.",
                "employment_type": "Full-time",
                "start_date": "2025-01",
                "end_date": "Present",
                "is_current": True,
                "duration": "1 year",
            },
            {
                "index": 1,
                "company_name": "Sales Co",
                "position_or_title": "Account Executive - North America",
                "description": "Prospected, managed pipeline through close, and grew named accounts.",
                "employment_type": "Full-time",
                "start_date": "2021-01",
                "end_date": "2024-12",
                "is_current": False,
                "duration": "4 years",
            },
        ],
        "source_row": {},
    }


def _model_grading(value: int = 2) -> dict:
    role = get_role_profile("zeiss_visiogen")
    grading = {column: value for column in role.component_score_maxima}
    grading.update(
        {
            "International Market Sales Unverified": "No",
            "Lead Generation / Prospecting Unverified": "No",
            "Pipeline / Conversion Unverified": "No",
            "Key Account Management Unverified": "No",
            "Date-Quality Warning": "No",
            "Strongest Evidence": "Sales Co: North America sales | Sales Co: pipeline ownership | Sales Co: named-account growth",
            "Missing or Unclear Information": "Customer-success outcomes are not stated.",
            "Score Rationale": "Dated experience supports US sales, prospecting, pipeline conversion, and account growth. Customer-success outcomes remain unverified.",
        }
    )
    return grading


def _calculated_row(grading: dict | None = None) -> dict:
    role = get_role_profile("zeiss_visiogen")
    row = {
        "Candidate": "Account Executive",
        "Profile URL": "https://www.linkedin.com/in/account-executive/",
        "Rank Number": "",
        **(grading or _model_grading()),
    }
    return coerce_fixed_row(apply_calculated_fields(row, _candidate(), role), role)


def test_role_is_separate_selectable_and_has_no_bundled_rubric() -> None:
    role = get_role_profile("zeiss_visiogen")

    assert role_options()["ZEISS VisioGen: Account Executive - US Sales / Key Account Manager"] == "zeiss_visiogen"
    assert role_options()["Head Sales"] == "head_sales"
    assert _default_rubric_path("zeiss_visiogen") == ""
    assert role.total_column == "Final Score (/75)"
    assert role.total_max == 75
    assert sum(role.category_scores.values()) == 75
    assert len(role.component_score_maxima) == 18
    assert set(role.component_score_maxima).isdisjoint(role.output_columns)


def test_run_saves_uploaded_rubric_and_restores_role(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    init_run("zeiss-run", [_candidate()], "# Uploaded ZEISS rubric", "test-model", role_key="zeiss_visiogen")

    assert role_for_run("zeiss-run").key == "zeiss_visiogen"
    assert (run_dir("zeiss-run") / "rubric.md").read_text(encoding="utf-8") == "# Uploaded ZEISS rubric"


def test_schema_requests_only_judgment_fields_with_exact_component_maxima() -> None:
    role = get_role_profile("zeiss_visiogen")
    grading = _response_schema(role)["properties"]["grading"]
    requested = set(grading["required"])

    assert set(role.component_score_maxima) <= requested
    assert set(role.category_scores).isdisjoint(requested)
    assert {"Current Company", "Current Title", "Final Score (/75)", "Rank Number"}.isdisjoint(requested)
    for capability in CAPABILITIES:
        assert grading["properties"][f"{capability} — Evidence Points"] == {
            "type": "integer", "minimum": 0, "maximum": 4
        }
        assert grading["properties"][f"{capability} — Recency Points"]["maximum"] == 3
        assert grading["properties"][f"{capability} — Evidenced Duration Points"]["maximum"] == 3


def test_python_calculates_scores_total_and_boundaries() -> None:
    row = _calculated_row()
    assert [row[column] for column in get_role_profile("zeiss_visiogen").category_scores] == [9, 9, 9, 9, 6, 3]
    assert row["Final Score (/75)"] == 45
    assert row["Current Company"] == "Current Co"
    assert row["Current Title"] == "Operations Manager"
    assert validate_output_row(row, "zeiss_visiogen") == []

    role = get_role_profile("zeiss_visiogen")
    zero = _model_grading()
    maximum = _model_grading()
    for component, cap in role.component_score_maxima.items():
        zero[component] = 0
        maximum[component] = cap
    assert _calculated_row(zero)["Final Score (/75)"] == 0
    assert _calculated_row(maximum)["Final Score (/75)"] == 75


def test_python_overwrites_model_supplied_mechanical_values() -> None:
    grading = _model_grading()
    grading.update({column: 0 for column in get_role_profile("zeiss_visiogen").category_scores})
    grading["Final Score (/75)"] = 0
    row = _calculated_row(grading)
    assert row["International Market Sales Experience Score (/15)"] == 9
    assert row["Final Score (/75)"] == 45


def test_validation_rejects_missing_fractional_and_out_of_range_components() -> None:
    for column, maximum in get_role_profile("zeiss_visiogen").component_score_maxima.items():
        missing = _calculated_row()
        missing[column] = ""
        assert any("must be a whole number" in error for error in validate_output_row(missing, "zeiss_visiogen"))

        fractional = _calculated_row()
        fractional[column] = 1.5
        assert any("must be a whole number" in error for error in validate_output_row(fractional, "zeiss_visiogen"))

        excessive = _calculated_row()
        excessive[column] = maximum + 1
        assert any(
            f"must be between 0 and {maximum}" in error
            for error in validate_output_row(excessive, "zeiss_visiogen")
        )


def test_validation_enforces_warning_enums_evidence_count_and_rationale_limit() -> None:
    row = _calculated_row()
    row["Date-Quality Warning"] = "Maybe"
    row["Strongest Evidence"] = "One | Two | Three | Four"
    row["Score Rationale"] = "word " * 51
    errors = validate_output_row(row, "zeiss_visiogen")
    assert any("Date-Quality Warning must be one of" in error for error in errors)
    assert any("Strongest Evidence has more than three items" in error for error in errors)
    assert any("no longer than 50 words" in error for error in errors)


def test_ranking_uses_capability_order_then_name() -> None:
    base = _calculated_row()
    higher_international = {**base, "Candidate": "Zulu", "International Market Sales Experience Score (/15)": 10, "Lead Generation and New Business Prospecting Score (/15)": 8}
    higher_leads = {**base, "Candidate": "Alpha", "International Market Sales Experience Score (/15)": 9, "Lead Generation and New Business Prospecting Score (/15)": 9}
    higher_international["Final Score (/75)"] = higher_leads["Final Score (/75)"] = 45
    ranked = prepare_output_rows([higher_leads, higher_international], "zeiss_visiogen")
    assert [row["Candidate"] for row in ranked] == ["Zulu", "Alpha"]

    ranked = prepare_output_rows([{**base, "Candidate": "Beta"}, {**base, "Candidate": "Alpha"}], "zeiss_visiogen")
    assert [row["Candidate"] for row in ranked] == ["Alpha", "Beta"]


def test_payload_is_minimal_includes_employment_type_and_merges_duplicates() -> None:
    candidate = normalize_candidate(
        {
            "publicIdentifier": "sales-person",
            "linkedinUrl": "https://www.linkedin.com/in/sales-person/",
            "fullName": "Sales Person",
            "headline": "Account Executive",
            "about": "Builds new business.",
            "location": "Chicago",
            "education": [{"schoolName": "Unused"}],
            "skills": ["Unused global skill"],
            "projects": [{"title": "Unused project"}],
            "websites": ["https://unused.example"],
            "experience": [
                {"companyName": "Sales Co", "title": "Account Executive", "description": "Prospected.", "location": "New York, United States", "employmentType": "Internship", "startDate": "2023", "endDate": "2024", "duration": "1 year", "skills": ["Unused role skill"]},
                {"companyName": "Sales Co", "title": "Account Executive", "description": "Closed deals.", "employmentType": "Internship", "startDate": "2023", "endDate": "2024", "duration": "1 year", "skills": ["Another unused skill"]},
            ],
        },
        0,
    )
    payload = _candidate_payload(candidate, get_role_profile("zeiss_visiogen"))
    assert set(payload) == {"LinkedIn Profile ID", "LinkedIn URL", "Candidate Name", "Headline", "About", "experiences"}
    assert len(payload["experiences"]) == 1
    assert payload["experiences"][0]["description"] == "Prospected. | Closed deals."
    assert payload["experiences"][0]["experience_location"] == "New York, United States"
    assert payload["experiences"][0]["employment_type"] == "Internship"
    assert "experience_skills" not in payload["experiences"][0]
    assert "workplace_type" not in payload["experiences"][0]
    assert "company_location" not in payload["experiences"][0]
    assert "Location" not in payload and "Education" not in payload and "Skills" not in payload and "Projects" not in payload


def test_title_only_and_unrelated_current_role_are_sent_with_dates() -> None:
    title_only = normalize_candidate(
        {"publicIdentifier": "title-only", "linkedinUrl": "https://www.linkedin.com/in/title-only/", "fullName": "Title Only", "experience": [
            {"companyName": "Current Co", "title": "Operations Manager", "startDate": "2025", "endDate": "Present", "description": ""},
            {"companyName": "Sales Co", "title": "Account Executive - North America", "startDate": "2021", "endDate": "2023", "description": ""},
            {"companyName": "Undated Co", "title": "Account Manager", "description": ""},
        ]}, 0
    )
    role = get_role_profile("zeiss_visiogen")
    payload = _candidate_payload(title_only, role)
    assert payload["experiences"][1]["position_or_title"] == "Account Executive - North America"
    assert payload["experiences"][1]["start_date"] == "2021"
    assert payload["experiences"][1]["end_date"] == "2023"
    assert payload["experiences"][2]["start_date"] == ""
    assert payload["experiences"][2]["end_date"] == ""
    assert candidate_input_issue(title_only, role.key, role.evidence_sources, role.require_experience, role.skip_if_no_evidence) == ""


def test_missing_experience_location_is_safe_and_sent_as_empty() -> None:
    candidate = normalize_candidate(
        {
            "publicIdentifier": "no-location",
            "linkedinUrl": "https://www.linkedin.com/in/no-location/",
            "fullName": "No Location",
            "experience": [{"companyName": "Sales Co", "title": "Account Executive"}],
        },
        0,
    )

    payload = _candidate_payload(candidate, get_role_profile("zeiss_visiogen"))
    assert payload["experiences"][0]["experience_location"] == ""


def test_headline_about_and_title_only_profiles_are_not_skipped() -> None:
    role = get_role_profile("zeiss_visiogen")
    profiles = [
        {"publicIdentifier": "headline-only", "linkedinUrl": "https://www.linkedin.com/in/headline-only/", "fullName": "Headline Only", "headline": "Account Executive"},
        {"publicIdentifier": "about-only", "linkedinUrl": "https://www.linkedin.com/in/about-only/", "fullName": "About Only", "about": "Prospected for new customers."},
        {"publicIdentifier": "title-only", "linkedinUrl": "https://www.linkedin.com/in/title-only/", "fullName": "Title Only", "experience": [{"companyName": "Example", "title": "Key Account Manager", "description": ""}]},
    ]
    for index, profile in enumerate(profiles):
        candidate = normalize_candidate(profile, index)
        assert candidate_input_issue(
            candidate,
            role.key,
            role.evidence_sources,
            role.require_experience,
            role.skip_if_no_evidence,
        ) == ""


def test_identity_only_profile_is_skipped_without_an_api_call() -> None:
    role = get_role_profile("zeiss_visiogen")
    candidate = normalize_candidate(
        {
            "publicIdentifier": "identity-only",
            "linkedinUrl": "https://www.linkedin.com/in/identity-only/",
            "fullName": "Identity Only",
        },
        0,
    )
    issue = candidate_input_issue(
        candidate,
        role.key,
        role.evidence_sources,
        role.require_experience,
        role.skip_if_no_evidence,
    )
    assert role.skip_if_no_evidence is True
    assert issue == "none of the selected evidence sources contain usable data"


def test_invalid_identity_and_post_urls_follow_safe_skip_rules() -> None:
    role = get_role_profile("zeiss_visiogen")
    missing_identity = {**_candidate(), "candidate_name": "", "linkedin_url": ""}
    assert "candidate name is empty" in candidate_input_issue(missing_identity, role.key, role.evidence_sources, False, False)
    assert "LinkedIn profile URL is empty" in candidate_input_issue(missing_identity, role.key, role.evidence_sources, False, False)

    post = {**_candidate(), "linkedin_url": "https://www.linkedin.com/posts/some-post"}
    assert "post/activity" in candidate_input_issue(post, role.key, role.evidence_sources, False, False)


def test_contradictory_dates_can_be_flagged_without_crashing() -> None:
    grading = _model_grading()
    grading["Date-Quality Warning"] = "Yes"
    candidate = deepcopy(_candidate())
    candidate["experiences"][1]["start_date"] = "2025"
    candidate["experiences"][1]["end_date"] = "2022"
    payload = _candidate_payload(candidate, get_role_profile("zeiss_visiogen"))
    assert payload["experiences"][1]["start_date"] == "2025"
    assert payload["experiences"][1]["end_date"] == "2022"
    assert validate_output_row(_calculated_row(grading), "zeiss_visiogen") == []


def test_full_evaluation_flow_calculates_mechanical_fields(monkeypatch) -> None:
    grading = _model_grading()

    def fake_evaluate_candidate(**_kwargs):
        return deepcopy(grading), {"grading": deepcopy(grading)}

    monkeypatch.setattr("candidate_evaluator.openai_scoring.evaluate_candidate", fake_evaluate_candidate)
    result = _evaluate_candidate_for_run("unused", "unused", "uploaded-rubric", _candidate(), get_role_profile("zeiss_visiogen"))
    assert result["state"] == "completed"
    assert result["row"]["Final Score (/75)"] == 45
    assert result["row"]["Current Company"] == "Current Co"


def test_head_sales_component_contract_remains_unchanged() -> None:
    role = get_role_profile("head_sales")
    maxima = role.component_score_maxima
    assert {maximum for column, maximum in maxima.items() if column.endswith("Evidence Points")} == {4}
    assert {maximum for column, maximum in maxima.items() if column.endswith("Impact Points")} == {4}
    assert {maximum for column, maximum in maxima.items() if column.endswith("Evidenced Duration Points")} == {2}
    grading = _response_schema(role)["properties"]["grading"]
    assert grading["properties"]["Dealer / Distributor Network Building — Impact Points"]["maximum"] == 4
    assert grading["properties"]["Dealer / Distributor Network Building — Evidenced Duration Points"]["maximum"] == 2
