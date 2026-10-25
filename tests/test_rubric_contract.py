from pathlib import Path
from unittest.mock import Mock

import pytest

from candidate_evaluator.openai_scoring import evaluate_candidates
from candidate_evaluator.roles import get_role_profile
from candidate_evaluator.rubric_contract import rubric_input_issue


RUBRIC = (Path(__file__).parents[1] / "rubrics" / "sde3.md").read_text()


def test_bundled_linkedin_rubric_is_compatible():
    assert rubric_input_issue(RUBRIC, get_role_profile("sde3")) == ""


@pytest.mark.parametrize("rubric", [
    "# SDE3 Technical Assessment: Scoring Rubric\nEach candidate is scored out of 100 points. Python memoize25, FastAPI/Django35, SQL40.",
    "# Unrelated rubric\nMaximum score:62. Evidence Recency Duration.",
    RUBRIC.replace("62", "100"),
    RUBRIC.replace("**Maximum score:** 62 points.", "**Maximum score:** 100 points."),
    "",
])
def test_incompatible_sde3_rubrics_are_rejected_before_provider_call(monkeypatch, rubric):
    client = Mock()
    monkeypatch.setattr("candidate_evaluator.openai_scoring.OpenAI", client)
    with pytest.raises(ValueError, match="does not match SDE3 LinkedIn"):
        evaluate_candidates(api_key="unused", model="unused", rubric_text=rubric,
                            candidates=[{}], role_key="sde3")
    client.assert_not_called()


def test_other_roles_keep_existing_rubric_behavior():
    assert rubric_input_issue("User-supplied custom rubric", get_role_profile("backend")) == ""


def test_capability_maxima_and_prose_word_limit_are_not_overall_score_limits():
    rubric = RUBRIC + "\nMaximum 150 words. Category maximum20.\n"
    assert rubric_input_issue(rubric, get_role_profile("sde3")) == ""
