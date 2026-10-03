from __future__ import annotations

import re
from typing import Any, Optional

from .roles import RoleProfile, get_role_profile


def expected_outcome(total_score: float, role: RoleProfile) -> str:
    for low, high, label in role.outcome_bands:
        if low <= total_score <= high:
            return label
    raise ValueError(f"Total Score {total_score} is outside the 0-{role.total_max} range.")


def validate_output_row(row: dict[str, Any], role_or_key: str | RoleProfile = "design") -> list[str]:
    role = _resolve_role(role_or_key)
    errors: list[str] = []
    missing = [column for column in role.output_columns if column not in row]
    if missing:
        errors.append(f"Missing required columns: {', '.join(missing)}")

    category_scores = []
    for column, maximum in role.category_scores.items():
        score = _as_number(row.get(column), column, errors, integer_only=not role.numeric_scores)
        if score is None:
            continue
        allowed = role.allowed_scores.get(column)
        if allowed and score not in allowed:
            errors.append(f"{column} must be one of {sorted(allowed)}; got {score}.")
        elif score < 0 or score > maximum:
            errors.append(f"{column} must be between 0 and {maximum}; got {score}.")
        category_scores.append(score)

    total = _as_number(row.get(role.total_column), role.total_column, errors, integer_only=not role.numeric_scores)
    if total is not None:
        if total > role.total_max:
            errors.append(f"{role.total_column} must be no more than {role.total_max}; got {total}.")
        if len(category_scores) == len(role.category_scores) and not _numbers_equal(total, sum(category_scores)):
            errors.append(f"{role.total_column} must equal category score sum {sum(category_scores)}; got {total}.")
        if role.outcome_bands:
            try:
                expected = expected_outcome(total, role)
                actual = row.get(role.outcome_column)
                if actual != expected:
                    errors.append(f"{role.outcome_column} must be {expected!r} for {role.total_column} {total}; got {actual!r}.")
            except ValueError as exc:
                errors.append(str(exc))

    for column, allowed_values in (role.column_enums or {}).items():
        if row.get(column) not in allowed_values:
            errors.append(f"{column} must be one of {allowed_values}; got {row.get(column)!r}.")

    evidence_columns = role.strongest_evidence_columns or [f"Strongest Evidence {i}" for i in range(1, 4)]
    evidence_items = []
    for column in evidence_columns:
        value = str(row.get(column, "") or "").strip()
        if not value:
            continue
        if len(evidence_columns) == 1:
            evidence_items.extend(item.strip() for item in re.split(r"\s*(?:\||\n|•)\s*", value) if item.strip())
        else:
            evidence_items.append(value)
    if len(evidence_items) > 3:
        errors.append("Strongest Evidence has more than three items.")

    rationale = str(row.get("Score Rationale", "") or "")
    rationale_words = _word_count(rationale)
    if role.rationale_min_words and rationale_words < role.rationale_min_words:
        errors.append(f"Score Rationale must be at least {role.rationale_min_words} words; got {rationale_words}.")
    if role.rationale_max_words and rationale_words > role.rationale_max_words:
        errors.append(f"Score Rationale must be no longer than {role.rationale_max_words} words; got {rationale_words}.")

    return errors


def coerce_fixed_row(row: dict[str, Any], role_or_key: str | RoleProfile = "design") -> dict[str, Any]:
    role = _resolve_role(role_or_key)
    columns = list(dict.fromkeys(role.output_columns + role.grading_columns))
    fixed = {column: row.get(column, "") for column in columns}
    numeric_columns = list(role.category_scores) + [role.total_column] + (role.ranking_tiebreaker_columns or [])
    for column in numeric_columns:
        if fixed[column] != "":
            fixed[column] = float(fixed[column]) if role.numeric_scores else int(fixed[column])
    return fixed


def _resolve_role(role_or_key: str | RoleProfile) -> RoleProfile:
    return role_or_key if isinstance(role_or_key, RoleProfile) else get_role_profile(role_or_key)


def _as_int(value: Any, name: str, errors: list[str]) -> Optional[int]:
    try:
        if isinstance(value, bool):
            raise ValueError
        return int(value)
    except (TypeError, ValueError):
        errors.append(f"{name} must be a whole number; got {value!r}.")
        return None


def _as_number(value: Any, name: str, errors: list[str], integer_only: bool) -> Optional[float]:
    if integer_only:
        return _as_int(value, name, errors)
    try:
        if isinstance(value, bool):
            raise ValueError
        return float(value)
    except (TypeError, ValueError):
        errors.append(f"{name} must be a number; got {value!r}.")
        return None


def _numbers_equal(left: float, right: float) -> bool:
    return abs(float(left) - float(right)) < 1e-9


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text))
