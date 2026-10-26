"""Translate Unipile LinkedIn profile exports into the existing import contract.

Reference: https://developer.unipile.com/docs/retrieving-users
No network calls, source mutation, sorting, or inferred employment durations.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote


def is_unipile_profile(profile: dict[str, Any]) -> bool:
    return profile.get("object") == "UserProfile" or any(
        key in profile for key in ("public_identifier", "provider_id", "work_experience", "first_name", "last_name")
    )


def _text(value: Any) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def _entries(profile: dict[str, Any], key: str, warnings: list[str]) -> list[dict[str, Any]]:
    value = profile.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        warnings.append(f"Unipile {key} must be an array; no entries were imported.")
        return []
    entries = [item for item in value if isinstance(item, dict)]
    if len(entries) != len(value):
        warnings.append(f"Unipile {key} contains malformed entries that were ignored.")
    return entries


def _date(value: Any) -> str:
    if isinstance(value, dict):
        text = _text(value.get("text"))
        if text:
            return text
        year, month = value.get("year"), value.get("month")
        if isinstance(year, int) and not isinstance(year, bool) and year > 0:
            if isinstance(month, int) and not isinstance(month, bool) and 1 <= month <= 12:
                return f"{year:04d}-{month:02d}"
            return str(year)
        return ""
    text = _text(value)
    # Unipile's full-profile example uses M/D/YYYY. Keep its stated precision.
    match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
    if match:
        month, day, year = map(int, match.groups())
        if 1 <= month <= 12 and 1 <= day <= 31:
            return f"{year:04d}-{month:02d}-{day:02d}"
    return text


def adapt_unipile_profile(profile: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    provider = _text(profile.get("provider"))
    if provider and provider.upper() != "LINKEDIN":
        raise ValueError("Only LinkedIn Unipile profiles are supported.")
    warnings: list[str] = []
    identifier = _text(profile.get("public_identifier"))
    url = _text(profile.get("public_profile_url")) or _text(profile.get("linkedinUrl"))
    if not url and identifier and not identifier.startswith(("ACo", "urn:")) and not re.search(r"[/?#:\s]", identifier):
        url = f"https://www.linkedin.com/in/{quote(identifier, safe='-._~%')}/"
    experiences = []
    for exp in _entries(profile, "work_experience", warnings):
        if not any(_text(exp.get(key)) for key in ("company", "position", "role", "description", "duration")) and not any(
            _date(exp.get(key)) for key in ("start", "end")
        ):
            warnings.append("Unipile work_experience contains an empty entry that was ignored.")
            continue
        start, end = _date(exp.get("start")), _date(exp.get("end"))
        current = end.casefold() in {"present", "current"} or (
            "end" in exp and exp["end"] is None and bool(start)
        )
        experiences.append({
            "companyName": _text(exp.get("company")),
            "position": _text(exp.get("position")) or _text(exp.get("role")),
            "description": _text(exp.get("description")),
            "employmentType": _text(exp.get("employment_type")),
            "startDate": start,
            "endDate": "Present" if current and not end else end,
            "isCurrent": current,
            "duration": _text(exp.get("duration")),
            "skills": [
                item.get("name", "") if isinstance(item, dict) else item
                for item in exp.get("skills", [])
            ] if isinstance(exp.get("skills"), list) else [],
        })
    education = [{
        "schoolName": _text(edu.get("school")),
        "degree": _text(edu.get("degree")),
        "fieldOfStudy": _text(edu.get("field_of_study")),
        "period": " - ".join(value for value in (_date(edu.get("start")), _date(edu.get("end"))) if value),
    } for edu in _entries(profile, "education", warnings)]
    count = profile.get("work_experience_total_count")
    if isinstance(count, int) and not isinstance(count, bool) and count > len(experiences):
        warnings.append(f"Unipile work history is incomplete: {len(experiences)} of {count} entries supplied. Retrieve full experience before relying on scores.")
    throttled = profile.get("throttled_sections")
    if throttled:
        sections = ", ".join(map(str, throttled)) if isinstance(throttled, list) else str(throttled)
        warnings.append(f"Unipile throttled sections: {sections}. Retrieve these sections again before relying on scores.")
    result = {
        "publicIdentifier": identifier or _text(profile.get("provider_id")),
        "linkedinUrl": url,
        "firstName": _text(profile.get("first_name")),
        "lastName": _text(profile.get("last_name")),
        "headline": _text(profile.get("headline")),
        "about": _text(profile.get("summary")),
        "location": profile.get("location"),
        "experience": experiences,
        "education": education,
        "skills": profile.get("skills"),
        "websites": profile.get("websites"),
        "projects": profile.get("projects"),
    }
    # is_open_profile describes messaging access, not job-seeking intent.
    if "is_open_to_work" in profile:
        result["openToWork"] = profile["is_open_to_work"]
    return result, warnings
