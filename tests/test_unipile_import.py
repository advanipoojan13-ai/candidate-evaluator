from __future__ import annotations

import json
from copy import deepcopy

import pytest

from app import _candidates_from_json_text, _evaluate_candidate_for_run
from candidate_evaluator.extractor import (
    candidate_input_issue, load_profiles_from_text, normalize_candidate,
    normalize_candidates, preview_candidates,
)
from candidate_evaluator.openai_scoring import _candidate_payload
from candidate_evaluator.roles import get_role_profile


def profile():
    return {
        "object": "UserProfile", "provider": "LINKEDIN",
        "provider_id": "ACoABC", "public_identifier": "alex-sales",
        "first_name": "Alex", "last_name": "Sales", "headline": "Account Executive",
        "summary": "Grew US accounts and built a sales pipeline.",
        "location": "Chicago", "websites": ["https://example.com"],
        "is_open_profile": True, "follower_count": 1000,
        "skills": [{"name": "Selling"}],
        "education": [{"school": "Example University", "degree": "MBA", "start": "1/1/2018", "end": "1/1/2020"}],
        "work_experience_total_count": 2,
        "work_experience": [
            {"company": "Current Co", "position": "Account Executive", "description": "Prospected US leads.", "employment_type": "Full-time", "start": "2/1/2024", "end": None, "skills": [{"name": "Prospecting"}]},
            {"company": "Past Co", "position": "Account Manager", "description": "Grew key accounts.", "start": "1/1/2020", "end": "1/1/2023"},
        ],
    }


def issue(candidate):
    role = get_role_profile("zeiss_visiogen")
    return candidate_input_issue(candidate, role.key, role.evidence_sources, role.require_experience, role.skip_if_no_evidence)


@pytest.mark.parametrize("wrap", [lambda p: p, lambda p: [p], *[lambda p, key=k: {key: [p]} for k in ("items", "profiles", "data", "results")], lambda p: {"data": p}, lambda p: {"data": {"items": [p]}}])
def test_supported_roots_and_app_upload_path(wrap):
    candidates = _candidates_from_json_text(json.dumps(wrap(profile())))
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["candidate_name"] == "Alex Sales"
    assert candidate["linkedin_url"] == "https://www.linkedin.com/in/alex-sales/"
    assert candidate["about"] == "Grew US accounts and built a sales pipeline."
    assert candidate["education"] == ["Example University | MBA | 2018-01-01 - 2020-01-01"]
    assert candidate["experiences"][0]["experience_skills"] == ["Prospecting"]
    assert issue(candidate) == ""


def test_apify_and_unipile_produce_same_zeiss_scoring_payload():
    unipile = normalize_candidate(profile(), 0)
    apify = normalize_candidate({
        "publicIdentifier": "alex-sales", "linkedinUrl": "https://www.linkedin.com/in/alex-sales/",
        "firstName": "Alex", "lastName": "Sales", "headline": "Account Executive",
        "about": "Grew US accounts and built a sales pipeline.",
        "experience": [
            {"companyName": "Current Co", "position": "Account Executive", "description": "Prospected US leads.", "employmentType": "Full-time", "startDate": "2024-02-01", "endDate": "Present"},
            {"companyName": "Past Co", "position": "Account Manager", "description": "Grew key accounts.", "startDate": "2020-01-01", "endDate": "2023-01-01"},
        ],
    }, 0)
    role = get_role_profile("zeiss_visiogen")
    assert _candidate_payload(unipile, role) == _candidate_payload(apify, role)
    payload = _candidate_payload(unipile, role)
    assert set(payload) == {"LinkedIn Profile ID", "LinkedIn URL", "Candidate Name", "Headline", "About", "experiences"}
    assert "experience_skills" not in payload["experiences"][0]


@pytest.mark.parametrize("start,end,has_end,expected_start,expected_end,current", [
    ("2/1/2024", None, True, "2024-02-01", "Present", True),
    ({"year": 2021, "month": 5}, {"year": 2023}, True, "2021-05", "2023", False),
    ({"year": 2021}, "Current", True, "2021", "Current", True),
    (None, None, True, "", "", False),
    ("2021", None, False, "2021", "", False),
    ({"year": 0, "month": 0}, {}, True, "", "", False),
    ("2025", "2022", True, "2025", "2022", False),
    ({"text": "Jan 2020"}, "Present", True, "Jan 2020", "Present", True),
])
def test_dates_keep_precision_and_do_not_invent_durations(start, end, has_end, expected_start, expected_end, current):
    p = profile()
    exp = {"company": "Example", "position": "Sales", "start": start}
    if has_end:
        exp["end"] = end
    p["work_experience"] = [exp]
    actual = normalize_candidate(p, 0)["experiences"][0]
    assert (actual["start_date"], actual["end_date"], actual["is_current"]) == (expected_start, expected_end, current)
    assert actual["duration"] == ""


def test_complete_profile_is_not_mutated_and_order_and_preview_are_preserved():
    original = profile()
    before = deepcopy(original)
    candidate = normalize_candidate(original, 0)
    assert original == before
    assert [e["company_name"] for e in candidate["experiences"]] == ["Current Co", "Past Co"]
    assert "Prospected US leads." in candidate["source_row"]["Experience 0"]
    assert "experience/1" in preview_candidates([candidate])[0]
    assert "import_warnings" not in candidate
    assert not candidate["open_to_work_present"]


@pytest.mark.parametrize("identifier", [None, "ACoABC", "urn:li:member:123", "https://linkedin.com/in/x", "bad/name", "bad name"])
def test_internal_ids_never_become_public_urls(identifier):
    p = profile()
    p["public_identifier"] = identifier
    candidate = normalize_candidate(p, 0)
    assert candidate["linkedin_url"] == ""
    assert "URL is empty" in issue(candidate)
    assert candidate["linkedin_profile_id"] == (identifier or "ACoABC")


def test_explicit_url_provider_id_and_unicode_names():
    p = profile()
    p.pop("public_identifier")
    p.update(public_profile_url="https://www.linkedin.com/in/real-person/", first_name=" Zoë ", last_name=" 王 ")
    candidate = normalize_candidate(p, 0)
    assert candidate["candidate_name"] == "Zoë 王"
    assert candidate["linkedin_profile_id"] == "ACoABC"
    assert issue(candidate) == ""


@pytest.mark.parametrize("section", ["work_experience", "education"])
@pytest.mark.parametrize("value", [None, [], "invalid", {}, [None, 123, "bad"]])
def test_optional_and_malformed_sections_do_not_crash(section, value):
    p = profile()
    p[section] = value
    candidate = normalize_candidate(p, 0)
    assert candidate["experiences" if section == "work_experience" else "education"] == []


def test_partial_and_throttled_data_warn_without_leaking_into_scoring():
    p = profile()
    p["work_experience_total_count"] = 8
    p["throttled_sections"] = ["experience", "skills"]
    candidate = normalize_candidate(p, 0)
    assert len(candidate["import_warnings"]) == 2
    assert "2 of 8" in candidate["import_warnings"][0]
    assert "experience, skills" in candidate["import_warnings"][1]
    assert "import_warnings" not in _candidate_payload(candidate, get_role_profile("zeiss_visiogen"))


def test_missing_name_is_skipped_instead_of_using_provider_id_as_name():
    p = profile()
    p.pop("first_name")
    p.pop("last_name")
    assert "candidate name is empty" in issue(normalize_candidate(p, 0))


@pytest.mark.parametrize("evidence", [{"headline": "US sales"}, {"summary": "Prospected US customers"}, {"work_experience": [{"position": "Account Executive"}]}])
def test_sparse_but_usable_zeiss_profiles(evidence):
    p = {"public_identifier": "person", "first_name": "Person", **evidence}
    assert issue(normalize_candidate(p, 0)) == ""


@pytest.mark.parametrize("data", [{"items": [profile(), None]}, {"data": [123]}, {"object": "Error", "details": [{}]}, {"object": "Error", "items": [profile()]}, {"type": "errors/rate_limit", "details": [{}]}, 42, None])
def test_invalid_roots_are_rejected(data):
    with pytest.raises(ValueError):
        load_profiles_from_text(json.dumps(data))


def test_non_linkedin_profile_rejected():
    with pytest.raises(ValueError, match="Only LinkedIn"):
        normalize_candidate({**profile(), "provider": "WHATSAPP"}, 0)


def test_bom_and_mixed_provider_formats():
    p = {"publicIdentifier": "legacy", "fullName": "Legacy User", "linkedinUrl": "https://linkedin.com/in/legacy", "about": "Sales"}
    candidates = normalize_candidates(load_profiles_from_text("\ufeff" + json.dumps([p, profile()])))
    assert [c["candidate_name"] for c in candidates] == ["Legacy User", "Alex Sales"]
    assert [c["source_index"] for c in candidates] == [0, 1]


def test_zeiss_evaluation_receives_normalized_unipile_and_validates_output(monkeypatch):
    from tests.test_zeiss_visiogen import _model_grading

    captured = []
    def evaluate(**kwargs):
        captured.append(_candidate_payload(kwargs["candidate"], get_role_profile("zeiss_visiogen")))
        return _model_grading(), {"usage": {}}
    monkeypatch.setattr("candidate_evaluator.openai_scoring.evaluate_candidate", evaluate)
    # Match the application's existing single-candidate evaluation contract.
    result = _evaluate_candidate_for_run("key", "model", "rubric", normalize_candidate(profile(), 0), get_role_profile("zeiss_visiogen"))
    assert captured[0]["experiences"][0]["company_name"] == "Current Co"
    assert result["state"] == "completed", result
    assert result["row"]["Candidate"] == "Alex Sales"
    assert result["row"]["Final Score (/75)"] == 45


def test_empty_experience_is_not_usable_evidence():
    p = {"public_identifier": "person", "first_name": "Person", "work_experience": [{}]}
    candidate = normalize_candidate(p, 0)
    assert candidate["experiences"] == []
    assert "none of the selected evidence" in issue(candidate)
    assert "empty entry" in candidate["import_warnings"][0]


def test_role_alias_and_explicit_false_open_to_work():
    p = profile()
    p["work_experience"] = [{"company": "Example", "role": "Key Account Manager", "start": {"year": 2021}, "end": {"year": 2023}}]
    p["is_open_to_work"] = False
    candidate = normalize_candidate(p, 0)
    assert candidate["experiences"][0]["position_or_title"] == "Key Account Manager"
    assert candidate["open_to_work_present"] is True
    assert candidate["open_to_work"] is False


def test_partial_import_warnings_are_visible_in_app_preview(monkeypatch):
    import app
    from types import SimpleNamespace

    p = profile()
    p["throttled_sections"] = ["experience"]
    warnings = []
    monkeypatch.setattr(app, "st", SimpleNamespace(
        subheader=lambda *a: None, write=lambda *a: None,
        warning=warnings.append, button=lambda *a, **k: False, session_state={},
    ))
    app._show_preview([normalize_candidate(p, 0)], "rubric", get_role_profile("zeiss_visiogen"))
    assert len(warnings) == 1
    assert "Alex Sales: Unipile throttled sections: experience" in warnings[0]
