"""Conservative, rubric-defined date facts for the SDE3 evaluation pipeline.

These facts describe a role's available dates. Whether a capability was used
throughout that role remains an evidence decision, rather than a date inference.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any


_CURRENT_MARKERS = {"present", "current"}
_MONTHS = {
    name: index
    for index, names in enumerate(
        (
            ("jan", "january"),
            ("feb", "february"),
            ("mar", "march"),
            ("apr", "april"),
            ("may",),
            ("jun", "june"),
            ("jul", "july"),
            ("aug", "august"),
            ("sep", "sept", "september"),
            ("oct", "october"),
            ("nov", "november"),
            ("dec", "december"),
        ),
        start=1,
    )
    for name in names
}


@dataclass(frozen=True)
class _ProfileDate:
    year: int
    month: int | None = None
    day: int | None = None

    @property
    def month_index(self) -> int | None:
        return self.year * 12 + self.month - 1 if self.month is not None else None

    @property
    def month_text(self) -> str | None:
        return f"{self.year:04d}-{self.month:02d}" if self.month is not None else None

    def is_future(self, evaluation_date: date) -> bool:
        if self.month is None:
            return self.year > evaluation_date.year
        if self.day is None:
            return (self.year, self.month) > (evaluation_date.year, evaluation_date.month)
        return date(self.year, self.month, self.day) > evaluation_date


def prepare_experience_dates(
    experiences: list[dict[str, Any]], evaluation_date: date
) -> list[dict[str, Any]]:
    """Return copies with date facts, leaving source fields untouched.

    Month intervals use elapsed months, without an inclusive ``+1``. Year-only
    dates never become invented month intervals. Their recency is an upper
    bound on age (January of the stated end year), which conservatively avoids
    awarding a higher recency band when the missing month could change it.

    ``is_current`` must be an explicit boolean supplied by the source; callers
    must not infer it solely from a missing end date. Present/Current end-date
    text also establishes current employment.
    """
    return [
        {**experience, "calculated_dates": _calculate_dates(experience, evaluation_date)}
        for experience in experiences
    ]


def _calculate_dates(experience: dict[str, Any], evaluation_date: date) -> dict[str, Any]:
    result: dict[str, Any] = {
        "duration_months": None,
        "months_since_end": None,
        "date_quality_warning": False,
        "basis": "insufficient_dates",
        "start_month": None,
        "end_month": None,
    }
    start_text = _text(experience.get("start_date"))
    end_text = _text(experience.get("end_date"))
    current_marker = end_text.casefold() in _CURRENT_MARKERS
    explicit_current = experience.get("is_current") is True

    try:
        start = _parse_date(start_text)
        end = (
            _ProfileDate(evaluation_date.year, evaluation_date.month, evaluation_date.day)
            if current_marker or (explicit_current and not end_text)
            else _parse_date(end_text)
        )
    except ValueError:
        result.update(date_quality_warning=True, basis="invalid_dates")
        return result

    if explicit_current and end_text and not current_marker:
        result.update(date_quality_warning=True, basis="contradictory_current_status")
        return result
    if any(value is not None and value.is_future(evaluation_date) for value in (start, end)):
        result.update(date_quality_warning=True, basis="future_dates")
        return result
    if start and end and _definitely_reversed(start, end):
        result.update(date_quality_warning=True, basis="contradictory_dates")
        return result

    if end:
        end_month = end.month if end.month is not None else 1
        result["months_since_end"] = (
            (evaluation_date.year - end.year) * 12 + evaluation_date.month - end_month
        )

    written_months = _parse_duration(experience.get("duration"))
    bounds = _duration_bounds(start, end, evaluation_date)
    written_conflict = (
        written_months is not None
        and bounds is not None
        and not bounds[0] - 1 <= written_months <= bounds[1] + 1
    )
    if written_conflict:
        result["date_quality_warning"] = True

    if start and end and start.month is not None and end.month is not None:
        result.update(
            duration_months=end.month_index - start.month_index,
            basis="month_dates; written_duration_conflict" if written_conflict else "month_dates",
            start_month=start.month_text,
            end_month=end.month_text,
        )
        return result

    if start and end and start.month is None and end.month is None:
        result.update(
            duration_months=(6 if start.year == end.year else 12 * (end.year - start.year - 1) + 8),
            basis=(
                "year_only_estimate; recency uses conservative year boundary"
                + ("; written_duration_conflict" if written_conflict else "")
            ),
        )
        return result

    if written_conflict:
        result["basis"] = "contradictory_written_duration"
    elif written_months is not None:
        # Tolerate an inclusive month count without allowing its extra month
        # to cross a rubric duration threshold beyond the available date span.
        supported_months = min(written_months, bounds[1]) if bounds is not None else written_months
        result.update(duration_months=supported_months, basis="written_duration")
    return result


def _duration_bounds(
    start: _ProfileDate | None, end: _ProfileDate | None, evaluation_date: date
) -> tuple[int, int] | None:
    """Bound elapsed months without turning uncertain dates into intervals.

    Even when an end date is unknown, elapsed time cannot exceed the time
    since the stated start through evaluation. That bound does not establish
    current employment or grant recency. A one-month tolerance is applied by
    the caller for common inclusive month counts in written durations.
    """
    if start is None:
        return None
    evaluation_month = evaluation_date.year * 12 + evaluation_date.month - 1
    earliest_start = start.month_index if start.month is not None else start.year * 12
    latest_start = start.month_index if start.month is not None else min(start.year * 12 + 11, evaluation_month)
    if end is None:
        return 0, max(0, evaluation_month - earliest_start)
    earliest_end = end.month_index if end.month is not None else end.year * 12
    latest_end = end.month_index if end.month is not None else min(end.year * 12 + 11, evaluation_month)
    return max(0, earliest_end - latest_start), max(0, latest_end - earliest_start)


def _definitely_reversed(start: _ProfileDate, end: _ProfileDate) -> bool:
    if start.year != end.year:
        return start.year > end.year
    if start.month is None or end.month is None:
        return False
    if start.month != end.month:
        return start.month > end.month
    return start.day is not None and end.day is not None and start.day > end.day


def _parse_date(value: str) -> _ProfileDate | None:
    if not value:
        return None
    year_only = re.fullmatch(r"\d{4}", value)
    if year_only:
        year = int(value)
        date(year, 1, 1)
        return _ProfileDate(year)

    iso = re.fullmatch(r"(\d{4})[-/](\d{1,2})(?:[-/](\d{1,2}))?", value)
    if iso:
        year, month = int(iso[1]), int(iso[2])
        day = int(iso[3]) if iso[3] else None
        date(year, month, day if day is not None else 1)
        return _ProfileDate(year, month, day)

    month_year = re.fullmatch(r"([a-zA-Z]+|\d{1,2})[.,/\s-]+(\d{4})", value)
    if month_year:
        month_text, year = month_year[1].casefold(), int(month_year[2])
        month = int(month_text) if month_text.isdigit() else _MONTHS.get(month_text)
        if month is not None:
            date(year, month, 1)
            return _ProfileDate(year, month)
    raise ValueError("Unrecognized or impossible profile date.")


def _parse_duration(value: Any) -> int | None:
    text = _text(value).casefold()
    match = re.fullmatch(
        r"(?:(\d+(?:\.\d+)?)\s*(?:years?|yrs?|y)\s*)?"
        r"(?:(\d+(?:\.\d+)?)\s*(?:months?|mos?|m)\s*)?",
        text,
    )
    if not match or not any(match.groups()):
        return None
    try:
        months = Decimal(match[1] or "0") * 12 + Decimal(match[2] or "0")
        return int(months) if months == months.to_integral_value() else None
    except InvalidOperation:
        return None


def _text(value: Any) -> str:
    return " ".join(str(value).split()) if value is not None else ""
