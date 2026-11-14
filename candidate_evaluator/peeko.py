"""Peeko's structured evidence contract and deterministic scoring."""
import re
from decimal import Decimal, localcontext

from .dates import _calculate_dates, _parse_date

SCORE_COLUMNS = (
    "Acquisition Campaign Management Score (/10)",
    "Campaign Ownership, Creation and Optimisation Score (/10)",
    "App and Website Conversion Outcomes Score (/10)",
    "Scaling — Annual Budget Managed Score (/10)",
    "Funnel Optimisation & Conversion Improvement Score (/3)",
    "Campaign Metrics Improved Score (/10)",
)
TOTAL_COLUMN = "Final Score (/40)"
CUTOFF_COLUMN = "Cutoff Met (Yes/No)"
REVIEW_COLUMN = "Review (Yes/No)"
UNVERIFIED_COLUMNS = (
    "Acquisition Campaign Management Unverified",
    "Campaign Ownership, Creation and Optimisation Unverified",
    "App and Website Conversion Outcomes Unverified",
    "Annual Budget Unverified",
    "Funnel Optimisation Unverified",
    "Campaign Metrics Improved Unverified",
)
WARNING_COLUMNS = (*UNVERIFIED_COLUMNS, "Date-Quality Warning")
NARRATIVE_COLUMNS = ("Strongest Evidence", "Missing or Unclear Information", "Score Rationale")
OUTPUT_COLUMNS = [
    "Rank Number", "Candidate", "Profile URL", "Current Company", "Current Title",
    *SCORE_COLUMNS[:4], TOTAL_COLUMN, *SCORE_COLUMNS[4:], CUTOFF_COLUMN, REVIEW_COLUMN,
    *WARNING_COLUMNS, *NARRATIVE_COLUMNS,
]
# Use integer tenths until the score and cutoff are settled.
OWNERSHIP_TIERS = {"end_to_end": 10, "creation": 7, "optimisation": 3, "none": 0}
CONVERSION_TIERS = {
    "app_conversions": 10, "website_conversions": 7, "app_campaign": 5,
    "website_campaign": 3, "none": 0,
}
BUDGET_PERIODS = {"annual": 1, "monthly": 12, "quarterly": 4}


def _object(**properties):
    return {
        "type": "object", "properties": properties, "required": list(properties),
        "additionalProperties": False,
    }


def _one_of(values, kind="string"):
    return {"type": kind, "enum": list(values)}


def _nullable(schema):
    return {"anyOf": [schema, {"type": "null"}]}


def _array(items):
    return {"type": "array", "items": items}


def grading_schema():
    string = {"type": "string"}
    optional_string = _nullable(string)
    components = _object(
        evidence=_one_of(range(1, 5), "integer"),
        recency=_one_of(range(4), "integer"),
        duration=_one_of(range(4), "integer"),
        sources=_array(string),
    )
    return _object(
        google=_nullable(components),
        meta=_nullable(components),
        ownership=_object(tier=_one_of(OWNERSHIP_TIERS), components=_nullable(components)),
        conversion=_object(
            tier=_one_of(CONVERSION_TIERS), components=_nullable(components),
            destination_unverified={"type": "boolean"},
        ),
        budgets=_array(_object(amount_inr=string, period=_one_of(BUDGET_PERIODS), source=string)),
        funnel=_object(score=_one_of(range(4), "integer"), source=optional_string),
        metrics=_object(
            score=_one_of((0, 1, 3, 6, 10), "integer"), source=optional_string,
            metric=optional_string, numeric_value=optional_string, action=optional_string,
            improvement=optional_string, baseline=optional_string, second_metric=optional_string,
        ),
        periods=_array(_object(
            experience_index={"type": "integer", "minimum": 0},
            basis=_one_of(("role_span", "stated_period")),
            start=optional_string, end=optional_string, written_duration=optional_string,
        )),
        unrelated_work={"type": "boolean"},
        date_quality_warning={"type": "boolean"},
        **{column: string for column in NARRATIVE_COLUMNS},
    )


def _check_schema(value, schema, path="Peeko grading"):
    """Validate provider results, including responses repaired by DeepSeek."""
    if "anyOf" in schema:
        if value is None:
            return
        _check_schema(value, schema["anyOf"][0], path)
        return
    kind = schema["type"]
    expected_type = {"object": dict, "array": list, "string": str, "integer": int, "boolean": bool}[kind]
    if type(value) is not expected_type:
        raise ValueError(f"{path} must be {kind}.")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path} must be one of {schema['enum']}.")
    if "minimum" in schema and value < schema["minimum"]:
        raise ValueError(f"{path} must be at least {schema['minimum']}.")
    if kind == "object":
        properties = schema["properties"]
        if set(value) != properties.keys():
            raise ValueError(f"{path} has missing or unexpected fields.")
        for field, child in properties.items():
            _check_schema(value[field], child, f"{path}.{field}")
    elif kind == "array":
        for index, item in enumerate(value):
            _check_schema(item, schema["items"], f"{path}[{index}]")


def _components(entry):
    if not all(source.strip() for source in entry["sources"]) or not entry["sources"]:
        raise ValueError("Peeko requires a source for awarded component points.")
    if entry["evidence"] < 4 and (entry["recency"] or entry["duration"]):
        raise ValueError("Dated points require a qualifying experience description.")
    return [entry["evidence"], entry["recency"], entry["duration"]]


def _tier_score(entry, tiers):
    multiplier = tiers[entry["tier"]]
    components = entry["components"]
    if bool(multiplier) != (components is not None):
        raise ValueError("Peeko tier and component evidence must agree.")
    return sum(_components(components)) * multiplier if multiplier else 0


def _budget(budgets):
    supported = []
    for budget in budgets:
        amount_text = budget["amount_inr"]
        if not re.fullmatch(r"[0-9]+(?:[.][0-9]+)?", amount_text):
            raise ValueError("Peeko budget must be a non-negative decimal INR amount.")
        if not budget["source"].strip():
            raise ValueError("Peeko requires a source for each budget.")
        with localcontext() as context:
            context.prec = len(amount_text) + 2
            annual = Decimal(amount_text) * BUDGET_PERIODS[budget["period"]]
        supported.append((annual, budget))
    if not supported:
        return 0, None, None
    annual, source = max(supported, key=lambda item: item[0])
    points = next((points for minimum, points in (
        (30_000_000, 10), (10_000_000, 6), (5_000_000, 3),
    ) if annual >= minimum), int(annual > 0))
    return points, format(annual, "f"), source


def _date(value):
    return _parse_date(value or "")


def _review_interval(period, experiences, evaluation_date):
    experience = experiences.get(period["experience_index"])
    if experience is None or not experience.get("description", "").strip():
        raise ValueError("Peeko qualifying periods must reference an experience description.")
    # Review measures identifiable hands-on work, which can include work excluded
    # from the rubric's full-time-only Duration component.
    if period["basis"] == "role_span":
        if any(period[key] is not None for key in ("start", "end", "written_duration")):
            raise ValueError("Peeko role-span evidence must use the source role dates.")
        source = experience
    else:
        source = {
            "start_date": period["start"], "end_date": period["end"],
            "duration": period["written_duration"],
        }
    facts = _calculate_dates(source, evaluation_date)
    months = facts["duration_months"]
    if not months:
        return None, 0, facts["date_quality_warning"]
    raw_end = (source.get("end_date") or "").strip()
    if facts["end_month"]:
        end = _date(facts["end_month"]).month_index
    else:
        if raw_end.casefold() in {"present", "current"} or (not raw_end and source.get("is_current") is True):
            end = evaluation_date.year * 12 + evaluation_date.month - 1
        else:
            parsed_end = _date(raw_end)
            if parsed_end:
                end = parsed_end.month_index if parsed_end.month is not None else parsed_end.year * 12 + 6
            else:
                parsed_start = _date((source.get("start_date") or "").strip())
                if not parsed_start or parsed_start.month_index is None:
                    return None, months, facts["date_quality_warning"]
                end = parsed_start.month_index + months
    if end > evaluation_date.year * 12 + evaluation_date.month - 1 and not (
        raw_end.isdecimal() and len(raw_end) == 4
    ):
        return None, 0, True
    return (end - months, end), 0, facts["date_quality_warning"]


def _merged_months(intervals):
    total = 0
    previous_end = 0
    for start, end in sorted(intervals):
        total += max(0, end - max(start, previous_end))
        previous_end = max(previous_end, end)
    return total


def _skills_only_acquisition(candidate):
    skills = list(candidate.get("skills") or [])
    for experience in candidate.get("experiences") or []:
        skills.extend(experience.get("experience_skills") or [])
    names = {" ".join(skill.casefold().split()) for skill in skills}
    google = any(re.fullmatch(
        r"google (?:ads(?: app campaigns?)?|adwords|advertising|app campaigns?|uac)"
        r"|adwords|universal app campaigns?|uac", name
    ) for name in names)
    meta = any(re.fullmatch(
        r"(?:meta|facebook|fb|instagram) (?:ads(?: manager)?|advertising)", name
    ) for name in names)
    return (0, 3, 10)[int(google) + int(meta)]


def calculate_grading(grading, candidate, evaluation_date):
    _check_schema(grading, grading_schema())
    platform_points = [_components(grading[key]) for key in ("google", "meta") if grading[key] is not None]
    if len(platform_points) == 2:
        acquisition = sum(map(min, zip(*platform_points))) * 10
    elif platform_points:
        acquisition = sum(platform_points[0]) * 3
    else:
        acquisition = _skills_only_acquisition(candidate)

    ownership = _tier_score(grading["ownership"], OWNERSHIP_TIERS)
    conversion = _tier_score(grading["conversion"], CONVERSION_TIERS)
    if grading["conversion"]["destination_unverified"] and grading["conversion"]["tier"] != "website_campaign":
        raise ValueError("Peeko unspecified destination must use the website campaign-work tier.")
    budget_points, annual_budget, budget_source = _budget(grading["budgets"])
    funnel, metrics = grading["funnel"], grading["metrics"]
    if funnel["score"] and not (funnel["source"] or "").strip():
        raise ValueError("Peeko funnel points require a source.")
    if metrics["score"] and not all((metrics[key] or "").strip() for key in ("source", "metric")):
        raise ValueError("Peeko metric points require a named metric and source.")
    if metrics["score"] >= 6 and not all((metrics[key] or "").strip() for key in ("action", "improvement")):
        raise ValueError("Peeko quantified improvement points require action and improvement.")
    if metrics["score"] == 10 and not any((metrics[key] or "").strip() for key in ("baseline", "second_metric")):
        raise ValueError("Peeko top metric points require a baseline or a second metric.")

    from .extractor import merge_duplicate_experiences

    experiences = merge_duplicate_experiences(candidate.get("experiences") or [], preserve_employment_details=True)
    indexed = {experience.get("index", index): experience for index, experience in enumerate(experiences)}
    date_warning = grading["date_quality_warning"] or any(
        _calculate_dates(experience, evaluation_date)["date_quality_warning"] for experience in experiences
    )
    intervals = []
    longest_unplaced_duration = 0
    for period in grading["periods"]:
        interval, unplaced_duration, warning = _review_interval(period, indexed, evaluation_date)
        longest_unplaced_duration = max(longest_unplaced_duration, unplaced_duration)
        date_warning |= warning
        if interval is not None:
            intervals.append(interval)
    # An undated duration could fully overlap every other period. Retain
    # only the lower bound we can defend without adding those periods.
    hands_on_months = max(_merged_months(intervals), longest_unplaced_duration)
    review = (
        len(platform_points) == 1 or hands_on_months < 24
        or (grading["unrelated_work"] and not all((acquisition, ownership, conversion)))
    )
    total_tenths = acquisition + ownership + conversion + budget_points * 10
    unverified = (
        not platform_points, not ownership, not conversion, annual_budget is None,
        funnel["score"] == 0, metrics["score"] == 0,
    )
    missing = grading["Missing or Unclear Information"].strip()
    if not platform_points and acquisition:
        missing = f"LC-1 skills-only credit. Hands-on Google and Meta work unverified. {missing}".strip()
    if len(platform_points) == 1:
        platform = "Google" if grading["google"] is None else "Meta"
        missing = f"{platform} hands-on work unverified. {missing}".strip()
    if grading["conversion"]["destination_unverified"]:
        missing = f"Campaign destination unverified. {missing}".strip()

    current = next((experience for experience in experiences if experience.get("is_current") is True), {})
    return {
        "Rank Number": "",
        "Candidate": candidate.get("candidate_name", ""),
        "Profile URL": candidate.get("linkedin_url", ""),
        "Current Company": current.get("company_name", ""),
        "Current Title": current.get("position_or_title", ""),
        **dict(zip(SCORE_COLUMNS, (
            acquisition / 10, ownership / 10, conversion / 10, float(budget_points),
            float(funnel["score"]), float(metrics["score"]),
        ))),
        TOTAL_COLUMN: total_tenths / 10,
        CUTOFF_COLUMN: _yes_no(total_tenths >= 270),
        REVIEW_COLUMN: _yes_no(review),
        **dict(zip(UNVERIFIED_COLUMNS, map(_yes_no, unverified))),
        "Date-Quality Warning": _yes_no(date_warning),
        **{column: grading[column] for column in NARRATIVE_COLUMNS},
        "Missing or Unclear Information": missing,
        "Peeko Audit": {
            "grading": grading, "annual_budget_inr": annual_budget,
            "budget_source": budget_source, "hands_on_months": hands_on_months,
            "evaluation_date": evaluation_date.isoformat(),
        },
    }


def _yes_no(condition):
    return "Yes" if condition else "No"


def write_excel(frame, destination):
    """Preserve numeric cells and display Peeko scores to one decimal."""
    from pandas import ExcelWriter

    with ExcelWriter(destination, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False)
        worksheet = writer.sheets["Sheet1"]
        for index, name in enumerate(frame.columns, start=1):
            if name in (*SCORE_COLUMNS, TOTAL_COLUMN):
                for row in range(2, worksheet.max_row + 1):
                    worksheet.cell(row=row, column=index).number_format = "0.0"
