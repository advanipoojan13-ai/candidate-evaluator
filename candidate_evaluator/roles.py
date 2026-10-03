from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Optional

from .constants import SOURCE_COLUMNS
from .evidence import (
    CUSTOM_EVIDENCE_SOURCES,
    EXPERIENCE_EVIDENCE_SOURCES,
    LEGACY_EVIDENCE_SOURCE_ALIASES,
)


@dataclass(frozen=True)
class RoleProfile:
    key: str
    label: str
    role_name: str
    grading_columns: list[str]
    category_scores: OrderedDict[str, float]
    allowed_scores: dict[str, set[float]]
    total_column: str
    total_max: float
    outcome_column: str
    outcome_bands: list[tuple[float, float, str]]
    evidence_confidence_values: list[str]
    system_prompt: str
    instructions: list[str]
    internal_role_flag_name: str
    internal_role_evidence_name: str
    export_columns: Optional[list[str]] = None
    numeric_scores: bool = False
    ranked: bool = False
    column_enums: Optional[dict[str, list[str]]] = None
    ranking_tiebreaker_columns: Optional[list[str]] = None
    strongest_evidence_columns: Optional[list[str]] = None
    rationale_min_words: int = 0
    evidence_sources: Optional[list[str]] = None
    require_experience: bool = False
    skip_if_no_evidence: bool = True

    @property
    def output_columns(self) -> list[str]:
        return self.export_columns or (SOURCE_COLUMNS + self.grading_columns)


DESIGN_GRADING_COLUMNS = [
    "Total Relevant Design Experience — Months",
    "Total Relevant Design Experience — Years and Months",
    "Total Weighted Relevant Design Experience — Months",
    "Total Weighted Relevant Design Experience — Years and Months",
    "Weighted Design-Agency Experience — Months",
    "Weighted Design-Agency Experience — Years and Months",
    "UX/Product Design Experience and Career Depth — Score",
    "User Research, Insight and Synthesis — Score",
    "UX Craft and Complex Workflow Design — Score",
    "Product Thinking, UX Strategy and Ownership — Score",
    "Validation, Behavioural Data and Outcomes — Score",
    "Design Systems, Engineering and Accessibility — Score",
    "Design-Agency Experience and Breadth — Score",
    "Total Score",
    "Ranking",
    "Evidence Confidence",
    "Strongest Evidence 1",
    "Strongest Evidence 2",
    "Strongest Evidence 3",
    "Missing or Unclear Information",
    "Score Rationale",
]

DESIGN_CATEGORY_SCORES = OrderedDict(
    [
        ("UX/Product Design Experience and Career Depth — Score", 15),
        ("User Research, Insight and Synthesis — Score", 12),
        ("UX Craft and Complex Workflow Design — Score", 10),
        ("Product Thinking, UX Strategy and Ownership — Score", 9),
        ("Validation, Behavioural Data and Outcomes — Score", 5),
        ("Design Systems, Engineering and Accessibility — Score", 4),
        ("Design-Agency Experience and Breadth — Score", 5),
    ]
)

QA_GRADING_COLUMNS = [
    "Total Relevant QA Experience — Months",
    "Total Relevant QA Experience — Years and Months",
    "Total Weighted Relevant QA Experience — Months",
    "Total Weighted Relevant QA Experience — Years and Months",
    "Rest Assured / API Automation — Score",
    "Manual API / Postman — Score",
    "Python Automation — Score",
    "Java Proficiency — Score",
    "Selenium UI Automation — Score",
    "SQL and Data Validation — Score",
    "CI/CD and Pipelines — Score",
    "Total Score",
    "Decision",
    "Evidence Confidence",
    "Strongest Evidence 1",
    "Strongest Evidence 2",
    "Strongest Evidence 3",
    "Missing or Unclear Information",
    "Score Rationale",
]

QA_CATEGORY_SCORES = OrderedDict(
    [
        ("Rest Assured / API Automation — Score", 35),
        ("Manual API / Postman — Score", 15),
        ("Python Automation — Score", 15),
        ("Java Proficiency — Score", 15),
        ("Selenium UI Automation — Score", 15),
        ("SQL and Data Validation — Score", 10),
        ("CI/CD and Pipelines — Score", 5),
    ]
)

QA_ALLOWED_SCORES = {
    "Rest Assured / API Automation — Score": {0, 10, 18, 26, 35},
    "Manual API / Postman — Score": {0, 5, 10, 15},
    "Python Automation — Score": {0, 5, 10, 15},
    "Java Proficiency — Score": {0, 5, 10, 15},
    "Selenium UI Automation — Score": {0, 5, 10, 15},
    "SQL and Data Validation — Score": {0, 3, 6, 10},
    "CI/CD and Pipelines — Score": {0, 2, 3, 5},
}


BACKEND_GRADING_COLUMNS = [
    "Current Company",
    "Current Title",
    "PHP Score (/20)",
    "Python Score (/20)",
    "Laravel Score (/12)",
    "AWS Score (/8)",
    "Final Score (/60)",
    "PHP Unverified",
    "Python Unverified",
    "Backend Relevance Unverified",
    "Seniority Unverified",
    "Date-Quality Warning",
    "Strongest Evidence",
    "Missing or Unclear Information",
    "Score Rationale",
    # These are retained internally for deterministic ranking tie-breaks.
    "Weighted Recency Subtotal",
    "Weighted Duration Subtotal",
    "Weighted Evidence Subtotal",
]

BACKEND_OUTPUT_COLUMNS = [
    "Rank Number",
    "Candidate",
    "Profile URL",
    "Current Company",
    "Current Title",
    "PHP Score (/20)",
    "Python Score (/20)",
    "Laravel Score (/12)",
    "AWS Score (/8)",
    "Final Score (/60)",
    "PHP Unverified",
    "Python Unverified",
    "Backend Relevance Unverified",
    "Seniority Unverified",
    "Date-Quality Warning",
    "Strongest Evidence",
    "Missing or Unclear Information",
    "Score Rationale",
]

BACKEND_CATEGORY_SCORES = OrderedDict(
    [
        ("PHP Score (/20)", 20),
        ("Python Score (/20)", 20),
        ("Laravel Score (/12)", 12),
        ("AWS Score (/8)", 8),
    ]
)

BACKEND_WARNING_ENUMS = {
    "PHP Unverified": ["Yes", "No"],
    "Python Unverified": ["Yes", "No"],
    "Backend Relevance Unverified": ["Yes", "No"],
    "Seniority Unverified": ["Yes", "No"],
    "Date-Quality Warning": ["Yes", "No"],
}


AI_ENGINEER_TRJ_GRADING_COLUMNS = [
    "Current Company",
    "Current Title",
    "AI / LLM / Agentic Systems Score (/30)",
    "Python Score (/25)",
    "API & System Integration Score (/20)",
    "Workflow Automation Score (/15)",
    "TypeScript / Node.js Score (/5)",
    "Ownership / Production Maturity Score (/5)",
    "Final Score (/100)",
    "AI / LLM / Agentic Systems Unverified",
    "Python Unverified",
    "API & System Integration Unverified",
    "Seniority Unverified",
    "Date-Quality Warning",
    "Evidence Confidence",
    "Strongest Evidence 1",
    "Strongest Evidence 2",
    "Strongest Evidence 3",
    "Missing or Unclear Information",
    "Score Rationale",
]

AI_ENGINEER_TRJ_OUTPUT_COLUMNS = [
    "Rank Number",
    "Candidate",
    "Profile URL",
    *AI_ENGINEER_TRJ_GRADING_COLUMNS,
]

AI_ENGINEER_TRJ_CATEGORY_SCORES = OrderedDict(
    [
        ("AI / LLM / Agentic Systems Score (/30)", 30),
        ("Python Score (/25)", 25),
        ("API & System Integration Score (/20)", 20),
        ("Workflow Automation Score (/15)", 15),
        ("TypeScript / Node.js Score (/5)", 5),
        ("Ownership / Production Maturity Score (/5)", 5),
    ]
)

AI_ENGINEER_TRJ_WARNING_ENUMS = {
    "AI / LLM / Agentic Systems Unverified": ["Yes", "No"],
    "Python Unverified": ["Yes", "No"],
    "API & System Integration Unverified": ["Yes", "No"],
    "Seniority Unverified": ["Yes", "No"],
    "Date-Quality Warning": ["Yes", "No"],
}


ROLE_PROFILES = {
    "design": RoleProfile(
        key="design",
        label="Design / Product UX",
        role_name="senior Product/UX Designer",
        grading_columns=DESIGN_GRADING_COLUMNS,
        category_scores=DESIGN_CATEGORY_SCORES,
        allowed_scores={},
        total_column="Total Score",
        total_max=60,
        outcome_column="Ranking",
        outcome_bands=[
            (45, 60, "Strong relevance"),
            (32, 44, "Good relevance"),
            (20, 31, "Limited relevance"),
            (0, 19, "Low relevance"),
        ],
        evidence_confidence_values=["High", "Medium", "Low"],
        system_prompt=(
            "You are a strict candidate evaluator for senior Product/UX Designer profiles. "
            "Score only from the supplied candidate fields and the supplied rubric. "
            "Use all experience entries, not only the first three. "
            "Use whole-number category scores and obey the supplied category maxima. "
            "Total Score must equal the sum of category scores and must not exceed 60. "
            "Ranking bands are: 45-60 Strong relevance, 32-44 Good relevance, "
            "20-31 Limited relevance, 0-19 Low relevance. "
            "Strongest Evidence must contain no more than three material evidence points. "
            "Score Rationale must be 50 to 75 words and no longer than 75 words."
        ),
        instructions=[
            "Use every experience entry supplied in candidate.experiences for scoring.",
            "Treat every experience index as a separate role, including multiple roles at the same company.",
            "Ignore skills, projects, courses, certifications, images, logos, followers, connections, IDs other than LinkedIn Profile ID, extra URLs, and scraper metadata.",
            "Return only fields required by the JSON schema.",
        ],
        internal_role_flag_name="relevant_design_role",
        internal_role_evidence_name="design_evidence_extracted",
    ),
    "qa": RoleProfile(
        key="qa",
        label="QA Automation Engineer",
        role_name="Senior QA Automation Engineer",
        grading_columns=QA_GRADING_COLUMNS,
        category_scores=QA_CATEGORY_SCORES,
        allowed_scores=QA_ALLOWED_SCORES,
        total_column="Total Score",
        total_max=100,
        outcome_column="Decision",
        outcome_bands=[
            (70, 100, "Shortlist"),
            (55, 69, "Hold"),
            (0, 54, "Reject"),
        ],
        evidence_confidence_values=["High", "Medium", "Low"],
        system_prompt=(
            "You are a strict candidate evaluator for Senior QA Automation Engineer profiles. "
            "Score only explicit evidence from the supplied professional experience entries and supplied rubric. "
            "Use all available experience entries supplied in candidate.experiences. "
            "Do not use headline, about, skills, education, certifications, projects, courses, recommendations, posts, or external assumptions for QA scoring. "
            "Use only allowed discrete category scores from the schema. "
            "Total Score must equal the sum of category scores and must not exceed 100. "
            "Decision bands are: 70-100 Shortlist, 55-69 Hold, 0-54 Reject. "
            "Strongest Evidence must contain no more than three material evidence points. "
            "Score Rationale must be 50 to 75 words and no longer than 75 words."
        ),
        instructions=[
            "Use every professional experience entry supplied in candidate.experiences for QA scoring.",
            "Count an experience only if title or description shows QA, test automation, software testing, SDET, or test engineering work.",
            "Ignore headline, about, skills, education, certifications, projects, courses, recommendations, posts, currentPosition, and external information for scoring.",
            "Score Python and Java separately; do not infer one from the other.",
            "Return only fields required by the JSON schema.",
        ],
        internal_role_flag_name="counted_for_qa_scoring",
        internal_role_evidence_name="qa_evidence_extracted",
    ),
    "backend": RoleProfile(
        key="backend",
        label="Backend Engineer",
        role_name="Senior Backend Engineer",
        grading_columns=BACKEND_GRADING_COLUMNS,
        category_scores=BACKEND_CATEGORY_SCORES,
        allowed_scores={},
        total_column="Final Score (/60)",
        total_max=60,
        outcome_column="Rank Number",
        outcome_bands=[],
        evidence_confidence_values=["High", "Medium", "Low"],
        system_prompt=(
            "You are a strict LinkedIn evidence evaluator for Senior Backend Engineer profiles. "
            "Score PHP, Python, Laravel, and AWS independently using only the supplied rubric and permitted candidate fields. "
            "Use all available experience entries. Do not infer PHP from Laravel, and do not infer Python from Django, Flask, or FastAPI. "
            "Use the strongest evidence source without stacking evidence points. Apply recency and duration independently per technology, "
            "including the rubric's Tier A, B, and C duration caps and non-overlapping duration rules. "
            "Technology scores and Final Score may contain one decimal place. Final Score must equal the four technology scores and must not exceed 60. "
            "Warnings do not change the score. Use 'Unverified' neutrally when evidence is absent. "
            "Return no more than three strongest evidence points in the single Strongest Evidence field, separated by ' | '. "
            "Score Rationale must contain 50 to 75 words."
        ),
        instructions=[
            "Use Headline, About, experience title, description, dates, duration, and experience-level skills only as permitted by the rubric.",
            "Do not use global skills, education, certifications, projects, courses, recommendations, followers, connections, or external information.",
            "Treat duplicate experience records as one record for evidence and duration; otherwise evaluate every experience entry.",
            "Current Company and Current Title are identification fields only and do not earn points.",
            "For year-only dates, use 6 months when start and end year match; otherwise use 12 x (end year - start year - 1) + 8 months.",
            "Calculate each hidden weighted subtotal by multiplying the PHP, Python, Laravel, and AWS raw component by 2.0, 2.0, 1.2, and 0.8 respectively, then summing. Return the recency, duration, and evidence subtotals for ranking tie-breaks only; do not add them to Final Score again.",
            "Return only fields required by the JSON schema.",
        ],
        internal_role_flag_name="relevant_backend_role",
        internal_role_evidence_name="backend_evidence_extracted",
        export_columns=BACKEND_OUTPUT_COLUMNS,
        numeric_scores=True,
        ranked=True,
        column_enums=BACKEND_WARNING_ENUMS,
        ranking_tiebreaker_columns=[
            "PHP Score (/20)",
            "Python Score (/20)",
            "Laravel Score (/12)",
            "AWS Score (/8)",
            "Weighted Recency Subtotal",
            "Weighted Duration Subtotal",
            "Weighted Evidence Subtotal",
        ],
        strongest_evidence_columns=["Strongest Evidence"],
        rationale_min_words=50,
    ),
    "ai_engineer_trj": RoleProfile(
        key="ai_engineer_trj",
        label="AI Engineer TRJ",
        role_name="Senior AI & Automation Engineer",
        grading_columns=AI_ENGINEER_TRJ_GRADING_COLUMNS,
        category_scores=AI_ENGINEER_TRJ_CATEGORY_SCORES,
        allowed_scores={},
        total_column="Final Score (/100)",
        total_max=100,
        outcome_column="Rank Number",
        outcome_bands=[],
        evidence_confidence_values=["High", "Medium", "Low"],
        system_prompt=(
            "You are a strict LinkedIn evidence evaluator for Senior AI & Automation Engineer profiles. "
            "Score AI/LLM/agentic systems, Python, API/system integration, workflow automation, TypeScript/Node.js, "
            "and ownership/production maturity independently using only the supplied rubric and permitted candidate fields. "
            "For each capability, calculate raw Evidence, Recency, and Evidenced Duration components, then apply the rubric multiplier. "
            "Use the strongest evidence source without stacking evidence points, use only non-overlapping supported duration, and do not infer "
            "one capability from another. Scores and Final Score may contain one decimal place. Final Score must equal the six capability scores "
            "and must not exceed 100. Warnings do not change the score. Describe missing evidence neutrally as unverified. "
            "Score Rationale must contain 50 to 75 words."
        ),
        instructions=[
            "Use only Headline, About, experience title, experience description, experience-level skills or technologies, experience dates or duration, and Projects for scoring.",
            "Use name, profile URL, current company or title, location, and employment type only for identification; they earn no points.",
            "Do not score global skills, top skills, education, certifications, courses, recommendations, endorsements, followers, connections, languages, volunteering, company reputation, industry, recruiter-search match, LinkedIn-inferred skills, or outside knowledge.",
            "Treat duplicate experience records as one record for evidence and duration; otherwise evaluate every experience entry.",
            "Headline, About, and Projects receive zero Recency and zero Duration points.",
            "Using ChatGPT, Copilot, or Claude as a productivity tool is not AI/LLM capability evidence. POCs and prototypes do not by themselves prove production maturity.",
            "Workflow Automation means identifiable business or operational workflows. Do not count QA/test automation, CI/CD, infrastructure automation, browser testing, or industrial/manufacturing automation.",
            "Plain JavaScript and frontend-only work do not by themselves qualify for TypeScript / Node.js scoring.",
            "Return only fields required by the JSON schema. Rank Number is calculated after all candidates are scored and must not be returned.",
        ],
        internal_role_flag_name="relevant_ai_automation_role",
        internal_role_evidence_name="ai_automation_evidence_extracted",
        export_columns=AI_ENGINEER_TRJ_OUTPUT_COLUMNS,
        numeric_scores=True,
        ranked=True,
        column_enums=AI_ENGINEER_TRJ_WARNING_ENUMS,
        ranking_tiebreaker_columns=[
            "AI / LLM / Agentic Systems Score (/30)",
            "Python Score (/25)",
            "API & System Integration Score (/20)",
            "Workflow Automation Score (/15)",
            "Ownership / Production Maturity Score (/5)",
            "TypeScript / Node.js Score (/5)",
        ],
        strongest_evidence_columns=[
            "Strongest Evidence 1",
            "Strongest Evidence 2",
            "Strongest Evidence 3",
        ],
        rationale_min_words=50,
        evidence_sources=["Location", "Headline", "About", "All experiences", "Projects"],
        skip_if_no_evidence=False,
    ),
}


DEFAULT_ROLE_KEY = "design"
CUSTOM_ROLE_KEY = "custom"

CUSTOM_META_COLUMNS = [
    "Evidence Confidence",
    "Strongest Evidence 1",
    "Strongest Evidence 2",
    "Strongest Evidence 3",
    "Missing or Unclear Information",
    "Score Rationale",
]

DEFAULT_CUSTOM_ROLE_CONFIG: dict[str, Any] = {
    "role_name": "Custom Role",
    "categories": [
        {"name": "Relevant Experience", "max_score": 20, "allowed_scores": []},
        {"name": "Role-specific Skills", "max_score": 20, "allowed_scores": []},
        {"name": "Ownership and Impact", "max_score": 20, "allowed_scores": []},
    ],
    "outcome_column": "Decision",
    "outcome_bands": [
        {"minimum": 0, "maximum": 29, "label": "Low match"},
        {"minimum": 30, "maximum": 44, "label": "Potential match"},
        {"minimum": 45, "maximum": 60, "label": "Strong match"},
    ],
    "evidence_sources": ["Headline", "About", "All experiences"],
    "require_experience": False,
}


def role_options() -> dict[str, str]:
    return {
        **{profile.label: profile.key for profile in ROLE_PROFILES.values()},
        "Custom Role": CUSTOM_ROLE_KEY,
    }


def get_role_profile(role_key: Optional[str], custom_config: Optional[dict[str, Any]] = None) -> RoleProfile:
    if role_key == CUSTOM_ROLE_KEY:
        return build_custom_role_profile(custom_config or DEFAULT_CUSTOM_ROLE_CONFIG)
    return ROLE_PROFILES.get(role_key or DEFAULT_ROLE_KEY, ROLE_PROFILES[DEFAULT_ROLE_KEY])


def prepare_output_rows(
    rows: list[dict],
    role_or_key: Optional[str | RoleProfile],
    custom_config: Optional[dict[str, Any]] = None,
) -> list[dict]:
    role = role_or_key if isinstance(role_or_key, RoleProfile) else get_role_profile(role_or_key, custom_config)
    prepared = [dict(row) for row in rows]
    if role.ranked:
        tie_columns = role.ranking_tiebreaker_columns or []

        def rank_key(row: dict) -> tuple:
            numeric = [-_number(row.get(role.total_column))]
            numeric.extend(-_number(row.get(column)) for column in tie_columns)
            return (*numeric, str(row.get("Candidate", "")).casefold())

        prepared.sort(key=rank_key)
        for index, row in enumerate(prepared, start=1):
            row[role.outcome_column] = index
    return [{column: row.get(column, "") for column in role.output_columns} for row in prepared]


def validate_custom_role_config(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    role_name = str(config.get("role_name") or "").strip()
    if not role_name:
        errors.append("Role name is required.")
    elif len(role_name) > 100:
        errors.append("Role name must be 100 characters or fewer.")

    categories = config.get("categories") or []
    if not 1 <= len(categories) <= 12:
        errors.append("Add between 1 and 12 scoring categories.")

    category_columns: list[str] = []
    total_max = 0
    for index, category in enumerate(categories, start=1):
        name = str(category.get("name") or "").strip()
        if not name:
            errors.append(f"Category {index} needs a name.")
        column = _custom_score_column(name) if name else ""
        if column and column.casefold() in {item.casefold() for item in category_columns}:
            errors.append(f"Category names must be unique; {name!r} is repeated.")
        if column:
            category_columns.append(column)

        maximum = _whole_number(category.get("max_score"))
        if maximum is None or maximum < 1 or maximum > 100:
            errors.append(f"{name or f'Category {index}'} maximum score must be a whole number from 1 to 100.")
            maximum = 0
        total_max += maximum

        allowed_scores = category.get("allowed_scores") or []
        normalized_allowed: list[int] = []
        for value in allowed_scores:
            score = _whole_number(value)
            if score is None:
                errors.append(f"{name or f'Category {index}'} has a non-whole allowed score: {value!r}.")
                continue
            normalized_allowed.append(score)
            if score < 0 or score > maximum:
                errors.append(f"{name or f'Category {index}'} allowed scores must be between 0 and {maximum}.")
        if len(normalized_allowed) != len(set(normalized_allowed)):
            errors.append(f"{name or f'Category {index}'} allowed scores contain duplicates.")

    if total_max > 500:
        errors.append("The combined maximum score must be 500 or less.")

    outcome_column = str(config.get("outcome_column") or "").strip()
    if not outcome_column:
        errors.append("Outcome column name is required.")
    reserved = {*(column.casefold() for column in SOURCE_COLUMNS), *(column.casefold() for column in CUSTOM_META_COLUMNS), "total score"}
    conflicting_categories = [column for column in category_columns if column.casefold() in reserved]
    if conflicting_categories:
        errors.append(f"Scoring categories conflict with reserved output columns: {', '.join(conflicting_categories)}.")
    if outcome_column and outcome_column.casefold() in reserved:
        errors.append(f"Outcome column {outcome_column!r} conflicts with another output column.")
    if outcome_column and outcome_column.casefold() in {column.casefold() for column in category_columns}:
        errors.append(f"Outcome column {outcome_column!r} conflicts with a scoring category.")

    bands = config.get("outcome_bands") or []
    normalized_bands: list[tuple[int, int, str]] = []
    if not bands:
        errors.append("Add at least one outcome band.")
    for index, band in enumerate(bands, start=1):
        low = _whole_number(band.get("minimum"))
        high = _whole_number(band.get("maximum"))
        label = str(band.get("label") or "").strip()
        if low is None or high is None:
            errors.append(f"Outcome band {index} minimum and maximum must be whole numbers.")
            continue
        if low < 0 or high < low:
            errors.append(f"Outcome band {index} must have 0 <= minimum <= maximum.")
        if not label:
            errors.append(f"Outcome band {index} needs a label.")
        normalized_bands.append((low, high, label))

    if normalized_bands:
        ordered = sorted(normalized_bands, key=lambda item: (item[0], item[1]))
        if ordered[0][0] != 0:
            errors.append("Outcome bands must start at 0.")
        for previous, current in zip(ordered, ordered[1:]):
            if current[0] != previous[1] + 1:
                errors.append("Outcome bands must cover every whole-number score without gaps or overlaps.")
                break
        if ordered[-1][1] != total_max:
            errors.append(f"Outcome bands must end at the combined maximum score of {total_max}.")
        labels = [label.casefold() for _, _, label in ordered if label]
        if len(labels) != len(set(labels)):
            errors.append("Outcome band labels must be unique.")

    evidence_sources = config.get("evidence_sources") or []
    if not evidence_sources:
        errors.append("Select at least one permitted LinkedIn evidence source.")
    supported_sources = set(CUSTOM_EVIDENCE_SOURCES) | LEGACY_EVIDENCE_SOURCE_ALIASES
    unknown_sources = sorted(set(evidence_sources) - supported_sources)
    if unknown_sources:
        errors.append(f"Unknown evidence sources: {', '.join(unknown_sources)}.")
    if config.get("require_experience") and not set(evidence_sources).intersection(EXPERIENCE_EVIDENCE_SOURCES):
        errors.append("When experience is required, select at least one experience evidence source.")
    return list(dict.fromkeys(errors))


def build_custom_role_profile(config: dict[str, Any]) -> RoleProfile:
    errors = validate_custom_role_config(config)
    if errors:
        raise ValueError("Invalid custom role configuration: " + "; ".join(errors))

    category_scores: OrderedDict[str, float] = OrderedDict()
    allowed_scores: dict[str, set[float]] = {}
    for category in config["categories"]:
        column = _custom_score_column(str(category["name"]).strip())
        maximum = int(category["max_score"])
        category_scores[column] = maximum
        values = {int(value) for value in (category.get("allowed_scores") or [])}
        if values:
            allowed_scores[column] = values

    outcome_column = str(config["outcome_column"]).strip()
    bands = sorted(
        [
            (int(band["minimum"]), int(band["maximum"]), str(band["label"]).strip())
            for band in config["outcome_bands"]
        ],
        key=lambda item: (item[0], item[1]),
    )
    role_name = str(config["role_name"]).strip()
    evidence_sources = list(config["evidence_sources"])
    band_text = ", ".join(f"{low}-{high} {label}" for low, high, label in bands)
    source_text = ", ".join(evidence_sources)
    grading_columns = [
        *category_scores,
        "Total Score",
        outcome_column,
        *CUSTOM_META_COLUMNS,
    ]
    return RoleProfile(
        key=CUSTOM_ROLE_KEY,
        label=f"Custom: {role_name}",
        role_name=role_name,
        grading_columns=grading_columns,
        category_scores=category_scores,
        allowed_scores=allowed_scores,
        total_column="Total Score",
        total_max=sum(category_scores.values()),
        outcome_column=outcome_column,
        outcome_bands=bands,
        evidence_confidence_values=["High", "Medium", "Low"],
        system_prompt=(
            f"You are a strict candidate evaluator for {role_name} profiles. "
            "Score only from the supplied rubric and the explicitly permitted candidate evidence fields. "
            f"Permitted evidence sources are: {source_text}. Ignore every other candidate field for scoring. "
            "Use whole-number category scores and do not infer unstated skills, responsibilities, seniority, or results. "
            f"Total Score must equal the category score sum and must not exceed {sum(category_scores.values())}. "
            f"{outcome_column} bands are: {band_text}. "
            "Return at most three strongest evidence points and keep Score Rationale to 75 words or fewer."
        ),
        instructions=[
            "Apply the uploaded rubric exactly and score every configured category independently.",
            f"Use only these evidence sources: {source_text}.",
            "Use every supplied experience entry when experience is a permitted source.",
            "Use zero when required evidence is absent; do not invent or infer missing facts.",
            "Return only fields required by the JSON schema.",
        ],
        internal_role_flag_name="relevant_custom_role",
        internal_role_evidence_name="custom_role_evidence_extracted",
        rationale_min_words=0,
        evidence_sources=evidence_sources,
        require_experience=bool(config.get("require_experience")),
    )


def _custom_score_column(name: str) -> str:
    return name if name.casefold().endswith("score") else f"{name} — Score"


def _whole_number(value: Any) -> Optional[int]:
    try:
        if isinstance(value, bool) or value is None or str(value).strip() == "":
            return None
        number = float(value)
        return int(number) if number.is_integer() else None
    except (TypeError, ValueError):
        return None


def _number(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
