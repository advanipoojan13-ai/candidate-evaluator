"""Reject a rubric that cannot be applied by the selected fixed scoring mode."""
from __future__ import annotations

import re
import unicodedata

from .roles import RoleProfile


def rubric_input_issue(rubric_text: str, role: RoleProfile) -> str:
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
