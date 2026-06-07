# AGENTS.md

IELTS / Academic English Anki deck builder — notes DB + scraper pipeline (Oxford / Cambridge + AWL + audio TTS).

## Setup commands

- Install deps: `pip install -r requirements.txt` (then `python -c "import nltk; nltk.download('wordnet'); nltk.download('omw-1.4')"`)
- Build (editable): `pip install -e .`
- Test: `pytest` — config in `pyproject.toml [tool.pytest.ini_options]`, `testpaths = ["tests"]`, `pythonpath = ["."]`
- Lint: not configured — match existing style, no new lint configs without asking

## Project layout

- `src/` — Python package (per `pyproject.toml [tool.setuptools]` — package skeleton not yet committed)
  - `scraper/` — owned by `scraper` rein: Oxford/Cambridge + AWL data ingestion, audio TTS
  - `deck_builder/` — owned by `deck-builder` rein: `.apkg` packaging, EAVM note type generation
  - `config.py` — shared config
- `tests/` — pytest tests, mostly mirrored layout (`tests/scraper/test_x.py` ↔ `src/scraper/x.py`). Non-mirrored layout allowed for cross-cutting infra (e.g. `tests/design/test_design_sync.py`).
- `tools/` — standalone CLI scripts and shared helpers (not part of `src/` package). Leading-underscore names (`_foo.py`) are private/inspector scripts; no-underscore names are real tools (e.g. `check_design_sync.py`, `scrape_oxford.py`).
- `data/` — scraped + cleaned word records; `.cache_html/` and `*.bak` are gitignored
- `audio/` — generated TTS files (UK/US per word)
- `design/` — Anki card visual design system. **`design/index.html` (vùng 2 card CSS) is the source of truth** — `EAVM/styling.txt` derives from it and is baked into `.apkg`. `tools/check_design_sync.py` enforces the sync.
- `vocab_list/` — source word lists (Oxford 3000/5000 markdown, AWL json/yml)
- `update_anki_deck.py` — top-level entry point that runs the full pipeline (referenced by `design/EAVM/README.md`; not yet committed — owned by `developer` rein)

## Architecture context

For non-trivial tasks, read `.understand-anything/knowledge-graph.json` for the structural map (files, layers, tour).

If the file is missing or stale, run `/understand --full` to (re)build it.

Refresh with `/understand --full` after major refactors.

## Code style

- Python 3.10+ (async-friendly: `edge-tts`, `aiohttp`)
- Async I/O for scraping + TTS — match the existing pattern, don't mix blocking
- No formal docstring format enforced; brief comments are fine
- For the `ielts-deck` team: read `.harness/agent.md` first, route to the right rein

## Testing instructions

- `pytest` only — no new test framework without asking
- Add tests for every new behavior — see existing `tests/test_extraction.py` (expected path, not yet committed)
- All tests must pass before commit
- `pythonpath = ["."]` in pytest config → use absolute imports via `src.*`

## PR & commit conventions

- **Single-branch project** — commit directly to `main`. No feature branches, no PRs.
- Conventional commits (`feat:` / `fix:` / `docs:` / `refactor:`)
- One concern per commit — don't bundle scraper change with design change
- Run `pytest` before pushing; red build = revert or fix-forward

## Domain-specific notes

### Audio TTS fallback chain
For each `(word, accent ∈ {UK, US})` pair, try in order:
1. Cambridge dictionary audio URL
2. Oxford Learner's audio URL
3. `edge-tts` synthesis (last resort)

### EAVM note type
The Anki note type `English Academic Vocabulary Model` is generated from
`design/EAVM/{front,back}_template.txt` + `styling.txt`. Do **not** hand-edit
fields inside Anki — edit the templates and re-run the packager. See
`design/EAVM/README.md § Lưu ý quan trọng khi chỉnh sửa JavaScript` for the
literal-newline gotcha in template JS.

### Design system sync
`design/index.html` (vùng 2) is the **source of truth** for the card CSS.
`design/EAVM/styling.txt` is auto-baked into `.apkg` and **must** stay in sync
with `index.html`. Enforce via:

- `python -m tools.check_design_sync` — CLI, exit 0/1
- `pytest tests/design/` — pytest version, share core parser

Selector class names in `index.html` are **immutable contracts** — renaming
breaks every template that references them. To mark a rule as preview-only
(don't sync to `.apkg`), add `/* @preview-only */` on its own line immediately
before the rule. See `design/README.md` for the full workflow.

### Data freshness
`vocab_list/` is the seed. The scraper re-validates against live pages to catch
new examples, IPA changes, and CEFR re-classifications.

## Security

- Never commit scraped HTML that contains user data (current sources are public dictionaries — fine)
- `.cache_html/`, `*.apkg`, `data/*.bak` are gitignored — keep it that way
- Any paid-service API keys go in `.env` (gitignored), never in code
