import csv
import io
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from app import _default_rubric_path, _load_inputs, _rows_to_csv_bytes, _rows_to_xlsx_bytes
from candidate_evaluator.extractor import normalize_candidate
from candidate_evaluator.openai_scoring import _candidate_payload, _fixed_prompt, _response_schema
from candidate_evaluator.roles import get_role_profile, prepare_output_rows, role_options
from candidate_evaluator.validation import apply_calculated_fields, coerce_fixed_row, validate_output_row


ROLE = get_role_profile("lucio")


def test_lucio_uses_uploaded_rubric_and_sends_relevant_evidence():
    assert role_options()[ROLE.label] == "lucio"
    path = _default_rubric_path("lucio")
    bundled = Path(path).read_text(encoding="utf-8")
    uploaded = bundled + "\nUse revised examples for marketing evidence.\n"
    upload = SimpleNamespace(getvalue=lambda: uploaded.encode())
    assert _load_inputs(None, "", upload, path, "lucio")[1] == uploaded
    assert _fixed_prompt(ROLE, uploaded).endswith(uploaded)

    role = {
        "title": "Marketing Intern",
        "company": {"name": "Example Co", "headquarters": "USA"},
        "startDate": "2025-01",
        "endDate": "Present",
    }
    profile = {
        "fullName": "Example Candidate",
        "experience": [role, {**role, "company": {"name": "Example Co"},
                               "company_description": "Serves clients in the UK."}],
        "education": [{"degree": "LLB", "start": "2024", "end": "2027"}],
        "projects": [{"name": "Campaign", "startDate": "2025-02"}],
        "volunteering": [{"title": "Community campaign", "description": "Ran outreach."}],
        "skills": ["Field Marketing"],
    }
    person = normalize_candidate(profile, 0, lucio=True, include_project_dates=True)
    payload = _candidate_payload(person, ROLE)
    assert "LLB" in payload["Education"][0]
    assert payload["Projects"][0]["start_date"] == "2025-02"
    assert payload["Volunteer Experience"][0]["description"] == "Ran outreach."
    assert payload["Skills"] == ["Field Marketing"]
    assert len(payload["experiences"]) == 1
    assert payload["experiences"][0]["employer_details"] == {
        "headquarters": "USA", "description": "Serves clients in the UK.",
    }


def test_lucio_keeps_raw_components_out_of_display_and_exports():
    schema = _response_schema(ROLE)["properties"]["grading"]
    grading = {
        "C1 Evidence": 1.5, "C1 Recency": 2, "C1 Duration": 1,
        "C2 Evidence": 4, "C2 Recency": 2, "Law Degree": "Yes",
        "Strongest Evidence": "Experience: campaign outreach",
        "Missing or Unclear Information": "",
        "Score Rationale": "Marketing work and international exposure are supported.",
    }
    assert set(schema["required"]) == set(grading)
    assert schema["properties"]["C1 Evidence"]["type"] == "number"
    assert schema["properties"]["C1 Recency"]["type"] == "integer"
    assert schema["properties"]["Law Degree"]["enum"] == ["Yes", "No"]

    def scoring_row(values):
        evaluated = apply_calculated_fields(
            {"Candidate": "Example Candidate", "Profile URL": "", **values}, {}, ROLE,
        )
        return coerce_fixed_row(evaluated, ROLE)

    row = scoring_row(grading)
    assert validate_output_row(row, ROLE) == []
    assert row[ROLE.total_column] == pytest.approx(5.4 + 6 * 8 / 7)
    assert scoring_row({**grading, **ROLE.component_score_maxima})[ROLE.total_column] == 20
    for invalid in ({"C1 Recency": 1.5}, {"C2 Evidence": 4.5}, {"Law Degree": "Maybe"}):
        evaluated = apply_calculated_fields(
            {"Candidate": "Example Candidate", "Profile URL": "", **grading, **invalid}, {}, ROLE,
        )
        assert validate_output_row(evaluated, ROLE)
    displayed = prepare_output_rows([row], ROLE)
    assert list(displayed[0]) == ROLE.output_columns
    assert ROLE.output_columns[ROLE.output_columns.index(ROLE.total_column) + 1] == "Law Degree"
    assert displayed[0][ROLE.total_column] == 12.3
    assert not set(ROLE.component_score_maxima).intersection(displayed[0])
    csv_rows = list(csv.DictReader(io.StringIO(_rows_to_csv_bytes(displayed, ROLE.report_columns).decode())))
    assert csv_rows[0][ROLE.total_column] == "12.3"
    workbook = _rows_to_xlsx_bytes(displayed, ROLE.report_columns)
    frame = pd.read_excel(io.BytesIO(workbook))
    assert list(frame.columns) == ROLE.output_columns
    assert frame.loc[0, ROLE.total_column] == 12.3
