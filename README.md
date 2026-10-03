# Candidate Evaluator

A local Streamlit app for evaluating Apify LinkedIn profile JSON files against a rubric with the OpenAI API.

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
- **Custom Role** creates a validated scoring contract from a role name, scoring categories, category maxima, optional discrete scores, outcome bands, and permitted LinkedIn evidence sources.

Backend Engineer automatically loads `rubrics/backend_engineer.md`. You may still upload a replacement rubric, but it must preserve the Backend role's scoring categories and output contract.

Each saved run stores its role. Custom runs also store the complete custom configuration, so resume/retry/export use the same schema that the run started with.

## Custom Roles

Select **Custom Role**, upload the role's rubric, and complete the setup table. A custom run cannot start until:

- the role has a name and 1-12 unique scoring categories
- each category has a whole-number maximum from 1 to 100
- optional allowed scores are whole numbers inside that category's range
- outcome bands cover every score from 0 through the combined maximum without gaps or overlaps
- at least one permitted LinkedIn evidence source is selected

The app builds the OpenAI JSON schema and export columns from that configuration. It validates every response again before saving it: category values, allowed discrete scores, total-score arithmetic, outcome band, required columns, evidence count, and rationale length. Profiles missing identity or all selected evidence are skipped individually without stopping the run or making an OpenAI call.

Custom roles can independently permit location, headline, About, experiences 0-4, all experiences, current company, role titles, durations, global skills, experience-level skills, education, website, open-to-work, hiring, and services signals. Only the selected evidence is included in the OpenAI candidate payload.

## Safety

The app does not hardcode or save the OpenAI API key. Evaluation cannot start unless both are true:

- an API key is pasted into the password field
- `I approve paid OpenAI API calls for this run` is checked

The preview flow makes no OpenAI API calls.

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
