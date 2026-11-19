"""Reject a rubric that cannot be applied by the selected fixed scoring mode."""
from __future__ import annotations

import re
import unicodedata

from .roles import FE_ORANGE_CAPABILITIES, SAFEGOLD_CAPABILITIES, RoleProfile
from .safegold import MEDIUM_RULES


def rubric_input_issue(rubric_text: str, role: RoleProfile) -> str:
    if role.key == "safegold":
        return _safegold_rubric_issue(rubric_text, role.total_max)
    if role.key == "fe_orange":
        return _fe_orange_rubric_issue(rubric_text)
    if role.key == "peeko2":
        from . import peeko2

        if not all(column in rubric_text for column in (*peeko2.SCORE_COLUMNS, peeko2.TOTAL_COLUMN)):
            return "Upload the simplified Peeko2 LinkedIn rubric with a 36-point total."
        return ""
    if role.key == "peeko":
        if "Final Score (/36)" in rubric_text:
            return "Select Peeko2 for the simplified 36-point LinkedIn rubric."
        if not all(re.search(rf"\bLC[-\s]+{number}\b", rubric_text, re.IGNORECASE) for number in range(1, 6)) or re.search(
            r"\bLC[-\s]+6\b", rubric_text, re.IGNORECASE
        ):
            return "Upload the Peeko LinkedIn rubric with updated criteria LC-1 through LC-5."
        return ""
    if role.key != "sde3":
        return ""
    text = unicodedata.normalize("NFKC", rubric_text).casefold()
    words = re.sub(r"[^a-z0-9]+", " ", text).strip()
    capability_checks = (
        "shipped ai agent" in words or "agent chatbot delivery" in words,
        "fastapi" in words and "django" in words,
        "backend" in words and "system architecture" in words,
        "ai solution breadth" in words and ("judgment" in words or "judgement" in words),
    )
    component_checks = all(re.search(rf"\b{component}\b", words) for component in ("evidence", "recency", "duration"))
    maxima = []
    for line in text.splitlines():
        # Keep line and sentence boundaries: a paragraph ending in "Final
        # Score." followed by section "2." is not a two-point score limit.
        line = re.sub(r"[*_#`>]", "", line)
        maxima.extend(re.findall(
            r"\b(?:maximum\s+score|total\s+score|final\s+score)"
            r"\s*(?:(?:is|of|out\s+of)\s*)?[:=(/\s]*(\d+)\b",
            line,
        ))
    if (
        not all(capability_checks)
        or not component_checks
        or not re.search(r"\b62\b", words)
        or any(int(maximum) != 62 for maximum in maxima)
    ):
        return (
            "This rubric does not match SDE3 LinkedIn scoring. This mode requires the four LinkedIn "
            "capabilities scored by Evidence, Recency and Duration, for a maximum of 62. "
            "Use the bundled SDE3 LinkedIn rubric; technical-assessment rubrics need their own scoring mode."
        )
    return ""


def _safegold_rubric_issue(rubric_text: str, total_max: float) -> str:
    text = unicodedata.normalize("NFKC", rubric_text).replace("**", "")
    capabilities = []
    channels = []
    weight_pattern = r"[xX×]\s*(\d+(?:\.\d+)?)"
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) == 3 and cells[0] in SAFEGOLD_CAPABILITIES:
            weights = tuple(float(value) for value in re.findall(weight_pattern, cells[1]))
            capabilities.append((cells[0], weights, cells[2]))
        if len(cells) == 5 and cells[1] in MEDIUM_RULES:
            weight = re.fullmatch(weight_pattern, cells[3])
            channels.append((cells[0], cells[1], float(weight[1]) if weight else None, cells[4]))
    expected_capabilities = [
        (name, (maximum / 10,), str(maximum))
        for name, maximum in SAFEGOLD_CAPABILITIES.items()
        if name != "Customer Support Medium"
    ]
    expected_capabilities.append((
        "Customer Support Medium",
        tuple(weight for weight, _ in MEDIUM_RULES.values()),
        str(SAFEGOLD_CAPABILITIES["Customer Support Medium"]),
    ))
    expected_channels = [
        (str(priority), label, weight, f"{weight * 10:g}")
        for priority, (label, (weight, _)) in enumerate(MEDIUM_RULES.items(), start=1)
    ]
    totals = re.findall(r"maximum\s+score\s*:\s*(\d+(?:\.\d+)?)", text, re.IGNORECASE)
    if capabilities != expected_capabilities or channels != expected_channels or (
        not totals or any(float(total) != total_max for total in totals)
    ):
        return (
            "This rubric does not match the SafeGold scoring configuration. "
            "Use the six-capability SafeGold rubric with a maximum of 53 and the configured channel weights."
        )
    return ""


def _fe_orange_rubric_issue(rubric_text: str) -> str:
    """Require the fixed C1-C10 calculation table before accepting an override.

    Evidence guidance can be revised, but a different weight or component scale
    needs a corresponding application change rather than silently using old math.
    """
    text = unicodedata.normalize("NFKC", rubric_text).replace("\\", "")
    rows = {}
    for line in text.splitlines():
        cells = [cell.strip().replace("**", "") for cell in line.strip().strip("|").split("|")]
        if len(cells) < 6 or not re.fullmatch(r"C(?:10|[1-9])", cells[0], re.I):
            continue
        key = cells[0].upper()
        try:
            values = (int(cells[-3]), float(cells[-2].lstrip("xX×")), int(cells[-1]))
        except ValueError:
            return "FE orange requires the C1-C10 scoring table with numeric raw maxima, multipliers and maxima."
        if key in rows:
            return "FE orange requires exactly one scoring-table row for each capability C1-C10."
        rows[key] = values
    expected = {
        name.split()[0]: (10 if index in (0, 9) else 4, multiplier, maximum)
        for index, (name, maximum, multiplier) in enumerate(FE_ORANGE_CAPABILITIES)
    }
    totals = re.findall(r"maximum\s+score\s*:\s*(\d+)", text.replace("**", "").casefold())
    if rows != expected or not totals or any(int(total) != 133 for total in totals):
        return (
            "This rubric does not match FE orange's fixed 133-point calculation. Keep the C1-C10 scoring table: "
            "C1 and C10 use Evidence + Recency + Duration; C2-C9 use Evidence only. "
            "Use the bundled FE orange rubric. Updated weights or component scales require matching app changes."
        )
    return ""
