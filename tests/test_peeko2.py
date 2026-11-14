from datetime import date
from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import load_workbook

from app import _default_rubric_path, _load_inputs, _rows_to_csv_bytes, _rows_to_xlsx_bytes
from candidate_evaluator import peeko, peeko2
from candidate_evaluator.openai_scoring import _candidate_payload, _response_schema
from candidate_evaluator.roles import get_role_profile, prepare_output_rows, role_options
from candidate_evaluator.rubric_contract import rubric_input_issue
from candidate_evaluator.validation import apply_calculated_fields, validate_output_row

TODAY = date(2026, 11, 14)
ROLE = get_role_profile("peeko2")


def tier(name, evidence=4, index=0):
    return {"tier": name, "components": {
        "evidence": evidence, "sources": ["Relevant profile evidence"],
        "recency_experience_index": index,
    }}


def profile(**dates):
    return {"candidate_name": "Example", "experiences": [{
        "index": 0, "description": "Ran Google and Meta paid acquisition.",
        "company_name": "Example Co", "position_or_title": "Marketer", **dates,
    }]}


@pytest.fixture
def grading():
    empty = {"tier": "none", "components": None}
    return {
        "google": {"level": "none", "source": None},
        "meta": {"level": "none", "source": None},
        "ownership": dict(empty), "funnel": dict(empty),
        "conversion": {**empty, "destination_unverified": False},
        "metrics": {**empty, "metric": None, "action": None, "measured_result": None},
        "date_quality_warning": False,
        **dict.fromkeys(peeko.NARRATIVE_COLUMNS, ""),
    }


def score(grading, candidate=None):
    row = peeko2.calculate_grading(grading, candidate or profile(is_current=True), TODAY)
    assert validate_output_row(row, ROLE) == []
    return row


@pytest.mark.parametrize("google,meta,expected", [
    ("none", "none", 0), ("mention", "none", 4), ("none", "hands_on", 7),
    ("mention", "mention", 8), ("hands_on", "mention", 11), ("hands_on", "hands_on", 14),
])
def test_platform_anchors_and_review(grading, google, meta, expected):
    grading.update(google={"level": google, "source": "Google Ads"},
                   meta={"level": meta, "source": "Meta Ads"})
    row = score(grading)
    assert row[peeko2.TOTAL_COLUMN] == expected
    assert row[peeko.REVIEW_COLUMN] == ("No" if expected == 14 else "Yes")
    assert row[peeko.UNVERIFIED_COLUMNS[0]] == ("Yes" if expected in {0, 4, 8} else "No")


@pytest.mark.parametrize("field,name,expected", [
    ("ownership", "ownership", 7), ("ownership", "creation", 5.95),
    ("ownership", "optimisation", 4.9), ("ownership", "management", 4.2),
    ("conversion", "app_conversions", 5), ("conversion", "website_conversions", 3.5),
    ("conversion", "app_campaign", 2.5), ("conversion", "website_campaign", 1.5),
    ("funnel", "measured_improvement", 3), ("funnel", "change_implemented", 2.01),
    ("funnel", "funnel_analysis", .99), ("metrics", "quantified_improvement", 7),
    ("metrics", "quantified_result", 5.95), ("metrics", "hands_on", 4.2),
])
def test_all_weighted_tiers(grading, field, name, expected):
    grading[field].update(tier(name))
    if field == "metrics":
        grading[field].update(metric="CAC", action="Adjusted bids", measured_result="20%")
    assert score(grading)[peeko2.TOTAL_COLUMN] == expected


@pytest.mark.parametrize("end,recency,warning", [
    ("2026-11", 3, "No"), ("2025-11", 3, "No"), ("2025-10", 2, "No"),
    ("2023-11", 2, "No"), ("2023-10", 1, "No"), ("2021-11", 1, "No"),
    ("2021-10", 0, "No"), ("2025", 3, "No"), ("2023", 2, "No"),
    ("2021", 1, "No"), ("2026-12", 0, "Yes"), ("2026-13", 0, "Yes"),
    ("", 0, "Yes"), ("unknown", 0, "Yes"),
])
def test_recency_boundaries_and_date_errors(grading, end, recency, warning):
    grading["ownership"] = tier("ownership")
    row = score(grading, profile(start_date="2019", end_date=end, duration="999 years"))
    assert row[peeko2.TOTAL_COLUMN] == 4 + recency
    assert row["Date-Quality Warning"] == warning


def test_fixed_credit_and_unsupported_date_reference(grading):
    grading["conversion"].update(tier("app_mention", 1, None))
    grading["metrics"].update(tier("keyword_only", 1, None), metric="ROAS")
    grading["ownership"] = tier("management", 4, 999)
    grading["funnel"] = tier("funnel_analysis", 3, None)
    row = score(grading)
    assert row[peeko2.SCORE_COLUMNS[1]] == 2.4
    assert row[peeko2.SCORE_COLUMNS[2]] == 1
    assert row[peeko.UNVERIFIED_COLUMNS[2]] == "Yes"
    assert row[peeko2.SCORE_COLUMNS[4]] == .3
    assert row["Date-Quality Warning"] == "Yes"


def test_all_criteria_maximum_and_export(grading):
    for platform in ("google", "meta"):
        grading[platform] = {"level": "hands_on", "source": platform}
    grading["ownership"] = tier("ownership")
    grading["conversion"].update(tier("app_conversions"))
    grading["funnel"] = tier("measured_improvement")
    grading["metrics"].update(tier("quantified_improvement"), metric="CAC",
                              action="Adjusted bids", measured_result="20% lower")
    candidate = profile(is_current=True)
    row = apply_calculated_fields(grading, candidate, ROLE)
    assert row[peeko2.TOTAL_COLUMN] == 36
    assert row[peeko.CUTOFF_COLUMN] == "Yes" and row[peeko.REVIEW_COLUMN] == "No"
    assert (row["Current Company"], row["Current Title"]) == ("Example Co", "Marketer")
    rows = prepare_output_rows([row, {**row, "Candidate": "Another"}], ROLE)
    assert [r["Rank Number"] for r in rows] == [1, 1]
    assert list(rows[0]) == peeko2.OUTPUT_COLUMNS
    assert b"36.00" in _rows_to_csv_bytes(rows, ROLE.output_columns)
    cell = load_workbook(BytesIO(_rows_to_xlsx_bytes(rows, ROLE.output_columns))).active["K2"]
    assert cell.value == 36 and cell.number_format == "0.00"


def test_registration_default_upload_and_provider_schema(grading):
    assert role_options()["Peeko2"] == "peeko2"
    bundled = Path(_default_rubric_path("peeko2"))
    raw = b'[{"name":"Example","work_experience":[{"role":"Marketer","start":"2023","tools":["Google Ads"]}]}]'
    [candidate], rubric = _load_inputs(BytesIO(raw), "", None, str(bundled), "peeko2")
    assert not rubric_input_issue(rubric, ROLE)
    assert rubric_input_issue(rubric, get_role_profile("peeko"))
    assert rubric_input_issue("Old rubric with Final Score (/43)", ROLE)
    exp = _candidate_payload(candidate, ROLE)["experiences"][0]
    assert exp["is_current"] and exp["experience_tools"] == ["Google Ads"]
    assert "duration" not in exp
    schema = _response_schema(ROLE)["properties"]["grading"]
    assert set(schema["required"]) == set(grading)
    assert "periods" not in schema["properties"]


@pytest.mark.parametrize("case", ["platform_source", "metric_name", "unquantified", "keyword_date", "wrong_destination", "duration"])
def test_invalid_provider_contract(grading, case):
    if case == "platform_source":
        grading["google"]["level"] = "mention"
    elif case == "metric_name":
        grading["metrics"].update(tier("hands_on"))
    elif case == "unquantified":
        grading["metrics"].update(tier("quantified_result"), metric="ROAS", measured_result="higher")
    elif case == "keyword_date":
        grading["metrics"].update(tier("keyword_only", 1, 0), metric="ROAS")
    elif case == "wrong_destination":
        grading["conversion"]["destination_unverified"] = True
    else:
        grading["ownership"] = tier("ownership")
        grading["ownership"]["components"]["duration"] = 2
    with pytest.raises(ValueError, match="Peeko2"):
        score(grading)


@pytest.mark.parametrize("units,expected", [(17009, "No"), (17010, "Yes")])
def test_cutoff_uses_exact_score_even_when_display_matches(grading, units, expected):
    grading.update(google={"level": "hands_on", "source": "Google Ads"},
                   meta={"level": "hands_on", "source": "Meta Ads"})
    if units == 17009:
        grading["ownership"] = tier("creation", 3, None)
        grading["conversion"].update(tier("website_conversions", 3, None))
        grading["funnel"] = tier("change_implemented", 4, None)
        grading["metrics"].update(tier("quantified_result"), metric="ROAS", measured_result="2.5x")
    else:
        grading["ownership"] = tier("ownership", 3, None)
        grading["conversion"].update(tier("website_conversions"))
        grading["funnel"] = tier("measured_improvement", 4, 1)
        grading["metrics"].update(tier("hands_on", 3, None), metric="ROAS")
    end_date = "2024-11" if units == 17009 else "2023-10"
    candidate = profile(start_date="2022-01", end_date=end_date)
    candidate["experiences"].append({
        "index": 1, "description": "Improved signup conversion.", "is_current": True,
    })
    row = score(grading, candidate)
    assert row[peeko2.TOTAL_COLUMN] == units / 700
    assert f"{row[peeko2.TOTAL_COLUMN]:.2f}" == "24.30"
    assert row[peeko.CUTOFF_COLUMN] == expected


@pytest.mark.parametrize("provider", ["openai", "deepseek"])
def test_provider_batch_to_export(grading, monkeypatch, provider):
    import json
    from types import SimpleNamespace

    from app import _evaluate_candidate_batch_for_run

    grading["google"] = {"level": "mention", "source": "Skills: Google Ads"}
    content = json.dumps({"evaluations": [{"candidate_number": 1, "grading": grading}]})

    def create_response(**kwargs):
        if provider == "deepseek":
            assert kwargs["text"]["format"]["schema"]["type"] == "object"
            return SimpleNamespace(output_text=content)
        assert kwargs["response_format"]["json_schema"]["strict"]
        choice = SimpleNamespace(message=SimpleNamespace(content=content), finish_reason="stop")
        return SimpleNamespace(choices=[choice])

    endpoint = SimpleNamespace(create=create_response)
    client = SimpleNamespace(chat=SimpleNamespace(completions=endpoint), responses=endpoint)
    monkeypatch.setattr("candidate_evaluator.openai_scoring.OpenAI", lambda **kwargs: client)
    candidate = {**profile(is_current=True), "linkedin_profile_id": "example", "source_row": {}}
    rubric = Path(_default_rubric_path(ROLE.key)).read_text(encoding="utf-8-sig")
    outcome = _evaluate_candidate_batch_for_run(
        "key", "model", rubric, [candidate], ROLE, provider_key=provider,
    )
    [result] = outcome["results"]
    assert result["state"] == "completed"
    [row] = prepare_output_rows([result["row"]], ROLE)
    assert row[peeko2.TOTAL_COLUMN] == 4
    assert row[peeko.REVIEW_COLUMN] == "Yes"
