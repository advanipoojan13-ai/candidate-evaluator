from __future__ import annotations

import itertools
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from candidate_evaluator.providers import get_provider
from candidate_evaluator.roles import get_role_profile, prepare_output_rows
from candidate_evaluator.sde3_scoring import _fallback_explanation, evaluate_sde3_candidates
from candidate_evaluator.validation import (
    _word_count,
    apply_calculated_fields,
    coerce_fixed_row,
    limit_rationale,
    normalize_rationale_row,
    validate_output_row,
)


def _long_rationale() -> str:
    return " ".join(["FastAPI/Django"] * 150 + ["Extra."])


def _grading() -> dict:
    role = get_role_profile("sde3")
    return {
        **{column: 2 for column in role.component_score_maxima},
        **{column: "No" for column in role.column_enums},
        "Strongest Evidence": "Built and deployed an agent.",
        "Missing or Unclear Information": "Sustained use is unverified.",
    }


def _row() -> dict:
    candidate = {"candidate_name": "Example", "linkedin_url": "example", "experiences": []}
    return apply_calculated_fields(
        {
            "Candidate": "Example", "Profile URL": "example", "Rank Number": "",
            "Score Rationale": _long_rationale(), **_grading(),
        },
        candidate,
        "sde3",
    )


def test_exact_budget_is_retained_and_limit_matches_validation_word_count():
    text = " ".join(["FastAPI/Django"] * 150)

    assert limit_rationale(text) == text
    assert _word_count(text) == 150


def test_unicode_whitespace_has_one_consistent_word_definition():
    separators = ["\u00a0", "\u2003", "\u2028", "\u2029", "\t", "\n"]
    text = "".join(f"word{index}{separators[index % len(separators)]}" for index in range(151))

    result = limit_rationale(text)

    assert len(result.split()) == 150
    assert _word_count(result) == 150
    assert result.endswith("…")


def test_long_explanation_prefers_a_complete_sentence_within_budget():
    sentence = " ".join(["evidence"] * 70) + "."
    text = sentence + " " + " ".join(["details"] * 120) + "."

    assert limit_rationale(text) == sentence


def test_sentence_ending_quotes_are_kept():
    sentence = 'The profile states "deployed an agent."'
    text = sentence + " " + " ".join(["details"] * 160)

    assert limit_rationale(text) == sentence


def test_long_unpunctuated_explanation_still_has_firm_150_word_limit():
    result = limit_rationale(" ".join(["evidence"] * 600))

    assert _word_count(result) == 150
    assert result.endswith("…")


def test_row_normalization_preserves_scores_and_source_rows():
    row = _row()
    snapshot = deepcopy(row)

    normalized = normalize_rationale_row(row, "sde3")

    assert row == snapshot
    assert normalized is not row
    assert _word_count(normalized["Score Rationale"]) <= 150
    assert normalized["Final Score (/62)"] == 37.2
    assert {key: value for key, value in normalized.items() if key != "Score Rationale"} == {
        key: value for key, value in row.items() if key != "Score Rationale"
    }


def test_coercion_caps_before_validation_without_rejecting_valid_scores():
    normalized = coerce_fixed_row(_row(), "sde3")

    assert _word_count(normalized["Score Rationale"]) <= 150
    assert normalized["Final Score (/62)"] == 37.2
    assert validate_output_row(normalized, "sde3") == []


def test_direct_validation_rejects_an_unnormalized_over_budget_rationale():
    assert any("150 words" in error for error in validate_output_row(_row(), "sde3"))


def test_export_preparation_caps_existing_rows_without_changing_saved_data():
    row = _row()
    snapshot = deepcopy(row)

    output = prepare_output_rows([row], "sde3")

    assert _word_count(output[0]["Score Rationale"]) <= 150
    assert output[0]["Final Score (/62)"] == 37.2
    assert output[0]["Rank Number"] == 1
    assert row == snapshot


def test_other_roles_keep_their_existing_rationale_policy():
    row = {"Score Rationale": "word " * 200}

    assert normalize_rationale_row(row, "ai_engineer_trj") == row


@pytest.mark.parametrize("points", list(itertools.product(range(5), range(4), range(4))))
def test_fallback_covers_all_capabilities_and_total_within_150_words(points):
    role = get_role_profile("sde3")
    grading = _grading()
    for rule in role.component_scoring.values():
        grading.update(zip(rule.columns, points))
    grading[role.total_column] = 37.2
    grading["Missing or Unclear Information"] = "unverified " * 500

    text = _fallback_explanation(grading, role)

    assert _word_count(text) <= 150
    assert "37.2/62" in text
    for category in role.category_scores:
        assert category.rsplit(" Score (/", 1)[0] in text


def test_model_ignoring_limit_is_capped_locally_without_rescoring_or_extra_request():
    calls = []
    original_text = " ".join(["evidence"] * 500)

    def request(prompt, payload, _schema, stage):
        calls.append((prompt, payload, stage))
        grading = _grading() if stage == "sde3_component_scores" else {"Score Rationale": original_text}
        return SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content=json.dumps({"evaluations": [{"candidate_number": 1, "grading": grading}]})),
                finish_reason="stop",
            )],
            usage=None,
        )

    candidate = {"candidate_name": "Example", "linkedin_url": "example", "experiences": []}
    results = evaluate_sde3_candidates(
        candidates=[candidate], payloads=[{}], role=get_role_profile("sde3"),
        rubric_text="Historical rubric allowed 250 words.", provider=get_provider("openai"), request=request,
    )

    grading, raw = results[0]
    assert len(calls) == 2
    assert "150 total words per candidate" in calls[1][0]
    assert "not 150 words per capability" in calls[1][0]
    assert _word_count(grading["Score Rationale"]) <= 150
    assert grading["Final Score (/62)"] == 37.2
    assert raw["rationale_truncated"] is True
    assert raw["explanation_status"] == "calculated_summary"
    for category in get_role_profile("sde3").category_scores:
        assert category.rsplit(" Score (/", 1)[0] in grading["Score Rationale"]
    assert original_text in raw["provider_diagnostics"][1]["response_content"]
