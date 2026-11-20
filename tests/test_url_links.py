import io
from unittest.mock import patch

import pytest

import app
from candidate_evaluator.extractor import normalize_candidate, candidate_input_issue
from candidate_evaluator.openai_scoring import evaluate_candidates
from candidate_evaluator.roles import get_role_profile, prepare_output_rows
from candidate_evaluator.url_links import extract_links, evaluate, OUTPUT_COLUMNS
from candidate_evaluator.validation import apply_calculated_fields, coerce_fixed_row, validate_output_row


@pytest.mark.parametrize("field", ["about", "headline", "description", "summary", "bio"])
def test_text_links_ignore_label(field):
    links = extract_links({field: "Find me here: https://example.com/work"})
    assert links[0]["url"] == "https://example.com/work"
    assert links[0]["sources"] == [field]


@pytest.mark.parametrize("field", ["websites", "contactInfo", "contact_info", "featured", "projects", "experience", "currentPosition", "unexpected"])
def test_nested_fields(field):
    links = extract_links({field: [{"link": "https://example.com/a"}]})
    assert len(links) == 1
    assert links[0]["sources"] == [field + "[0].link"]


@pytest.mark.parametrize("field", ["moreProfiles", "companyLogo", "profilePicture", "certifications", "skills", "location", "education"])
def test_every_field_is_scanned(field):
    links = extract_links({field: {"url": "https://example.com/a"}})
    assert links[0]["url"] == "https://example.com/a"
    assert links[0]["sources"] == [field + ".url"]


def test_multiple_duplicate_urls_preserve_paths_and_queries():
    links = extract_links({
        "about": "https://GitHub.com/A/Repo?x=One and https://github.com/A/Repo?x=One.",
        "projects": [{"link": "https://github.com/A/Repo?x=One"},
                     {"link": "https://github.com/A/Other"}],
    })
    assert len(links) == 2
    assert links[0]["category"] == "GitHub URLs"
    assert links[0]["sources"] == ["about", "projects[0].link"]
    assert links[0]["url"].endswith("?x=One")


def test_bare_domain_and_parentheses():
    links = extract_links({"about": "(ravivarma.pages.dev) www.example.com/work"})
    assert [x["url"] for x in links] == ["ravivarma.pages.dev", "www.example.com/work"]


def test_linkedin_and_images_retained_in_other_urls():
    links = extract_links({"about": "me@example.com https://linkedin.com/in/me https://media.licdn.com/a"})
    assert [entry["url"] for entry in links] == ["https://linkedin.com/in/me", "https://media.licdn.com/a"]
    assert all(entry["category"] == "Other URLs" for entry in links)


def test_nulls_and_numbers():
    assert extract_links({"about": None, "projects": [], "count": 42, "flag": True}) == []


@pytest.mark.parametrize("has_links", [True, False])
def test_normal_entry_point_no_api_and_exports(has_links):
    profile = {"firstName": "Sample",
               "about": "https://github.com/sample/repo" if has_links else ""}
    candidate = normalize_candidate(profile, 0)
    role = get_role_profile("portfolio_links")
    assert candidate_input_issue(candidate, role.key, evidence_sources=[], skip_if_no_evidence=False) == ""
    with patch("candidate_evaluator.openai_scoring.OpenAI", side_effect=AssertionError("API called")):
        results = evaluate_candidates(api_key="", model="", rubric_text="", candidates=[candidate], role_profile=role)
    grading, raw = results[0]
    assert results.usage == {}
    row = coerce_fixed_row(apply_calculated_fields(grading, candidate, role), role)
    assert validate_output_row(row, role) == []
    assert row["Link Found"] == int(has_links)
    rows = prepare_output_rows([row], role)
    csv_bytes = app._rows_to_csv_bytes(rows, OUTPUT_COLUMNS)
    assert b"Other URLs" in csv_bytes
    import openpyxl
    book = openpyxl.load_workbook(io.BytesIO(app._rows_to_xlsx_bytes(rows, OUTPUT_COLUMNS)))
    assert book.active.cell(2, 3).value == int(has_links)


def test_other_urls_preserved():
    candidate = normalize_candidate({"about": "Look here https://unusual.example.org/me"}, 0)
    row = evaluate(candidate)
    assert row["Other URLs"] == "https://unusual.example.org/me"


def test_malformed_url_does_not_fail_candidate():
    links = extract_links({"about": "https://example.com:bad/path https://github.com/me"})
    assert [entry["url"] for entry in links] == ["https://github.com/me"]


def test_application_batch_and_saved_run(tmp_path, monkeypatch):
    from candidate_evaluator.progress import init_run, commit_batch_results, result_rows, role_for_run
    monkeypatch.chdir(tmp_path)
    candidate = normalize_candidate({"publicIdentifier": "me", "about": "https://github.com/me"}, 0)
    role = get_role_profile("portfolio_links")
    init_run("urls", [candidate], "Local URL extraction", "", role.key)
    assert role_for_run("urls").key == role.key
    batch = app._evaluate_candidate_batch_for_run("", "", "", [candidate], role)
    assert batch["results"][0]["state"] == "completed"
    assert batch["usage"] == {}
    commit_batch_results("urls", [candidate], batch)
    assert result_rows("urls")[0]["GitHub URLs"] == "https://github.com/me"


def test_company_names_and_associations_are_retained():
    links = extract_links({"experience": [{"companyName": "Cerebrone.ai"}],
                           "projects": [{"associatedWith": "iNeuron.ai"}]})
    assert {entry["url"] for entry in links} == {"Cerebrone.ai", "iNeuron.ai"}


def test_uncommon_domains_are_not_missed():
    links = extract_links({"about": "me.engineering/work me.cloud me.photography"})
    assert [entry["url"] for entry in links] == ["me.engineering/work", "me.cloud", "me.photography"]


def test_other_urls_are_separate_lines_in_csv_and_excel():
    candidate = normalize_candidate({"firstName": "Test", "unknown": [
        "https://one.example.com/path", "https://two.example.com/path"
    ]}, 0)
    row = evaluate(candidate)
    expected = "https://one.example.com/path\nhttps://two.example.com/path"
    assert row["Other URLs"] == expected
    import csv
    parsed = list(csv.DictReader(io.StringIO(app._rows_to_csv_bytes([row], OUTPUT_COLUMNS).decode("utf-8"))))
    assert parsed[0]["Other URLs"] == expected
    import openpyxl
    book = openpyxl.load_workbook(io.BytesIO(app._rows_to_xlsx_bytes([row], OUTPUT_COLUMNS)))
    assert book.active.cell(2, 7).value == expected
    assert book.active.cell(2, 7).alignment.wrap_text is True
    assert book["All URLs"].cell(2, 4).value == expected.splitlines()[0]
    assert book["All URLs"].cell(3, 4).value == expected.splitlines()[1]


def test_different_schemes_and_paths_remain_separate():
    links = extract_links({"about": "http://example.com/a https://example.com/a https://example.com/a/"})
    assert len(links) == 3


def test_excel_long_summary_retains_all_links_in_detail_sheet():
    urls = ["https://example.com/" + str(index) + "/" + "x" * 200 for index in range(170)]
    candidate = normalize_candidate({"firstName": "Test", "links": urls}, 0)
    row = evaluate(candidate)
    import openpyxl
    book = openpyxl.load_workbook(io.BytesIO(app._rows_to_xlsx_bytes([row], OUTPUT_COLUMNS)))
    assert "See All URLs sheet" in book["Candidates"].cell(2, 7).value
    assert [r[3] for r in book["All URLs"].iter_rows(min_row=2, values_only=True)] == urls
