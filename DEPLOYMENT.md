# Deploying Candidate Evaluator To Streamlit Cloud

This app is a Streamlit app. It can run on Railway or Streamlit Community Cloud.

## Railway

1. Deploy this repository using the included Dockerfile.
2. Add a persistent volume mounted at `/data`.
3. Set `CANDIDATE_DATA_DIR=/data` and an `APP_PASSWORD` in service variables.
4. Generate a public domain after the service is healthy.

The app requires a password on Railway and stops before loading candidate data
when the password is not configured. Each browser session must sign in. This is
a single-team app: signed-in users share runs and results.
The volume stores new runs and exports across deployments. Existing runs on your
Mac are not uploaded with the application. Download exports as a separate backup.

## Before You Deploy

- Do not upload `.venv/`, `work/`, `outputs/`, or local result files to GitHub.
- Do not hardcode OpenAI or DeepSeek API keys. The app asks for the selected provider's key in the UI.
- Uploaded candidate JSON files and rubrics should be uploaded through the deployed app UI.

## GitHub Files Needed

Upload these files and folders:

- `app.py`
- `requirements.txt`
- `.streamlit/config.toml`
- `candidate_evaluator/`
- `README.md`
- `DEPLOYMENT.md`

Do not upload:

- `.venv/`
- `work/`
- `outputs/`
- `__pycache__/`
- `.pytest_cache/`

## Streamlit Cloud Steps

1. Go to `https://share.streamlit.io`.
2. Sign in with GitHub.
3. Click **Create app** or **New app**.
4. Choose the GitHub repo that contains this project.
5. Choose the branch, usually `main`.
6. Set the main file path to `app.py`.
7. Click **Deploy**.

## After Deploying

1. Open the deployed app URL.
2. Upload the LinkedIn JSON file.
3. Upload the rubric Markdown file.
4. Choose the evaluation role.
5. Choose OpenAI or DeepSeek, select its model, and paste that provider's API key.
6. Preview the first five candidates.
7. Approve API calls.
8. Start evaluation.
9. Download CSV/Excel when complete.

## Important Cloud Note

Streamlit Cloud storage is not meant to be permanent. Always download CSV/Excel outputs after a run.
