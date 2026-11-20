import csv
import json
from io import BytesIO, StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from openpyxl import load_workbook

from app import (
    _candidate_input_issue_for_role, _default_rubric_path, _evaluate_candidate_batch_for_run,
    _load_inputs, _rows_to_csv_bytes, _rows_to_xlsx_bytes,
)
from candidate_evaluator import openai_scoring, progress
from candidate_evaluator.extractor import normalize_candidate
from candidate_evaluator.roles import SAFEGOLD_CHANNELS_COLUMN, get_role_profile, prepare_output_rows, role_options
from candidate_evaluator.rubric_contract import rubric_input_issue
from candidate_evaluator.safegold import CHANNELS, LEGACY_OUTPUT_COLUMNS, LEGACY_SCORES, LEGACY_TOTAL
from candidate_evaluator.validation import apply_calculated_fields, coerce_fixed_row, validate_output_row


ROOT = Path(__file__).resolve().parents[1]
ROLE = get_role_profile("safegold")
RUBRIC = (ROOT / "rubrics" / "safegold.md").read_text(encoding="utf-8")
FACING, SUPPORT_CHANNELS, BANKING, ARABIC = ROLE.category_scores


def grading(scores=(0, 0, 0, 0), channels=()):
    facing, _, _, arabic = scores
    return {
        **dict(zip(ROLE.category_scores, scores)),
        SAFEGOLD_CHANNELS_COLUMN: list(channels),
        "Arabic Proficiency Identified": "Native" if arabic else "Unverified",
        "Arabic Unverified": "No" if arabic else "Yes",
        "Customer-Facing Experience Unverified": "No" if facing >= 10 else "Yes",
        "Strongest Evidence": "Example Bank: handled customer enquiries" if facing else "",
        "Missing or Unclear Information": "Arabic is unverified." if not arabic else "",
        "Score Rationale": "Relevant professional responsibilities are recorded where available.",
    }


def candidate(name="Example Candidate"):
    return normalize_candidate({
        "name": name, "public_identifier": name.lower().replace(" ", "-"),
        "work_experience": [{
            "company": "Example Bank", "role": "Support Agent", "start": "2020-01",
            "description": "Handled customer support calls and chat. Investigated failed payments.",
        }],
    }, 0, safegold=True)


def scored(values, person=None):
    person = candidate() if person is None else person
    row = apply_calculated_fields({
        "Candidate": person["candidate_name"], "Profile URL": person["linkedin_url"],
        "Rank Number": "", **values,
    }, person, ROLE)
    row = coerce_fixed_row(row, ROLE)
    assert validate_output_row(row, ROLE) == []
    return row


def test_role_loads_exact_rubric_and_forwards_only_scoring_evidence():
    assert role_options()["SafeGold - Customer Support"] == "safegold"
    rubric_path = _default_rubric_path("safegold")
    work = {
        "role": "Support Agent", "company": "Example Bank", "start": {"year": 2022, "month": 1},
        "description": "Handled customer calls", "skills": [{"name": "Case escalation"}],
        "tools": ["CRM"], "location": "City", "status": "Full-time",
    }
    raw = {
        "name": "Example Candidate", "public_identifier": "example",
        "summary": "Phone support", "headline": "Support Agent",
        "skills": ["Banking"], "topSkills": ["Unrelated skill"],
        "languages": [{"name": "Arabic", "proficiency": "NATIVE_OR_BILINGUAL"}],
        "education": [{"school": "School"}], "location": "City",
        "work_experience": [work, {**work, "description": "Resolved email tickets", "skills": ["Email Support"]}],
        "projects": [{"name": "Help Desk", "description": "Customer support", "tools": ["Zendesk"], "start": "2022-02"}],
    }
    [person], rubric = _load_inputs(
        BytesIO(json.dumps({"items": [raw]}).encode()), "", None, rubric_path, ROLE.key,
    )
    assert rubric == RUBRIC
    assert not rubric_input_issue(rubric, ROLE)
    assert person["source_format"] == "unipile"
    payload = openai_scoring._candidate_payload(person, ROLE)
    assert set(payload) == {
        "LinkedIn Profile ID", "LinkedIn URL", "Candidate Name", "Headline", "About", "experiences",
        "Projects", "Skills", "Languages",
    }
    assert payload["Skills"] == ["Banking"]
    assert payload["Languages"] == [{"name": "Arabic", "proficiency": "NATIVE_OR_BILINGUAL"}]
    assert payload["Projects"] == [{"name": "Help Desk", "description": "Customer support", "technologies": ["Zendesk"]}]
    [merged_work] = payload["experiences"]
    assert merged_work == {
        "company_name": "Example Bank", "position_or_title": "Support Agent",
        "description": "Handled customer calls | Resolved email tickets",
        "experience_skills": ["Case escalation", "Email Support"],
    }
    assert len(person["experiences"]) == 2
    assert all(work["is_current"] for work in person["experiences"])


def test_nested_language_and_partial_profile_can_be_scored():
    person = normalize_candidate({
        "name": "Example Candidate", "public_identifier": "example", "visibility": "partial",
        "specifics": {"linkedin": {"languages": ["Arabic"], "throttled_sections": ["linkedin_work_experience"]}},
    }, 0, safegold=True)
    assert not _candidate_input_issue_for_role(person, ROLE)
    payload = openai_scoring._candidate_payload(person, ROLE)
    assert payload["Languages"] == [{"name": "Arabic"}]
    assert "experiences" not in payload
    row = scored(grading((0, 0, 0, 3)), person)
    assert row[ROLE.total_column] == 3
    assert row["Customer-Facing Experience Unverified"] == "Yes"


@pytest.mark.parametrize("role_details", [
    {"start": "2021-03", "is_current": False},
    {"start": "9999-01"},
    {"start": "unknown"},
    {"start": "2020-01", "end": "2021-03"},
])
def test_unipile_does_not_mark_ended_invalid_or_explicit_noncurrent_roles_current(role_details):
    person = normalize_candidate({
        "name": "Example Candidate", "public_identifier": "example",
        "work_experience": [{"role": "Support Agent", "company": "Example Bank", **role_details}],
    }, 0, safegold=True)
    row = scored(grading(), person)
    assert (row["Current Company"], row["Current Title"]) == ("", "")


@pytest.mark.parametrize("count,points", [(0, 0), (1, 4), (2, 6), (3, 8), (4, 10), (5, 10)])
def test_distinct_support_channel_score_and_order(count, points):
    channels = (*reversed(CHANNELS[:count]), *CHANNELS[:1]) if count else ()
    row = scored(grading((0, points, 0, 0), channels))
    assert row[SUPPORT_CHANNELS] == row[ROLE.total_column] == points
    assert row[SAFEGOLD_CHANNELS_COLUMN] == (" | ".join(CHANNELS[:count]) or "Not stated")


def test_maximum_and_exact_export_columns():
    top = scored(grading((15, 10, 10, 5), CHANNELS))
    bottom = scored(grading())
    assert (top["Current Company"], top["Current Title"]) == ("Example Bank", "Support Agent")
    output = prepare_output_rows([bottom, top], ROLE)
    expected_columns = [
        line.split(". ", 1)[1]
        for line in RUBRIC.split("Export exactly these columns:", 1)[1].strip().split("\n\n", 1)[0].splitlines()
    ]
    assert list(output[0]) == ROLE.output_columns == expected_columns
    assert [row["Rank Number"] for row in output] == [1, 2]
    assert [row[ROLE.total_column] for row in output] == [40, 0]
    csv_text = _rows_to_csv_bytes(output, ROLE.output_columns).decode("utf-8-sig")
    assert next(csv.reader(StringIO(csv_text))) == expected_columns
    sheet = load_workbook(BytesIO(_rows_to_xlsx_bytes(output, ROLE.output_columns))).active
    assert [cell.value for cell in sheet[1]] == expected_columns
    assert sheet.cell(2, expected_columns.index(ROLE.total_column) + 1).value == 40


def test_ranking_uses_criterion_order_then_name():
    rows = [
        scored(grading((10, 4, 6, 0), CHANNELS[:1]), candidate("Zulu")),
        scored(grading((10, 4, 6, 0), CHANNELS[:1]), candidate("Alpha")),
        scored(grading((12, 0, 8, 0)), candidate("Bravo")),
        scored(grading((10, 6, 3, 2), CHANNELS[:2]), candidate("Charlie")),
        scored(grading((10, 6, 0, 5), CHANNELS[:2]), candidate("Delta")),
        scored(grading((10, 6, 0, 2), CHANNELS[:2]), candidate("Echo")),
    ]
    output = prepare_output_rows(rows, ROLE)
    assert [row["Candidate"] for row in output] == ["Charlie", "Delta", "Bravo", "Alpha", "Zulu", "Echo"]
    assert [row["Rank Number"] for row in output] == list(range(1, 7))


@pytest.mark.parametrize("old,new", [
    ("Maximum Score:** 40", "Maximum Score:** 53"),
    ("| Customer-Facing Experience | 15 |", "| Customer-Facing Experience | 14 |"),
    ("| 2 | 6 |", "| 2 | 5 |"),
    ("| Arabic not mentioned | 0 |", "| Arabic not mentioned | 1 |"),
])
def test_rubric_rejects_mismatched_scoring(old, new):
    assert old in RUBRIC
    assert "does not match" in rubric_input_issue(RUBRIC.replace(old, new), ROLE)


def test_schema_requests_fixed_scores_without_calculated_fields():
    schema = openai_scoring._response_schema(ROLE)["properties"]["grading"]
    assert set(schema["required"]) == set(grading())
    assert {ROLE.total_column, ROLE.outcome_column}.isdisjoint(schema["properties"])
    for column, allowed in ROLE.allowed_scores.items():
        assert schema["properties"][column]["type"] == "integer"
        assert schema["properties"][column]["enum"] == sorted(allowed)
    assert schema["properties"][SAFEGOLD_CHANNELS_COLUMN]["items"]["enum"] == list(CHANNELS)


@pytest.mark.parametrize("values,message", [
    ({FACING: 14}, "JSON integer"),
    ({BANKING: "3"}, "JSON integer"),
    ({ARABIC: True}, "JSON integer"),
    ({SUPPORT_CHANNELS: 6}, "0 distinct channels"),
    ({SAFEGOLD_CHANNELS_COLUMN: ["Unknown"]}, "channel categories"),
    ({"Arabic Unverified": "No"}, "must match"),
])
def test_rejects_inconsistent_model_grading(values, message):
    with pytest.raises(ValueError, match=message):
        apply_calculated_fields(grading() | values, candidate(), ROLE)


@pytest.mark.parametrize("provider", ["openai", "deepseek"])
def test_provider_path_accepts_valid_candidate_and_rejects_invalid_candidate(monkeypatch, provider):
    valid = grading((15, 10, 10, 5), CHANNELS)
    invalid = grading((0, 6, 0, 0), CHANNELS[:1])
    data = {"evaluations": [
        {"candidate_number": 1, "grading": valid},
        {"candidate_number": 2, "grading": invalid},
    ]}
    content = json.dumps(data)
    response = SimpleNamespace(output_text=content, choices=[SimpleNamespace(message=SimpleNamespace(content=content))])
    client = SimpleNamespace(
        responses=SimpleNamespace(create=lambda **kwargs: response),
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: response)),
    )
    monkeypatch.setattr(openai_scoring, "OpenAI", lambda **kwargs: client)
    result = _evaluate_candidate_batch_for_run("fake", "test", RUBRIC, [candidate(), candidate()], ROLE, provider)
    first, second = result["results"]
    assert first["state"] == "completed" and first["row"][ROLE.total_column] == 40
    assert second["state"] == "failed" and "1 distinct channels" in second["error"]


def test_previous_runs_export_original_scores_and_reject_resuming(tmp_path, monkeypatch):
    monkeypatch.setattr(progress, "RUNS_DIR", tmp_path)
    run_path = tmp_path / "old"
    run_path.mkdir()
    (run_path / "status.json").write_text(json.dumps({"role": ROLE.key}), encoding="utf-8")
    old_rubric = "# Previous rubric\n**Maximum score:** 53\n" + LEGACY_TOTAL
    (run_path / "rubric.md").write_text(old_rubric, encoding="utf-8")
    legacy_role = progress.role_for_run("old")
    [row] = prepare_output_rows([{LEGACY_TOTAL: 53, LEGACY_SCORES[0]: 10}], legacy_role)
    assert list(row) == LEGACY_OUTPUT_COLUMNS
    assert row[LEGACY_TOTAL] == 53
    assert "does not match" in rubric_input_issue(old_rubric, legacy_role)


def test_role_selection_loads_default_rubric_in_streamlit(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    monkeypatch.delenv("RAILWAY_ENVIRONMENT_ID", raising=False)
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=15).run()
    next(widget for widget in app.text_input if widget.label == "Or JSON file path").set_value("")
    next(widget for widget in app.selectbox if widget.label == "Evaluation role").select(ROLE.label).run()
    assert not app.exception and not app.error
    assert any(widget.value == "Rubric loaded: yes" for widget in app.markdown)
    assert next(widget for widget in app.text_input if widget.label == "Or rubric file path").value == str(
        ROOT / "rubrics" / "safegold.md"
    )
