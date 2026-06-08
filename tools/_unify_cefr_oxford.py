"""Unify CEFRLevel to Oxford 3000/5000, with Cambridge as fallback.

Motivation: the Anki deck's CEFR field is set by tools/build_notes.py
running the cefr_chain chain. The chain is Oxford-primary in design
(Step 1 def_cefr -> Step 2 vocab_cefr[word][pos] -> Step 3 head_cefr
-> Step 4 cambridge_cefr -> Step 5 UNCLASSIFIED), but Step 1's
`def_cefr` is sometimes polluted with Cambridge values from the
cambridge scrape (the bug _cleanup_oxford_pollution.py partially
addresses for 32 specific words). Net effect: ~15% of Anki cards that
are in Oxford 3000/5000 still display a CEFR that disagrees with the
vocab-list value.

This fixer overrides the chain's output for the *current* notes.json:
  - For every note whose `Word` is in the Oxford 3000/5000 vocab map,
    replace `CEFRLevel` with the lowest Oxford CEFR across that word's
    POS entries. Lowest = most accessible = matches the existing
    `resolve_record_cefr` "pick min" semantics.
  - For every note NOT in the Oxford map, keep the current `CEFRLevel`
    (which is the chain's Cambridge value, or UNCLASSIFIED if no
    Cambridge data).
  - Sync the Tags field: replace `cefr::cambridge` with `cefr::oxford`
    for words now flipped to Oxford; add `cefr::oxford` to words that
    lacked any `cefr::*` tag; add `cefr::cambridge` to words that
    fall back to Cambridge and don't already have the tag. (This
    matches build_notes.build_tags behaviour for downstream tooling.)
  - Update `_meta.cefr_resolved` and `_meta.cefr_source` for
    consistency with the chain contract.

Idempotent: re-running on already-unified notes.json is a no-op
(both branches' "if word in map: set level + tag" are stable).

The fix is a one-shot — it does NOT modify cefr_chain.py. The chain's
design is correct; the data is the issue. Re-running the chain from
scratch (re-scrape) may re-introduce pollution; in that case re-run
this fixer on the regenerated notes.json.

Usage:
  python tools/_unify_cefr_oxford.py --dry-run
  python tools/_unify_cefr_oxford.py
  python tools/_unify_cefr_oxford.py --notes path/to/notes.json
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# Repo paths
PR = Path(r"C:\Users\admin\Downloads\ielts-deck")
DATA = PR / "data"
VOCAB_DIR = PR / "vocab_list" / "Oxford"
DEFAULT_NOTES = DATA / "notes.json"

# CEFR ordering for the "lowest = most accessible" pick
CEFR_RANK: dict[str, int] = {
    "A1": 1, "A2": 2, "B1": 3, "B2": 4, "C1": 5, "C2": 6,
    "UNCLASSIFIED": 99,
}


def load_oxford_map(vocab_dir: Path) -> dict[str, dict[str, str]]:
    """Word -> {pos: cefr} map from vocab_list/Oxford/*.md.

    Reuses src.scraper.cefr_chain.load_vocab_cefr + clean_pos so the
    POS normalization is identical to the chain's lookups.
    """
    from src.scraper.cefr_chain import load_vocab_cefr
    return load_vocab_cefr(vocab_dir)


def pick_lowest_cefr(pos_to_cefr: dict[str, str]) -> str | None:
    """Return the lowest-ranked CEFR in a {pos: cefr} map, or None."""
    if not pos_to_cefr:
        return None
    valid = [c for c in pos_to_cefr.values() if c in CEFR_RANK and c != "UNCLASSIFIED"]
    if not valid:
        return None
    return min(valid, key=lambda c: CEFR_RANK[c])


def pick_cefr_for_note(pos_to_cefr: dict[str, str], note_pos: str) -> str | None:
    """Pick the most relevant Oxford CEFR for a note.

    Strategy:
      1. Walk the note's POS tokens in order (comma-separated). For each
         normalized POS, if the vocab map has an entry, return that CEFR.
         This preserves per-sense granularity and follows the order the
         card author wrote POSes in (matches the per-def chain semantics
         where the first def wins).
      2. If no POS matches but a per-POS entry exists, return the
         lowest across all POSes (matches resolve_record_cefr semantics).
      3. If the map is empty, return None.

    Order matters: a `set()` of POSes loses insertion order and would
    make multi-POS notes like "adjective, noun" pick non-deterministically
    between adj (B2) and n (C1) entries.
    """
    if not pos_to_cefr:
        return None
    from src.scraper.cefr_chain import clean_pos
    note_pos_list: list[str] = []
    seen: set[str] = set()
    for raw in (note_pos or "").split(","):
        cp = clean_pos(raw)
        if cp and cp not in seen:
            seen.add(cp)
            note_pos_list.append(cp)
    for np in note_pos_list:
        if np in pos_to_cefr and pos_to_cefr[np] in CEFR_RANK and pos_to_cefr[np] != "UNCLASSIFIED":
            return pos_to_cefr[np]
    return pick_lowest_cefr(pos_to_cefr)


def update_tags(tags: str, new_source: str) -> str:
    """Update the cefr::<source> token in a space-separated tag string.

    Rules:
      - Drop any existing `cefr::oxford` or `cefr::cambridge` token.
      - Add `cefr::<new_source>` iff new_source is 'oxford' or 'cambridge'.
    Other tags are preserved in their original order.
    """
    tokens = tags.split() if tags else []
    kept = [t for t in tokens if t not in ("cefr::oxford", "cefr::cambridge")]
    if new_source in ("oxford", "cambridge"):
        kept.append(f"cefr::{new_source}")
    return " ".join(kept)


def unify_note(note: dict, oxford_map: dict[str, dict[str, str]]) -> tuple[str, str, bool]:
    """Compute the unified (CEFRLevel, cefr_source, changed?) for one note.

    Returns the new CEFRLevel, the new cefr_source, and a bool indicating
    whether the note's CEFRLevel/Tags would change.
    """
    word = (note.get("Word") or "").strip().lower()
    cur_level = (note.get("CEFRLevel") or "").strip()
    note_pos = note.get("PartOfSpeech") or ""

    pos_map = oxford_map.get(word, {})

    if pos_map:
        # Oxford-primary: prefer per-POS match, fall back to lowest across POSes
        new_level = pick_cefr_for_note(pos_map, note_pos) or "UNCLASSIFIED"
        new_source = "oxford"
    else:
        # Cambridge-fallback: keep current value (chain already produced
        # either the cambridge_cefr or UNCLASSIFIED)
        new_level = cur_level or "UNCLASSIFIED"
        new_source = "cambridge" if new_level != "UNCLASSIFIED" else "unclassified"

    changed = (new_level != cur_level) or (update_tags(note.get("Tags", ""), new_source) != note.get("Tags", ""))
    return new_level, new_source, changed


def main():
    p = argparse.ArgumentParser(description="Unify Anki notes.json CEFR to Oxford (Cambridge fallback)")
    p.add_argument("--notes", default=str(DEFAULT_NOTES), help="Path to notes.json")
    p.add_argument("--dry-run", action="store_true", help="Print plan, do not write")
    p.add_argument("--verbose", action="store_true", help="Print per-note deltas")
    args = p.parse_args()

    notes_path = Path(args.notes)
    print(f"Loading {notes_path}...")
    with notes_path.open("r", encoding="utf-8") as f:
        notes: list[dict] = json.load(f)
    print(f"  {len(notes)} notes loaded")

    print(f"Loading Oxford vocab from {VOCAB_DIR}...")
    oxford_map = load_oxford_map(VOCAB_DIR)
    print(f"  {len(oxford_map)} words in Oxford 3000/5000")

    # Audit + apply
    stats = {
        "in_oxford": 0,
        "in_cambridge_only": 0,
        "unclassified": 0,
        "changed_cefr": 0,
        "changed_tags": 0,
        "unchanged": 0,
        "oxford_to_oxford": 0,        # was already right
        "oxford_to_cambridge": 0,     # was cambridge, now oxford (the goal)
        "cambridge_to_cambridge": 0,
        "cambridge_to_oxford": 0,
    }
    deltas: list[tuple[str, str, str]] = []  # (word, old, new)

    for n in notes:
        word = (n.get("Word") or "").strip()
        cur_level = (n.get("CEFRLevel") or "").strip()
        cur_tags = n.get("Tags") or ""
        cur_source = "oxford" if "cefr::oxford" in cur_tags.split() else (
            "cambridge" if "cefr::cambridge" in cur_tags.split() else "unclassified"
        )

        new_level, new_source, changed = unify_note(n, oxford_map)

        # Bucket
        if new_source == "oxford":
            stats["in_oxford"] += 1
        elif new_source == "cambridge":
            stats["in_cambridge_only"] += 1
        else:
            stats["unclassified"] += 1

        if cur_level != new_level:
            stats["changed_cefr"] += 1
        if update_tags(cur_tags, new_source) != cur_tags:
            stats["changed_tags"] += 1
        if not changed:
            stats["unchanged"] += 1
        else:
            deltas.append((word, cur_level, new_level))
            # Track flow direction
            if cur_source == "oxford" and new_source == "oxford":
                stats["oxford_to_oxford"] += 1
            elif cur_source == "cambridge" and new_source == "oxford":
                stats["cambridge_to_oxford"] += 1
            elif cur_source == "oxford" and new_source == "cambridge":
                stats["oxford_to_cambridge"] += 1
            else:
                stats["cambridge_to_cambridge"] += 1

        if args.verbose and cur_level != new_level:
            print(f"  {word:25s}  {cur_level:12s} -> {new_level:12s}  (src {cur_source} -> {new_source})")

    # Report
    print(f'\n{"="*70}')
    print("Plan:")
    for k, v in stats.items():
        print(f"  {k:25s} = {v}")
    print(f'\nTotal CEFR changes: {stats["changed_cefr"]}')
    print(f'Total tag updates:  {stats["changed_tags"]}')

    # Top-20 sample of CEFR-only changes (skip tag-only)
    cefr_deltas = [(w, o, n) for w, o, n in deltas if o != n]
    if cefr_deltas:
        print(f'\n--- All {len(cefr_deltas)} CEFR changes ---')
        for w, o, n in cefr_deltas:
            print(f"  {w:25s}  {o:12s} -> {n}")

    if args.dry_run:
        print(f'\n[DRY-RUN] No changes written. Re-run without --dry-run to apply.')
        return

    if stats["changed_cefr"] == 0 and stats["changed_tags"] == 0:
        print(f'\nNo changes to apply. Exiting.')
        return

    # Backup
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bak = notes_path.with_suffix(f".{ts}.bak")
    shutil.copy2(notes_path, bak)
    print(f'\nBackup written: {bak}')

    # Apply
    for n in notes:
        word = (n.get("Word") or "").strip()
        new_level, new_source, _ = unify_note(n, oxford_map)
        old_level = n.get("CEFRLevel") or ""
        n["CEFRLevel"] = new_level
        n["Tags"] = update_tags(n.get("Tags", ""), new_source)
        # Update _meta for consistency (build_notes.py writes these)
        meta = n.setdefault("_meta", {})
        meta["cefr_resolved"] = new_level
        meta["cefr_source"] = new_source

    with notes_path.open("w", encoding="utf-8") as f:
        json.dump(notes, f, ensure_ascii=False, indent=2)
    print(f'Saved {notes_path}')

    # Sanity: distribution
    from collections import Counter
    new_dist = Counter((n.get("CEFRLevel") or "").strip() for n in notes)
    print(f'\n--- New CEFRLevel distribution ---')
    for lvl in ("A1", "A2", "B1", "B2", "C1", "C2", "UNCLASSIFIED"):
        if lvl in new_dist:
            print(f"  {lvl:13s} = {new_dist[lvl]}")


if __name__ == "__main__":
    main()
