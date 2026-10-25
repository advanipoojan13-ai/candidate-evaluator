# Candidate Evaluator

A local Streamlit app for evaluating Apify LinkedIn profile JSON files against a rubric with OpenAI or DeepSeek.

## Run

```bash
.venv/bin/streamlit run app.py
```

The app opens with the sample JSON and rubric paths prefilled when those files are available:

- `/Users/sehermehta/Documents/Documents - Seher’s MacBook Air/Codex/candidate-evaluator/sample.json`
- `/Users/sehermehta/Documents/Documents - Seher’s MacBook Air/Codex/candidate-evaluator/rubric.md`

You can also upload a different LinkedIn JSON file and rubric.

Use **Evaluation role** to choose the scoring mode:

- **Design / Product UX** keeps the original 60-point design evaluator.
- **QA Automation Engineer** uses the 100-point QA automation rubric and QA-specific output columns.
- **Backend Engineer** uses the bundled 60-point PHP, Python, Laravel, and AWS rubric, including decimal scores, evidence warnings, and deterministic rank numbers.
- **AI Engineer TRJ** uses the bundled 100-point AI and automation rubric, including capability-specific evidence, recency and duration scoring, evidence warnings, and deterministic rank numbers.
- **Head Sales** uses a user-uploaded rubric and a fixed 60-point component-scoring contract. The model returns Evidence, Impact, and Duration points; Python calculates weighted capability scores, the final score, and deterministic rank numbers.
- **SDE3** uses the bundled 62-point Agentic AI Technical Lead rubric. Python prepares the date and duration inputs, the model applies the rubric, Python validates and calculates the scores, and a separate request explains those fixed scores.
- **Custom Role** creates a validated scoring contract from a role name, scoring categories, category maxima, optional discrete scores, outcome bands, and permitted LinkedIn evidence sources.

Backend Engineer automatically loads `rubrics/backend_engineer.md`, AI Engineer TRJ automatically loads `rubrics/ai_engineer_trj.md`, and SDE3 automatically loads `rubrics/sde3.md`. You may still upload a replacement rubric, but it must preserve the selected role's scoring categories and output contract.

Head Sales does not load a bundled rubric. Select the role and upload a compatible Markdown rubric for every new run.

Each saved run stores its role. Custom runs also store the complete custom configuration, so resume/retry/export use the same schema that the run started with.

## Custom Roles

Select **Custom Role**, upload the role's rubric, and complete the setup table. A custom run cannot start until:

- the role has a name and 1-12 unique scoring categories
- each category has a whole-number maximum from 1 to 100
- optional allowed scores are whole numbers inside that category's range
- outcome bands cover every score from 0 through the combined maximum without gaps or overlaps
- at least one permitted LinkedIn evidence source is selected

The app builds the JSON schema and export columns from that configuration. It validates every response again before saving it: category values, allowed discrete scores, total-score arithmetic, outcome band, required columns, evidence count, and rationale length. Profiles missing identity or all selected evidence are skipped individually without stopping the run or making a paid API call.

Custom roles can independently permit location, headline, About, projects, experiences 0-4, all experiences, current company, role titles, durations, global skills, experience-level skills, education, website, open-to-work, hiring, and services signals. Only the selected evidence is included in the provider request.

## AI Providers

Use **AI provider** to choose OpenAI or DeepSeek. The model menu changes with the provider.

- OpenAI keeps the existing strict Chat Completions JSON-schema flow.
- DeepSeek uses `https://api.deepseek.com` and its Responses API structured-output flow.
- DeepSeek Flash is the default DeepSeek model; DeepSeek V4 Pro is also available.
- DeepSeek reasoning defaults to **Off (lowest cost)** and can be changed to Low, High, or Maximum.

Each run stores its provider, model, and reasoning setting so resume and retry use the original configuration. API keys are never saved; paste the matching provider key again when resuming a run.

## SDE3 evaluation order

1. Merge duplicate experience records and retain only permitted evidence. Calculate elapsed role months, recency inputs, and date-quality flags in Python. Year-only and written-duration estimates remain marked as estimates; a missing end date does not imply current employment.
2. Request the 12 Evidence, Recency, and Evidenced Duration judgments, with short numeric keys first and no long explanation. Capability-specific duration still requires rubric judgment: full role tenure is not automatic evidence of sustained capability use, and overlapping periods and source caps must be respected.
3. Validate every component as an explicit JSON integer in range, then calculate weighted capability scores and the final score in Python. Missing decisions never become zero. Keep independently valid batch records; give each missing or invalid candidate one individual recovery request.
4. Send validated scores and their permitted evidence to a separate explanation request. Each candidate's complete explanation is limited to **150 total words across all four capabilities and the overall conclusion**, not 150 per capability. The application also caps normalized rows, saved-result previews, CSV, and Excel exports without changing numeric scores. Only explanation text is accepted from this response; it cannot overwrite scores. If the provider returns an overlong explanation, fails, or omits a candidate, save valid scores with a clearly labelled calculated summary covering all four capabilities within the same limit. Full provider responses remain available in raw diagnostics.

A successful SDE3 batch normally uses two API calls. Individual score recovery can add one call per affected candidate. Saved raw results include date inputs, stage diagnostics, response/request IDs when provided, completion status, missing/invalid decisions, and usage across all stages. Other roles keep their existing request flow.

## Safety

The app does not hardcode or save provider API keys. Evaluation cannot start unless both are true:

- an API key is pasted into the password field
- the paid API-call approval for the selected provider is checked

The preview flow makes no provider API calls.

## Progress And Outputs

Each run is saved under `work/runs/<run_id>/` after every candidate, including:

- normalized candidate data
- per-candidate status
- successful rows
- failed rows
- raw structured model responses

Exports are saved under `outputs/` and are also available as CSV and Excel downloads in the app.

## Validation

The app validates every model response before saving a completed row:

- category score caps
- total score sum and the selected role's maximum
- ranking/decision band where configured
- fixed output columns
- maximum three strongest evidence fields
- score rationale no longer than 75 words

Invalid responses are marked failed and can be retried from the app.
