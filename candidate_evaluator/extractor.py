from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional, Union

from .constants import SOURCE_COLUMNS
from .evidence import has_selected_evidence


ALLOWED_EXPERIENCE_FIELDS = [
    "companyName",
    "position",
    "title",
    "description",
    "location",
    "employmentType",
    "startDate",
    "endDate",
    "duration",
]


def load_profiles_from_text(text: str) -> list[dict[str, Any]]:
    data = json.loads(text)
    if isinstance(data, list):
        profiles = _profile_records(data)
    elif isinstance(data, dict):
        profiles = [data] if _looks_like_profile(data) else _find_profile_list(data)
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
            return _profile_records(value)
    for value in data.values():
        if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
            profiles = _profile_records(value)
            if profiles and any(_looks_like_profile(item) for item in profiles):
                return profiles
    raise ValueError("Could not find a list of candidate profiles in the JSON object.")


def _profile_records(records: list[Any]) -> list[Any]:
    """Keep candidate-like records while ignoring known mixed search results."""
    return [record for record in records if not isinstance(record, dict) or not _known_non_person(record)]


def _known_non_person(record: dict[str, Any]) -> bool:
    record_type = _clean(record.get("type")).upper()
    object_type = _clean(record.get("object")).upper()
    return record_type in {"COMPANY", "JOB", "JOBS", "POST", "SCHOOL"} or object_type in {
        "COMPANYSEARCHRESULT",
        "JOBSEARCHRESULT",
        "POSTSEARCHRESULT",
    }


def _looks_like_profile(record: dict[str, Any]) -> bool:
    object_type = _clean(record.get("object")).casefold()
    record_type = _clean(record.get("type")).casefold()
    if object_type in {"userprofile", "peoplesearchresult", "linkedinjobapplicant"} or record_type == "people":
        return True
    profile_keys = {
        "publicIdentifier", "linkedinUrl", "fullName", "experience",
        "public_identifier", "public_profile_url", "profile_url", "display_name",
        "work_experience", "current_positions", "candidate_id", "recruiter_candidate_id",
    }
    return bool(profile_keys.intersection(record))


def normalize_candidate(profile: dict[str, Any], index: int) -> dict[str, Any]:
    specifics = _linkedin_specifics(profile)
    experience_items, current_positions = _experience_items(profile, specifics)
    is_unipile = _is_unipile_profile(profile)
    experiences = [
        _normalize_experience(exp, i, unipile=is_unipile, current_position=current_positions)
        for i, exp in enumerate(experience_items)
        if isinstance(exp, dict)
    ]
    education_items = _first_list(profile.get("education"), specifics.get("education"))
    education = [_format_education(edu) for edu in education_items if isinstance(edu, dict)]
    public_identifier = _first_nonempty(profile.get("publicIdentifier"), profile.get("public_identifier"))
    linkedin_url = _first_nonempty(
        profile.get("linkedinUrl"), profile.get("public_profile_url"), profile.get("profile_url")
    )
    if not linkedin_url and public_identifier:
        linkedin_url = f"https://www.linkedin.com/in/{public_identifier}/"
    open_to_work, open_to_work_present = _nested_value(
        profile, specifics, "openToWork", "is_open_to_work"
    )
    hiring, hiring_present = _nested_value(profile, specifics, "hiring", "is_hiring")
    services, services_present = _nested_value(profile, specifics, "services", "services_page_url")
    throttled_sections = _string_list(
        _first_list(profile.get("throttled_sections"), specifics.get("throttled_sections"))
    )
    candidate = {
        "source_index": index,
        "source_format": "unipile" if is_unipile else "apify",
        "source_visibility": _clean(profile.get("visibility")).casefold(),
        "throttled_sections": throttled_sections,
        "linkedin_profile_id": _first_nonempty(
            public_identifier,
            profile.get("provider_id"),
            profile.get("id"),
            profile.get("candidate_id"),
            profile.get("recruiter_candidate_id"),
            f"candidate-{index + 1}",
        ),
        "linkedin_url": linkedin_url,
        "candidate_name": _candidate_name(profile),
        "headline": _first_nonempty(profile.get("headline"), profile.get("description")),
        "about": _first_nonempty(profile.get("about"), profile.get("summary"), profile.get("bio")),
        "location": _format_location(_first_value(profile.get("location"), specifics.get("location"))),
        "skills": _normalize_skills(
            _first_list(profile.get("skills"), specifics.get("skills")), profile.get("topSkills")
        ),
        "website": _first_website(profile.get("websites")),
        "education": education,
        "projects": _normalize_projects(_first_list(profile.get("projects"), specifics.get("projects"))),
        "experiences": experiences,
        "open_to_work": open_to_work,
        "open_to_work_present": open_to_work_present,
        "hiring": hiring,
        "hiring_present": hiring_present,
        "services": services,
        "services_present": services_present,
    }
    candidate["source_row"] = build_source_row(candidate)
    return candidate


def normalize_candidates(profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = [normalize_candidate(profile, index) for index, profile in enumerate(profiles)]
    used_ids: set[str] = set()
    next_suffix: dict[str, int] = {}
    for candidate in candidates:
        candidate_id = str(candidate["linkedin_profile_id"])
        unique_id = candidate_id
        if unique_id in used_ids:
            suffix = next_suffix.get(candidate_id, 2)
            unique_id = f"{candidate_id}--duplicate-{suffix}"
            while unique_id in used_ids:
                suffix += 1
                unique_id = f"{candidate_id}--duplicate-{suffix}"
            next_suffix[candidate_id] = suffix + 1
        used_ids.add(unique_id)
        # Progress and result files are keyed by candidate ID. Keep duplicate
        # source profiles independent without changing the original source row.
        candidate["linkedin_profile_id"] = unique_id
    return candidates


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
    skip_if_no_evidence: bool = True,
) -> str:
    """Return why one record should be skipped before making an API call."""
    reasons = []
    if candidate.get("source_format") == "unipile" and candidate.get("source_visibility") == "partial":
        reasons.append("Unipile returned a partial profile; retrieve the complete profile before evaluation")
    throttled = _relevant_throttled_sections(candidate, evidence_sources)
    if throttled:
        reasons.append(
            "Unipile throttled required profile section(s): " + ", ".join(throttled)
        )
    linkedin_url = str(candidate.get("linkedin_url") or "").casefold()
    if not candidate.get("candidate_name"):
        reasons.append("candidate name is empty")
    if not linkedin_url:
        reasons.append("LinkedIn profile URL is empty")
    elif any(marker in linkedin_url for marker in ("linkedin.com/posts/", "linkedin.com/feed/update/")):
        reasons.append("URL is a LinkedIn post/activity rather than a candidate profile")
    if evidence_sources is not None:
        if skip_if_no_evidence:
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
    skip_if_no_evidence: bool = True,
) -> list[str]:
    """Summarize records that will be skipped without blocking valid records."""
    post_records = []
    empty_evidence_records = []
    missing_identity_records = []
    incomplete_unipile_records = []
    for candidate in candidates:
        candidate_id = str(candidate.get("linkedin_profile_id") or candidate.get("source_index", "unknown"))
        linkedin_url = str(candidate.get("linkedin_url") or "").casefold()
        if any(marker in linkedin_url for marker in ("linkedin.com/posts/", "linkedin.com/feed/update/")):
            post_records.append(candidate_id)
        if not candidate.get("candidate_name") or not linkedin_url:
            missing_identity_records.append(candidate_id)
        if (
            candidate.get("source_format") == "unipile"
            and candidate.get("source_visibility") == "partial"
        ) or _relevant_throttled_sections(candidate, evidence_sources):
            incomplete_unipile_records.append(candidate_id)
        if evidence_sources is not None and skip_if_no_evidence:
            lacks_evidence = not has_selected_evidence(candidate, evidence_sources) or (
                require_experience and not candidate.get("experiences")
            )
        elif evidence_sources is not None:
            lacks_evidence = False
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
    if incomplete_unipile_records:
        issues.append(
            f"{len(incomplete_unipile_records)} Unipile record(s) are partial or have required throttled sections."
        )
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
        if not existing.get("experience_location") and experience.get("experience_location"):
            existing["experience_location"] = experience["experience_location"]
        existing["experience_skills"] = list(
            dict.fromkeys([*(existing.get("experience_skills") or []), *(experience.get("experience_skills") or [])])
        )
    return merged


def _normalize_experience(
    exp: dict[str, Any], index: int, *, unipile: bool = False, current_position: bool = False
) -> dict[str, Any]:
    start_value = _first_raw(exp, "startDate", "start", "started_on")
    end_value = _first_raw(exp, "endDate", "end", "ended_on")
    end_date = _format_date(end_value)
    company = _first_nonempty(exp.get("companyName"), _object_name(exp.get("company")))
    position = _first_nonempty(
        exp.get("position"), exp.get("title"), exp.get("role"), _object_name(exp.get("job_title"))
    )
    explicit_current = _first_raw(exp, "isCurrent", "is_current", "current")
    # Unipile v1 commonly omits ``end`` for a current role, while v2 returns
    # ``ended_on: null``. Both shapes mean the role is open-ended.
    unipile_open_ended = (
        unipile
        and end_value in (None, "")
        and start_value not in (None, "")
    )
    return {
        "index": index,
        "company_name": company,
        "position_or_title": position,
        "description": _clean(exp.get("description")),
        "experience_location": _format_location(exp.get("location")),
        "employment_type": _first_nonempty(
            exp.get("employmentType"), exp.get("employment_type"), exp.get("status")
        ),
        "workplace_type": _first_nonempty(exp.get("workplaceType"), exp.get("workplace_type")),
        "start_date": _format_date(start_value),
        "end_date": end_date,
        "is_current": (
            end_date.casefold() in {"present", "current"}
            or explicit_current is True
            or current_position
            or unipile_open_ended
        ),
        "duration": _clean(exp.get("duration")),
        # Kept internal for rubrics that explicitly allow role-attached skills.
        "experience_skills": _string_list(exp.get("skills")),
    }


def _normalize_projects(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    projects: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, str):
            description = _clean(item)
            if description:
                projects.append({"name": "", "description": description, "technologies": []})
            continue
        if not isinstance(item, dict):
            continue
        project = {
            "name": _clean(_first_nonempty(item.get("name"), item.get("title"), item.get("projectName"))),
            "description": _clean(_first_nonempty(item.get("description"), item.get("summary"))),
            "technologies": _normalize_project_technologies(item),
        }
        if any(_has_normalized_value(field) for field in project.values()):
            projects.append(project)
    return projects


def _has_normalized_value(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    return bool(value)


def _normalize_project_technologies(project: dict[str, Any]) -> list[str]:
    for key in ("technologies", "skills", "techStack"):
        value = project.get(key)
        if not value:
            continue
        if isinstance(value, list):
            normalized = []
            for item in value:
                name = _object_name(item)
                if name and name not in normalized:
                    normalized.append(name)
            return normalized
        if isinstance(value, str):
            return [_clean(value)]
    return []


def _format_experience_for_cell(exp: dict[str, Any]) -> str:
    parts = [
        exp.get("position_or_title"),
        exp.get("company_name"),
        exp.get("experience_location"),
        exp.get("employment_type"),
        _date_range(exp.get("start_date"), exp.get("end_date")),
        exp.get("duration"),
        exp.get("description"),
    ]
    return " | ".join(str(part).strip() for part in parts if _clean(part))


def _format_education(edu: dict[str, Any]) -> str:
    school = _first_nonempty(edu.get("schoolName"), _object_name(edu.get("school")))
    degree = _object_name(edu.get("degree"))
    field = _first_nonempty(
        edu.get("fieldOfStudy"),
        edu.get("field_of_study"),
        ", ".join(_string_list(edu.get("fields_of_study"))),
    )
    period = _first_nonempty(
        edu.get("period"),
        _date_range(
            _format_date(_first_raw(edu, "start", "started_on")),
            _format_date(_first_raw(edu, "end", "ended_on")),
        ),
    )
    return " | ".join(part for part in (school, degree, field, period) if part)


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
            name = _object_name(item)
            if name and name not in names:
                names.append(name)
    return names


def _format_date(value: Any) -> str:
    if isinstance(value, dict):
        text = _clean(value.get("text"))
        if text:
            return text
        year = _clean(value.get("year"))
        month = _clean(value.get("month"))
        day = _clean(value.get("day"))
        if year:
            if month and day:
                if year.isdigit() and month.isdigit() and day.isdigit():
                    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
                return " ".join(part for part in (month, day, year) if part)
            if month:
                if year.isdigit() and month.isdigit():
                    return f"{int(year):04d}-{int(month):02d}"
                return f"{month} {year}"
            return year
        return ""
    text = _clean(value)
    # Unipile v1 commonly returns M/D/YYYY strings; convert them to the
    # canonical year-first representation consumed by the date calculator.
    match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
    if match:
        month, day, year = map(int, match.groups())
        if 1 <= month <= 12 and 1 <= day <= 31:
            return f"{year:04d}-{month:02d}-{day:02d}"
    return text


def _date_range(start: str, end: str) -> str:
    if start and end:
        return f"{start} - {end}"
    return start or end or ""


def _candidate_name(profile: dict[str, Any]) -> str:
    first_last = " ".join(
        part
        for part in [
            _first_nonempty(profile.get("firstName"), profile.get("first_name")),
            _first_nonempty(profile.get("lastName"), profile.get("last_name")),
        ]
        if part
    )
    return _first_nonempty(
        first_last,
        profile.get("fullName"),
        profile.get("display_name"),
        profile.get("name"),
        profile.get("publicIdentifier"),
        profile.get("public_identifier"),
        "",
    )


def _first_website(value: Any) -> str:
    if isinstance(value, list):
        return _object_url(value[0]) if value else ""
    return _object_url(value)


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
    normalized = []
    for item in value:
        name = _object_name(item)
        if name and name not in normalized:
            normalized.append(name)
    return normalized


def _linkedin_specifics(profile: dict[str, Any]) -> dict[str, Any]:
    specifics = profile.get("specifics")
    if not isinstance(specifics, dict):
        return {}
    linkedin = specifics.get("linkedin")
    return linkedin if isinstance(linkedin, dict) else specifics


def _experience_items(
    profile: dict[str, Any], specifics: dict[str, Any]
) -> tuple[list[Any], bool]:
    sources = (
        (profile.get("experience"), False),
        (profile.get("work_experience"), False),
        (specifics.get("experience"), False),
        (profile.get("current_positions"), True),
    )
    for value, current_position in sources:
        if isinstance(value, list) and value:
            return value, current_position
    return [], False


def _is_unipile_profile(profile: dict[str, Any]) -> bool:
    if _clean(profile.get("provider")).casefold() == "linkedin":
        return True
    if _clean(profile.get("object")).casefold() in {
        "userprofile", "peoplesearchresult", "linkedinjobapplicant", "searchresult"
    }:
        return True
    return any(
        key in profile
        for key in (
            "provider_id", "public_identifier", "public_profile_url", "profile_url",
            "display_name", "work_experience", "current_positions", "specifics",
            "candidate_id", "recruiter_candidate_id",
        )
    )


def _nested_value(
    profile: dict[str, Any], specifics: dict[str, Any], *keys: str
) -> tuple[Any, bool]:
    for container in (profile, specifics):
        for key in keys:
            if key in container:
                return container.get(key), container.get(key) is not None
    return None, False


def _first_list(*values: Any) -> list[Any]:
    for value in values:
        if isinstance(value, list) and value:
            return value
    return []


def _first_raw(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping:
            return mapping.get(key)
    return None


def _first_value(*values: Any) -> Any:
    for value in values:
        if value is not None and (not isinstance(value, str) or value.strip()):
            return value
    return None


def _object_name(value: Any) -> str:
    if isinstance(value, dict):
        return _first_nonempty(value.get("name"), value.get("text"), value.get("title"))
    return _clean(value)


def _object_url(value: Any) -> str:
    if isinstance(value, dict):
        return _first_nonempty(value.get("url"), value.get("link"))
    return _clean(value)


def _relevant_throttled_sections(
    candidate: dict[str, Any], evidence_sources: Optional[list[str]]
) -> list[str]:
    if candidate.get("source_format") != "unipile":
        return []
    raw_sections = candidate.get("throttled_sections") or []
    section_aliases = {
        "work_experience": "experience",
        "experiences": "experience",
        "project": "projects",
    }
    sections = set()
    for section in raw_sections:
        normalized = str(section).strip().casefold().removeprefix("linkedin_")
        if normalized:
            sections.add(section_aliases.get(normalized, normalized))
    selected = set(evidence_sources or [])
    relevant = set()
    if not evidence_sources or selected.intersection(
        {"All experiences", "Experience entries", "Experience role titles", "Experience durations", "Experience-level skills"}
    ) or any(source.startswith("Experience ") for source in selected):
        relevant.add("experience")
    if not evidence_sources or "Projects" in selected:
        relevant.add("projects")
    return sorted(sections.intersection(relevant))
