# Implementation Plan - Fix CEFR Resolution Chain & Cambridge Tagging (Y1 Scope)

This plan resolves the conflict in CEFR resolution where `cefr::cambridge` tags were always 0 cards because Cambridge-sourced CEFR levels were previously written into Oxford-specific database fields (`cefr` and `def_cefr`).

## User Review Required

> [!IMPORTANT]
> The database (`data/oxford_full.jsonl`) will be cleaned up to restore Oxford-specific fields (`cefr`) back to their original Oxford vocab value (or `None` for words not in Oxford 3000/5000). 32 records affected. Cambridge CEFR levels are stored exclusively in `cambridge_cefr`.

## Scope (Y1, confirmed 2026-06-08)

**In scope (32 records)**: 32 words where `source=oxford` and `cefr` field was polluted with Cambridge value (i.e., `rec['cefr'] == rec['cambridge_cefr']`).
- 13/32 have Oxford vocab value → revert `cefr` to vocab value (alongside=B2, deed=C1, deprive=C1, derive=B2, devote=B2, dispose=C1, full-time=B2, halfway=C1, line-up=C1, mainland=C1, marathon=B2, pace=B2, solo=C1).
- 19/32 NOT in Oxford vocab → revert `cefr` to `None` (ambiguous, concurrent, constrain, denote, deviate, discrete, equate, finite, id, ignorant, implicate, innovate, intrinsic, levy, notwithstanding, orient, qualitative, reluctance, subordinate).

**Out of scope (deferred to follow-up ticket)**: 8 disputed words where `source=cambridge` and `cur_cefr` field differs from `cambridge_cefr`. 3/8 (content, minute, pension) have `cur_cefr` matching the true Oxford vocab value (no fix needed but worth re-checking after the cleanup). 3/8 (bow, contrary, proceedings) have `cur_cefr` mismatched with ox_vocab (data integrity issue). 2/8 (grave, wellbeing) have no ox_vocab entry. See `~/.mavis/scratchpads/mvs_4f4e20ab947e40d9b24199d942991941/disputed_audit.md` for full details.

**Expected outcome after cleanup**:
- 19 cards re-tagged `cefr::cambridge` (the 19 words that have no Oxford vocab fallback)
- 13 cards remain `cefr::oxford` (the 13 words with Oxford vocab value)
- 8 disputed words keep current tags (no change)
- Net: `cefr::cambridge` count rises from 0 to ~19

## Proposed Changes

### Database Cleanup

#### [MODIFY] [oxford_full.jsonl](file:///C:/Users/admin/Downloads/ielts-deck/data/oxford_full.jsonl)
- Revert `cefr` field for 32 polluted words:
  - 13 words with Oxford vocab value → set to vocab value (e.g. `alongside` → `B2`, `deed` → `C1`, etc.)
  - 19 words without Oxford vocab → set to `None`
- Do NOT touch `cambridge_cefr` or `cambridge_all_cefrs` fields.
- Do NOT touch the 8 disputed (source=cambridge) records.
- Do NOT touch `def_cefr` per-sense fields (those are Oxford fkcefr values, not affected by the Cambridge pollution).

#### [NEW] [tools/_cleanup_oxford_pollution.py](file:///C:/Users/admin/Downloads/ielts-deck/tools/_cleanup_oxford_pollution.py)
- Idempotent cleanup script:
  1. Load `oxford_full.jsonl`
  2. Build hard-coded 32-word revert map (word → target cefr value, from audit)
  3. For each record: if word in map AND current `cefr` == `cambridge_cefr` (sanity check), set `cefr` to target value
  4. Skip records that don't match the pollution signature
  5. Write to `.bak` first, then overwrite
  6. Print summary: reverted-to-vocab (13), reverted-to-None (19), skipped (X)
- Allow `--dry-run` flag to preview without writing.

---

### Scraper Pipeline

#### [MODIFY] [_fetch_cambridge_cefr.py](file:///C:/Users/admin/Downloads/ielts-deck/tools/_fetch_cambridge_cefr.py)
- **Fix `as_completed` mapping bug**: Wrap tasks so that words are correctly associated with their completed asynchronous fetch results.
- **Fix standard output encoding error**: Change standard arrow `→` to `->` in print statements to avoid `UnicodeEncodeError` on Windows.
- **Prevent Oxford field pollution**: Stop setting `rec['cefr']` and `d['def_cefr']` to the Cambridge CEFR value. Store it strictly in `rec['cambridge_cefr']` and `rec['cambridge_all_cefrs']`.

---

### Card & Note Generation

#### [MODIFY] [build_notes.py](file:///C:/Users/admin/Downloads/ielts-deck/tools/build_notes.py)
- Fall back to `cambridge_cefr` if Oxford `cefr` is missing/None when checking CEFR levels to include, setting the `CEFRLevel` field, and generating debug metadata.

#### [MODIFY] [split_study_cards.py](file:///C:/Users/admin/Downloads/ielts-deck/tools/split_study_cards.py)
- Re-run the split script. Now that Oxford fields (`rec['cefr']`) are clean, the 19 words with no Oxford vocab will fall through to Step 5 of the resolution chain and correctly tag the resulting cards with `cefr::cambridge`.

---

## Verification Plan

### Automated Tests
- Run `python tools/_cleanup_oxford_pollution.py --dry-run` first to preview changes.
- Run `python tools/_cleanup_oxford_pollution.py` to apply.
- Run `python -m tools._fetch_cambridge_cefr` (smoke test on a few words) to verify it doesn't pollute the JSONL.
- Run `python -m tools.split_study_cards` to regenerate study cards.
- Run a verification command to count `cefr::cambridge` tags in `data/study_split.tsv` — expect ~19.
- Run `pytest` to verify all existing tests still pass.

### Manual Audit
- Pick 3 sample words from the 19 reverting-to-None group (e.g. `ambiguous`, `concurrent`, `constrain`) and confirm their study cards now have `cefr::cambridge` tag and CEFR=Cambridge value.
- Pick 3 sample words from the 13 reverting-to-vocab group (e.g. `alongside`, `deed`, `deprive`) and confirm their study cards have `cefr::oxford` tag and CEFR=Oxford vocab value.
- Pick 1 disputed word (e.g. `bow`) and confirm it's UNCHANGED (still source=cambridge, still cefr=B2, still cefr::oxford tag).
