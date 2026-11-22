"""Fixed scoring and evidence audit for SafeGold performance marketing."""

import re
from collections import OrderedDict
from datetime import date

from .dates import _parse_date


ROLE_KEY = "safegold_performance_marketer"
CRITERIA = {
    "C1": ("Google Ads operations", "Google Ads Score (/6)", (0, 1, 2, 4, 6)),
    "C2": ("Meta Ads operations", "Meta Ads Score (/6)", (0, 1, 2, 4, 6)),
    "C3": ("App acquisition", "App Acquisition Score (/8)", (0, 1, 2, 5, 8)),
    "C4": ("Experimentation", "Experimentation Score (/9)", (0, 1, 3, 6, 9)),
    "C5": ("Optimisation and scaling", "Optimisation and Scaling Score (/6)", (0, 1, 2, 4, 6)),
    "C6": ("Measurement and analysis", "Measurement and Analysis Score (/5)", (0, 1, 3, 5)),
}
SCORES = OrderedDict((column, tiers[-1]) for _, column, tiers in CRITERIA.values())
ALLOWED_SCORES = {column: set(tiers) for _, column, tiers in CRITERIA.values()}
TOTAL = "Final Score (/40)"
NOTES = "Missing or Unclear Information"
AUDIT = "Criterion Audit"
STATES = ("supported", "mention only", "no qualifying evidence", "explicit absence")
OUTPUT_COLUMNS = [
    "Candidate", "Profile URL", "Current Company", "Current Title",
    *SCORES, TOTAL, "Strongest Evidence", NOTES, "Score Rationale",
    "Fintech Experience", "Startup Experience", "Relevant Paid-Marketing Duration and Recency",
    "Location and Mumbai Availability",
]


def rubric_issue(text: str) -> str:
    rows = re.findall(
        r"^\s*\|\s*(C[1-6])\s*\|\s*([^|]+?)\s*\|\s*([0-9, ]+)\s*\|\s*(\d+)\s*\|",
        text, re.MULTILINE,
    )
    expected = [
        (criterion, name, tiers, tiers[-1]) for criterion, (name, _, tiers) in CRITERIA.items()
    ]
    actual = [
        (criterion, name, tuple(int(score) for score in scores.split(",")), int(maximum))
        for criterion, name, scores, maximum in rows
    ]
    if actual != expected or not re.search(r"\*\*Total\*\*\s*\|\s*\|\s*\*\*40\*\*", text):
        return "Use the SafeGold performance marketing rubric with its six configured score scales and 40-point total."
    if re.search(
        r"Use null:|Null is allowed for every criterion|If any criterion is null|"
        r"Award 0 only if a statement explicitly rules out", text, re.IGNORECASE,
    ):
        return "Upload the revised SafeGold rubric that assigns 0 when there is no qualifying evidence."
    return ""


def audit_schema() -> dict:
    claim = {
        "type": "object", "additionalProperties": False,
        "required": ["source_path", "role_or_project", "supporting_text"],
        "properties": {
            field: {"type": "string"} for field in ("source_path", "role_or_project", "supporting_text")
        },
    }
    entry = {
        "type": "object", "additionalProperties": False,
        "required": ["evidence_state", "claims", "anchor_matched", "reason"],
        "properties": {
            "evidence_state": {"type": "string", "enum": list(STATES)},
            "claims": {"type": "array", "items": claim},
            "anchor_matched": {"type": "string"},
            "reason": {"type": "string"},
        },
    }
    return {
        "type": "object", "additionalProperties": False, "required": list(CRITERIA),
        "properties": {criterion: entry for criterion in CRITERIA},
    }


def calculate_total(row: dict) -> int:
    points = 0
    for _, column, tiers in CRITERIA.values():
        if column not in row:
            raise ValueError(f"Missing required score: {column}.")
        score = row[column]
        if type(score) is not int or score not in tiers:
            raise ValueError(f"{column} must be an integer from {tiers}.")
        points += score
    return points


def report_row(row: dict) -> dict:
    """Display legacy unscored criteria as zero while preserving the saved result."""
    report = dict(row)
    legacy_gaps = []
    for name, column, _ in CRITERIA.values():
        if report.get(column) in (None, ""):
            report[column] = 0
            legacy_gaps.append(name)
    if legacy_gaps:
        note = f"Previously unscored criteria are shown as 0: {', '.join(legacy_gaps)}."
        report[NOTES] = " ".join(filter(None, (report.get(NOTES), note)))
    report[TOTAL] = calculate_total(report)
    return {column: report.get(column, "") for column in OUTPUT_COLUMNS}


def write_excel(frame, destination) -> None:
    from openpyxl.styles import Alignment
    from openpyxl.utils import get_column_letter
    from pandas import ExcelWriter

    with ExcelWriter(destination, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name="Candidates", index=False)
        sheet = writer.sheets["Candidates"]
        sheet.freeze_panes = "B2"
        sheet.auto_filter.ref = sheet.dimensions
        sheet.row_dimensions[1].height = 32
        for index, column in enumerate(frame.columns, start=1):
            is_score = column in SCORES or column == TOTAL
            width = 16 if is_score else 24 if index <= 4 else 44
            sheet.column_dimensions[get_column_letter(index)].width = width
            for (cell,) in sheet.iter_rows(min_col=index, max_col=index):
                cell.alignment = Alignment(
                    vertical="top", horizontal="center" if is_score else "left", wrap_text=True,
                )
                if cell.data_type == "f":
                    cell.data_type = "s"


def assessed_audit(row: dict, sources: dict) -> dict:
    audit = row.get(AUDIT)
    if not isinstance(audit, dict) or set(audit) != set(CRITERIA):
        raise ValueError("Criterion Audit must contain C1 through C6 exactly once.")
    assessed = {}
    for criterion, (_, column, _) in CRITERIA.items():
        score = row[column]
        entry = audit[criterion]
        if not isinstance(entry, dict):
            raise ValueError(f"{criterion} audit must be an object.")
        expected_states = {
            0: ("no qualifying evidence", "explicit absence"), 1: ("mention only",),
        }.get(score, ("supported",))
        if criterion == "C6" and score == 1:
            expected_states = ("mention only", "supported")
        if entry.get("evidence_state") not in expected_states:
            raise ValueError(f"{criterion} evidence state does not match the score.")
        if not isinstance(entry.get("reason"), str) or not entry["reason"].strip():
            raise ValueError(f"{criterion} audit requires a reason.")
        if score > 0 and (
            not isinstance(entry.get("anchor_matched"), str) or not entry["anchor_matched"].strip()
        ):
            raise ValueError(f"{criterion} audit requires a matched score anchor.")
        claims = entry.get("claims")
        if not isinstance(claims, list) or (
            (score > 0 or entry["evidence_state"] == "explicit absence") and not claims
        ):
            raise ValueError(f"{criterion} audit requires source claims for an assessed score.")
        for claim in claims:
            if not isinstance(claim, dict):
                raise ValueError(f"{criterion} source claim must be an object.")
            path, quote = claim.get("source_path"), claim.get("supporting_text")
            if (
                not isinstance(path, str) or not isinstance(quote, str) or not quote.strip()
                or not isinstance(claim.get("role_or_project"), str)
                or not claim["role_or_project"].strip()
                or " ".join(quote.split()) not in " ".join(sources.get(path, "").split())
            ):
                raise ValueError(f"{criterion} audit quote must match the supplied source field.")
        assessed[criterion] = {**entry, "score": score}
    return assessed


def current_employment(experiences: list[dict], today: date) -> tuple[str, str]:
    """Prefer current work, then latest-ended work, retaining unresolved ties."""
    current, ended = [], []
    for role in experiences:
        is_current = role.get("is_current") is True
        end = str(role.get("end_date") or "")
        if is_current and end.casefold() not in {"", "present", "current"}:
            continue
        try:
            role_date = _parse_date(str(role.get("start_date") or "") if is_current else end)
        except ValueError:
            role_date = None
        if role_date and role_date.is_future(today):
            continue
        if role_date:
            year = role_date.year
            lower = (year, role_date.month or 1, role_date.day or 1)
            upper = (year, role_date.month or 12, role_date.day or 31)
        elif is_current:
            lower, upper = (0, 0, 0), (today.year, today.month, today.day)
        else:
            continue
        (current if is_current else ended).append((lower, upper, role))
    ranges = current or ended
    latest_lower = max((lower for lower, _, _ in ranges), default=(0, 0, 0))
    selected = [role for _, upper, role in ranges if upper >= latest_lower]
    return tuple(
        " | ".join(dict.fromkeys(str(role[field]) for role in selected if role.get(field)))
        for field in ("company_name", "position_or_title")
    )
