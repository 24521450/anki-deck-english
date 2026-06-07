# Handoff — IELTS Anki Deck: Design v2 — COMPLETED

**Date:** 2026-06-07  
**Workspace:** `C:\Users\admin\Downloads\ielts-deck`  
**Corpus:** `24521450/anki-deck-english`  
**Next session focus:** Migration script (pipe-sep → Def1/Ex1 fields) + scraper update + `.apkg` rebuild.

---

## Project Context

IELTS Academic English Anki deck builder. Pipeline: scraper (Oxford/Cambridge + AWL) → note DB → `.apkg` packager.

- Note type: **English Academic Vocabulary Model (EAVM)**
- Templates: `design/EAVM/front_template.txt`, `back_template.txt`, `styling.txt`
- Design preview (source of visual truth): `design/index.html`
- Demo reference: `design/demo_test/index.html`
- Existing notes export: `data/English Academic Vocabulary.txt` (~5000 notes, TSV)
- Read `AGENTS.md` at repo root before touching anything.

---

## Work Done This Session — ALL DESIGN TASKS COMPLETE

### Status: EAVM Templates Fully Synced ✅

All design improvements from `demo_test/index.html` have been applied to the production EAVM files.

| Task | Description | Status |
|------|-------------|--------|
| B | `back_template.txt` — L3 grid, badge hierarchy, WF chips, word highlight, feature-row | ✅ DONE |
| C | `styling.txt` — v2 CSS appended (14,570 bytes, was 9,224) | ✅ DONE |
| D | `front_template.txt` — sense-count dots, corpus separator, cleaner JS | ✅ DONE |
| E | `design/index.html` — CSS + Section 01/02 synced to v2 layout | ✅ DONE |
| A | `src/deck_builder/migrate_fields.py` — migration script | ❌ NOT STARTED |
| F | Scraper — write Def1/Ex1…Def3/Ex3 natively | ❌ NOT STARTED |

---

## Design Decisions Finalized

### Field Schema — KEPT PIPE-SEPARATED (Decision Revised)

**Earlier plan** was to split `Definition`/`Example` into `Def1/Ex1`…`Def3/Ex3` fields.  
**Actual implementation:** Kept `Definition` (pipe-sep) + `Example` (pipe-sep). JS in the template does `split('|')` and renders as L3 grid. No new Anki fields needed for the visual design.

The Def1/Ex1 migration is still desirable long-term (simpler JS, better Anki field hygiene) but is NOT a blocker for the current design.

### Badge Hierarchy (implemented in back_template)

```
top-bar-left: [POS chips] [separator] [corpus badges]
top-bar-right: [CEFR badge]
meta-row: [IPA pill] [usage-tag]  ← old_fashioned, dialect, trademark, etc.
senses grid: L3 def/ex layout
word-family-box: WF chips
collocations: chips
feature-row: idioms, phrasal verbs  ← moved from footer (footer removed)
```

### All Design Tokens

| Element | Value |
|---------|-------|
| Sense grid | `grid-template-columns: 55fr 45fr` |
| Sense num badge | `color: #a78bfa; background: #2d2850; border-radius: 3px` |
| Word highlight | underline `rgba(167,139,250,0.45)`, `font-weight: 700`, `color: #f1f5f9` |
| IPA pill | JetBrains Mono, `background: #1b1a1a`, `border: 1px solid #272626` |
| WF chip POS colors | n=teal, v=blue, adj=purple, adv=amber, phr=orange |
| Sense count dots | 5px circles, `#2e2d2d`, only injected when `Definition.split('|').length > 1` |
| POS chip | 11px, padding 3px 12px, `#222121` bg |
| Fade animation | `fadeSlideIn 0.24s cubic-bezier(0.16,1,0.3,1)` |

### Dropped / Rejected

- Front card glow — rejected ("xấu")
- Source/AudioSource footer badges — removed
- Mobile-first CSS — explicitly excluded (desktop 440px+ only)

---

## What Needs To Be Done Next

### Task A — Migration Script (Python) — PRIORITY

**File to create:** `src/deck_builder/migrate_fields.py`

```python
# Pseudocode — positional split, keep blanks for missing senses
for each note in "data/English Academic Vocabulary.txt":
    defs = note["Definition"].split("|")  # M1: positional
    exs  = note["Example"].split("|")

    note["Def1"] = defs[0].strip() if len(defs) > 0 else ""
    note["Def2"] = defs[1].strip() if len(defs) > 1 else ""
    note["Def3"] = defs[2].strip() if len(defs) > 2 else ""
    note["Ex1"]  = exs[0].strip()  if len(exs)  > 0 else ""
    note["Ex2"]  = exs[1].strip()  if len(exs)  > 1 else ""
    note["Ex3"]  = exs[2].strip()  if len(exs)  > 2 else ""

    del note["Definition"]
    del note["Example"]
```

Add tests in `tests/deck_builder/test_migrate_fields.py` per AGENTS.md.

> **Note:** If you run this migration, you ALSO need to update `back_template.txt` to use `{{Def1}}`, `{{Def2}}`, `{{Def3}}` Mustache fields instead of the current `{{Definition}}` pipe-split approach. The current template JS handles pipe-split from `{{Definition}}` — it will break if the field no longer contains pipes.

### Task F — Update Scraper

- Write `Def1/Ex1`…`Def3/Ex3` directly (cap at 3 senses from Oxford/Cambridge)
- Owned by `scraper` rein per `AGENTS.md`

### Task G — Rebuild .apkg

Run `update_anki_deck.py` (entry point at repo root) to pack updated templates into `.apkg`.  
Per `design/EAVM/README.md` — watch for the **literal-newline gotcha** in template JS.

---

## Key Files Reference

| File | Purpose | State |
|------|---------|-------|
| `design/EAVM/styling.txt` | CSS source of truth → baked into `.apkg` | ✅ v2 (14,570 bytes) |
| `design/EAVM/back_template.txt` | Back card HTML + JS | ✅ v2 L3 grid |
| `design/EAVM/front_template.txt` | Front card HTML + JS | ✅ v2 sense dots |
| `design/index.html` | Design system preview | ✅ synced to v2 |
| `design/demo_test/index.html` | Original demo reference | ✅ final approved state |
| `data/English Academic Vocabulary.txt` | ~5000 notes (TSV), needs migration | ⏳ awaiting Task A |
| `AGENTS.md` | Team conventions — READ FIRST | — |

---

## JS Architecture in back_template.txt

The back card JS (in a single IIFE) does 7 things in order:

1. **POS chips** — splits `raw-pos-back` by `/[,\/]/`, injects numbered chips if multi-POS
2. **Corpus badges + separator** — reads Tags, injects corpus chips after a `top-bar-sep`
3. **Usage restriction tags** — injects `.usage-tag` spans into `usage-tags-container` (meta-row)
4. **L3 Senses grid** — splits `Definition|Definition2` + `Example|Example2`, renders `.sense-row` grid with word-highlight
5. **WF chips** — parses `word (pos)` lines, renders `.wf-chip` pills with POS color labels
6. **Collocations** — pipe-split → `.collocation-chip` spans
7. **Feature-row** — injects idioms/phrasal_verbs tags from Tags field into `.feature-row`

> **Anki JS gotcha:** Template JS uses `\\\\n|\\n|\n` regex to split WordFamily field — Anki encodes literal newlines as `\\n` in template context. Do not change this.

---

## Suggested Skills for Next Agent

- **`tdd`** — write migration script tests first (`tests/deck_builder/test_migrate_fields.py`)
- **`karpathy-guidelines`** — surgical changes; don't over-engineer the migration
- **`diagnose`** — if Anki template JS behaves unexpectedly (literal-newline gotcha above)
