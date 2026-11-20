"""Validate SafeGold model grades and format the channel evidence for export."""

from .roles import SAFEGOLD_CHANNELS_COLUMN


CHANNELS = (
    "Phone / Calls",
    "Live Chat / Messaging",
    "Email",
    "Social Media Customer Support",
    "Other Direct Customer Support Channels",
)
CHANNEL_POINTS = (0, 4, 6, 8, 10, 10)

LEGACY_TOTAL = "Final Score (/53)"
LEGACY_SCORES = [
    "Frontline Customer Support Score (/10)",
    "Issue Resolution, Complaints & Escalations Score (/12)",
    "KYC, AML/CFT, Disputes & Fraud Score (/8)",
    "Partner Support, Case Records & Support Tools Score (/8)",
    "Recurring Issues, Feedback & Support Content Score (/5)",
    "Customer Support Medium Score (/10)",
]
LEGACY_OUTPUT_COLUMNS = [
    "Rank Number", "Candidate", "Profile URL", "Current Company", "Current Title",
    *LEGACY_SCORES, LEGACY_TOTAL, "Selected Customer Support Medium",
    "Frontline Customer Support Unverified", "Issue Resolution, Complaints & Escalations Unverified",
    "Date-Quality Warning", "Strongest Evidence", "Missing or Unclear Information", "Score Rationale",
]


def normalize_grading(row: dict, allowed_scores: dict[str, set[float]]) -> None:
    for column, scores in allowed_scores.items():
        value = row.get(column)
        if type(value) is not int or value not in scores:
            raise ValueError(f"{column} must be a JSON integer from {sorted(scores)}.")

    reported_channels = row.get(SAFEGOLD_CHANNELS_COLUMN)
    if not isinstance(reported_channels, list) or any(channel not in CHANNELS for channel in reported_channels):
        raise ValueError("Return an array of qualifying SafeGold support channel categories.")
    channels = [channel for channel in CHANNELS if channel in reported_channels]
    points = CHANNEL_POINTS[len(channels)]
    if row["Customer Support Channels Score (/10)"] != points:
        raise ValueError(f"Customer Support Channels Score (/10) must be {points} for {len(channels)} distinct channels.")
    row[SAFEGOLD_CHANNELS_COLUMN] = " | ".join(channels) or "Not stated"

    arabic_unverified = "Yes" if row["Arabic Language Score (/5)"] == 0 else "No"
    if row.get("Arabic Unverified") != arabic_unverified:
        raise ValueError("Arabic Unverified must match the Arabic Language Score (/5).")
