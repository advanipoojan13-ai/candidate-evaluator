from __future__ import annotations

from copy import deepcopy
from datetime import date

import pytest

from candidate_evaluator.dates import prepare_experience_dates


EVALUATION_DATE = date(2026, 10, 24)


def _facts(**experience):
    return prepare_experience_dates([experience], EVALUATION_DATE)[0]["calculated_dates"]


@pytest.mark.parametrize("months", [0, 11, 12, 23, 24, 35, 36])
def test_elapsed_months_preserves_duration_band_boundaries(months):
    month_index = 2026 * 12 + 10 - 1 - months
    year, zero_based_month = divmod(month_index, 12)
    start = f"{year:04d}-{zero_based_month + 1:02d}"

    result = _facts(start_date=start, end_date="2026-10")

    assert result["duration_months"] == months
    assert result["months_since_end"] == 0
    assert result["start_month"] == start
    assert result["end_month"] == "2026-10"
    assert result["date_quality_warning"] is False


@pytest.mark.parametrize("months", [12, 13, 36, 37, 60, 61])
def test_recency_ages_preserve_band_boundaries(months):
    month_index = 2026 * 12 + 10 - 1 - months
    year, zero_based_month = divmod(month_index, 12)

    result = _facts(end_date=f"{year:04d}-{zero_based_month + 1:02d}")

    assert result["months_since_end"] == months
    assert result["duration_months"] is None


@pytest.mark.parametrize("end", ["Present", "current", " PRESENT "])
def test_current_role_ends_on_evaluation_date(end):
    result = _facts(start_date="Jan 2024", end_date=end)

    assert result["duration_months"] == 33
    assert result["months_since_end"] == 0
    assert result["end_month"] == "2026-10"


def test_only_explicit_current_status_resolves_missing_end():
    unknown = _facts(start_date="2024-01")
    current = _facts(start_date="2024-01", is_current=True)
    string_flag = _facts(start_date="2024-01", is_current="true")

    assert unknown["duration_months"] is None
    assert unknown["months_since_end"] is None
    assert current["duration_months"] == 33
    assert current["months_since_end"] == 0
    assert string_flag["duration_months"] is None


@pytest.mark.parametrize(
    ("start", "end", "months"),
    [("2024", "2024", 6), ("2024", "2025", 8), ("2022", "2025", 32)],
)
def test_year_only_estimates_follow_rubric_without_fabricated_months(start, end, months):
    result = _facts(start_date=start, end_date=end)

    assert result["duration_months"] == months
    assert result["start_month"] is None
    assert result["end_month"] is None
    assert result["date_quality_warning"] is False
    assert "year_only_estimate" in result["basis"]


def test_year_only_recency_is_conservative_at_ambiguous_boundary():
    result = _facts(end_date="2025")

    assert result["months_since_end"] == 21
    assert result["end_month"] is None


@pytest.mark.parametrize(
    ("duration", "months"),
    [("2 years 3 months", 27), ("1 yr 6 mos", 18), ("18 months", 18), ("1.5 years", 18), ("0 months", 0)],
)
def test_clear_written_duration_supports_incomplete_dates(duration, months):
    result = _facts(duration=duration)

    assert result["duration_months"] == months
    assert result["months_since_end"] is None
    assert result["start_month"] is None
    assert result["end_month"] is None
    assert result["basis"] == "written_duration"


def test_mixed_precision_uses_written_duration_and_preserves_known_end_recency():
    result = _facts(start_date="2024", end_date="2026-01", duration="2 years")

    assert result["duration_months"] == 24
    assert result["months_since_end"] == 9
    assert result["start_month"] is None
    assert result["end_month"] is None


def test_year_only_current_start_does_not_invent_start_month():
    result = _facts(start_date="2024", end_date="Present", duration="2 years 9 months")

    assert result["duration_months"] == 33
    assert result["start_month"] is None
    assert result["end_month"] is None
    assert result["months_since_end"] == 0


@pytest.mark.parametrize(
    ("start", "end", "written_duration"),
    [
        ("2025-12", "2025", "3 years"),
        ("2025", "2025-01", "3 years"),
        ("2026-08", "", "3 years"),
        ("2026", "Present", "3 years"),
    ],
)
def test_written_duration_cannot_exceed_partial_date_or_evaluation_bounds(start, end, written_duration):
    result = _facts(start_date=start, end_date=end, duration=written_duration)

    assert result["date_quality_warning"] is True
    assert result["duration_months"] is None
    assert result["basis"] == "contradictory_written_duration"
    assert result["start_month"] is None
    assert result["end_month"] is None
    if not end:
        assert result["months_since_end"] is None


@pytest.mark.parametrize("written_duration", ["3 years", "1 month"])
def test_exact_month_dates_retain_supported_duration_when_written_claim_conflicts(written_duration):
    result = _facts(start_date="2024-01", end_date="2025-01", duration=written_duration)

    assert result["duration_months"] == 12
    assert result["date_quality_warning"] is True
    assert result["basis"] == "month_dates; written_duration_conflict"
    assert result["start_month"] == "2024-01"
    assert result["end_month"] == "2025-01"


@pytest.mark.parametrize("written_duration", ["11 months", "12 months", "13 months"])
def test_month_count_rounding_or_inclusive_count_discrepancy_is_tolerated(written_duration):
    result = _facts(start_date="2024-01", end_date="2025-01", duration=written_duration)

    assert result["duration_months"] == 12
    assert result["date_quality_warning"] is False


def test_year_only_estimate_survives_an_exaggerated_written_claim_with_warning():
    result = _facts(start_date="2024", end_date="2025", duration="5 years")

    assert result["duration_months"] == 8
    assert result["date_quality_warning"] is True
    assert result["start_month"] is None
    assert result["end_month"] is None


def test_missing_end_written_fallback_remains_usable_within_evaluation_bound():
    result = _facts(start_date="2024-01", duration="2 years")

    assert result["duration_months"] == 24
    assert result["date_quality_warning"] is False
    assert result["months_since_end"] is None
    assert result["start_month"] is None
    assert result["end_month"] is None


@pytest.mark.parametrize("start", ["2025-11", "2024-11", "2023-11"])
def test_inclusive_written_month_cannot_cross_supported_duration_band(start):
    start_year = int(start[:4])
    written_months = (2026 - start_year) * 12
    result = _facts(start_date=start, duration=f"{written_months} months")

    assert result["duration_months"] == written_months - 1
    assert result["date_quality_warning"] is False
    assert result["months_since_end"] is None


@pytest.mark.parametrize("duration", ["about 2 years", "unknown", "a year", "-1 year", "1.1 years", ""])
def test_unclear_or_fractional_month_duration_is_not_guessed(duration):
    assert _facts(duration=duration)["duration_months"] is None


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("2026-13", "Present"),
        ("2024-02-30", "2025-01"),
        ("not a date", "2025-01"),
        ("2025-06", "2024-06"),
        ("2026-10-24", "2026-10-23"),
        ("2027", "2028"),
        ("2024-01", "2026-11"),
        ("2026-10-25", "Present"),
        ("2026", "2025"),
    ],
)
def test_bad_contradictory_and_future_dates_do_not_gain_written_duration(start, end):
    result = _facts(start_date=start, end_date=end, duration="5 years")

    assert result["date_quality_warning"] is True
    assert result["duration_months"] is None
    assert result["start_month"] is None
    assert result["end_month"] is None


def test_dated_end_contradicts_explicit_current_status():
    result = _facts(start_date="2024-01", end_date="2025-01", is_current=True)

    assert result["date_quality_warning"] is True
    assert result["duration_months"] is None


@pytest.mark.parametrize("start", ["Jan. 2024", "January 2024", "1 2024", "01/2024", "2024/01", "2024-01-12"])
def test_common_source_date_formats_are_normalized(start):
    result = _facts(start_date=start, end_date="October 2026")

    assert result["duration_months"] == 33
    assert result["start_month"] == "2024-01"


def test_preprocessing_does_not_mutate_source_experiences():
    experiences = [{"start_date": "2024-01", "end_date": "Present", "description": "Built an agent."}]
    snapshot = deepcopy(experiences)

    result = prepare_experience_dates(experiences, EVALUATION_DATE)

    assert experiences == snapshot
    assert result[0] is not experiences[0]
    assert result[0]["description"] == snapshot[0]["description"]
    assert "calculated_dates" not in experiences[0]
