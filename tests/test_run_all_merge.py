from __future__ import annotations

import json
from pathlib import Path

from src.run.run_all import _git_commit, _llm_info, _load_existing_summary


def test_load_existing_summary_missing_file_returns_empty(tmp_path: Path):
    cases, errors = _load_existing_summary(tmp_path)
    assert cases == []
    assert errors == {}


def test_load_existing_summary_reads_cases_and_errors(tmp_path: Path):
    (tmp_path / "batch_summary.json").write_text(
        json.dumps({"cases": [{"case_id": "HHG-001"}], "errors": {"HHG-002": "boom"}}),
        encoding="utf-8",
    )
    cases, errors = _load_existing_summary(tmp_path)
    assert cases == [{"case_id": "HHG-001"}]
    assert errors == {"HHG-002": "boom"}


def test_load_existing_summary_malformed_json_returns_empty(tmp_path: Path):
    (tmp_path / "batch_summary.json").write_text("{not valid", encoding="utf-8")
    cases, errors = _load_existing_summary(tmp_path)
    assert cases == []
    assert errors == {}


def test_git_commit_never_raises_and_returns_a_string():
    # Regression coverage for the UI contract fix: ui/src/contracts/
    # summary.ts requires run_id/git_commit/llm on batch_summary.json,
    # which run_all.py never produced -- BatchSummarySchema.safeParse
    # would fail on every real run. This just confirms the helper is
    # always safe to call (a git failure must not crash the batch).
    assert isinstance(_git_commit(), str)


def test_llm_info_reflects_env(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "groq")
    monkeypatch.setenv("GROQ_MODEL", "openai/gpt-oss-120b")
    assert _llm_info() == {"provider": "groq", "model": "openai/gpt-oss-120b"}

    monkeypatch.setenv("LLM_BACKEND", "ollama")
    assert _llm_info() == {"provider": "ollama", "model": "qwen3:4b-instruct"}


def test_review_targets_reject_historical_outputs_and_ancestors(tmp_path):
    import pytest
    from src.run.run_all import _validate_review_targets
    root = Path(__file__).resolve().parents[1]
    for old in [root / "cases", root / "cases/subdir", root / "runs/latest", root / "runs", root]:
        with pytest.raises(ValueError, match="Historical submission"):
            _validate_review_targets(old, tmp_path, "REVIEW-test")


def test_review_targets_require_isolated_graph_ids(tmp_path):
    import pytest
    from src.run.run_all import _validate_review_targets
    for prefix in [None, "CASE", "REVIEW-bad/slash"]:
        with pytest.raises(ValueError):
            _validate_review_targets(tmp_path / "cases", tmp_path / "run", prefix)
    _validate_review_targets(tmp_path / "cases", tmp_path / "run", "REVIEW-test")


def test_review_graph_id_does_not_replace_submission():
    from src.run.run_case import _graph_case_id
    assert _graph_case_id("REVIEW-test", "HHG-017") == "REVIEW-test-HHG-017"
    import pytest
    with pytest.raises(ValueError, match="REVIEW-"):
        _graph_case_id("CASE", "HHG-017")


async def _review_batch(monkeypatch, tmp_path, *, write_ok=True, trace_ok=True):
    from unittest.mock import AsyncMock, MagicMock
    import src.run.run_all as batch
    from src.agent.schemas import AnswerFile
    root = Path(__file__).resolve().parents[1]
    answer = AnswerFile.model_validate_json((root / "cases/HHG-017.json").read_text())
    answer.case.written_to_graph = write_ok
    answer.case.graph_case_id = "REVIEW-test-HHG-017" if write_ok else ""
    monkeypatch.setattr(batch, "_load_case_pack", lambda _: [{"case_id": "HHG-017"}])
    monkeypatch.setattr(batch, "load_dataset_index", lambda _: object())
    monkeypatch.setattr(batch, "validate_answer", lambda *args: [])
    tg = MagicMock()
    tg.__aenter__ = AsyncMock(return_value=tg)
    tg.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(batch, "TigerGraphMCP", MagicMock(return_value=tg))
    run = AsyncMock(return_value=(answer, {}))
    monkeypatch.setattr(batch, "run_single_case_with_context", run)
    def trace(*args, **kwargs):
        if not trace_ok:
            raise RuntimeError("test trace failure")
        return {"case_id": "HHG-017"}
    monkeypatch.setattr(batch, "build_trace", trace)
    result = await batch.run_all(cases_dir=tmp_path / "cases", runs_dir=tmp_path / "run",
                                 data_dir=tmp_path, graph_case_prefix="REVIEW-test")
    assert run.call_args.kwargs["graph_case_prefix"] == "REVIEW-test"
    return result


def test_review_batch_propagates_prefix_and_records_success(monkeypatch, tmp_path):
    import asyncio
    result = asyncio.run(_review_batch(monkeypatch, tmp_path))
    assert result["cases_valid"] == 1
    assert result["cases_failed"] == 0


def test_failed_graph_receipt_is_not_a_valid_completed_case(monkeypatch, tmp_path):
    import asyncio
    result = asyncio.run(_review_batch(monkeypatch, tmp_path, write_ok=False))
    assert result["cases_valid"] == 0
    assert result["cases_written_to_graph"] == 0


def test_trace_failure_is_not_a_successful_batch(monkeypatch, tmp_path):
    import asyncio
    result = asyncio.run(_review_batch(monkeypatch, tmp_path, trace_ok=False))
    assert result["cases_failed"] == 1
    assert "Trace generation failed" in result["errors"]["HHG-017"]
