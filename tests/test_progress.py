from __future__ import annotations

import os
from pathlib import Path

import pytest

from candidate_evaluator import progress as progress_module
from candidate_evaluator.progress import (
    candidate_status_rows,
    commit_batch_results,
    completed_preview_rows,
    init_run,
    load_status,
    mark_completed,
    mark_failed,
    mark_skipped,
    progress_counts,
    record_api_usage,
    recover_batch_results,
    result_rows,
    role_for_run,
)


def _batch_usage() -> dict[str, int]:
    return {
        "api_calls": 1,
        "input_tokens": 100,
        "cached_input_tokens": 80,
        "cache_write_tokens": 0,
        "output_tokens": 40,
        "reasoning_tokens": 30,
        "total_tokens": 140,
    }


def test_progress_tracks_completed_and_failed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    candidates = [
        {"source_index": 0, "linkedin_profile_id": "a", "source_row": {"Candidate Name": "A"}},
        {"source_index": 1, "linkedin_profile_id": "b", "source_row": {"Candidate Name": "B"}},
    ]
    init_run("run-1", candidates, "rubric", "model")
    mark_completed("run-1", "a", {"Candidate Name": "A"}, {"ok": True}, elapsed_seconds=10)
    mark_failed("run-1", "b", "bad output", elapsed_seconds=20)
    counts = progress_counts("run-1")
    assert counts["total"] == 2
    assert counts["evaluated"] == 2
    assert counts["completed"] == 1
    assert counts["failed"] == 1
    assert counts["running"] == 0
    assert counts["remaining"] == 0
    assert counts["export_ready"] is True
    assert counts["avg_seconds_per_candidate"] == 15
    assert result_rows("run-1") == [{"Candidate Name": "A"}]
    assert load_status("run-1")["candidates"]["b"]["error"] == "bad output"
    assert os.path.exists("work/runs/run-1/status.json")

    status_rows = candidate_status_rows("run-1")
    assert status_rows == [
        {
            "Candidate Name": "A",
            "Status": "Done",
            "Total Score": "",
            "Ranking": "",
            "Error Message": "",
        },
        {
            "Candidate Name": "B",
            "Status": "Failed",
            "Total Score": "",
            "Ranking": "",
            "Error Message": "bad output",
        },
    ]
    assert completed_preview_rows("run-1") == [
        {
            "Candidate Name": "A",
            "Total Score": "",
            "Ranking": "",
            "Score Rationale": "",
        }
    ]


def test_progress_stores_role_and_uses_qa_decision_column(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    candidates = [
        {"source_index": 0, "linkedin_profile_id": "a", "source_row": {"Candidate Name": "A"}},
    ]
    init_run("run-qa", candidates, "rubric", "model", role_key="qa")
    row = {"Candidate Name": "A", "Total Score": 72, "Decision": "Shortlist", "Score Rationale": "Good QA evidence."}
    mark_completed("run-qa", "a", row, {"ok": True}, elapsed_seconds=5)
    assert load_status("run-qa")["role"] == "qa"
    assert role_for_run("run-qa").key == "qa"
    assert candidate_status_rows("run-qa") == [
        {
            "Candidate Name": "A",
            "Status": "Done",
            "Total Score": 72,
            "Decision": "Shortlist",
            "Error Message": "",
        }
    ]
    assert completed_preview_rows("run-qa") == [
        {
            "Candidate Name": "A",
            "Total Score": 72,
            "Decision": "Shortlist",
            "Score Rationale": "Good QA evidence.",
        }
    ]


def test_progress_stores_provider_model_and_reasoning_without_api_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    candidates = [
        {"source_index": 0, "linkedin_profile_id": "a", "source_row": {"Candidate Name": "A"}},
    ]
    init_run(
        "run-deepseek",
        candidates,
        "rubric",
        "deepseek-flash",
        provider_key="deepseek",
        reasoning_effort="low",
    )

    status = load_status("run-deepseek")
    assert status["provider"] == "deepseek"
    assert status["model"] == "deepseek-flash"
    assert status["reasoning_effort"] == "low"
    assert "api_key" not in status


def test_backend_progress_uses_final_score_and_computed_rank(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    candidates = [
        {"source_index": 0, "linkedin_profile_id": "a", "candidate_name": "A", "source_row": {"Candidate Name": "A"}},
        {"source_index": 1, "linkedin_profile_id": "b", "candidate_name": "B", "source_row": {"Candidate Name": "B"}},
    ]
    init_run("run-backend", candidates, "rubric", "model", role_key="backend")
    base = {
        "PHP Score (/20)": 10,
        "Python Score (/20)": 10,
        "Laravel Score (/12)": 5,
        "AWS Score (/8)": 5,
        "Final Score (/60)": 30,
        "Weighted Recency Subtotal": 8,
        "Weighted Duration Subtotal": 7,
        "Weighted Evidence Subtotal": 15,
        "Score Rationale": "Backend evidence.",
    }
    mark_completed("run-backend", "a", {**base, "Candidate": "A", "Profile URL": "a"}, {"ok": True})
    mark_completed(
        "run-backend",
        "b",
        {**base, "Candidate": "B", "Profile URL": "b", "PHP Score (/20)": 12, "Python Score (/20)": 8},
        {"ok": True},
    )
    status = candidate_status_rows("run-backend")
    assert status[0]["Final Score (/60)"] == 30
    assert status[0]["Rank Number"] == 2
    assert status[1]["Rank Number"] == 1
    preview = completed_preview_rows("run-backend")
    assert [row["Candidate Name"] for row in preview] == ["B", "A"]


def test_progress_tracks_skipped_without_exporting_it(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    candidates = [
        {"source_index": 0, "linkedin_profile_id": "a", "source_row": {"Candidate Name": "A"}},
        {"source_index": 1, "linkedin_profile_id": "b", "source_row": {"Candidate Name": "B"}},
    ]
    init_run("run-skip", candidates, "rubric", "model")
    mark_completed("run-skip", "a", {"Candidate Name": "A"}, {"ok": True}, elapsed_seconds=10)
    mark_skipped("run-skip", "b", "Skipped before API call: no experience entries.")

    counts = progress_counts("run-skip")
    assert counts["evaluated"] == 2
    assert counts["completed"] == 1
    assert counts["failed"] == 0
    assert counts["skipped"] == 1
    assert counts["remaining"] == 0
    assert counts["avg_seconds_per_candidate"] == 10
    assert result_rows("run-skip") == [{"Candidate Name": "A"}]
    assert candidate_status_rows("run-skip")[1]["Status"] == "Skipped"


def test_progress_accumulates_real_usage_receipts_across_batches(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    candidates = [
        {"source_index": index, "linkedin_profile_id": f"candidate-{index}", "source_row": {}}
        for index in range(10)
    ]
    init_run("run-usage", candidates, "rubric", "model")

    record_api_usage(
        "run-usage",
        {
            "api_calls": 1,
            "input_tokens": 8000,
            "cached_input_tokens": 0,
            "cache_write_tokens": 0,
            "output_tokens": 2000,
            "reasoning_tokens": 100,
            "total_tokens": 10000,
        },
    )
    record_api_usage(
        "run-usage",
        {
            "api_calls": 1,
            "input_tokens": 7500,
            "cached_input_tokens": 3000,
            "cache_write_tokens": 0,
            "output_tokens": 1900,
            "reasoning_tokens": 80,
            "total_tokens": 9400,
        },
    )

    assert progress_counts("run-usage")["api_usage"] == {
        "api_calls": 2,
        "input_tokens": 15500,
        "cached_input_tokens": 3000,
        "cache_write_tokens": 0,
        "output_tokens": 3900,
        "reasoning_tokens": 180,
        "total_tokens": 19400,
    }


def test_batch_results_and_usage_are_committed_together(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    candidates = [
        {"source_index": 0, "linkedin_profile_id": "a", "source_row": {"Candidate Name": "A"}},
        {"source_index": 1, "linkedin_profile_id": "b", "source_row": {"Candidate Name": "B"}},
    ]
    init_run("run-batch", candidates, "rubric", "model")

    commit_batch_results(
        "run-batch",
        candidates,
        {
            "usage": _batch_usage(),
            "results": [
                {
                    "state": "completed",
                    "row": {"Candidate Name": "A", "Total Score": 10},
                    "raw": {"candidate_number": 1},
                    "elapsed_seconds": 2,
                },
                {
                    "state": "completed",
                    "row": {"Candidate Name": "B", "Total Score": 20},
                    "raw": {"candidate_number": 2},
                    "elapsed_seconds": 2,
                },
            ],
        },
    )

    counts = progress_counts("run-batch")
    assert counts["completed"] == 2
    assert counts["remaining"] == 0
    assert counts["api_usage"] == _batch_usage()
    assert result_rows("run-batch") == [
        {"Candidate Name": "A", "Total Score": 10},
        {"Candidate Name": "B", "Total Score": 20},
    ]


def test_staged_batch_is_recovered_after_interruption_without_double_charging(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    candidates = [
        {"source_index": 0, "linkedin_profile_id": "a", "source_row": {"Candidate Name": "A"}},
        {"source_index": 1, "linkedin_profile_id": "b", "source_row": {"Candidate Name": "B"}},
    ]
    init_run("run-recovery", candidates, "rubric", "model")
    batch_result = {
        "usage": _batch_usage(),
        "results": [
            {
                "state": "completed",
                "row": {"Candidate Name": "A"},
                "raw": {"candidate_number": 1},
                "elapsed_seconds": 3,
            },
            {
                "state": "completed",
                "row": {"Candidate Name": "B"},
                "raw": {"candidate_number": 2},
                "elapsed_seconds": 3,
            },
        ],
    }

    original_apply = progress_module._apply_batch_receipt
    monkeypatch.setattr(
        progress_module,
        "_apply_batch_receipt",
        lambda _run_id, _receipt: (_ for _ in ()).throw(RuntimeError("simulated page interruption")),
    )
    with pytest.raises(RuntimeError, match="simulated page interruption"):
        commit_batch_results("run-recovery", candidates, batch_result)

    assert progress_counts("run-recovery")["completed"] == 0
    assert progress_counts("run-recovery")["api_usage"]["api_calls"] == 0

    monkeypatch.setattr(progress_module, "_apply_batch_receipt", original_apply)
    assert recover_batch_results("run-recovery") == 1
    assert progress_counts("run-recovery")["completed"] == 2
    assert progress_counts("run-recovery")["api_usage"] == _batch_usage()

    assert recover_batch_results("run-recovery") == 0
    assert progress_counts("run-recovery")["api_usage"] == _batch_usage()
