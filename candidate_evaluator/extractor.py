from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional, Union

from .constants import SOURCE_COLUMNS
from .evidence import has_selected_evidence


ALLOWED_EXPERIENCE_FIELDS = [
    "companyName",
    "position",
    "title",
    "description",
    "employmentType",
    "startDate",
    "endDate",
    "duration",
]


def load_profiles_from_text(text: str) -> list[dict[str, Any]]:
    data = json.loads(text)
    if isinstance(data, list):
        profiles = data
    elif isinstance(data, dict):
        profiles = _find_profile_list(data)
    else:
        raise ValueError("JSON root must be a list of profiles or an object containing a profile list.")
    if not all(isinstance(item, dict) for item in profiles):
        raise ValueError("Every candidate profile must be a JSON object.")
    return profiles


def load_profiles(path: Union[str, Path]) -> list[dict[str, Any]]:
    return load_profiles_from_text(Path(path).read_text(encoding="utf-8"))


def _find_profile_list(data: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("items", "profiles", "data", "results"):
        value = data.get(key)
        if isinstance(value, list) and all(isinstance(item, dict) for item in value):
            return value
    for value in data.values():
        if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
            return value
    raise ValueError("Could not find a list of candidate profiles in the JSON object.")


def normalize_candidate(profile: dict[str, Any], index: int) -> dict[str, Any]:
    experiences = [_normalize_experience(exp, i) for i, exp in enumerate(profile.get("experience") or []) if isinstance(exp, dict)]
    education = [_format_education(edu) for edu in (profile.get("education") or []) if isinstance(edu, dict)]
    candidate = {
        "source_index": index,
        "linkedin_profile_id": _first_nonempty(profile.get("publicIdentifier"), profile.get("id"), f"candidate-{index + 1}"),
        "linkedin_url": _clean(profile.get("linkedinUrl")),
        "candidate_name": _candidate_name(profile),
        "headline": _clean(profile.get("headline")),
        "about": _clean(profile.get("about")),
        "location": _format_location(profile.get("location")),
        "skills": _normalize_skills(profile.get("skills"), profile.get("topSkills")),
        "website": _first_website(profile.get("websites")),
        "education": education,
        "experiences": experiences,
        "open_to_work": profile.get("openToWork"),
        "open_to_work_present": "openToWork" in profile,
        "hiring": profile.get("hiring"),
        "hiring_present": "hiring" in profile,
        "services": profile.get("services"),
        "services_present": "services" in profile and profile.get("services") is not None,
    }
    candidate["source_row"] = build_source_row(candidate)
    return candidate


def normalize_candidates(profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [normalize_candidate(profile, index) for index, profile in enumerate(profiles)]


def build_source_row(candidate: dict[str, Any]) -> dict[str, str]:
    experiences = candidate.get("experiences") or []
    education = candidate.get("education") or []
    row = {
        "LinkedIn Profile ID": candidate.get("linkedin_profile_id", ""),
        "LinkedIn URL": candidate.get("linkedin_url", ""),
        "Candidate Name": candidate.get("candidate_name", ""),
        "Headline": candidate.get("headline", ""),
        "Experience 0": _format_experience_for_cell(experiences[0]) if len(experiences) > 0 else "",
        "Experience 1": _format_experience_for_cell(experiences[1]) if len(experiences) > 1 else "",
        "Education 0": education[0] if len(education) > 0 else "",
        "Education 1": education[1] if len(education) > 1 else "",
        "About": candidate.get("about", ""),
        "Website": candidate.get("website", ""),
    }
    return {column: row.get(column, "") for column in SOURCE_COLUMNS}


def preview_candidates(candidates: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    preview = []
    for candidate in candidates[:limit]:
        item = dict(candidate["source_row"])
        item["Experience Entries Detected"] = len(candidate.get("experiences") or [])
        for i, exp in enumerate(candidate.get("experiences") or []):
            item[f"experience/{i}"] = _format_experience_for_cell(exp)
        preview.append(item)
    return preview


def candidate_input_issue(
    candidate: dict[str, Any],
    role_key: str = "",
    evidence_sources: Optional[list[str]] = None,
    require_experience: bool = False,
) -> str:
    """Return why one record should be skipped before making an API call."""
    reasons = []
    linkedin_url = str(candidate.get("linkedin_url") or "").casefold()
    if not candidate.get("candidate_name"):
        reasons.append("candidate name is empty")
    if not linkedin_url:
        reasons.append("LinkedIn profile URL is empty")
    elif any(marker in linkedin_url for marker in ("linkedin.com/posts/", "linkedin.com/feed/update/")):
        reasons.append("URL is a LinkedIn post/activity rather than a candidate profile")
    if evidence_sources is not None:
        if require_experience and not candidate.get("experiences"):
            reasons.append("no experience entries are available for this custom role")
        if not has_selected_evidence(candidate, evidence_sources):
            reasons.append("none of the selected evidence sources contain usable data")
    elif role_key == "qa":
        if not candidate.get("experiences"):
            reasons.append("no experience entries are available for QA scoring")
    elif not any((candidate.get("headline"), candidate.get("about"), candidate.get("experiences"))):
        reasons.append("headline, About text, and experience entries are all empty")
    return "; ".join(reasons)


def candidate_input_issues(
    candidates: list[dict[str, Any]],
    role_key: str = "",
    evidence_sources: Optional[list[str]] = None,
    require_experience: bool = False,
) -> list[str]:
    """Summarize records that will be skipped without blocking valid records."""
    post_records = []
    empty_evidence_records = []
    missing_identity_records = []
    for candidate in candidates:
        candidate_id = str(candidate.get("linkedin_profile_id") or candidate.get("source_index", "unknown"))
        linkedin_url = str(candidate.get("linkedin_url") or "").casefold()
        if any(marker in linkedin_url for marker in ("linkedin.com/posts/", "linkedin.com/feed/update/")):
            post_records.append(candidate_id)
        if not candidate.get("candidate_name") or not linkedin_url:
            missing_identity_records.append(candidate_id)
        if evidence_sources is not None:
            lacks_evidence = not has_selected_evidence(candidate, evidence_sources) or (
                require_experience and not candidate.get("experiences")
            )
        else:
            lacks_evidence = not candidate.get("experiences") if role_key == "qa" else not any(
                (candidate.get("headline"), candidate.get("about"), candidate.get("experiences"))
            )
        if lacks_evidence:
            empty_evidence_records.append(candidate_id)

    issues = []
    if post_records:
        issues.append(
            f"{len(post_records)} record(s) use LinkedIn post/activity URLs instead of candidate profile URLs."
        )
    if missing_identity_records:
        issues.append(f"{len(missing_identity_records)} record(s) have an empty candidate name or LinkedIn profile URL.")
    if empty_evidence_records:
        if evidence_sources is not None:
            evidence_label = "usable data in the custom role's selected evidence sources"
        else:
            evidence_label = "experience entries required for QA scoring" if role_key == "qa" else "headline, About text, or experience entries"
        issues.append(
            f"{len(empty_evidence_records)} record(s) contain no {evidence_label} to score."
        )
    return issues


def merge_duplicate_experiences(experiences: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    by_role: dict[tuple[str, ...], dict[str, Any]] = {}
    for experience in experiences:
        key = tuple(
            str(experience.get(field, "")).strip().casefold()
            for field in ("company_name", "position_or_title", "start_date", "end_date", "duration")
        )
        existing = by_role.get(key)
        if existing is None:
            existing = dict(experience)
            existing["experience_skills"] = list(experience.get("experience_skills") or [])
            by_role[key] = existing
            merged.append(existing)
            continue
        descriptions = [existing.get("description", ""), experience.get("description", "")]
        existing["description"] = " | ".join(dict.fromkeys(text for text in descriptions if text))
        existing["experience_skills"] = list(
            dict.fromkeys([*(existing.get("experience_skills") or []), *(experience.get("experience_skills") or [])])
        )
    return merged


def _normalize_experience(exp: dict[str, Any], index: int) -> dict[str, Any]:
    end_date = _format_date(exp.get("endDate"))
    return {
        "index": index,
        "company_name": _clean(exp.get("companyName")),
        "position_or_title": _clean(_first_nonempty(exp.get("position"), exp.get("title"))),
        "description": _clean(exp.get("description")),
        "employment_type": _clean(exp.get("employmentType")),
        "start_date": _format_date(exp.get("startDate")),
        "end_date": end_date,
        "is_current": not end_date or end_date.casefold() in {"present", "current"},
        "duration": _clean(exp.get("duration")),
        # Kept internal for rubrics that explicitly allow role-attached skills.
        "experience_skills": _string_list(exp.get("skills")),
    }


def _format_experience_for_cell(exp: dict[str, Any]) -> str:
    parts = [
        exp.get("position_or_title"),
        exp.get("company_name"),
        exp.get("employment_type"),
        _date_range(exp.get("start_date"), exp.get("end_date")),
        exp.get("duration"),
        exp.get("description"),
    ]
    return " | ".join(str(part).strip() for part in parts if _clean(part))


def _format_education(edu: dict[str, Any]) -> str:
    parts = [edu.get("schoolName"), edu.get("degree"), edu.get("fieldOfStudy"), edu.get("period")]
    return " | ".join(_clean(part) for part in parts if _clean(part))


def _format_location(value: Any) -> str:
    if not isinstance(value, dict):
        return _clean(value)
    parsed = value.get("parsed") if isinstance(value.get("parsed"), dict) else {}
    return _first_nonempty(
        value.get("linkedinText"),
        value.get("text"),
        parsed.get("text"),
        ", ".join(
            part
            for part in (
                _clean(parsed.get("city")),
                _clean(parsed.get("state")),
                _clean(parsed.get("countryFull") or parsed.get("country")),
            )
            if part
        ),
    )


def _normalize_skills(skills: Any, top_skills: Any) -> list[str]:
    names: list[str] = []
    for value in (skills, top_skills):
        if not isinstance(value, list):
            continue
        for item in value:
            name = _clean(item.get("name")) if isinstance(item, dict) else _clean(item)
            if name and name not in names:
                names.append(name)
    return names


def _format_date(value: Any) -> str:
    if isinstance(value, dict):
        return _clean(value.get("text")) or " ".join(_clean(value.get(k)) for k in ("month", "year") if _clean(value.get(k)))
    return _clean(value)


def _date_range(start: str, end: str) -> str:
    if start and end:
        return f"{start} - {end}"
    return start or end or ""


def _candidate_name(profile: dict[str, Any]) -> str:
    first_last = " ".join(part for part in [_clean(profile.get("firstName")), _clean(profile.get("lastName"))] if part)
    return _first_nonempty(first_last, profile.get("fullName"), profile.get("name"), profile.get("publicIdentifier"), "")


def _first_website(value: Any) -> str:
    if isinstance(value, list):
        return _clean(value[0]) if value else ""
    return _clean(value)


def _first_nonempty(*values: Any) -> str:
    for value in values:
        cleaned = _clean(value)
        if cleaned:
            return cleaned
    return ""


def _clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return " ".join(value.split())
    return str(value)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_clean(item) for item in value if _clean(item)]
