# Unipile import migration for ZEISS VisioGen

The local importer now translates Unipile profiles into the same candidate structure used by Apify. Select the existing **ZEISS VisioGen: Account Executive - US Sales / Key Account Manager** role and upload the new JSON through the existing input. No new credentials or live Unipile calls are needed for file imports.

## Required changes implemented

| Unipile input | Existing evaluator field / behavior |
| --- | --- |
| `public_identifier` | LinkedIn Profile ID; public profile URL constructed when an explicit URL is absent |
| `provider_id` | ID fallback only; never used to construct a public profile URL |
| `public_profile_url` | LinkedIn URL, when supplied |
| `first_name`, `last_name` | Candidate Name |
| `headline` | Headline |
| `summary` | About |
| `work_experience` | All experience entries, preserving input order |
| `company`, `position` (or `role`), `description` | Company, role title, role evidence |
| `employment_type`, `duration` | Preserved when supplied; never invented |
| `start`, `end` | Normalized dates, retaining partial precision |
| `education[].school`, `degree`, `field_of_study`, `start`, `end` | Education preview / source export |
| `skills`, experience `skills`, `websites`, `projects`, `location` | Existing optional evidence fields |
| `work_experience_total_count`, `throttled_sections` | Import warnings shown before evaluation |

The loader accepts one profile object, a profile array, and named wrappers (`items`, `profiles`, `data`, `results`), including nested object wrappers. It handles a UTF-8 BOM. It rejects malformed candidate arrays and recognized API error roots rather than interpreting section arrays as candidates.

Date strings such as `2/1/2024` become `2024-02-01`. Year/month objects retain their available precision. An explicit null end with a supplied start is treated as a current role; a missing end key or two missing dates does not establish a current role. Contradictory dates are retained for the existing date-quality evaluation. Durations are not calculated by the importer.

Missing names and missing profile URLs follow the existing skip checks. A public identifier alone is not substituted for a person's name. Internal identifiers alone cannot provide a public URL. `is_open_profile` is not mapped to open-to-work intent.

## Scoring behavior

The ZEISS rubric, component weights, recency rules, calculated totals, ranking, and export columns remain unchanged. The model receives identity, headline, About, and permitted experience fields. Education, global skills, role skills, images, followers, and import metadata do not enter this role's scoring payload. Existing duplicate-experience merging still applies.

Tests compare equivalent Apify and Unipile records and require identical ZEISS scoring payloads. Integration coverage also checks the evaluation and calculated output with a simulated model response; this makes no paid model calls and does not establish real-world score accuracy.

## Export requirements to check next

Unipile's [profile guide](https://developer.unipile.com/docs/retrieving-users) documents the full-profile fields. Its [profile API reference](https://developer.unipile.com/reference/userscontroller_getprofilebyidentifier) describes section selection and throttled sections. Request the full `experience` section and the summary needed for this rubric; a preview can omit older evidence. The guide demonstrates `linkedin_sections=*`, while the API reference recommends selecting only needed sections for repeated requests.

The [search API reference](https://developer.unipile.com/reference/linkedincontroller_search) documents cursor pagination. A search result export can contain less evidence than a retrieved full profile. Export every intended page and retrieve full profiles where needed before uploading. The importer does not fetch additional pages or enrich records.

Completeness warnings are advisory: partial records can still be evaluated under the existing rubric. Counts detect known truncation, but absence of a count or warning does not prove completeness. Export-specific wrappers, grouped experiences, or renamed fields outside the documented profile structure need checking against the actual JSON.

When the new JSON is supplied, check candidate count, identity, profile links, work-history count and order, dates, descriptions, and warnings in the extraction preview before approving any paid evaluation.

## Automated verification

Run the full suite from the repository root with `python -m pytest -q`. On Windows installations with restricted temporary folders, set `TEMP` and `TMP` to an existing writable folder in this workspace before running pytest.

The new tests cover supported roots, mixed Apify/Unipile files, equivalent scoring payloads, null and partial dates, contradictory dates, missing identity, internal identifiers, Unicode names, malformed optional sections, sparse evidence, throttled/truncated data, source immutability, preview output, invalid roots, non-LinkedIn providers, and calculated ZEISS output.

Verified locally on 26 October 2026: **163 passed, 2 skipped**, including **53 new Unipile tests**. Both skips depend on an external sample JSON absent from this workspace. The full passing run used `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=tmp/pytest-unipile-final` with local test access for Streamlit's temporary files and loopback connection. No live Unipile or paid scoring requests were made.

The supplied export was subsequently checked: all **400 profiles** imported, with **0 import failures**, **0 pre-evaluation skips**, and **0 duplicate IDs**. One empty experience entry was ignored. An unresolved date-handling limitation affects **437 roles across 367 profiles**: these roles have a start date but omit the end key, which this adapter treats as not current. Review or correct that interpretation before relying on recency and duration scoring. Candidate data and per-profile audit reports are excluded from the source commit.
