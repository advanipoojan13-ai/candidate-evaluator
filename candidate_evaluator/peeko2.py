"""Structured evidence and deterministic scoring for the simplified Peeko rubric."""
import re

from . import peeko
from .dates import _calculate_dates, _parse_date

MAXIMA = (14, 7, 5, 3, 7)
SCORE_COLUMNS = tuple(
    f"{column.rsplit(' (/', 1)[0]} (/{maximum})"
    for column, maximum in zip(peeko.SCORE_COLUMNS, MAXIMA)
)
TOTAL_COLUMN = "Final Score (/36)"
OUTPUT_COLUMNS = [*peeko.OUTPUT_COLUMNS[:5], *SCORE_COLUMNS, TOTAL_COLUMN, *peeko.OUTPUT_COLUMNS[11:]]
# Scores are represented in units of 1/700 point before cutoff and ranking.
CUTOFF_UNITS = 2430 * 7
OWNERSHIP = {"ownership": 100, "creation": 85, "optimisation": 70, "management": 60, "none": 0}
CONVERSION = {**peeko.CONVERSION_TIERS, "app_mention": 0}
FUNNEL = {"measured_improvement": 100, "change_implemented": 67, "funnel_analysis": 33, "none": 0}
METRICS = {**peeko.METRIC_TIERS, "quantified_result": 85}


def grading_schema():
    string = {"type": "string"}
    optional = peeko._nullable(string)
    platform = peeko._object(level=peeko._one_of(("none", "mention", "hands_on")), source=optional)
    components = peeko._object(
        evidence=peeko._one_of((1, 3, 4), "integer"),
        sources=peeko._array(string),
        recency_experience_index=peeko._nullable({"type": "integer", "minimum": 0}),
    )

    def criterion(tiers, **details):
        return peeko._object(tier=peeko._one_of(tiers),
                             components=peeko._nullable(components), **details)

    return peeko._object(
        google=platform, meta=platform,
        ownership=criterion(OWNERSHIP),
        conversion=criterion(CONVERSION, destination_unverified={"type": "boolean"}),
        funnel=criterion(FUNNEL),
        metrics=criterion(METRICS, metric=optional, action=optional, measured_result=optional),
        date_quality_warning={"type": "boolean"},
        **{column: string for column in peeko.NARRATIVE_COLUMNS},
    )


def _recency(experience, facts, evaluation_date):
    if facts["date_quality_warning"]:
        return 0
    months = facts["months_since_end"]
    if months is None:
        return 0
    end = _parse_date((experience.get("end_date") or "").strip()) if not experience.get("is_current") else None
    if end and end.month is None:
        months = (evaluation_date.year - end.year) * 12
    return next((points for limit, points in ((12, 3), (36, 2), (60, 1)) if months <= limit), 0)


def _score(entry, tiers, maximum, indexed, evaluation_date):
    tier, components = entry["tier"], entry["components"]
    if tier == "none":
        if components is not None:
            raise ValueError("Peeko2 requires null components for a non-qualifying tier.")
        return 0, 0, False
    if not components or not components["sources"] or not all(s.strip() for s in components["sources"]):
        raise ValueError("Peeko2 requires a source for every qualifying tier.")
    evidence = components["evidence"]
    index = components["recency_experience_index"]
    if tier in {"keyword_only", "app_mention"}:
        if index is not None or evidence != 1:
            raise ValueError("Peeko2 mention-only tiers require one Evidence point and no recency reference.")
        return (700 if tier == "app_mention" else 210), 0, False
    if evidence not in {3, 4}:
        raise ValueError("Peeko2 hands-on tiers require qualifying Experience, About or Headline evidence.")
    recency, warning = 0, False
    if index is not None:
        existing = indexed.get(index)
        if not existing or evidence != 4 or not (existing[0].get("description") or "").strip():
            warning = True
        else:
            experience, facts = existing
            recency = _recency(experience, facts, evaluation_date)
            warning = facts["date_quality_warning"] or facts["months_since_end"] is None
    return (evidence + recency) * maximum * tiers[tier], recency, warning


def calculate_grading(grading, candidate, evaluation_date):
    from .extractor import merge_duplicate_experiences

    peeko._check_schema(grading, grading_schema(), "Peeko2 grading")
    experiences = merge_duplicate_experiences(candidate.get("experiences") or [], preserve_employment_details=True)
    indexed = {
        experience.get("index", index): (experience, _calculate_dates({**experience, "duration": None}, evaluation_date))
        for index, experience in enumerate(experiences)
    }
    warning = grading["date_quality_warning"] or any(facts["date_quality_warning"] for _, facts in indexed.values())
    platform_scores = {}
    for platform in ("google", "meta"):
        entry = grading[platform]
        if entry["level"] != "none" and not (entry["source"] or "").strip():
            raise ValueError("Peeko2 platform credit requires a source.")
        platform_scores[platform] = {"none": 0, "mention": 4, "hands_on": 7}[entry["level"]]
    hands_on = sum(points == 7 for points in platform_scores.values())

    scores = [sum(platform_scores.values()) * 700]
    recencies = {}
    for field, tiers, maximum in zip(("ownership", "conversion", "funnel", "metrics"),
                                     (OWNERSHIP, CONVERSION, FUNNEL, METRICS), MAXIMA[1:]):
        units, recency, date_warning = _score(grading[field], tiers, maximum, indexed, evaluation_date)
        scores.append(units)
        recencies[field] = recency
        warning |= date_warning

    metrics = grading["metrics"]
    if scores[-1] and not (metrics["metric"] or "").strip():
        raise ValueError("Peeko2 metric credit requires a named metric.")
    if metrics["tier"] in {"quantified_result", "quantified_improvement"}:
        if not re.search(r"\d", metrics["measured_result"] or ""):
            raise ValueError("Peeko2 quantified metric tiers require a measured result.")
        if metrics["tier"] == "quantified_improvement" and not (metrics["action"] or "").strip():
            raise ValueError("Peeko2 quantified improvement requires a candidate action.")

    conversion = grading["conversion"]
    if conversion["destination_unverified"] and conversion["tier"] != "website_campaign":
        raise ValueError("Peeko2 unspecified destination requires the website campaign-work tier.")

    missing = grading["Missing or Unclear Information"].strip()
    if hands_on == 1:
        platform = "Google" if platform_scores["google"] != 7 else "Meta"
        missing = f"{platform} hands-on work unverified. {missing}".strip()
    if conversion["destination_unverified"]:
        missing = f"Campaign destination unverified. {missing}".strip()
    unverified = (hands_on == 0, not scores[1], conversion["tier"] in {"none", "app_mention"},
                  not scores[3], not scores[4])
    current = next((experience for experience in experiences if experience.get("is_current") is True), {})
    total = sum(scores)
    return {
        "Rank Number": "",
        "Candidate": candidate.get("candidate_name", ""),
        "Profile URL": candidate.get("linkedin_url", ""),
        "Current Company": current.get("company_name", ""),
        "Current Title": current.get("position_or_title", ""),
        **dict(zip(SCORE_COLUMNS, (units / 700 for units in scores))),
        TOTAL_COLUMN: total / 700,
        peeko.CUTOFF_COLUMN: peeko._yes_no(total >= CUTOFF_UNITS),
        peeko.REVIEW_COLUMN: peeko._yes_no(hands_on < 2),
        **dict(zip(peeko.UNVERIFIED_COLUMNS, map(peeko._yes_no, unverified))),
        "Date-Quality Warning": peeko._yes_no(warning),
        **{column: grading[column] for column in peeko.NARRATIVE_COLUMNS},
        "Missing or Unclear Information": missing,
        "Peeko2 Audit": {
            "grading": grading, "platform_scores": platform_scores, "recency": recencies,
            "evaluation_date": evaluation_date.isoformat(),
        },
    }
