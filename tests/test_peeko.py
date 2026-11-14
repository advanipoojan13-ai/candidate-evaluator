from copy import deepcopy
from datetime import date
from io import BytesIO
import json
from types import SimpleNamespace

import pytest
from openpyxl import load_workbook
from streamlit.testing.v1 import AppTest

from app import _evaluate_candidate_batch_for_run, _rows_to_csv_bytes, _rows_to_xlsx_bytes
from candidate_evaluator.extractor import normalize_candidate
from candidate_evaluator.openai_scoring import _candidate_payload, _response_schema
from candidate_evaluator.peeko import (
    CUTOFF_COLUMN, LEGACY_OUTPUT_COLUMNS, OUTPUT_COLUMNS, REVIEW_COLUMN, SCORE_COLUMNS, TOTAL_COLUMN, UNVERIFIED_COLUMNS,
    calculate_grading,
)
from candidate_evaluator.progress import init_run, role_for_run, save_exports
from candidate_evaluator.roles import get_role_profile, prepare_output_rows
from candidate_evaluator.rubric_contract import rubric_input_issue
from candidate_evaluator.validation import validate_output_row

TODAY = date(2026, 11, 14)
RUBRIC = "\n".join(f"### LC-{i}" for i in range(1, 6))


def components(evidence=4, recency=3, duration=3):
    return {"evidence": evidence, "recency": recency, "duration": duration, "sources": ["0: acquired users"]}


def span(index=0, **kwargs):
    return {
        "experience_index": index, "basis": "role_span", "start": None,
        "end": None, "written_duration": None, **kwargs,
    }


def experience(start="2022-01", end="2024-01", index=0, **kwargs):
    return {
        "index": index, "description": "Ran paid campaigns.", "company_name": f"Employer {index}",
        "position_or_title": "Marketer", "start_date": start, "end_date": end, **kwargs,
    }


def candidate(*experiences):
    return {
        "candidate_name": "Test Candidate", "linkedin_url": "https://www.linkedin.com/in/example/",
        "linkedin_profile_id": "example", "source_index": 0, "source_row": {}, "experiences": list(experiences),
    }


@pytest.fixture
def grading():
    return {
        "google": None, "meta": None,
        "ownership": {"tier": "none", "components": None},
        "conversion": {"tier": "none", "components": None, "destination_unverified": False},
        "funnel": {"tier": "none", "components": None},
        "metrics": {
            "tier": "none", "components": None,
            "metric": None, "action": None, "improvement": None,
        },
        "periods": [], "unrelated_work": False, "date_quality_warning": False,
        "Strongest Evidence": "", "Missing or Unclear Information": "", "Score Rationale": "",
    }


def score(grading, *experiences):
    row = calculate_grading(grading, candidate(*experiences), TODAY)
    assert validate_output_row(row, "peeko") == []
    return row


def test_role_dropdown_schema_and_rubric_without_calculation_sections():
    app = AppTest.from_string("from app import _role_selector\nimport streamlit as st\nst.write(_role_selector())", default_timeout=15).run()
    app.selectbox[0].select("Peeko").run()
    assert app.markdown[0].value == "peeko"
    role = get_role_profile("peeko")
    required = _response_schema(role)["properties"]["grading"]["required"]
    assert set(required).isdisjoint({*SCORE_COLUMNS, TOTAL_COLUMN, CUTOFF_COLUMN, REVIEW_COLUMN, "Rank Number"})
    assert not rubric_input_issue(RUBRIC, role)
    assert rubric_input_issue("# SDE3", role)


def test_filtered_payload_preserves_qualifying_fields_and_merges_duplicates():
    raw = {
        "display_name": "Candidate", "public_identifier": "example", "skills": ["Global"],
        "education": [{"school": "School"}], "headline": "Marketing", "summary": "About",
        "work_experience": [
            {"role": "Marketer", "start": "2020", "description": "Built paid campaigns"},
            {"role": "Marketer", "start": "2020", "description": "Managed Meta ads", "tools": ["Meta Ads"],
             "skills": [{"name": "Campaigns"}], "employment_type": "Part-time", "is_current": True},
            {"role": "Second role", "start": "2025", "is_current": False},
        ],
    }
    normalized = normalize_candidate(raw, 0, peeko=True)
    role = get_role_profile("peeko")
    payload = _candidate_payload(normalized, role)
    assert payload["Headline"] == "Marketing" and payload["About"] == "About"
    assert payload["Skills"] == ["Global"] and "Education" not in payload and "Website" not in payload
    first, second = payload["experiences"]
    assert first["description"] == "Built paid campaigns | Managed Meta ads"
    assert first["experience_tools"] == ["Meta Ads"]
    assert first["experience_skills"] == ["Campaigns"]
    assert first["employment_type"] == "Part-time" and first["is_current"]
    assert not second["is_current"]


@pytest.mark.parametrize(("source_field", "dates", "expected"), [
    ("work_experience", {"start": {"year": 2024, "month": 6}}, True),
    ("work_experience", {"started_on": "2024-06", "ended_on": None}, True),
    ("work_experience", {"start": "2024-06", "end": "2025-06"}, False),
    ("work_experience", {"start": "2024-06", "is_current": False}, False),
    ("work_experience", {"start": "2024-13"}, False),
    ("work_experience", {"start": "2099-06"}, False),
    ("work_experience", {}, False),
    ("experience", {"startDate": "2024-06"}, False),
    ("experience", {"startDate": "2024-06", "endDate": "Present"}, True),
])
def test_current_employment_export(grading, source_field, dates, expected):
    raw = {source_field: [{"role": "Media Buyer", "company": "Example", **dates}]}
    profile = normalize_candidate(raw, 0, peeko=True)
    row = calculate_grading(grading, profile, TODAY)
    assert profile["experiences"][0]["is_current"] is expected
    assert row["Current Title"] == ("Media Buyer" if expected else "")
    assert row["Current Company"] == ("Example" if expected else "")


@pytest.mark.parametrize(("global_skills", "attached_skills", "hands_on", "expected"), [
    (["Digital Marketing", "PPC"], [], False, 0),
    (["Google Ads"], [], False, 0.3),
    ([], ["Facebook Ads", "Instagram Ads"], False, 0.3),
    (["  Google   AdWords "], ["Meta Ads Manager"], False, 1.0),
    (["Google Ads"], ["Google App Campaigns"], False, 0.3),
    ([], ["Meta Ads"], True, 2.4),
])
def test_skills_only_fallback(grading, global_skills, attached_skills, hands_on, expected):
    profile = normalize_candidate({
        "skills": [{"name": name} for name in global_skills],
        "work_experience": [{
            "role": "Marketer",
            "skills": [{"name": name} for name in attached_skills],
        }],
    }, 0, peeko=True)
    if hands_on:
        grading["google"] = components(4, 0, 0)
    row = calculate_grading(grading, profile, TODAY)
    assert row[SCORE_COLUMNS[0]] == expected
    assert row[TOTAL_COLUMN] == expected
    assert row[UNVERIFIED_COLUMNS[0]] == ("No" if hands_on else "Yes")
    assert row[REVIEW_COLUMN] == "Yes"
    assert validate_output_row(row, "peeko") == []


def test_one_off_duration_scoring_does_not_extend_review_period(grading):
    job = experience(description="Launched a Google and Meta campaign for Diwali.")
    grading["google"] = grading["meta"] = components(4, 0, 2)
    row = score(grading, job)
    assert row[SCORE_COLUMNS[0]] == 9
    assert row["Peeko Audit"]["hands_on_months"] == 0
    assert row[REVIEW_COLUMN] == "Yes"


@pytest.mark.parametrize(("google", "meta", "expected"), [
    (None, None, 0), ((4, 3, 3), None, 6), (None, (4, 2, 1), 4.2),
    ((4, 3, 0), (4, 0, 3), 6), ((4, 3, 3), (3, 0, 0), 4.5), ((4, 3, 3), (4, 3, 3), 15),
])
def test_platform_handling(grading, google, meta, expected):
    grading["google"] = components(*google) if google else None
    grading["meta"] = components(*meta) if meta else None
    row = score(grading)
    assert row[SCORE_COLUMNS[0]] == expected
    assert row[UNVERIFIED_COLUMNS[0]] == ("No" if google or meta else "Yes")
    if bool(google) != bool(meta):
        assert "hands-on work unverified" in row["Missing or Unclear Information"]


@pytest.mark.parametrize(("field", "tier", "expected"), [
    ("ownership", "end_to_end", 5), ("ownership", "creation", 3.5), ("ownership", "optimisation", 1.5),
    ("conversion", "app_conversions", 10), ("conversion", "website_conversions", 7),
    ("conversion", "app_campaign", 5), ("conversion", "website_campaign", 3),
])
def test_tier_weights(grading, field, tier, expected):
    grading[field].update(tier=tier, components=components())
    if tier == "website_campaign":
        grading[field]["destination_unverified"] = True
    row = score(grading)
    assert row[SCORE_COLUMNS[1 if field == "ownership" else 2]] == expected
    if tier == "website_campaign":
        assert "Campaign destination unverified" in row["Missing or Unclear Information"]


@pytest.mark.parametrize(("field", "tier", "points", "expected"), [
    ("funnel", "measured_improvement", (4, 3, 3), 3),
    ("funnel", "change_implemented", (4, 2, 1), 1.4),
    ("funnel", "funnel_analysis", (3, 0, 0), 0.3),
    ("metrics", "quantified_improvement", (4, 3, 3), 10),
    ("metrics", "hands_on", (4, 2, 1), 4.2),
    ("metrics", "keyword_only", (1, 0, 0), 0.3),
])
def test_funnel_and_metric_components_contribute_to_total(grading, field, tier, points, expected):
    grading[field].update(tier=tier, components=components(*points))
    if field == "metrics":
        grading[field].update(metric="CAC", action="Adjusted bids", improvement="20% lower")
    row = score(grading)
    assert row[SCORE_COLUMNS[3 if field == "funnel" else 4]] == expected
    assert row[TOTAL_COLUMN] == expected


def test_all_five_criteria_compute_maximum(grading):
    grading.update(google=components(), meta=components())
    grading["ownership"].update(tier="end_to_end", components=components())
    grading["conversion"].update(tier="app_conversions", components=components())
    grading["funnel"].update(tier="measured_improvement", components=components())
    grading["metrics"].update(tier="quantified_improvement", components=components(),
                              metric="CAC", action="Adjusted bids", improvement="20% lower")
    row = score(grading)
    assert row[TOTAL_COLUMN] == 43
    assert (row[CUTOFF_COLUMN], row[REVIEW_COLUMN]) == ("Yes", "Yes")


@pytest.mark.parametrize(("jobs", "periods", "months", "warning"), [
    ([experience(end="2023-12")], [span()], 23, "No"),
    ([experience()], [span()], 24, "No"),
    ([experience(), experience("2023-01", "2025-01", 1)], [span(), span(1), span()], 36, "No"),
    ([experience("2022", "2022")], [span()], 6, "No"),
    ([experience("2021", "2023"), experience("2023-01", "2024-01", 1)],
     [span(), span(1)], 26, "No"),
    ([experience("2024-11", "Present", is_current=True)], [span()], 24, "No"),
    ([experience("2024-11", "", is_current=False)], [span()], 0, "No"),
    ([experience("2025-01", "", duration="12 months")], [span()], 12, "No"),
    ([experience("", "", duration="12 months")], [span()], 12, "No"),
    ([experience("", "", duration="2 years"), experience("2023-01", "2024-01", 1)],
     [span(), span(1)], 24, "No"),
    ([experience("2027-01", "2028-01")], [span()], 0, "Yes"),
    ([experience("2025-01", "2024-01")], [span()], 0, "Yes"),
    ([experience("2025-02-30", "2026-01")], [span()], 0, "Yes"),
    ([experience()], [span(basis="stated_period", start="2023-04", end="2023-05")], 1, "No"),
])
def test_review_counts_only_nonoverlapping_supported_periods(grading, jobs, periods, months, warning):
    grading.update(google=components(), meta=components(), periods=periods)
    row = score(grading, *jobs)
    assert row["Peeko Audit"]["hands_on_months"] == months
    assert row[REVIEW_COLUMN] == ("Yes" if months < 24 else "No")
    assert row["Date-Quality Warning"] == warning


def test_unrelated_work_and_one_platform_independently_trigger_review(grading):
    grading.update(google=components(), meta=components(), periods=[span()], unrelated_work=True)
    assert score(grading, experience())[REVIEW_COLUMN] == "Yes"
    grading["ownership"].update(tier="creation", components=components())
    grading["conversion"].update(tier="app_campaign", components=components())
    assert score(grading, experience())[REVIEW_COLUMN] == "No"
    grading["meta"] = None
    assert score(grading, experience())[REVIEW_COLUMN] == "Yes"


@pytest.mark.parametrize("case", [
    "missing", "boolean", "fraction", "invalid_tier", "tier_without_components", "dated_title",
    "empty_source", "legacy_budget", "dated_metric_keyword", "invalid_review_index",
    "funnel_without_source", "bad_metric_tier", "missing_metric_change",
])
def test_malformed_provider_fields_are_rejected(grading, case):
    if case == "missing":
        del grading["periods"]
    elif case in {"boolean", "fraction", "dated_title", "empty_source"}:
        grading["google"] = components()
        field, value = {
            "boolean": ("recency", True), "fraction": ("duration", 1.5),
            "dated_title": ("evidence", 2), "empty_source": ("sources", []),
        }[case]
        grading["google"][field] = value
    elif case in {"invalid_tier", "tier_without_components"}:
        grading["ownership"]["tier"] = "other" if case == "invalid_tier" else "creation"
    elif case == "legacy_budget":
        grading["budgets"] = []
    elif case == "dated_metric_keyword":
        grading["metrics"].update(tier="keyword_only", metric="CAC", components=components(1, 1, 0))
    elif case == "invalid_review_index":
        grading["periods"] = [span(999)]
    elif case == "funnel_without_source":
        grading["funnel"].update(tier="change_implemented", components={**components(), "sources": []})
    elif case == "bad_metric_tier":
        grading["metrics"]["tier"] = "other"
    else:
        grading["metrics"].update(tier="quantified_improvement", components=components(),
                                  metric="CAC", action="Adjusted bids", improvement="lower")
    with pytest.raises(ValueError):
        calculate_grading(grading, candidate(experience()), TODAY)


def test_shared_ranks_export_order_and_numeric_excel_cells(grading, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    row = score(grading)
    rows = [
        {**row, "Candidate": "C", TOTAL_COLUMN: 26.9},
        {**row, "Candidate": "B", TOTAL_COLUMN: 27.0},
        {**row, "Candidate": "A", TOTAL_COLUMN: 27.0},
    ]
    prepared = prepare_output_rows(rows, "peeko")
    assert [(row["Candidate"], row["Rank Number"]) for row in prepared] == [("A", 1), ("B", 1), ("C", 3)]
    assert list(prepared[0]) == OUTPUT_COLUMNS
    assert "Peeko Audit" not in prepared[0]
    assert "27.00" in _rows_to_csv_bytes(prepared, OUTPUT_COLUMNS).decode()

    init_run("peeko-run", [candidate()], RUBRIC, "test-model", role_key="peeko")
    assert role_for_run("peeko-run").key == "peeko"
    _, saved_xlsx = save_exports("peeko-run", rows)
    for workbook in (saved_xlsx, BytesIO(_rows_to_xlsx_bytes(prepared, OUTPUT_COLUMNS))):
        cell = load_workbook(workbook).active["K2"]
        assert cell.value == 27 and cell.data_type == "n" and cell.number_format == "0.00"


@pytest.mark.parametrize("provider", ["openai", "deepseek"])
def test_mocked_provider_batch_preserves_raw_audit_and_isolates_bad_candidate(grading, monkeypatch, provider):
    grading["google"] = components()
    invalid = deepcopy(grading)
    invalid["google"]["duration"] = True
    response_text = json.dumps({"evaluations": [
        {"candidate_number": 1, "grading": grading},
        {"candidate_number": 2, "grading": invalid},
    ]})

    def create_response(*args, **kwargs):
        if provider == "deepseek":
            assert kwargs["text"]["format"]["schema"]["type"] == "object"
            return SimpleNamespace(output_text=response_text)
        assert kwargs["response_format"]["json_schema"]["strict"]
        choice = SimpleNamespace(message=SimpleNamespace(content=response_text), finish_reason="stop")
        return SimpleNamespace(choices=[choice])

    endpoint = SimpleNamespace(create=create_response)
    client = SimpleNamespace(chat=SimpleNamespace(completions=endpoint), responses=endpoint)
    monkeypatch.setattr("candidate_evaluator.openai_scoring.OpenAI", lambda **kwargs: client)
    second = {**candidate(), "linkedin_profile_id": "other"}
    outcome = _evaluate_candidate_batch_for_run(
        "key", "model", RUBRIC, [candidate(), second], get_role_profile("peeko"), provider_key=provider,
    )
    valid, failed = outcome["results"]
    assert valid["state"] == "completed" and valid["row"][TOTAL_COLUMN] == 6
    assert valid["row"]["Peeko Audit"]["grading"]["google"]["evidence"] == 4
    assert valid["raw"]["grading"]["google"]["evidence"] == 4
    assert failed["state"] == "failed"


@pytest.mark.parametrize(("duration", "total", "cutoff"), [(1, 28.7, "No"), (2, 29.05, "Yes")])
def test_cutoff_uses_exact_hundredths(grading, duration, total, cutoff):
    grading.update(google=components(), meta=components())
    grading["ownership"].update(tier="creation", components=components(4, 3, duration))
    grading["conversion"].update(tier="app_conversions", components=components())
    grading["funnel"].update(tier="change_implemented", components=components(3, 0, 0))
    grading["metrics"].update(tier="keyword_only", components=components(1, 0, 0), metric="CAC")
    row = score(grading)
    assert row[TOTAL_COLUMN] == total
    assert row[CUTOFF_COLUMN] == cutoff


def test_uploaded_json_and_rubric_use_peeko_importer():
    from app import _load_inputs

    raw = {
        "display_name": "Test Candidate", "public_identifier": "example",
        "work_experience": [{"role": "Marketer", "start": "2023", "tools": ["Google Ads"]}],
    }
    [profile], uploaded_rubric = _load_inputs(
        BytesIO(json.dumps([raw]).encode()), "", BytesIO(RUBRIC.encode()), "", "peeko",
    )
    assert uploaded_rubric == RUBRIC
    assert profile["experiences"][0]["experience_tools"] == ["Google Ads"]
    assert profile["experiences"][0]["is_current"] is True


def test_completed_run_persists_component_audit_and_keeps_exact_export_columns(grading, monkeypatch, tmp_path):
    from candidate_evaluator.progress import mark_completed, result_rows

    monkeypatch.chdir(tmp_path)
    grading["google"] = components()
    row = score(grading)
    init_run("audit", [candidate()], RUBRIC, "test-model", role_key="peeko")
    mark_completed("audit", "example", row, {"grading": grading})
    [restored] = result_rows("audit")
    assert restored["Peeko Audit"]["grading"]["google"] == grading["google"]
    assert list(prepare_output_rows([restored], role_for_run("audit"))[0]) == OUTPUT_COLUMNS



def test_saved_legacy_peeko_results_keep_original_export_schema(tmp_path, monkeypatch):
    from candidate_evaluator.progress import mark_completed, result_rows

    monkeypatch.chdir(tmp_path)
    legacy_rubric = RUBRIC + "\n### LC-6"
    init_run("legacy", [candidate()], legacy_rubric, "test-model", role_key="peeko")
    role = role_for_run("legacy")
    assert rubric_input_issue(legacy_rubric, role)
    row = dict.fromkeys(LEGACY_OUTPUT_COLUMNS, "")
    row.update({"Candidate": "Test Candidate", "Final Score (/40)": 27.0,
                "Scaling — Annual Budget Managed Score (/10)": 6.0})
    mark_completed("legacy", "example", row, {})
    [restored] = prepare_output_rows(result_rows("legacy"), role)
    assert list(restored) == LEGACY_OUTPUT_COLUMNS
    assert restored["Final Score (/40)"] == 27.0
    assert restored["Scaling — Annual Budget Managed Score (/10)"] == 6.0
