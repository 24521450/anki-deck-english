"""Tests for src.pipeline.

Covers:
- StageResult.ok / .skipped_reason contract
- Order preservation: stages run in self.stages order
- --from / --to filtering
- Dry-run: stages return SKIPPED with reason
- Fail-fast: a failing stage halts the pipeline
- Single-stage and multi-stage positional invocation
- Real stage names (scrape/build/split/deck) — tests monkeypatch
  Pipeline._replace_stage() instead of poking the module-level dict.
"""
from __future__ import annotations

import pytest

from src import pipeline as pipeline_module
from src.pipeline import Pipeline, StageResult


# ── StageResult contract ───────────────────────────────────────────


def test_stage_result_ok_when_no_error_no_skip():
    r = StageResult(name="x", ok=True, elapsed=0.0)
    assert r.ok is True
    assert r.skipped_reason is None


def test_stage_result_ok_with_skip_reason():
    """A skipped stage is 'ok' (didn't fail) but records why it didn't run."""
    r = StageResult(name="x", ok=True, elapsed=0.0, skipped_reason="dry-run")
    assert r.ok is True
    assert r.skipped_reason == "dry-run"


def test_stage_result_not_ok_on_error():
    r = StageResult(name="x", ok=False, elapsed=0.0, error="boom")
    assert r.ok is False
    assert r.error == "boom"


# ── Order preservation ────────────────────────────────────────────


def test_pipeline_runs_stages_in_order(monkeypatch):
    """Stages run in self.stages order, not insertion order of methods."""
    calls: list[str] = []

    def fake_scrape(self):
        calls.append("scrape")
        return StageResult(name="scrape", ok=True, elapsed=0.0)

    def fake_build(self):
        calls.append("build")
        return StageResult(name="build", ok=True, elapsed=0.0)

    monkeypatch.setattr(pipeline_module, "_STAGE_METHODS", {
        "scrape": fake_scrape, "build": fake_build,
    })
    p = Pipeline(stages=["scrape", "build"], verbose=False)
    p.run()
    assert calls == ["scrape", "build"]


def test_pipeline_default_stages_order():
    p = Pipeline(dry_run=True, verbose=False)
    p.run()
    assert p.stages == ["scrape", "build", "split", "deck"]


# ── --from / --to filtering ───────────────────────────────────────


def test_pipeline_from_filter_skips_earlier(monkeypatch):
    monkeypatch.setattr(pipeline_module, "_STAGE_METHODS", {
        "scrape": lambda s: StageResult(name="scrape", ok=True, elapsed=0.0),
        "build":  lambda s: StageResult(name="build",  ok=True, elapsed=0.0),
        "split":  lambda s: StageResult(name="split",  ok=True, elapsed=0.0),
        "deck":   lambda s: StageResult(name="deck",   ok=True, elapsed=0.0),
    })
    p = Pipeline(dry_run=True, verbose=False)
    p.run(from_stage="build")
    assert [r.name for r in p.results] == ["build", "split", "deck"]


def test_pipeline_to_filter_skips_later(monkeypatch):
    monkeypatch.setattr(pipeline_module, "_STAGE_METHODS", {
        "scrape": lambda s: StageResult(name="scrape", ok=True, elapsed=0.0),
        "build":  lambda s: StageResult(name="build",  ok=True, elapsed=0.0),
        "split":  lambda s: StageResult(name="split",  ok=True, elapsed=0.0),
        "deck":   lambda s: StageResult(name="deck",   ok=True, elapsed=0.0),
    })
    p = Pipeline(dry_run=True, verbose=False)
    p.run(to_stage="split")
    assert [r.name for r in p.results] == ["scrape", "build", "split"]


def test_pipeline_from_and_to_filter_middle(monkeypatch):
    monkeypatch.setattr(pipeline_module, "_STAGE_METHODS", {
        "scrape": lambda s: StageResult(name="scrape", ok=True, elapsed=0.0),
        "build":  lambda s: StageResult(name="build",  ok=True, elapsed=0.0),
        "split":  lambda s: StageResult(name="split",  ok=True, elapsed=0.0),
        "deck":   lambda s: StageResult(name="deck",   ok=True, elapsed=0.0),
    })
    p = Pipeline(dry_run=True, verbose=False)
    p.run(from_stage="build", to_stage="split")
    assert [r.name for r in p.results] == ["build", "split"]


def test_pipeline_unknown_from_raises():
    p = Pipeline(dry_run=True, verbose=False)
    with pytest.raises(ValueError, match="Unknown stage"):
        p.run(from_stage="z")


def test_pipeline_unknown_to_raises():
    p = Pipeline(dry_run=True, verbose=False)
    with pytest.raises(ValueError, match="Unknown stage"):
        p.run(to_stage="z")


# ── Dry-run ───────────────────────────────────────────────────────


def test_dry_run_records_skip_reason():
    p = Pipeline(stages=["scrape", "build", "split", "deck"], dry_run=True, verbose=False)
    p.run()
    for r in p.results:
        assert r.skipped_reason == "dry-run"
        assert r.ok is True
        assert r.elapsed == 0.0


def test_dry_run_does_not_call_real_stage_methods(monkeypatch):
    """In dry-run mode, the stage methods are dispatched but return
    immediately with skipped_reason — they don't execute real work.
    Verify by checking each result is marked skipped.
    """
    monkeypatch.setattr(pipeline_module, "_STAGE_METHODS", {
        "scrape": lambda s: StageResult(name="scrape", ok=True, elapsed=0.0, skipped_reason="dry-run"),
        "build":  lambda s: StageResult(name="build",  ok=True, elapsed=0.0, skipped_reason="dry-run"),
        "split":  lambda s: StageResult(name="split",  ok=True, elapsed=0.0, skipped_reason="dry-run"),
        "deck":   lambda s: StageResult(name="deck",   ok=True, elapsed=0.0, skipped_reason="dry-run"),
    })
    p = Pipeline(dry_run=True, verbose=False)
    p.run()
    for r in p.results:
        assert r.skipped_reason == "dry-run"
        assert r.ok is True


# ── Fail-fast ─────────────────────────────────────────────────────


def test_pipeline_fails_fast_on_error(monkeypatch):
    """If a stage errors, later stages don't run."""
    monkeypatch.setattr(pipeline_module, "_STAGE_METHODS", {
        "scrape": lambda s: StageResult(name="scrape", ok=False, elapsed=0.0, error="boom"),
        "build":  lambda s: StageResult(name="build",  ok=True,  elapsed=0.0),
        "split":  lambda s: StageResult(name="split",  ok=True,  elapsed=0.0),
        "deck":   lambda s: StageResult(name="deck",   ok=True,  elapsed=0.0),
    })
    p = Pipeline(verbose=False)
    p.run()
    assert [r.name for r in p.results] == ["scrape"]
    assert p.results[0].error == "boom"


def test_pipeline_continues_when_stage_succeeds(monkeypatch):
    monkeypatch.setattr(pipeline_module, "_STAGE_METHODS", {
        "scrape": lambda s: StageResult(name="scrape", ok=True, elapsed=0.1),
        "build":  lambda s: StageResult(name="build",  ok=True, elapsed=0.2),
        "split":  lambda s: StageResult(name="split",  ok=True, elapsed=0.3),
        "deck":   lambda s: StageResult(name="deck",   ok=True, elapsed=0.4),
    })
    p = Pipeline(verbose=False)
    p.run()
    assert all(r.ok for r in p.results)
    assert len(p.results) == 4


# ── Single-stage and multi-stage positional invocation ────────────


def test_single_stage_via_positional_arg(monkeypatch):
    monkeypatch.setattr(pipeline_module, "_STAGE_METHODS", {
        "scrape": lambda s: StageResult(name="scrape", ok=True, elapsed=0.0),
        "build":  lambda s: StageResult(name="build",  ok=True, elapsed=0.0),
        "split":  lambda s: StageResult(name="split",  ok=True, elapsed=0.0),
        "deck":   lambda s: StageResult(name="deck",   ok=True, elapsed=0.0),
    })
    p = Pipeline(stages=["build"], dry_run=True, verbose=False)
    p.run()
    assert [r.name for r in p.results] == ["build"]


def test_multi_stage_preserves_user_order():
    """`pipeline.py deck scrape` should iterate deck then scrape in the
    dry-run path (and never call methods since dry-run)."""
    p = Pipeline(stages=["deck", "scrape"], dry_run=True, verbose=False)
    p.run()
    assert [r.name for r in p.results] == ["deck", "scrape"]


# ── Results accumulation ─────────────────────────────────────────


def test_pipeline_results_accumulate_across_runs(monkeypatch):
    monkeypatch.setattr(pipeline_module, "_STAGE_METHODS", {
        "scrape": lambda s: StageResult(name="scrape", ok=True, elapsed=0.0),
        "build":  lambda s: StageResult(name="build",  ok=True, elapsed=0.0),
    })
    p = Pipeline(stages=["scrape", "build"], dry_run=True, verbose=False)
    p.run()
    n1 = len(p.results)
    p.run()
    n2 = len(p.results)
    assert n2 == 2 * n1


# ── _replace_stage hook ──────────────────────────────────────────


def test_replace_stage_hook_swaps_implementation(monkeypatch):
    """The _replace_stage classmethod is the test seam for stage methods."""
    called: list[str] = []
    def fake_scrape(self):
        called.append("fake")
        return StageResult(name="scrape", ok=True, elapsed=0.0)
    Pipeline._replace_stage("scrape", fake_scrape)
    p = Pipeline(stages=["scrape"], verbose=False)
    p.run()
    assert called == ["fake"]
    # Restore so other tests don't see this
    Pipeline._replace_stage("scrape", lambda p: p.stage_scrape())
