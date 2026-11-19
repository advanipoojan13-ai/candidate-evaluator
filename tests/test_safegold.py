import json
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from openpyxl import load_workbook

from app import (
    _default_rubric_path, _evaluate_candidate_batch_for_run, _load_inputs,
    _rows_to_csv_bytes, _rows_to_xlsx_bytes,
)
from candidate_evaluator import openai_scoring
from candidate_evaluator.extractor import normalize_candidate
from candidate_evaluator.roles import (
    SAFEGOLD_MEDIUM_COLUMN, SAFEGOLD_MEDIUM_SCORE, get_role_profile, prepare_output_rows, role_options,
)
from candidate_evaluator.rubric_contract import rubric_input_issue
from candidate_evaluator.safegold import CHANNEL_COMPONENTS, CHANNELS
from candidate_evaluator.validation import apply_calculated_fields, coerce_fixed_row, validate_output_row


ROOT = Path(__file__).resolve().parents[1]
ROLE = get_role_profile("safegold")
RUBRIC = (ROOT / "rubrics" / "safegold.md").read_text(encoding="utf-8")


def channel(evidence=4, recency=3, duration=3):
    return {"evidence": evidence, "recency": recency, "duration": duration}


def grading(maximum=False, **channels):
    return {
        **{
            name: maximum_points if maximum else 0
            for name, maximum_points in ROLE.component_score_maxima.items()
            if not name.startswith("C6 ")
        },
        CHANNEL_COMPONENTS: dict.fromkeys(CHANNELS) | channels,
        "Frontline Customer Support Unverified": "No",
        "Issue Resolution, Complaints & Escalations Unverified": "No",
        "Date-Quality Warning": "No",
        "Strongest Evidence": "Example Bank: handled phone and chat queries",
        "Missing or Unclear Information": "Language proficiency is unverified.",
        "Score Rationale": "Direct customer support and escalation handling are documented.",
    }


def candidate():
    return normalize_candidate({
        "name": "Example Candidate", "public_identifier": "example-candidate",
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


def test_role_loads_unipile_and_bundled_rubric_with_filtered_evidence():
    assert role_options()["SafeGold - Customer Support"] == "safegold"
    rubric_path = _default_rubric_path("safegold")
    assert Path(rubric_path).read_text(encoding="utf-8") == RUBRIC
    work = {
        "role": "Support Agent", "company": "Example Bank", "start": {"year": 2022, "month": 1},
        "description": "Handled chat and calls", "skills": [{"name": "Case escalation"}],
        "tools": ["Zendesk"], "logo": "Logo", "location": "City", "status": "Full-time",
    }
    raw = {
        "name": "Example Candidate", "public_identifier": "example",
        "summary": "Phone and chat support", "headline": "Support Agent", "skills": ["Global skill"],
        "education": [{"school": "School"}], "location": "City", "network_distance": 2,
        "work_experience": [work, {**work, "tools": ["Freshdesk"]}],
        "projects": [{"name": "Help Desk", "description": "Live project", "start": "2022-02", "end": "2023-08"}],
    }
    override = RUBRIC + "\nAdditional evidence example.\n"
    [person], rubric = _load_inputs(
        BytesIO(json.dumps({"items": [raw]}).encode()), "", BytesIO(override.encode()), rubric_path, ROLE.key,
    )
    assert rubric == override
    assert not rubric_input_issue(rubric, ROLE)
    assert person["source_format"] == "unipile"
    assert all(work["is_current"] for work in person["experiences"])
    payload = openai_scoring._candidate_payload(person, ROLE)
    assert set(payload) == {
        "LinkedIn Profile ID", "LinkedIn URL", "Candidate Name", "Headline", "About", "experiences", "Projects",
    }
    [work] = payload["experiences"]
    assert {"experience_location", "employment_type", "workplace_type"}.isdisjoint(work)
    assert work["experience_skills"] == ["Case escalation"]
    assert work["experience_tools"] == ["Zendesk", "Freshdesk"]
    assert work["calculated_dates"]["months_since_end"] == 0
    assert payload["Projects"][0]["calculated_dates"]["duration_months"] == 18
    assert len(person["experiences"]) == 2


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
    assert not person["experiences"][0]["is_current"]
    row = scored(grading(), person)
    assert (row["Current Company"], row["Current Title"]) == ("", "")


@pytest.mark.parametrize("channels,expected_label,points", [
    ({}, "", 0),
    ({"Social Media": channel()}, "Social Media", 2),
    ({"Email": channel(), "Social Media": channel()}, "Email", 4),
    ({"Chat": channel(), "Email": channel()}, "Chat", 6),
    ({"Calls": channel(), "Email": channel()}, "Calls", 8),
    ({"Calls": channel(), "Chat": channel(), "Email": channel()}, "Calls + Chat", 10),
    ({"Calls": channel(4, 1, 3), "Chat": channel(3, 3, 1), "Email": channel()}, "Calls + Chat", 5),
])
def test_channel_priority_and_componentwise_minimum(channels, expected_label, points):
    row = scored(grading(**channels))
    assert row[SAFEGOLD_MEDIUM_COLUMN] == expected_label
    assert row[SAFEGOLD_MEDIUM_SCORE] == row[ROLE.total_column] == points
    if points == 5:
        assert [row[name] for name in ROLE.component_scoring[SAFEGOLD_MEDIUM_SCORE].columns] == [3, 1, 1]


def test_maximum_and_exact_export_columns():
    top = scored(grading(maximum=True, Calls=channel(), Chat=channel()))
    bottom = scored(grading())
    assert list(top[column] for column in ROLE.category_scores) == [10, 12, 8, 8, 5, 10]
    assert top[ROLE.total_column] == 53
    assert len(ROLE.component_score_maxima) == 18
    assert (top["Current Company"], top["Current Title"]) == ("Example Bank", "Support Agent")
    output = prepare_output_rows([bottom, top], ROLE)
    assert list(output[0]) == ROLE.output_columns
    assert [row["Rank Number"] for row in output] == [1, 2]
    assert [row[ROLE.total_column] for row in output] == [53, 0]
    csv = _rows_to_csv_bytes(output, ROLE.output_columns).decode("utf-8")
    assert "C6 Evidence (0-4)" not in csv and "Calls + Chat" in csv
    sheet = load_workbook(BytesIO(_rows_to_xlsx_bytes(output, ROLE.output_columns))).active
    assert [cell.value for cell in sheet[1]] == ROLE.output_columns
    assert sheet.cell(2, ROLE.output_columns.index(ROLE.total_column) + 1).value == 53


@pytest.mark.parametrize("old,new", [
    ("Maximum score:** 53", "Maximum score:** 53.5"),
    ("| Frontline Customer Support | x1.0 | 10 |", "| Frontline Customer Support | x1.1 | 11 |"),
    ("| x0.80 | 8 |", "| x0.70 | 7 |"),
    ("| 2 | Calls |", "| 3 | Calls |"),
])
def test_rubric_rejects_mismatched_scoring(old, new):
    assert old in RUBRIC
    assert "does not match" in rubric_input_issue(RUBRIC.replace(old, new), ROLE)


def test_schema_requests_channel_components_without_calculated_fields():
    schema = openai_scoring._response_schema(ROLE)["properties"]["grading"]
    assert set(schema["required"]) == set(grading())
    assert set(ROLE.category_scores).isdisjoint(schema["properties"])
    assert {ROLE.total_column, SAFEGOLD_MEDIUM_COLUMN}.isdisjoint(schema["properties"])
    assert set(schema["properties"][CHANNEL_COMPONENTS]["required"]) == set(CHANNELS)


@pytest.mark.parametrize("provider", ["openai", "deepseek"])
def test_provider_path_scores_valid_candidate_and_rejects_invalid_candidate(monkeypatch, provider):
    valid = grading(maximum=True, Calls=channel(), Chat=channel())
    invalid = grading(Calls=channel(evidence=0))
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
    assert first["state"] == "completed" and first["row"][ROLE.total_column] == 53
    assert second["state"] == "failed" and "Calls evidence" in second["error"]


def test_role_selection_loads_default_rubric_in_streamlit(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    monkeypatch.delenv("RAILWAY_ENVIRONMENT_ID", raising=False)
    app = AppTest.from_file(str(ROOT / "app.py")).run()
    next(widget for widget in app.text_input if widget.label == "Or JSON file path").set_value("")
    next(widget for widget in app.selectbox if widget.label == "Evaluation role").select(ROLE.label).run()
    assert not app.exception and not app.error
    assert any(widget.value == "Rubric loaded: yes" for widget in app.markdown)
    assert next(widget for widget in app.text_input if widget.label == "Or rubric file path").value == str(
        ROOT / "rubrics" / "safegold.md"
    )
