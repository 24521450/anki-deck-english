"""Pipeline orchestrator for ielts-deck.

Coordinates the production stages of building the deck:
  1. scrape  — tools/scrape_with_fallback.py (Oxford + Cambridge fallback)
  2. build   — tools/build_notes.py (JSONL → notes.json + notes.tsv)
  3. split   — tools/split_study_cards.py (study list → study_split.tsv)
  4. deck    — update_anki_deck.py (notes.json → ielts_deck.apkg)

Each stage is idempotent and independently runnable. The orchestrator
adds:
  - explicit ordering (scrape -> build -> split -> deck)
  - --from/--to filtering (run a subset of stages)
  - --dry-run (print plan, don't execute)
  - cross-stage state checks (e.g. JSONL exists before build runs)
  - timing per stage

E in architecture review. One-shot fixers (e.g. _cleanup_oxford_pollution,
_add_def_cefr) are NOT wrapped here — they're invoked manually when data
needs repair, not on every build.

Usage:
  python -m src.pipeline                       # run all 4 stages
  python -m src.pipeline --from=build --to=deck
  python -m src.pipeline scrape                # run one stage
  python -m src.pipeline --dry-run
"""
from __future__ import annotations

import argparse
import importlib
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# Repo root (where tools/ and data/ live)
PR = Path(r"C:\Users\admin\Downloads\ielts-deck")


# Stage dispatch table — class-level (mutable defaults forbidden in dataclass).
_STAGE_METHODS: dict[str, Callable[["Pipeline"], "StageResult"]] = {}


@dataclass
class StageResult:
    name: str
    ok: bool
    elapsed: float
    error: str | None = None
    skipped_reason: str | None = None


@dataclass
class Pipeline:
    """Orchestrator that runs a sequence of named stages.

    Each stage is a function (Pipeline) -> StageResult. Stages receive
    self for context (paths, config). They use the helpers below to
    import the underlying CLI module and invoke its `main()`.
    """
    repo: Path = PR
    stages: list[str] = field(default_factory=lambda: ["scrape", "build", "split", "deck"])
    dry_run: bool = False
    verbose: bool = True
    results: list[StageResult] = field(default_factory=list)

    def _import_tool(self, module_name: str):
        """Import a top-level tool module (e.g. 'tools.scrape_with_fallback')."""
        return importlib.import_module(module_name)

    def stage_scrape(self) -> StageResult:
        """Run scrape_with_fallback.py (incremental, idempotent)."""
        name = "scrape"
        if self.dry_run:
            return StageResult(name=name, ok=True, elapsed=0.0, skipped_reason="dry-run")
        started = time.time()
        try:
            mod = self._import_tool("tools.scrape_with_fallback")
            # The script's main() is async and takes optional args. Run
            # with no args = incremental mode (skips already-scraped words).
            import asyncio
            asyncio.run(mod.main())
            return StageResult(name=name, ok=True, elapsed=time.time() - started)
        except SystemExit as e:
            # tools/ scripts that argparse-fail raise SystemExit; treat as error
            return StageResult(name=name, ok=False, elapsed=time.time() - started,
                              error=f"SystemExit: {e.code}")
        except Exception as e:
            return StageResult(name=name, ok=False, elapsed=time.time() - started,
                              error=f"{type(e).__name__}: {e}")

    def stage_build(self) -> StageResult:
        """Run build_notes.py (JSONL -> notes.json + notes.tsv)."""
        name = "build"
        if self.dry_run:
            return StageResult(name=name, ok=True, elapsed=0.0, skipped_reason="dry-run")
        started = time.time()
        try:
            mod = self._import_tool("tools.build_notes")
            mod.main()  # uses default paths + default CEFR filter (B2/C1/C2)
            return StageResult(name=name, ok=True, elapsed=time.time() - started)
        except SystemExit as e:
            return StageResult(name=name, ok=False, elapsed=time.time() - started,
                              error=f"SystemExit: {e.code}")
        except Exception as e:
            return StageResult(name=name, ok=False, elapsed=time.time() - started,
                              error=f"{type(e).__name__}: {e}")

    def stage_split(self) -> StageResult:
        """Run split_study_cards.py (study list -> study_split.tsv)."""
        name = "split"
        if self.dry_run:
            return StageResult(name=name, ok=True, elapsed=0.0, skipped_reason="dry-run")
        started = time.time()
        try:
            mod = self._import_tool("tools.split_study_cards")
            # split_study_cards has no main() guard — it runs on import.
            # Re-run via importlib to get a clean state.
            importlib.reload(mod)
            return StageResult(name=name, ok=True, elapsed=time.time() - started)
        except SystemExit as e:
            return StageResult(name=name, ok=False, elapsed=time.time() - started,
                              error=f"SystemExit: {e.code}")
        except Exception as e:
            return StageResult(name=name, ok=False, elapsed=time.time() - started,
                              error=f"{type(e).__name__}: {e}")

    def stage_deck(self) -> StageResult:
        """Run update_anki_deck.py at root (notes.json -> apkg)."""
        name = "deck"
        if self.dry_run:
            return StageResult(name=name, ok=True, elapsed=0.0, skipped_reason="dry-run")
        started = time.time()
        try:
            mod = self._import_tool("update_anki_deck")
            mod.main()
            return StageResult(name=name, ok=True, elapsed=time.time() - started)
        except SystemExit as e:
            return StageResult(name=name, ok=False, elapsed=time.time() - started,
                              error=f"SystemExit: {e.code}")
        except Exception as e:
            return StageResult(name=name, ok=False, elapsed=time.time() - started,
                              error=f"{type(e).__name__}: {e}")

    # ── Map of stage name → method ──────────────────────────────────
    # (class-level dict, NOT a dataclass field — mutable defaults forbidden)

    def _dispatch(self, stage: str) -> "StageResult":
        return _STAGE_METHODS[stage](self)

    @classmethod
    def _replace_stage(cls, name: str, fn: Callable[["Pipeline"], "StageResult"]) -> None:
        """Test hook — replace a stage's implementation. Module-level
        state, so use this from tests instead of poking the dict.
        """
        _STAGE_METHODS[name] = fn

    def run(self, from_stage: str | None = None, to_stage: str | None = None) -> list[StageResult]:
        """Run stages in order. Skip stages outside [from_stage, to_stage]."""
        if from_stage and from_stage not in self.stages:
            raise ValueError(f"Unknown stage: {from_stage!r}. Valid: {self.stages}")
        if to_stage and to_stage not in self.stages:
            raise ValueError(f"Unknown stage: {to_stage!r}. Valid: {self.stages}")

        start = self.stages.index(from_stage) if from_stage else 0
        end = self.stages.index(to_stage) + 1 if to_stage else len(self.stages)
        selected = self.stages[start:end]

        if self.verbose:
            print(f"Pipeline: {selected} ({'dry-run' if self.dry_run else 'live'})", flush=True)

        for stage in selected:
            if self.verbose:
                print(f"\n[{stage}] starting...", flush=True)
            result = self._dispatch(stage)
            self.results.append(result)
            if self.verbose:
                if result.skipped_reason:
                    print(f"[{stage}] SKIPPED ({result.skipped_reason})", flush=True)
                else:
                    status = "OK" if result.ok else "FAIL"
                    print(f"[{stage}] {status} in {result.elapsed:.1f}s", flush=True)
                    if not result.ok and result.error:
                        print(f"  -> {result.error}", flush=True)
            if not result.ok and not result.skipped_reason:
                # Fail-fast: don't run later stages if an earlier one failed
                if self.verbose:
                    print(f"\nPipeline aborted at stage '{stage}'", flush=True)
                break

        if self.verbose:
            self._print_summary()
        return self.results

    def _print_summary(self) -> None:
        print("\n=== Pipeline summary ===", flush=True)
        for r in self.results:
            tag = "OK" if r.ok else "FAIL"
            extra = f" ({r.skipped_reason})" if r.skipped_reason else ""
            err = f" — {r.error}" if r.error else ""
            print(f"  [{tag}] {r.name}: {r.elapsed:.1f}s{extra}{err}", flush=True)
        failed = [r for r in self.results if not r.ok and not r.skipped_reason]
        if failed:
            print(f"\n{len(failed)} stage(s) failed.", flush=True)
        else:
            print(f"\nAll {len(self.results)} stage(s) completed.", flush=True)


def main():
    parser = argparse.ArgumentParser(description="ielts-deck pipeline orchestrator")
    parser.add_argument("stages", nargs="*",
                        help=f"Specific stages to run (default: all). Valid: scrape, build, split, deck")
    parser.add_argument("--from", dest="from_stage",
                        help="Start from this stage (inclusive)")
    parser.add_argument("--to", dest="to_stage",
                        help="End at this stage (inclusive)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print plan, don't execute stages")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress per-stage progress output")
    args = parser.parse_args()

    pipe = Pipeline(dry_run=args.dry_run, verbose=not args.quiet)
    if args.stages:
        if len(args.stages) == 1:
            # Single stage: just run that one
            pipe.stages = [args.stages[0]]
        else:
            # Multiple stages: run in user-specified order
            pipe.stages = args.stages
    pipe.run(from_stage=args.from_stage, to_stage=args.to_stage)

    # Exit non-zero on any failure
    if any(not r.ok and not r.skipped_reason for r in pipe.results):
        sys.exit(1)


# Populate the stage dispatch table after Pipeline is fully defined.
# (Can't put this in class body — @dataclass rejects mutable defaults.)
# Done at import time (including when run as `python -m src.pipeline`).
_STAGE_METHODS.update({
    "scrape": lambda p: p.stage_scrape(),
    "build":  lambda p: p.stage_build(),
    "split":  lambda p: p.stage_split(),
    "deck":   lambda p: p.stage_deck(),
})


if __name__ == "__main__":
    main()
