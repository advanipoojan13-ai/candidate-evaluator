from __future__ import annotations

import pytest

from candidate_evaluator.roles import get_role_profile
from candidate_evaluator.validation import apply_calculated_fields, coerce_fixed_row, validate_output_row


def _valid_sde3_row() -> dict:
    role = get_role_profile("sde3")
    row = {column: "" for column in role.output_columns + role.grading_columns}
    row.update({column: 0 for column in role.category_scores})
    row.update({column: 0 for column in role.component_score_maxima})
    row[role.total_column] = 0
    for column, values in (role.column_enums or {}).items():
        row[column] = values[0]
    return row


@pytest.mark.parametrize("value", [2.5, "2.5", "2.0000000000000001", True, False, float("nan"), float("inf"), float("-inf"), "NaN", "Infinity"])
def test_coercion_rejects_invalid_component_scores_before_they_can_be_truncated(value) -> None:
    role = get_role_profile("sde3")
    component = next(iter(role.component_score_maxima))
    row = _valid_sde3_row()
    row[component] = value

    with pytest.raises(ValueError, match="must be a whole number"):
        coerce_fixed_row(row, role)


@pytest.mark.parametrize("value", [0, 2, 2.0, "0", "2", "2.0"])
def test_coercion_preserves_whole_components_and_legacy_numeric_strings(value) -> None:
    role = get_role_profile("sde3")
    component = next(iter(role.component_score_maxima))
    row = _valid_sde3_row()
    row[component] = value

    fixed = coerce_fixed_row(row, role)

    assert type(fixed[component]) is int
    assert fixed[component] == int(float(value))


def test_numeric_category_scores_keep_valid_decimals() -> None:
    role = get_role_profile("sde3")
    category = next(iter(role.category_scores))
    row = _valid_sde3_row()
    row[category] = "1.5"
    row[role.total_column] = "1.5"

    fixed = coerce_fixed_row(row, role)

    assert fixed[category] == 1.5
    assert fixed[role.total_column] == 1.5
    assert validate_output_row(fixed, role) == []


@pytest.mark.parametrize("value", [2.5, True, False, float("nan"), float("inf"), float("-inf")])
def test_integer_category_coercion_does_not_truncate_or_accept_boolean_scores(value) -> None:
    role = get_role_profile("design")
    row = {column: "" for column in role.output_columns + role.grading_columns}
    row[next(iter(role.category_scores))] = value

    with pytest.raises(ValueError, match="must be a whole number"):
        coerce_fixed_row(row, role)


@pytest.mark.parametrize("field_kind", ["component", "category", "total"])
@pytest.mark.parametrize("value", [True, False, float("nan"), float("inf"), float("-inf"), "NaN", "Infinity", 10**1000])
def test_validation_reports_invalid_numbers_without_overflowing(field_kind, value) -> None:
    role = get_role_profile("sde3")
    columns = {
        "component": next(iter(role.component_score_maxima)),
        "category": next(iter(role.category_scores)),
        "total": role.total_column,
    }
    row = _valid_sde3_row()
    column = columns[field_kind]
    row[column] = value

    errors = validate_output_row(row, role)

    assert any(error.startswith(f"{column} must be a ") for error in errors)


@pytest.mark.parametrize("field_kind", ["category", "total"])
@pytest.mark.parametrize("value", [True, False, float("nan"), float("inf"), float("-inf"), "NaN", "Infinity"])
def test_numeric_category_and_total_coercion_reject_nonfinite_or_boolean_scores(field_kind, value) -> None:
    role = get_role_profile("sde3")
    column = next(iter(role.category_scores)) if field_kind == "category" else role.total_column
    row = _valid_sde3_row()
    row[column] = value

    with pytest.raises(ValueError, match="must be a number"):
        coerce_fixed_row(row, role)


@pytest.mark.parametrize("value", [True, False, float("nan"), float("inf"), float("-inf"), 10**1000])
def test_calculated_fields_do_not_derive_capability_or_total_from_invalid_components(value) -> None:
    role = get_role_profile("sde3")
    category, rule = next(iter(role.component_scoring.items()))
    row = {column: 0 for column in role.component_score_maxima}
    row[rule.columns[0]] = value

    calculated = apply_calculated_fields(row, {}, role)

    assert category not in calculated
    assert role.total_column not in calculated


@pytest.mark.parametrize("value", [True, False, float("nan"), float("inf"), float("-inf"), 10**1000])
def test_calculated_fields_do_not_derive_total_from_invalid_category_scores(value) -> None:
    role = get_role_profile("sde3")
    row = {column: 0 for column in role.category_scores}
    row[next(iter(role.category_scores))] = value

    assert role.total_column not in apply_calculated_fields(row, {}, role)


def test_calculated_fields_skip_overflowed_weighted_scores_and_totals() -> None:
    role = get_role_profile("sde3")
    category, rule = next(iter(role.component_scoring.items()))
    components = {column: 1e308 for column in rule.columns}
    categories = {column: 1e308 for column in role.category_scores}

    assert category not in apply_calculated_fields(components, {}, role)
    assert role.total_column not in apply_calculated_fields(categories, {}, role)


@pytest.mark.parametrize("value", [True, False, float("nan"), float("inf"), float("-inf"), 10**1000])
def test_duration_formatting_skips_invalid_numeric_months(value) -> None:
    role = get_role_profile("design")
    display_column = "Total Relevant Design Experience — Years and Months"
    months_column = "Total Relevant Design Experience — Months"

    assert display_column not in apply_calculated_fields({months_column: value}, {}, role)


def test_zero_components_still_calculate_valid_zero_scores() -> None:
    role = get_role_profile("sde3")
    row = _valid_sde3_row()

    calculated = coerce_fixed_row(apply_calculated_fields(row, {}, role), role)

    assert calculated[role.total_column] == 0
    assert all(calculated[column] == 0 for column in role.category_scores)
    assert validate_output_row(calculated, role) == []
