from __future__ import annotations

from typing import Any


CUSTOM_EVIDENCE_SOURCES = [
    "Location",
    "Headline",
    "About",
    "Projects",
    "Experience 0",
    "Experience 1",
    "Experience 2",
    "Experience 3",
    "Experience 4",
    "All experiences",
    "Current company (Experience 0 company name)",
    "Experience role titles",
    "Experience durations",
    "Skills",
    "Experience-level skills",
    "Education",
    "Open-to-work signal",
    "Hiring signal",
    "Services offered",
    "All open-to signals",
    "Website",
]

# Custom runs created before the expanded selector used this name. Keeping it
# valid preserves resume, retry, and export behavior for those saved runs.
LEGACY_EVIDENCE_SOURCE_ALIASES = {"Experience entries"}

EXPERIENCE_EVIDENCE_SOURCES = {
    "Experience 0",
    "Experience 1",
    "Experience 2",
    "Experience 3",
    "Experience 4",
    "All experiences",
    "Current company (Experience 0 company name)",
    "Experience role titles",
    "Experience durations",
    "Experience-level skills",
    *LEGACY_EVIDENCE_SOURCE_ALIASES,
}


def custom_evidence_payload(candidate: dict[str, Any], evidence_sources: list[str]) -> dict[str, Any]:
    selected = set(evidence_sources)
    payload: dict[str, Any] = {}

    direct_fields = {
        "Location": ("Location", candidate.get("location")),
        "Headline": ("Headline", candidate.get("headline")),
        "About": ("About", candidate.get("about")),
        "Projects": ("Projects", candidate.get("projects") or []),
        "Website": ("Website", candidate.get("website")),
        "Skills": ("Skills", candidate.get("skills") or []),
        "Education": ("Education", candidate.get("education") or []),
    }
    for source, (payload_name, value) in direct_fields.items():
        if source in selected and _has_value(value):
            payload[payload_name] = value

    experiences = _selected_experiences(candidate.get("experiences") or [], selected)
    if experiences:
        payload["experiences"] = experiences

    open_signals = _selected_open_signals(candidate, selected)
    if open_signals:
        payload["Open-to signals"] = open_signals
    return payload


def has_selected_evidence(candidate: dict[str, Any], evidence_sources: list[str]) -> bool:
    return bool(custom_evidence_payload(candidate, evidence_sources))


def _selected_experiences(experiences: list[dict[str, Any]], selected: set[str]) -> list[dict[str, Any]]:
    include_all = bool(selected.intersection({"All experiences", *LEGACY_EVIDENCE_SOURCE_ALIASES}))
    indexed_sources = {
        int(source.rsplit(" ", 1)[1])
        for source in selected
        if source.startswith("Experience ") and source.rsplit(" ", 1)[1].isdigit()
    }
    current_company = "Current company (Experience 0 company name)" in selected
    role_titles = "Experience role titles" in selected
    durations = "Experience durations" in selected
    role_skills = "Experience-level skills" in selected

    filtered_experiences: list[dict[str, Any]] = []
    for position, experience in enumerate(experiences):
        experience_index = int(experience.get("index", position))
        if include_all or experience_index in indexed_sources:
            filtered_experiences.append(dict(experience))
            continue

        filtered: dict[str, Any] = {"index": experience_index}
        if current_company and experience_index == 0 and experience.get("company_name"):
            filtered["company_name"] = experience["company_name"]
        if role_titles and experience.get("position_or_title"):
            filtered["position_or_title"] = experience["position_or_title"]
        if durations:
            has_duration_data = any(_has_value(experience.get(field)) for field in ("start_date", "end_date", "duration"))
            for field in ("start_date", "end_date", "duration"):
                if _has_value(experience.get(field)):
                    filtered[field] = experience[field]
            if has_duration_data:
                filtered["is_current"] = bool(experience.get("is_current"))
        if role_skills and experience.get("experience_skills"):
            filtered["experience_skills"] = experience["experience_skills"]
        if len(filtered) > 1:
            filtered_experiences.append(filtered)
    return filtered_experiences


def _selected_open_signals(candidate: dict[str, Any], selected: set[str]) -> dict[str, Any]:
    include_all = "All open-to signals" in selected
    signals: dict[str, Any] = {}
    if (include_all or "Open-to-work signal" in selected) and candidate.get("open_to_work_present"):
        signals["open_to_work"] = candidate.get("open_to_work")
    if (include_all or "Hiring signal" in selected) and candidate.get("hiring_present"):
        signals["hiring"] = candidate.get("hiring")
    if (include_all or "Services offered" in selected) and candidate.get("services_present"):
        signals["services"] = candidate.get("services")
    return signals


def _has_value(value: Any) -> bool:
    if isinstance(value, bool):
        return True
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return bool(value)
