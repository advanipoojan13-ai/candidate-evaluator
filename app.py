from __future__ import annotations

from pathlib import Path
from typing import Any
from html import escape
import csv
import io
import json
import os
import hmac

import streamlit as st

from candidate_evaluator.constants import DEFAULT_PARALLEL_OPENAI_CALLS, OUTPUTS_DIR
from candidate_evaluator.extractor import (
    candidate_input_issue,
    candidate_input_issues,
    load_profiles,
    load_profiles_from_text,
    normalize_candidates,
    preview_candidates,
)
from candidate_evaluator.progress import (
    candidate_status_rows,
    completed_preview_rows,
    init_run,
    load_candidates,
    load_status,
    make_run_id,
    mark_completed,
    mark_failed,
    mark_skipped,
    progress_counts,
    reset_running,
    result_rows,
    result_rows_by_id,
    role_for_run,
    run_dir,
    run_select_options,
    save_exports,
    set_current,
)
from candidate_evaluator.providers import DEFAULT_PROVIDER_KEY, get_provider, provider_options
from candidate_evaluator.roles import (
    CUSTOM_EVIDENCE_SOURCES,
    CUSTOM_ROLE_KEY,
    DEFAULT_CUSTOM_ROLE_CONFIG,
    DEFAULT_ROLE_KEY,
    RoleProfile,
    get_role_profile,
    prepare_output_rows,
    role_options,
    validate_custom_role_config,
)
from candidate_evaluator.validation import apply_calculated_fields, coerce_fixed_row, validate_output_row
from candidate_evaluator.openai_scoring import BATCH_SIZE


DEFAULT_RUBRIC_PATH = "/Users/sehermehta/Documents/Documents - Seher’s MacBook Air/Codex/candidate-evaluator/rubric.md"
DEFAULT_SAMPLE_PATH = "/Users/sehermehta/Documents/Documents - Seher’s MacBook Air/Codex/candidate-evaluator/sample.json"


def main() -> None:
    st.set_page_config(page_title="Candidate Evaluator", layout="wide")
    _require_access()
    st.title("Candidate Evaluator")

    with st.sidebar:
        st.header("Inputs")
        role_key = _role_selector()
        provider_key = _provider_selector()
        json_upload = st.file_uploader("LinkedIn JSON", type=["json"])
        sample_path = st.text_input("Or JSON file path", value=DEFAULT_SAMPLE_PATH if Path(DEFAULT_SAMPLE_PATH).exists() else "")
        rubric_upload = st.file_uploader("Rubric Markdown", type=["md", "txt"], key=f"rubric-upload-{role_key}")
        rubric_path = st.text_input(
            "Or rubric file path",
            value=_default_rubric_path(role_key),
            key=f"rubric-path-{role_key}",
        )
        model = _model_selector(provider_key)
        reasoning_effort = _reasoning_selector(provider_key)
        provider = get_provider(provider_key)
        parallel_calls = st.number_input(
            "Parallel API calls",
            min_value=1,
            max_value=20,
            value=DEFAULT_PARALLEL_OPENAI_CALLS,
            step=1,
        )
        api_key = st.text_input(f"{provider.label} API key", type="password")
        approved = st.checkbox(f"I approve paid {provider.label} API calls for this run")

    candidates, rubric_text = _load_inputs(json_upload, sample_path, rubric_upload, rubric_path)
    custom_role_config, custom_role_errors = _custom_role_editor(role_key)
    role = None if custom_role_errors else get_role_profile(role_key, custom_role_config)

    _show_preview(candidates, rubric_text, role)
    _show_run_controls(
        candidates,
        rubric_text,
        role_key,
        custom_role_config,
        custom_role_errors,
        provider_key,
        model,
        reasoning_effort,
        int(parallel_calls),
        api_key,
        approved,
    )


def _require_access() -> None:
    password = os.environ.get("APP_PASSWORD", "")
    if not password:
        if os.environ.get("RAILWAY_ENVIRONMENT_ID"):
            st.error("App access has not been configured yet.")
            st.stop()
        return
    if st.session_state.get("access_granted"):
        return
    with st.form("app_login"):
        st.subheader("Candidate Evaluator")
        entered = st.text_input("App password", type="password")
        submitted = st.form_submit_button("Sign in")
    if submitted:
        if hmac.compare_digest(entered.encode(), password.encode()):
            st.session_state["access_granted"] = True
            st.rerun()
        st.error("Incorrect password.")
    st.stop()


def _role_selector() -> str:
    options = role_options()
    selected_label = st.selectbox("Evaluation role", options=list(options), index=0)
    return options[selected_label]


def _provider_selector() -> str:
    options = provider_options()
    selected_label = st.selectbox("AI provider", options=list(options), index=0)
    return options[selected_label]


def _custom_role_editor(role_key: str) -> tuple[dict[str, Any] | None, list[str]]:
    if role_key != CUSTOM_ROLE_KEY:
        return None, []

    st.subheader("Custom Role Setup")
    role_name = st.text_input("Role name", value="", key="custom-role-name")
    category_count = int(
        st.number_input(
            "Number of scoring categories",
            min_value=1,
            max_value=12,
            value=len(DEFAULT_CUSTOM_ROLE_CONFIG["categories"]),
            step=1,
            key="custom-role-category-count",
        )
    )
    st.markdown("**Scoring categories**")
    categories = []
    for index in range(category_count):
        default = (
            DEFAULT_CUSTOM_ROLE_CONFIG["categories"][index]
            if index < len(DEFAULT_CUSTOM_ROLE_CONFIG["categories"])
            else {"name": "", "max_score": 10, "allowed_scores": []}
        )
        name_col, max_col, allowed_col = st.columns([2, 1, 2])
        with name_col:
            name = st.text_input(
                f"Category {index + 1}",
                value=str(default["name"]),
                key=f"custom-role-category-name-{index}",
            )
        with max_col:
            maximum = int(
                st.number_input(
                    f"Maximum {index + 1}",
                    min_value=1,
                    max_value=100,
                    value=int(default["max_score"]),
                    step=1,
                    key=f"custom-role-category-max-{index}",
                )
            )
        with allowed_col:
            allowed_raw = st.text_input(
                f"Allowed scores {index + 1}",
                value=", ".join(str(value) for value in default["allowed_scores"]),
                help="Optional. Leave blank for any whole score from zero to the maximum, or enter values such as 0, 5, 10.",
                key=f"custom-role-category-allowed-{index}",
            )
        categories.append(
            {
                "name": name.strip(),
                "max_score": maximum,
                "allowed_scores": _parse_allowed_scores(allowed_raw),
            }
        )

    outcome_column = st.text_input(
        "Outcome column name",
        value=DEFAULT_CUSTOM_ROLE_CONFIG["outcome_column"],
        key="custom-role-outcome-column",
    )
    band_count = int(
        st.number_input(
            "Number of outcome bands",
            min_value=1,
            max_value=10,
            value=len(DEFAULT_CUSTOM_ROLE_CONFIG["outcome_bands"]),
            step=1,
            key="custom-role-band-count",
        )
    )
    st.markdown("**Outcome bands**")
    bands = []
    for index in range(band_count):
        default = (
            DEFAULT_CUSTOM_ROLE_CONFIG["outcome_bands"][index]
            if index < len(DEFAULT_CUSTOM_ROLE_CONFIG["outcome_bands"])
            else {"minimum": 0, "maximum": 0, "label": ""}
        )
        low_col, high_col, label_col = st.columns([1, 1, 2])
        with low_col:
            low = int(
                st.number_input(
                    f"Minimum {index + 1}",
                    min_value=0,
                    max_value=500,
                    value=int(default["minimum"]),
                    step=1,
                    key=f"custom-role-band-min-{index}",
                )
            )
        with high_col:
            high = int(
                st.number_input(
                    f"Maximum {index + 1}",
                    min_value=0,
                    max_value=500,
                    value=int(default["maximum"]),
                    step=1,
                    key=f"custom-role-band-max-{index}",
                )
            )
        with label_col:
            label = st.text_input(
                f"Outcome label {index + 1}",
                value=str(default["label"]),
                key=f"custom-role-band-label-{index}",
            )
        bands.append({"minimum": low, "maximum": high, "label": label.strip()})
    evidence_sources = st.multiselect(
        "Permitted LinkedIn evidence",
        options=CUSTOM_EVIDENCE_SOURCES,
        default=DEFAULT_CUSTOM_ROLE_CONFIG["evidence_sources"],
        key="custom-role-evidence",
    )
    require_experience = st.checkbox(
        "Require at least one experience entry",
        value=DEFAULT_CUSTOM_ROLE_CONFIG["require_experience"],
        key="custom-role-require-experience",
    )

    config = {
        "role_name": role_name.strip(),
        "categories": categories,
        "outcome_column": outcome_column.strip(),
        "outcome_bands": bands,
        "evidence_sources": evidence_sources,
        "require_experience": require_experience,
    }
    errors = validate_custom_role_config(config)
    if errors:
        st.error("Custom role setup needs attention:\n\n" + "\n".join(f"- {error}" for error in errors))
    else:
        role = get_role_profile(CUSTOM_ROLE_KEY, config)
        st.success(
            f"Configuration valid: {len(role.category_scores)} categories, "
            f"{int(role.total_max)} total points, {len(role.outcome_bands)} outcome bands."
        )
        with st.expander("Review generated output columns"):
            st.write(role.output_columns)
    return config, errors


def _parse_allowed_scores(value: Any) -> list[Any]:
    if value is None or not str(value).strip():
        return []
    parsed: list[Any] = []
    for item in str(value).replace(";", ",").split(","):
        item = item.strip()
        if not item:
            continue
        try:
            number = float(item)
            parsed.append(int(number) if number.is_integer() else number)
        except ValueError:
            parsed.append(item)
    return parsed


def _model_selector(provider_key: str) -> str:
    provider = get_provider(provider_key)
    custom_options = _custom_model_options(provider_key)
    model_options = {**provider.model_options, **custom_options}
    labels = list(model_options)
    default_label = next(
        (label for label, model_id in model_options.items() if model_id == provider.default_model),
        labels[0],
    )
    default_index = labels.index(default_label)
    selected_label = st.selectbox(f"{provider.label} model", options=labels, index=default_index)
    selected_model = model_options[selected_label]
    if selected_label == "Custom":
        return st.text_input("Custom model name", value=provider.default_model).strip()
    st.caption(f"API model: `{selected_model}`")
    return selected_model


def _reasoning_selector(provider_key: str) -> str:
    provider = get_provider(provider_key)
    if not provider.reasoning_options:
        return provider.default_reasoning_effort
    labels = list(provider.reasoning_options)
    default_label = next(
        (
            label
            for label, effort in provider.reasoning_options.items()
            if effort == provider.default_reasoning_effort
        ),
        labels[0],
    )
    selected_label = st.selectbox("Reasoning effort", options=labels, index=labels.index(default_label))
    return provider.reasoning_options[selected_label]


def _custom_model_options(provider_key: str = DEFAULT_PROVIDER_KEY) -> dict[str, str]:
    provider = get_provider(provider_key)
    with st.expander("Add custom model options"):
        raw_models = st.text_area(
            "Extra model names",
            placeholder=f"Paste exact {provider.label} model IDs, one per line.",
            help=f"Use this when {provider.label} gives you access to a model that is not listed above.",
            key=f"custom-model-options-{provider.key}",
        )
    options = {}
    for model in _parse_custom_models(raw_models):
        options[f"Custom: {model}"] = model
    return options


def _parse_custom_models(raw_models: str) -> list[str]:
    models = []
    seen = set()
    for line in raw_models.replace(",", "\n").splitlines():
        model = line.strip()
        if not model or model in seen:
            continue
        seen.add(model)
        models.append(model)
    return models


def _default_rubric_path(role_key: str) -> str:
    bundled_rubrics = {
        "backend": "backend_engineer.md",
        "ai_engineer_trj": "ai_engineer_trj.md",
    }
    if role_key in bundled_rubrics:
        bundled = Path(__file__).parent / "rubrics" / bundled_rubrics[role_key]
        return str(bundled) if bundled.exists() else ""
    return DEFAULT_RUBRIC_PATH if role_key == "design" and Path(DEFAULT_RUBRIC_PATH).exists() else ""


def _load_inputs(json_upload: Any, sample_path: str, rubric_upload: Any, rubric_path: str) -> tuple[list[dict[str, Any]], str]:
    candidates: list[dict[str, Any]] = []
    rubric_text = ""
    try:
        if json_upload is not None:
            candidates = _candidates_from_json_text(json_upload.getvalue().decode("utf-8"))
        elif sample_path:
            path = Path(sample_path)
            candidates = _candidates_from_json_path(str(path), path.stat().st_mtime_ns)
    except Exception as exc:
        st.error(f"Could not read LinkedIn JSON: {exc}")

    try:
        if rubric_upload is not None:
            rubric_text = rubric_upload.getvalue().decode("utf-8")
        elif rubric_path:
            rubric_text = Path(rubric_path).read_text(encoding="utf-8")
    except Exception as exc:
        st.error(f"Could not read rubric: {exc}")
    return candidates, rubric_text


@st.cache_data(show_spinner=False)
def _candidates_from_json_text(text: str) -> list[dict[str, Any]]:
    return normalize_candidates(load_profiles_from_text(text))


@st.cache_data(show_spinner=False)
def _candidates_from_json_path(path: str, _mtime_ns: int) -> list[dict[str, Any]]:
    return normalize_candidates(load_profiles(path))


def _show_preview(candidates: list[dict[str, Any]], rubric_text: str, role: RoleProfile | None) -> None:
    st.subheader("Extraction Preview")
    st.write(f"Candidates loaded: {len(candidates)}")
    st.write(f"Rubric loaded: {'yes' if rubric_text else 'no'}")
    if role is None:
        st.warning("Complete the custom role setup before starting an evaluation.")
        return
    issues = _candidate_input_issues_for_role(candidates, role)
    if issues:
        skipped_count = sum(bool(_candidate_input_issue_for_role(candidate, role)) for candidate in candidates)
        st.warning(f"{skipped_count} of {len(candidates)} profile(s) will be skipped without an API call.")
        for issue in issues:
            st.write(f"- {issue}")
        st.info(
            "The remaining valid profiles can still be evaluated. Skipped records will be logged in the status table "
            "and excluded from CSV/Excel. Optional fields such as Website or Education do not cause a skip."
        )
    if st.button("Preview first five candidates", disabled=not candidates):
        st.session_state["preview"] = preview_candidates(candidates, limit=5)
    if st.session_state.get("preview"):
        _display_table(st.session_state["preview"])


def _candidate_input_issue_for_role(candidate: dict[str, Any], role: RoleProfile) -> str:
    return candidate_input_issue(
        candidate,
        role.key,
        evidence_sources=role.evidence_sources,
        require_experience=role.require_experience,
        skip_if_no_evidence=role.skip_if_no_evidence,
    )


def _candidate_input_issues_for_role(candidates: list[dict[str, Any]], role: RoleProfile) -> list[str]:
    return candidate_input_issues(
        candidates,
        role.key,
        evidence_sources=role.evidence_sources,
        require_experience=role.require_experience,
        skip_if_no_evidence=role.skip_if_no_evidence,
    )


def _run_matches_role_config(
    run_id: str,
    role_key: str,
    custom_role_config: dict[str, Any] | None,
    provider_key: str,
    model: str,
    reasoning_effort: str,
) -> bool:
    try:
        status = load_status(run_id)
    except Exception:
        return False
    if status.get("role", DEFAULT_ROLE_KEY) != role_key:
        return False
    if status.get("provider", DEFAULT_PROVIDER_KEY) != provider_key:
        return False
    if status.get("model") != model:
        return False
    if status.get("reasoning_effort", "none") != reasoning_effort:
        return False
    if role_key == CUSTOM_ROLE_KEY:
        return status.get("custom_role_config") == custom_role_config
    return True


def _show_run_controls(
    candidates: list[dict[str, Any]],
    rubric_text: str,
    role_key: str,
    custom_role_config: dict[str, Any] | None,
    custom_role_errors: list[str],
    provider_key: str,
    model: str,
    reasoning_effort: str,
    parallel_calls: int,
    api_key: str,
    approved: bool,
) -> None:
    st.subheader("Evaluation")
    existing_run_options = run_select_options()
    selected_run_label = st.selectbox("Resume run", options=[""] + list(existing_run_options), index=0)
    selected_run = existing_run_options.get(selected_run_label, "")
    selected_run_status = load_status(selected_run) if selected_run else {}
    selected_run_role = role_for_run(selected_run) if selected_run else None
    selected_run_issues = (
        _candidate_input_issues_for_role(load_candidates(selected_run), selected_run_role)
        if selected_run_role
        else []
    )
    if selected_run_issues:
        st.warning("This saved run contains profile records that will be skipped.")
        for issue in selected_run_issues:
            st.write(f"- {issue}")
    if selected_run:
        saved_provider = get_provider(selected_run_status.get("provider", DEFAULT_PROVIDER_KEY))
        saved_reasoning = selected_run_status.get("reasoning_effort", "none")
        reasoning_label = f", reasoning: {saved_reasoning}" if saved_provider.reasoning_options else ""
        st.caption(
            f"Saved run provider: {saved_provider.label}; model: "
            f"`{selected_run_status.get('model', 'unknown')}`{reasoning_label}."
        )

    col1, col2, col3 = st.columns(3)
    with col1:
        start_clicked = st.button(
            "Start / resume evaluation",
            disabled=not candidates or not rubric_text or (not selected_run and bool(custom_role_errors)),
        )
    with col2:
        retry_clicked = st.button(
            "Retry failed candidates",
            disabled=not selected_run,
        )
    with col3:
        export_clicked = st.button("Save exports", disabled=not selected_run)

    session_run = st.session_state.get("active_run_id", "")
    if session_run and not _run_matches_role_config(
        session_run,
        role_key,
        custom_role_config,
        provider_key,
        model,
        reasoning_effort,
    ):
        session_run = ""
    active_run = selected_run or session_run
    ran_evaluation = False
    if start_clicked:
        _require_api_ready(api_key, approved, provider_key)
        if active_run:
            _require_run_provider(active_run, provider_key)
        if not active_run:
            active_run = make_run_id()
            init_run(
                active_run,
                candidates,
                rubric_text,
                model,
                role_key,
                custom_role_config=custom_role_config,
                provider_key=provider_key,
                reasoning_effort=reasoning_effort,
            )
            st.session_state["active_run_id"] = active_run
        _run_evaluation(active_run, api_key, parallel_calls, retry_failed=False)
        ran_evaluation = True

    if retry_clicked:
        _require_api_ready(api_key, approved, provider_key)
        _require_run_provider(selected_run, provider_key)
        _run_evaluation(selected_run, api_key, parallel_calls, retry_failed=True)
        ran_evaluation = True

    if export_clicked:
        rows = result_rows(selected_run)
        csv_path, xlsx_path = save_exports(selected_run, rows)
        st.success(f"Saved exports: {csv_path} and {xlsx_path}")

    if active_run and not ran_evaluation:
        _show_evaluation_status(active_run, parallel_calls)
    if active_run:
        _show_downloads(active_run)


def _require_api_ready(api_key: str, approved: bool, provider_key: str) -> None:
    provider = get_provider(provider_key)
    if not approved:
        st.error(f"Approve paid {provider.label} API calls before starting an evaluation.")
        st.stop()
    if not api_key:
        st.error(f"Paste a {provider.label} API key before starting an evaluation.")
        st.stop()


def _require_run_provider(run_id: str, provider_key: str) -> None:
    status = load_status(run_id)
    saved_provider_key = status.get("provider", DEFAULT_PROVIDER_KEY)
    if saved_provider_key == provider_key:
        return
    saved_provider = get_provider(saved_provider_key)
    st.error(
        f"This saved run uses {saved_provider.label}. Select {saved_provider.label} as the AI provider "
        f"and paste its API key before resuming."
    )
    st.stop()


def _run_evaluation(run_id: str, api_key: str, parallel_calls: int, retry_failed: bool) -> None:
    from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

    candidates = load_candidates(run_id)
    reset_running(run_id)
    status = load_status(run_id)
    provider_key = status.get("provider", DEFAULT_PROVIDER_KEY)
    model = status.get("model") or get_provider(provider_key).default_model
    reasoning_effort = status.get("reasoning_effort", "none")
    role = role_for_run(run_id)
    status_by_id = status.get("candidates", {})
    completed_row_ids = set(result_rows_by_id(run_id))
    progress = st.progress(0)
    message = st.empty()
    dashboard = st.empty()
    preview = st.empty()
    summary = st.empty()

    worklist = []
    skipped_in_pass = 0
    for candidate in candidates:
        candidate_id = candidate["linkedin_profile_id"]
        status_entry = status_by_id.get(candidate_id, {})
        state = status_entry.get("state", "pending")
        input_issue = _candidate_input_issue_for_role(candidate, role)
        if input_issue and state != "completed" and candidate_id not in completed_row_ids:
            mark_skipped(run_id, candidate_id, f"Skipped before API call: {input_issue}.")
            skipped_in_pass += 1
            continue
        if retry_failed and state == "failed":
            worklist.append(candidate)
        elif (
            not retry_failed
            and state != "completed"
            and candidate_id not in completed_row_ids
            and (
                state != "skipped"
                or str(status_entry.get("error", "")).startswith("Skipped before API call:")
            )
        ):
            worklist.append(candidate)

    rubric_text = (run_dir(run_id) / "rubric.md").read_text(encoding="utf-8")
    batches = [worklist[index : index + BATCH_SIZE] for index in range(0, len(worklist), BATCH_SIZE)]
    total = max(len(worklist) + skipped_in_pass, 1)
    max_workers = max(1, min(int(parallel_calls), len(batches) or 1))
    completed_in_pass = skipped_in_pass
    pending = list(batches)
    active: dict[Any, list[dict[str, Any]]] = {}
    progress.progress(completed_in_pass / total)
    provider = get_provider(provider_key)
    message.info(
        f"Running up to {max_workers} {provider.label} batch call(s) at a time, "
        f"with up to {BATCH_SIZE} candidates per call. "
        f"Skipped {skipped_in_pass} unusable profile(s) without an API call."
    )
    _render_live_status(run_id, dashboard, preview, summary, run_finished=False, parallel_calls=max_workers)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # OpenAI's first batch establishes the shared rubric prefix before
        # later batches run in parallel. Other providers can start at full concurrency.
        initial_limit = 1 if provider_key == DEFAULT_PROVIDER_KEY else max_workers
        while pending and len(active) < initial_limit:
            _submit_candidate_batch(
                executor,
                active,
                pending,
                run_id,
                api_key,
                provider_key,
                model,
                reasoning_effort,
                rubric_text,
                role,
            )
        _render_live_status(run_id, dashboard, preview, summary, run_finished=False, parallel_calls=max_workers)

        while active:
            done, _ = wait(active.keys(), return_when=FIRST_COMPLETED)
            for future in done:
                candidates_in_batch = active.pop(future)
                results = future.result()
                for candidate, result in zip(candidates_in_batch, results):
                    candidate_id = candidate["linkedin_profile_id"]
                    if result["state"] == "completed":
                        mark_completed(run_id, candidate_id, result["row"], result["raw"], result["elapsed_seconds"])
                    elif result["state"] == "skipped":
                        mark_skipped(
                            run_id,
                            candidate_id,
                            result["error"],
                            raw_response=result.get("raw"),
                            elapsed_seconds=result["elapsed_seconds"],
                        )
                    else:
                        mark_failed(run_id, candidate_id, result["error"], elapsed_seconds=result["elapsed_seconds"])
                    completed_in_pass += 1
                    progress.progress(completed_in_pass / total)

            while pending and len(active) < max_workers:
                _submit_candidate_batch(
                    executor,
                    active,
                    pending,
                    run_id,
                    api_key,
                    provider_key,
                    model,
                    reasoning_effort,
                    rubric_text,
                    role,
                )

            _render_live_status(run_id, dashboard, preview, summary, run_finished=False, parallel_calls=max_workers)

    message.success("Evaluation pass finished.")
    _render_live_status(run_id, dashboard, preview, summary, run_finished=True, parallel_calls=max_workers)


def _submit_candidate_batch(
    executor: ThreadPoolExecutor,
    active: dict[Any, list[dict[str, Any]]],
    pending: list[list[dict[str, Any]]],
    run_id: str,
    api_key: str,
    provider_key: str,
    model: str,
    reasoning_effort: str,
    rubric_text: str,
    role: RoleProfile,
) -> None:
    candidates = pending.pop(0)
    for candidate in candidates:
        set_current(run_id, candidate["linkedin_profile_id"])
    future = executor.submit(
        _evaluate_candidate_batch_for_run,
        api_key,
        model,
        rubric_text,
        candidates,
        role,
        provider_key,
        reasoning_effort,
    )
    active[future] = candidates


def _evaluate_candidate_batch_for_run(
    api_key: str,
    model: str,
    rubric_text: str,
    candidates: list[dict[str, Any]],
    role: RoleProfile,
    provider_key: str = DEFAULT_PROVIDER_KEY,
    reasoning_effort: str = "none",
) -> list[dict[str, Any]]:
    import time

    started = time.monotonic()
    try:
        from candidate_evaluator.openai_scoring import evaluate_candidates

        evaluations = evaluate_candidates(
            api_key=api_key,
            provider_key=provider_key,
            model=model,
            reasoning_effort=reasoning_effort,
            rubric_text=rubric_text,
            candidates=candidates,
            role_profile=role,
        )
        batch_elapsed = time.monotonic() - started
        elapsed = batch_elapsed / len(candidates)
        results = []
        for candidate, (grading, raw) in zip(candidates, evaluations):
            role_source = {
                **candidate["source_row"],
                "Candidate": candidate.get("candidate_name", ""),
                "Profile URL": candidate.get("linkedin_url", ""),
                "Rank Number": "",
            }
            row = apply_calculated_fields({**role_source, **grading}, candidate, role)
            row = coerce_fixed_row(row, role)
            errors = validate_output_row(row, role)
            if errors:
                results.append(
                    {
                        "state": "skipped",
                        "error": "Skipped after API call because the grading output was incomplete or invalid: "
                        + "; ".join(errors),
                        "raw": raw,
                        "elapsed_seconds": elapsed,
                    }
                )
            else:
                results.append({"state": "completed", "row": row, "raw": raw, "elapsed_seconds": elapsed})
        return results
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raw_content = getattr(exc, "raw_content", "")
        result = {
            "state": "skipped",
            "error": f"Skipped after API call because the batch output was empty, incomplete, or unreadable: {exc}",
            "raw": {"unparsed_content": raw_content} if raw_content else {},
            "elapsed_seconds": time.monotonic() - started,
        }
        return [dict(result) for _ in candidates]
    except Exception as exc:
        result = {"state": "failed", "error": str(exc), "elapsed_seconds": time.monotonic() - started}
        return [dict(result) for _ in candidates]


def _evaluate_candidate_for_run(
    api_key: str,
    model: str,
    rubric_text: str,
    candidate: dict[str, Any],
    role: RoleProfile,
    provider_key: str = DEFAULT_PROVIDER_KEY,
    reasoning_effort: str = "none",
) -> dict[str, Any]:
    """Compatibility path for a single candidate and focused unit tests."""
    import time

    started = time.monotonic()
    try:
        from candidate_evaluator.openai_scoring import evaluate_candidate

        grading, raw = evaluate_candidate(
            api_key=api_key,
            provider_key=provider_key,
            model=model,
            reasoning_effort=reasoning_effort,
            rubric_text=rubric_text,
            candidate=candidate,
            role_profile=role,
        )
        role_source = {
            **candidate["source_row"],
            "Candidate": candidate.get("candidate_name", ""),
            "Profile URL": candidate.get("linkedin_url", ""),
            "Rank Number": "",
        }
        row = apply_calculated_fields({**role_source, **grading}, candidate, role)
        row = coerce_fixed_row(row, role)
        errors = validate_output_row(row, role)
        if errors:
            return {
                "state": "skipped",
                "error": "Skipped after API call because the grading output was incomplete or invalid: "
                + "; ".join(errors),
                "raw": raw,
                "elapsed_seconds": time.monotonic() - started,
            }
        return {"state": "completed", "row": row, "raw": raw, "elapsed_seconds": time.monotonic() - started}
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raw_content = getattr(exc, "raw_content", "")
        return {
            "state": "skipped",
            "error": f"Skipped after API call because the grading output was empty or unreadable: {exc}",
            "raw": {"unparsed_content": raw_content} if raw_content else {},
            "elapsed_seconds": time.monotonic() - started,
        }
    except Exception as exc:
        return {"state": "failed", "error": str(exc), "elapsed_seconds": time.monotonic() - started}


def _show_evaluation_status(run_id: str, parallel_calls: int = DEFAULT_PARALLEL_OPENAI_CALLS) -> None:
    st.subheader("Evaluation Status")
    _render_live_status(
        run_id,
        st.empty(),
        st.empty(),
        st.empty(),
        run_finished=_run_is_finished(run_id),
        parallel_calls=parallel_calls,
    )


def _render_live_status(
    run_id: str,
    dashboard: Any,
    preview: Any,
    summary: Any,
    run_finished: bool,
    parallel_calls: int,
) -> None:
    counts = progress_counts(run_id)
    role = role_for_run(run_id)
    with dashboard.container():
        st.write(f"Evaluated: {counts['evaluated']} / {counts['total']}")
        col1, col2, col3, col4, col5, col6, col7 = st.columns(7)
        col1.metric("Completed", counts["completed"])
        col2.metric("Failed", counts["failed"])
        col3.metric("Skipped", counts["skipped"])
        col4.metric("Remaining", counts["remaining"])
        col5.metric("Total candidates", counts["total"])
        col6.metric("Avg sec / candidate", _format_seconds(counts["avg_seconds_per_candidate"]))
        col7.metric("Est. time remaining", _format_eta(counts, parallel_calls))
        st.write(f"Current candidate: {counts['current_candidate'] or 'None'}")
        _display_table(candidate_status_rows(run_id))

    with preview.container():
        st.subheader("Completed Results Preview")
        rows = completed_preview_rows(run_id)
        if rows:
            _display_table(rows)
        else:
            st.caption("No completed candidates yet.")

    if run_finished:
        with summary.container():
            st.subheader("Run Summary")
            col1, col2, col3, col4, col5 = st.columns(5)
            col1.metric("Total candidates", counts["total"])
            col2.metric("Completed", counts["completed"])
            col3.metric("Failed", counts["failed"])
            col4.metric("Skipped", counts["skipped"])
            col5.metric("Export ready", "yes" if counts["export_ready"] else "no")


def _run_is_finished(run_id: str) -> bool:
    counts = progress_counts(run_id)
    return counts["total"] > 0 and counts["evaluated"] == counts["total"]


def _format_seconds(value: float) -> str:
    if not value:
        return "n/a"
    return f"{value:.1f}s"


def _format_eta(counts: dict[str, Any], parallel_calls: int) -> str:
    avg_seconds = counts.get("avg_seconds_per_candidate", 0.0)
    remaining = counts.get("remaining", 0)
    if not avg_seconds or not remaining:
        return "n/a"
    effective_parallelism = max(1, min(int(parallel_calls), remaining + counts.get("running", 0)))
    return _format_duration(avg_seconds * remaining / effective_parallelism)


def _format_duration(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    minutes, secs = divmod(seconds, 60)
    hours, mins = divmod(minutes, 60)
    if hours:
        return f"{hours}h {mins}m"
    if mins:
        return f"{mins}m {secs}s"
    return f"{secs}s"


def _show_downloads(run_id: str) -> None:
    role = role_for_run(run_id)
    rows = result_rows(run_id)
    if not rows:
        return
    counts = progress_counts(run_id)
    if counts.get("skipped"):
        st.caption(f"{counts['skipped']} skipped profile(s) are logged in Evaluation Status and excluded from downloads.")
    fixed_rows = prepare_output_rows(rows, role)
    csv_data = _rows_to_csv_bytes(fixed_rows, role.output_columns)
    st.subheader("Downloads")
    csv_col, excel_col = st.columns(2)
    with csv_col:
        st.download_button(
            "Download CSV",
            csv_data,
            file_name=f"candidate_evaluation_{run_id}.csv",
            mime="text/csv",
            key=f"download-csv-{run_id}",
        )
    xlsx_path = Path(OUTPUTS_DIR) / f"candidate_evaluation_{role.key}_{run_id}.xlsx"
    with excel_col:
        if xlsx_path.exists():
            st.download_button(
                "Download Excel",
                xlsx_path.read_bytes(),
                file_name=f"candidate_evaluation_{run_id}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"download-excel-{run_id}",
            )
        else:
            st.caption("Click Save exports to create the Excel file.")
    st.subheader("Completed Output")
    _display_table(fixed_rows)


def _rows_to_csv_bytes(rows: list[dict[str, Any]], columns: list[str]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _display_table(rows: list[dict[str, Any]]) -> None:
    if not rows:
        st.caption("No rows to show.")
        return
    columns = list(rows[0].keys())
    header = "".join(f"<th>{escape(str(column))}</th>" for column in columns)
    body = []
    for row in rows:
        cells = "".join(f"<td>{escape(str(row.get(column, '')))}</td>" for column in columns)
        body.append(f"<tr>{cells}</tr>")
    st.markdown(
        """
        <style>
        .candidate-table-wrap {
            max-height: 520px;
            overflow: auto;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
        }
        .candidate-table {
            border-collapse: collapse;
            width: max-content;
            min-width: 100%;
            font-size: 13px;
            line-height: 1.35;
        }
        .candidate-table th,
        .candidate-table td {
            border-bottom: 1px solid #e5e7eb;
            border-right: 1px solid #eef2f7;
            padding: 8px 10px;
            vertical-align: top;
            max-width: 360px;
            white-space: normal;
            word-break: break-word;
        }
        .candidate-table th {
            position: sticky;
            top: 0;
            background: #f8fafc;
            z-index: 1;
            text-align: left;
            font-weight: 600;
        }
        </style>
        """
        + f"<div class='candidate-table-wrap'><table class='candidate-table'><thead><tr>{header}</tr></thead><tbody>{''.join(body)}</tbody></table></div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
