from __future__ import annotations

import json

from candidate_evaluator.extractor import (
    candidate_input_issue,
    candidate_input_issues,
    load_profiles_from_text,
    normalize_candidate,
    normalize_candidates,
)
from candidate_evaluator.roles import get_role_profile


def _sde3_issue(candidate: dict) -> str:
    role = get_role_profile("sde3")
    return candidate_input_issue(
        candidate,
        role.key,
        role.evidence_sources,
        role.require_experience,
        role.skip_if_no_evidence,
    )


def test_unipile_v1_full_profile_maps_to_existing_internal_contract() -> None:
    profile = {
        "object": "UserProfile",
        "provider": "LINKEDIN",
        "provider_id": "ACo-v1",
        "public_identifier": "ada-lovelace",
        "public_profile_url": "https://www.linkedin.com/in/ada-lovelace/",
        "first_name": "Ada",
        "last_name": "Lovelace",
        "headline": "Backend and Agentic AI Engineer",
        "summary": "Builds production AI agents.",
        "location": "London, United Kingdom",
        "websites": ["https://ada.example"],
        "is_open_to_work": True,
        "is_hiring": False,
        "skills": [{"name": "Python"}, {"name": "FastAPI"}],
        "work_experience": [
            {
                "company": "Analytical Engines",
                "position": "Senior Engineer",
                "description": "Shipped an agent platform with FastAPI.",
                "location": "London",
                "status": "FULL_TIME",
                "start": "4/1/2022",
                "skills": ["FastAPI", {"name": "LangGraph"}, {"text": "Python"}],
            }
        ],
        "education": [
            {
                "school": "University of London",
                "degree": "BSc",
                "field_of_study": "Mathematics",
                "start": "1/1/2016",
                "end": "1/1/2020",
            }
        ],
        "projects": [
            {
                "name": "Support Agent",
                "description": "Deployed a customer-support agent.",
                "skills": ["RAG", {"text": "FastAPI"}],
            }
        ],
    }

    candidate = normalize_candidate(profile, 0)

    assert candidate["source_format"] == "unipile"
    assert candidate["linkedin_profile_id"] == "ada-lovelace"
    assert candidate["linkedin_url"] == "https://www.linkedin.com/in/ada-lovelace/"
    assert candidate["candidate_name"] == "Ada Lovelace"
    assert candidate["headline"] == "Backend and Agentic AI Engineer"
    assert candidate["about"] == "Builds production AI agents."
    assert candidate["skills"] == ["Python", "FastAPI"]
    assert candidate["website"] == "https://ada.example"
    assert candidate["open_to_work"] is True
    assert candidate["open_to_work_present"] is True
    assert candidate["hiring"] is False
    assert candidate["hiring_present"] is True
    assert candidate["experiences"] == [
        {
            "index": 0,
            "company_name": "Analytical Engines",
            "position_or_title": "Senior Engineer",
            "description": "Shipped an agent platform with FastAPI.",
            "experience_location": "London",
            "employment_type": "FULL_TIME",
            "workplace_type": "",
            "start_date": "2022-04-01",
            "end_date": "",
            "is_current": True,
            "duration": "",
            "experience_skills": ["FastAPI", "LangGraph", "Python"],
        }
    ]
    assert candidate["projects"] == [
        {
            "name": "Support Agent",
            "description": "Deployed a customer-support agent.",
            "technologies": ["RAG", "FastAPI"],
        }
    ]
    assert candidate["education"] == [
        "University of London | BSc | Mathematics | 2016-01-01 - 2020-01-01"
    ]
    assert _sde3_issue(candidate) == ""


def test_unipile_v2_full_profile_maps_nested_linkedin_specifics() -> None:
    profile = {
        "object": "UserProfile",
        "id": "v2-internal-id",
        "public_identifier": "grace-hopper",
        "display_name": "Grace Hopper",
        "profile_url": "https://www.linkedin.com/in/grace-hopper/",
        "description": "Principal Backend Engineer",
        "bio": "Designs distributed AI systems.",
        "location": "New York, United States",
        "websites": [{"url": "https://grace.example"}],
        "specifics": {
            "is_open_to_work": False,
            "is_hiring": True,
            "skills": [{"name": "Python"}, {"text": "Django"}],
            "experience": [
                {
                    "company": {"id": "company-1", "name": "Compiler Co"},
                    "job_title": "Principal Engineer",
                    "started_on": "2023-02-01",
                    "ended_on": None,
                    "location": "Remote",
                    "description": "Built and deployed an agentic orchestration service.",
                    "employment_type": "FULL_TIME",
                    "workplace_type": "REMOTE",
                    "skills": ["Python", {"text": "Django"}],
                }
            ],
            "education": [
                {
                    "school": {"name": "Yale University"},
                    "degree": "MSc",
                    "fields_of_study": ["Computer Science", "Mathematics"],
                    "started_on": "1930",
                    "ended_on": "1934",
                }
            ],
            "projects": [
                {
                    "name": "Agent Runtime",
                    "description": "Production multi-agent runtime.",
                    "skills": [{"name": "LangGraph"}],
                }
            ],
        },
    }

    candidate = normalize_candidate(profile, 0)

    assert candidate["linkedin_profile_id"] == "grace-hopper"
    assert candidate["candidate_name"] == "Grace Hopper"
    assert candidate["headline"] == "Principal Backend Engineer"
    assert candidate["about"] == "Designs distributed AI systems."
    assert candidate["website"] == "https://grace.example"
    assert candidate["skills"] == ["Python", "Django"]
    experience = candidate["experiences"][0]
    assert experience["company_name"] == "Compiler Co"
    assert experience["position_or_title"] == "Principal Engineer"
    assert experience["start_date"] == "2023-02-01"
    assert experience["end_date"] == ""
    assert experience["is_current"] is True
    assert experience["employment_type"] == "FULL_TIME"
    assert experience["workplace_type"] == "REMOTE"
    assert experience["experience_skills"] == ["Python", "Django"]
    assert candidate["projects"][0]["technologies"] == ["LangGraph"]
    assert candidate["education"] == [
        "Yale University | MSc | Computer Science, Mathematics | 1930 - 1934"
    ]
    assert _sde3_issue(candidate) == ""


def test_unipile_v2_recruiter_search_data_wrapper_and_full_result() -> None:
    payload = {
        "data": [
            {
                "object": "PeopleSearchResult",
                "id": "recruiter-id",
                "candidate_id": "candidate-id",
                "display_name": "Katherine Johnson",
                "public_identifier": "katherine-johnson",
                "profile_url": "https://www.linkedin.com/in/katherine-johnson/",
                "visibility": "full",
                "headline": "Senior Software Engineer",
                "summary": "Builds reliable backend and AI services.",
                "work_experience": [
                    {
                        "company": {"name": "NASA"},
                        "job_title": "Senior Software Engineer",
                        "started_on": "2021-05",
                        "ended_on": "2025-06",
                        "description": "Designed distributed processing systems.",
                        "skills": ["Python"],
                    }
                ],
                "projects": [
                    {"name": "RAG Assistant", "description": "Shipped an internal assistant.", "skills": ["RAG"]}
                ],
            }
        ],
        "next_cursor": "next",
    }

    candidates = normalize_candidates(load_profiles_from_text(json.dumps(payload)))

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["candidate_name"] == "Katherine Johnson"
    assert candidate["about"] == "Builds reliable backend and AI services."
    assert candidate["experiences"][0]["company_name"] == "NASA"
    assert candidate["experiences"][0]["position_or_title"] == "Senior Software Engineer"
    assert candidate["experiences"][0]["is_current"] is False
    assert _sde3_issue(candidate) == ""


def test_unipile_v1_current_positions_are_current_experiences() -> None:
    candidate = normalize_candidate(
        {
            "type": "PEOPLE",
            "id": "recruiter-internal",
            "name": "Current Candidate",
            "public_identifier": "current-candidate",
            "headline": "AI Engineer",
            "current_positions": [
                {
                    "company": "Current Co",
                    "role": "AI Engineer",
                    "start": {"year": 2024, "month": 6},
                    "description": "Builds agent workflows.",
                }
            ],
        },
        0,
    )

    assert candidate["linkedin_url"] == "https://www.linkedin.com/in/current-candidate/"
    assert candidate["experiences"][0]["start_date"] == "2024-06"
    assert candidate["experiences"][0]["is_current"] is True
    assert _sde3_issue(candidate) == ""


def test_partial_recruiter_result_is_rejected_before_ai_call() -> None:
    candidate = normalize_candidate(
        {
            "object": "PeopleSearchResult",
            "id": "partial-id",
            "visibility": "partial",
            "headline": "Software Engineer",
            "work_experience": [
                {"company": {"name": "Example"}, "job_title": "Engineer", "description": "Backend work."}
            ],
        },
        0,
    )

    issue = _sde3_issue(candidate)

    assert "partial profile" in issue
    assert "candidate name is empty" in issue
    assert "LinkedIn profile URL is empty" in issue


def test_required_throttled_sections_are_not_treated_as_no_evidence() -> None:
    candidate = normalize_candidate(
        {
            "object": "UserProfile",
            "public_identifier": "throttled-person",
            "display_name": "Throttled Person",
            "profile_url": "https://www.linkedin.com/in/throttled-person/",
            "description": "Backend Engineer",
            "specifics": {
                "throttled_sections": ["linkedin_work_experience", "linkedin_project", "linkedin_education"]
            },
        },
        0,
    )

    issue = _sde3_issue(candidate)

    assert "experience" in issue
    assert "projects" in issue
    assert "education" not in issue
    summaries = candidate_input_issues(
        [candidate], evidence_sources=get_role_profile("sde3").evidence_sources, skip_if_no_evidence=False
    )
    assert any("partial or have required throttled sections" in item for item in summaries)


def test_irrelevant_throttled_section_does_not_block_sde3() -> None:
    candidate = normalize_candidate(
        {
            "object": "UserProfile",
            "public_identifier": "education-throttled",
            "display_name": "Education Throttled",
            "profile_url": "https://www.linkedin.com/in/education-throttled/",
            "description": "Backend Engineer",
            "specifics": {"throttled_sections": ["linkedin_education"]},
        },
        0,
    )

    assert _sde3_issue(candidate) == ""


def test_single_unipile_profile_is_not_mistaken_for_its_experience_list() -> None:
    profile = {
        "object": "UserProfile",
        "public_identifier": "single-person",
        "display_name": "Single Person",
        "profile_url": "https://www.linkedin.com/in/single-person/",
        "description": "Engineer",
        "specifics": {
            "experience": [
                {"company": {"name": "Example"}, "job_title": "Engineer", "started_on": "2024"}
            ]
        },
    }

    loaded = load_profiles_from_text(json.dumps(profile))

    assert loaded == [profile]
    assert normalize_candidates(loaded)[0]["candidate_name"] == "Single Person"


def test_mixed_search_results_ignore_known_non_people_records() -> None:
    payload = {
        "items": [
            {"type": "POST", "id": "post-1", "headline": "Not a person"},
            {"type": "COMPANY", "id": "company-1", "name": "Not a candidate"},
            {
                "type": "PEOPLE",
                "id": "person-1",
                "name": "Real Candidate",
                "public_identifier": "real-candidate",
                "headline": "Engineer",
            },
        ]
    }

    profiles = load_profiles_from_text(json.dumps(payload))

    assert [profile["id"] for profile in profiles] == ["person-1"]


def test_existing_apify_format_remains_unchanged() -> None:
    candidate = normalize_candidate(
        {
            "publicIdentifier": "apify-person",
            "linkedinUrl": "https://www.linkedin.com/in/apify-person/",
            "firstName": "Apify",
            "lastName": "Person",
            "headline": "Backend Engineer",
            "about": "Builds APIs.",
            "location": {"parsed": {"city": "Bengaluru", "countryFull": "India"}},
            "experience": [
                {
                    "companyName": "Apify Co",
                    "title": "Engineer",
                    "startDate": {"month": "Oct", "year": 2023},
                    "endDate": {"text": "Present"},
                    "skills": ["Python"],
                }
            ],
        },
        0,
    )

    assert candidate["source_format"] == "apify"
    assert candidate["candidate_name"] == "Apify Person"
    assert candidate["location"] == "Bengaluru, India"
    assert candidate["experiences"][0]["company_name"] == "Apify Co"
    assert candidate["experiences"][0]["start_date"] == "Oct 2023"
    assert candidate["experiences"][0]["end_date"] == "Present"
    assert candidate["experiences"][0]["is_current"] is True


def test_mixed_apify_and_unipile_records_are_normalized_independently() -> None:
    profiles = [
        {
            "publicIdentifier": "apify",
            "linkedinUrl": "https://www.linkedin.com/in/apify/",
            "fullName": "Apify Candidate",
            "headline": "Engineer",
        },
        {
            "object": "UserProfile",
            "public_identifier": "unipile",
            "display_name": "Unipile Candidate",
            "profile_url": "https://www.linkedin.com/in/unipile/",
            "description": "Engineer",
        },
    ]

    candidates = normalize_candidates(load_profiles_from_text(json.dumps(profiles)))

    assert [candidate["source_format"] for candidate in candidates] == ["apify", "unipile"]
    assert [candidate["candidate_name"] for candidate in candidates] == [
        "Apify Candidate",
        "Unipile Candidate",
    ]


def test_unipile_null_optional_fields_do_not_crash_normalization() -> None:
    candidate = normalize_candidate(
        {
            "object": "UserProfile",
            "id": "null-profile",
            "display_name": "Null Profile",
            "profile_url": "https://www.linkedin.com/in/null-profile/",
            "description": None,
            "bio": None,
            "websites": None,
            "specifics": {
                "experience": None,
                "education": None,
                "projects": None,
                "skills": None,
            },
        },
        0,
    )

    assert candidate["candidate_name"] == "Null Profile"
    assert candidate["headline"] == ""
    assert candidate["about"] == ""
    assert candidate["experiences"] == []
    assert candidate["projects"] == []
    assert candidate["skills"] == []

