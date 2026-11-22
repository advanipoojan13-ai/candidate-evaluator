import csv
import json
from datetime import date
from io import BytesIO, StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from openpyxl import load_workbook

from app import (
    _candidate_input_issue_for_role, _default_rubric_path, _evaluate_candidate_batch_for_run,
    _load_inputs, _rows_to_csv_bytes, _rows_to_xlsx_bytes,
)
from candidate_evaluator import openai_scoring, progress, safegold_performance_marketer as marketing
from candidate_evaluator.roles import get_role_profile, prepare_output_rows, role_options
from candidate_evaluator.rubric_contract import rubric_input_issue
from candidate_evaluator.validation import apply_calculated_fields


ROLE = get_role_profile(marketing.ROLE_KEY)
GOOGLE, META, APP, TESTING, OPTIMISATION, MEASUREMENT = ROLE.category_scores
QUOTE = "I managed Google Ads and tested video against carousel creative."
SOURCE = "work_experience[0].description"
UPLOADED_RUBRIC = """# Test upload for SafeGold performance marketing

| ID | Criterion | Allowed scores | Maximum |
|---|---|---|---:|
| C1 | Google Ads operations | 0, 1, 2, 4, 6 | 6 |
| C2 | Meta Ads operations | 0, 1, 2, 4, 6 | 6 |
| C3 | App acquisition | 0, 1, 2, 5, 8 | 8 |
| C4 | Experimentation | 0, 1, 3, 6, 9 | 9 |
| C5 | Optimisation and scaling | 0, 1, 2, 4, 6 | 6 |
| C6 | Measurement and analysis | 0, 1, 3, 5 | 5 |
| | **Total** | | **40** |
"""


def load_profile(**extra):
    profile = {
        "name": "Example Candidate",
        "public_identifier": "example",
        "work_experience": [{
            "company": "Example Studio", "role": "Performance Marketer",
            "start": "2023", "description": QUOTE,
        }],
        **extra,
    }
    [candidate], rubric = _load_inputs(
        BytesIO(json.dumps({"items": [profile]}).encode()), "", BytesIO(UPLOADED_RUBRIC.encode()), "", ROLE.key,
    )
    return candidate, rubric


def grading(scores):
    audit = {}
    for criterion, value in zip(marketing.CRITERIA, scores):
        state = {None: "unknown", 0: "explicit absence", 1: "mention only"}.get(value, "supported")
        audit[criterion] = {
            "evidence_state": state,
            "claims": [] if value is None else [
                {"source_path": SOURCE, "role_or_project": "Performance Marketer", "supporting_text": QUOTE}
            ],
            "anchor_matched": "" if value is None else f"Score {value}",
            "reason": "The section did not establish the criterion." if value is None else "Example assessed evidence.",
        }
    return {
        **dict(zip(ROLE.category_scores, scores)),
        marketing.AUDIT: audit,
        "Strongest Evidence": "Example Studio: managed Google Ads",
        "Missing or Unclear Information": "Some capabilities are unverified." if None in scores else "",
        "Score Rationale": "The profile provides evidence of Google Ads work.",
        "Fintech Experience": "No",
        "Startup Experience": "No",
        "Relevant Paid-Marketing Duration and Recency": "Google Ads: last use not established",
        "Location and Mumbai Availability": "Not stated",
    }


def test_role_loads_rubric_and_nullable_schema():
    assert role_options()["Safegold - Performance Marketer"] == ROLE.key
    assert _default_rubric_path(ROLE.key) == ""
    assert _load_inputs(None, "", None, "", ROLE.key) == ([], "")
    _, rubric = load_profile()
    assert rubric == UPLOADED_RUBRIC
    assert not rubric_input_issue(rubric, ROLE)
    support = Path(_default_rubric_path("safegold")).read_text(encoding="utf-8")
    assert rubric_input_issue(support, ROLE)
    assert rubric_input_issue(rubric.replace("0, 1, 3, 6, 9", "0, 1, 2, 6, 9"), ROLE)
    props = openai_scoring._response_schema(ROLE)["properties"]["grading"]["properties"]
    assert props[GOOGLE]["anyOf"] == [{"type": "integer", "enum": [0, 1, 2, 4, 6]}, {"type": "null"}]
    assert props[marketing.AUDIT]["required"] == list(marketing.CRITERIA)
    assert marketing.TOTAL not in props and "Current Company" not in props


def test_payload_preserves_source_paths_dates_and_partial_status():
    person, _ = load_profile(
        provider="LINKEDIN", visibility="partial", throttled_sections=["projects"],
        summary="Optimised paid acquisition", skills=["Global Meta Ads"], education=[{"school": "School"}],
        location="Mumbai", current_positions=[
            {"company": "Example Studio", "role": "Performance Marketer", "description": "Managed pacing."},
        ],
        specifics={"linkedin": {"experience": [
            {"company": "Different Studio", "title": "Analyst", "skills": [{"name": "GA4"}]},
        ]}},
        projects=[{"name": "Acquisition project", "description": "Ran campaigns", "start": "2022"}],
    )
    assert not _candidate_input_issue_for_role(person, ROLE)
    payload = openai_scoring._candidate_payload(person, ROLE)
    assert {"Skills", "Education", "Website"}.isdisjoint(payload)
    assert payload["Location"] == "Mumbai"
    assert payload["Source Availability"] == {"visibility": "partial", "throttled_sections": ["projects"]}
    assert payload["Source Text"][SOURCE] == QUOTE
    assert payload["Source Text"]["specifics.linkedin.experience[0].skills[0].name"] == "GA4"
    assert len(payload["experiences"]) == 2
    first = payload["experiences"][0]
    assert first["start_date"] == "2023"
    assert first["calculated_dates"]["start_month"] is None
    assert "months_since_end" not in first["calculated_dates"]
    assert set(first["source_paths"]) >= {SOURCE, "current_positions[0].description"}
    assert payload["Projects"][0]["start_date"] == "2022"
    assert payload["Source Text"]["projects[0].description"] == "Ran campaigns"


def test_current_company_prefers_latest_start_and_retains_uncertain_ties():
    today = date(2026, 11, 22)
    older = {"company_name": "Older", "position_or_title": "Analyst", "start_date": "2022-05", "is_current": True}
    first = {"company_name": "First", "position_or_title": "Lead", "start_date": "2024", "is_current": True}
    second = {"company_name": "Second", "position_or_title": "Marketer", "start_date": "2024-06", "is_current": True}
    assert marketing.current_employment([older, first, second], today) == ("First | Second", "Lead | Marketer")
    assert marketing.current_employment([
        {**older, "is_current": False, "end_date": "2023-03"},
        {**first, "is_current": False, "end_date": "2024-07"},
    ], today) == ("First", "Lead")


def test_unipile_open_ended_job_wins_over_older_ended_job():
    candidate, _ = load_profile(work_experience=[
        {"company": "Old Studio", "role": "Analyst", "start": "2020-03", "end": "2022-06"},
        {"company": "Current Studio", "role": "Marketer", "start": "2023-02"},
        {"company": "Undated Studio", "role": "Consultant"},
        {"company": "Unconfirmed Studio", "role": "Lead", "start": "2024-05", "is_current": False},
    ])
    assert [role["is_current"] for role in candidate["experiences"]] == [False, True, False, False]
    row = apply_calculated_fields(grading((None,) * 6), candidate, ROLE)
    assert (row["Current Company"], row["Current Title"]) == ("Current Studio", "Marketer")


@pytest.mark.parametrize("invalid", [3, -1, True, "4", 4.0])
def test_rejects_invalid_score_types_and_tiers(invalid):
    candidate, _ = load_profile()
    with pytest.raises(ValueError, match="Google Ads Score"):
        apply_calculated_fields(grading((invalid, None, None, None, None, None)), candidate, ROLE)


def test_rejects_missing_scores_and_unverifiable_claims():
    candidate, _ = load_profile()
    grade = grading((2, None, None, None, None, None))
    grade[marketing.AUDIT]["C1"]["claims"][0]["supporting_text"] = "Invented results."
    with pytest.raises(ValueError, match="quote must match"):
        apply_calculated_fields(grade, candidate, ROLE)
    del grade[META]
    with pytest.raises(ValueError, match="Missing required score"):
        apply_calculated_fields(grade, candidate, ROLE)


def test_full_evaluator_path_exports_incomplete_and_complete_results(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    candidate, rubric = load_profile()
    second = {**candidate, "linkedin_profile_id": "second", "source_index": 1}
    candidates = [candidate, second]
    scores = [(2, None, 0, 6, None, 1), (6, 6, 8, 9, 6, 5)]
    model_response = {"evaluations": [
        {"candidate_number": index, "grading": grading(values)} for index, values in enumerate(scores, 1)
    ]}
    monkeypatch.setattr(openai_scoring, "OpenAI", lambda **kwargs: object())
    monkeypatch.setattr(openai_scoring, "_create_response", lambda *args: SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(model_response)))], usage=None,
    ))
    batch = _evaluate_candidate_batch_for_run("stub", "stub", rubric, candidates, ROLE)
    assert [result["state"] for result in batch["results"]] == ["completed", "completed"], batch
    progress.init_run("pm", candidates, rubric, "stub", ROLE.key)
    progress.commit_batch_results("pm", candidates, batch)
    assert progress.role_for_run("pm").key == ROLE.key
    partial, complete = progress.result_rows("pm")
    assert partial[META] is None and partial[APP] == 0
    assert partial[marketing.TOTAL].startswith("9 evidenced points; incomplete")
    assert "C2 Meta Ads operations" in partial[marketing.TOTAL]
    assert complete[marketing.TOTAL] == 40
    assert partial[marketing.AUDIT]["C2"]["score"] is None
    assert partial[marketing.AUDIT]["C3"]["score"] == 0
    assert partial["Current Company"] == "Example Studio"
    rows = prepare_output_rows([partial, complete], ROLE)
    assert list(rows[0]) == ROLE.output_columns
    assert len(rows[0]) == 18
    csv_rows = list(csv.DictReader(StringIO(_rows_to_csv_bytes(rows, ROLE.output_columns).decode())))
    assert csv_rows[0][META] == "" and csv_rows[0][APP] == "0"
    workbook = load_workbook(BytesIO(_rows_to_xlsx_bytes(rows, ROLE.output_columns)))
    values = list(workbook.active.values)
    assert values[1][ROLE.output_columns.index(META)] is None
    assert values[1][ROLE.output_columns.index(APP)] == 0
    assert values[2][ROLE.output_columns.index(marketing.TOTAL)] == 40
