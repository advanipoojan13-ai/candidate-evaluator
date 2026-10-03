from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

try:
    import fcntl
except ImportError:  # pragma: no cover - non-Unix fallback
    fcntl = None

from .constants import OUTPUTS_DIR, RUNS_DIR
from .roles import DEFAULT_ROLE_KEY, RoleProfile, get_role_profile, prepare_output_rows


def make_run_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def run_dir(run_id: str) -> Path:
    return Path(RUNS_DIR) / run_id


def init_run(
    run_id: str,
    candidates: list[dict[str, Any]],
    rubric_text: str,
    model: str,
    role_key: str = DEFAULT_ROLE_KEY,
    custom_role_config: Optional[dict[str, Any]] = None,
) -> Path:
    path = run_dir(run_id)
    path.mkdir(parents=True, exist_ok=True)
    _write_json(path / "candidates.json", candidates)
    _write_json(path / "status.json", _initial_status(candidates, model, role_key, custom_role_config))
    (path / "rubric.md").write_text(rubric_text, encoding="utf-8")
    for name in ("rows.jsonl", "failed.jsonl", "skipped.jsonl", "raw_responses.jsonl"):
        (path / name).touch(exist_ok=True)
    return path


def list_runs() -> list[str]:
    root = Path(RUNS_DIR)
    if not root.exists():
        return []
    return sorted([p.name for p in root.iterdir() if p.is_dir()], reverse=True)


def run_select_options() -> dict[str, str]:
    options: dict[str, str] = {}
    for run_id in list_runs():
        status = load_status(run_id)
        if status.get("_load_error"):
            options[f"{run_id} — progress file temporarily unreadable"] = run_id
            continue
        try:
            role = get_role_profile(
                status.get("role", DEFAULT_ROLE_KEY),
                status.get("custom_role_config"),
            )
        except ValueError:
            options[f"{run_id} — invalid saved role configuration"] = run_id
            continue
        counts = _counts_from_status(status)
        label = (
            f"{run_id} — {role.label} — {counts['completed']} done / "
            f"{counts['failed']} failed / {counts['skipped']} skipped"
        )
        options[label] = run_id
    return options


def load_candidates(run_id: str) -> list[dict[str, Any]]:
    return json.loads((run_dir(run_id) / "candidates.json").read_text(encoding="utf-8"))


def load_status(run_id: str) -> dict[str, Any]:
    path = run_dir(run_id) / "status.json"
    if not path.exists():
        return {}
    try:
        return json.loads(_read_text_with_retries(path))
    except (OSError, TimeoutError, json.JSONDecodeError) as exc:
        return {"role": DEFAULT_ROLE_KEY, "candidates": {}, "_load_error": str(exc)}


def save_status(run_id: str, status: dict[str, Any]) -> None:
    if status.get("_load_error"):
        raise RuntimeError(f"Refusing to overwrite unreadable status for run {run_id}: {status['_load_error']}")
    with _locked_run(run_id):
        _write_json(run_dir(run_id) / "status.json", status)


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def mark_completed(
    run_id: str,
    candidate_id: str,
    row: dict[str, Any],
    raw_response: dict[str, Any],
    elapsed_seconds: Optional[float] = None,
) -> None:
    with _locked_run(run_id):
        path = run_dir(run_id)
        append_jsonl(path / "rows.jsonl", {"candidate_id": candidate_id, "row": row})
        append_jsonl(path / "raw_responses.jsonl", {"candidate_id": candidate_id, "raw_response": raw_response})
        status = load_status(run_id)
        if status.get("_load_error"):
            raise RuntimeError(f"Could not update progress for {candidate_id}: {status['_load_error']}")
        entry = status["candidates"].setdefault(candidate_id, {})
        entry.update({"state": "completed", "error": "", "updated_at": datetime.now().isoformat(timespec="seconds")})
        if elapsed_seconds is not None:
            entry["elapsed_seconds"] = round(elapsed_seconds, 3)
        _write_json(path / "status.json", status)


def mark_failed(
    run_id: str,
    candidate_id: str,
    error: str,
    raw_response: Optional[dict[str, Any]] = None,
    elapsed_seconds: Optional[float] = None,
) -> None:
    with _locked_run(run_id):
        path = run_dir(run_id)
        append_jsonl(path / "failed.jsonl", {"candidate_id": candidate_id, "error": error, "raw_response": raw_response or {}})
        status = load_status(run_id)
        if status.get("_load_error"):
            raise RuntimeError(f"Could not update failed status for {candidate_id}: {status['_load_error']}")
        entry = status["candidates"].setdefault(candidate_id, {})
        entry.update({"state": "failed", "error": error, "updated_at": datetime.now().isoformat(timespec="seconds")})
        if elapsed_seconds is not None:
            entry["elapsed_seconds"] = round(elapsed_seconds, 3)
        _write_json(path / "status.json", status)


def mark_skipped(
    run_id: str,
    candidate_id: str,
    reason: str,
    raw_response: Optional[dict[str, Any]] = None,
    elapsed_seconds: Optional[float] = None,
) -> None:
    with _locked_run(run_id):
        path = run_dir(run_id)
        append_jsonl(
            path / "skipped.jsonl",
            {"candidate_id": candidate_id, "reason": reason, "raw_response": raw_response or {}},
        )
        status = load_status(run_id)
        if status.get("_load_error"):
            raise RuntimeError(f"Could not update skipped status for {candidate_id}: {status['_load_error']}")
        entry = status["candidates"].setdefault(candidate_id, {})
        entry.update({"state": "skipped", "error": reason, "updated_at": datetime.now().isoformat(timespec="seconds")})
        if elapsed_seconds is None:
            entry.pop("elapsed_seconds", None)
        else:
            entry["elapsed_seconds"] = round(elapsed_seconds, 3)
        _write_json(path / "status.json", status)


def set_current(run_id: str, candidate_id: str) -> None:
    with _locked_run(run_id):
        status = load_status(run_id)
        if status.get("_load_error"):
            raise RuntimeError(f"Could not update current candidate for {candidate_id}: {status['_load_error']}")
        status["current_candidate"] = candidate_id
        entry = status["candidates"].setdefault(candidate_id, {})
        entry.update({"state": "running", "error": "", "updated_at": datetime.now().isoformat(timespec="seconds")})
        entry.pop("elapsed_seconds", None)
        _write_json(run_dir(run_id) / "status.json", status)


def reset_running(run_id: str) -> None:
    with _locked_run(run_id):
        status = load_status(run_id)
        if status.get("_load_error"):
            raise RuntimeError(f"Could not reset running candidates for run {run_id}: {status['_load_error']}")
        changed = False
        for entry in status.get("candidates", {}).values():
            if entry.get("state") == "running":
                entry["state"] = "pending"
                changed = True
        if status.get("current_candidate"):
            status["current_candidate"] = ""
            changed = True
        if changed:
            _write_json(run_dir(run_id) / "status.json", status)


def result_rows(run_id: str) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for item in load_jsonl(run_dir(run_id) / "rows.jsonl"):
        by_id[item["candidate_id"]] = item["row"]
    candidate_order = [candidate["linkedin_profile_id"] for candidate in load_candidates(run_id)]
    return [by_id[key] for key in candidate_order if key in by_id]


def result_rows_by_id(run_id: str) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for item in load_jsonl(run_dir(run_id) / "rows.jsonl"):
        rows[item["candidate_id"]] = item["row"]
    return rows


def candidate_status_rows(run_id: str, role_key: Optional[str] = None) -> list[dict[str, Any]]:
    role = role_for_run(run_id, role_key)
    candidates = load_candidates(run_id)
    status = load_status(run_id)
    status_by_id = status.get("candidates", {})
    rows_by_id = result_rows_by_id(run_id)
    ranked_rows = prepare_output_rows(list(rows_by_id.values()), role)
    rank_by_url = {row.get("Profile URL"): row.get(role.outcome_column, "") for row in ranked_rows}
    rows = []
    for candidate in candidates:
        candidate_id = candidate["linkedin_profile_id"]
        state = status_by_id.get(candidate_id, {}).get("state", "pending")
        result = rows_by_id.get(candidate_id, {})
        if result:
            state = "completed"
        source_row = candidate.get("source_row") or {}
        rows.append(
            {
                "Candidate Name": candidate.get("candidate_name") or source_row.get("Candidate Name") or candidate_id,
                "Status": _display_state(state),
                role.total_column: result.get(role.total_column, ""),
                role.outcome_column: (
                    rank_by_url.get(result.get("Profile URL"), "")
                    if role.ranked
                    else result.get(role.outcome_column, "")
                ),
                "Error Message": status_by_id.get(candidate_id, {}).get("error", ""),
            }
        )
    return rows


def completed_preview_rows(run_id: str, role_key: Optional[str] = None) -> list[dict[str, Any]]:
    role = role_for_run(run_id, role_key)
    rows = prepare_output_rows(result_rows(run_id), role) if role.ranked else result_rows(run_id)
    return [
        {
            "Candidate Name": row.get("Candidate Name") or row.get("Candidate", ""),
            role.total_column: row.get(role.total_column, ""),
            role.outcome_column: row.get(role.outcome_column, ""),
            "Score Rationale": row.get("Score Rationale", ""),
        }
        for row in rows
    ]


def role_for_run(run_id: str, override_role_key: Optional[str] = None) -> RoleProfile:
    status = load_status(run_id)
    role_key = override_role_key or status.get("role", DEFAULT_ROLE_KEY)
    return get_role_profile(role_key, status.get("custom_role_config"))


def progress_counts(run_id: str) -> dict[str, Any]:
    status = load_status(run_id)
    entries = status.get("candidates", {})
    completed_ids = set(result_rows_by_id(run_id))
    completed = len(completed_ids)
    failed = sum(1 for candidate_id, item in entries.items() if item.get("state") == "failed" and candidate_id not in completed_ids)
    skipped = sum(1 for candidate_id, item in entries.items() if item.get("state") == "skipped" and candidate_id not in completed_ids)
    running = sum(1 for item in entries.values() if item.get("state") == "running")
    total = len(entries)
    evaluated = completed + failed + skipped
    elapsed_values = [
        float(item["elapsed_seconds"])
        for item in entries.values()
        if item.get("state") in {"completed", "failed", "skipped"} and item.get("elapsed_seconds") is not None
    ]
    avg_seconds = sum(elapsed_values) / len(elapsed_values) if elapsed_values else 0.0
    return {
        "total": total,
        "evaluated": evaluated,
        "completed": completed,
        "failed": failed,
        "skipped": skipped,
        "running": running,
        "remaining": max(total - evaluated, 0),
        "current_candidate": _running_candidate_names(run_id, entries),
        "export_ready": completed > 0,
        "avg_seconds_per_candidate": avg_seconds,
    }


def save_exports(run_id: str, rows: list[dict[str, Any]], role_key: Optional[str] = None) -> tuple[Path, Path]:
    import pandas as pd

    role = role_for_run(run_id, role_key)
    output_dir = Path(OUTPUTS_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(prepare_output_rows(rows, role), columns=role.output_columns)
    csv_path = output_dir / f"candidate_evaluation_{role.key}_{run_id}.csv"
    xlsx_path = output_dir / f"candidate_evaluation_{role.key}_{run_id}.xlsx"
    frame.to_csv(csv_path, index=False)
    frame.to_excel(xlsx_path, index=False)
    return csv_path, xlsx_path


def _initial_status(
    candidates: list[dict[str, Any]],
    model: str,
    role_key: str,
    custom_role_config: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    return {
        "model": model,
        "role": role_key,
        "custom_role_config": custom_role_config if role_key == "custom" else None,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "current_candidate": "",
        "candidates": {
            candidate["linkedin_profile_id"]: {"state": "pending", "error": "", "source_index": candidate["source_index"]}
            for candidate in candidates
        },
    }


def _counts_from_status(status: dict[str, Any]) -> dict[str, int]:
    entries = status.get("candidates", {})
    return {
        "completed": sum(1 for item in entries.values() if item.get("state") == "completed"),
        "failed": sum(1 for item in entries.values() if item.get("state") == "failed"),
        "skipped": sum(1 for item in entries.values() if item.get("state") == "skipped"),
    }


def _display_state(state: str) -> str:
    return {
        "pending": "Pending",
        "running": "Running",
        "completed": "Done",
        "failed": "Failed",
        "skipped": "Skipped",
    }.get(state, state.title())


def _running_candidate_names(run_id: str, entries: dict[str, Any]) -> str:
    running_ids = {candidate_id for candidate_id, item in entries.items() if item.get("state") == "running"}
    if not running_ids:
        return ""
    names = []
    for candidate in load_candidates(run_id):
        candidate_id = candidate["linkedin_profile_id"]
        if candidate_id in running_ids:
            source_row = candidate.get("source_row") or {}
            names.append(candidate.get("candidate_name") or source_row.get("Candidate Name") or candidate_id)
    return ", ".join(names)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temp_path.replace(path)


@contextmanager
def _locked_run(run_id: str):
    path = run_dir(run_id)
    path.mkdir(parents=True, exist_ok=True)
    lock_path = path / ".progress.lock"
    with lock_path.open("a", encoding="utf-8") as handle:
        if fcntl is not None:
            fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(handle, fcntl.LOCK_UN)


def _read_text_with_retries(path: Path, attempts: int = 3, delay_seconds: float = 0.2) -> str:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, TimeoutError) as exc:
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(delay_seconds * (attempt + 1))
    if last_error:
        raise last_error
    return path.read_text(encoding="utf-8")
