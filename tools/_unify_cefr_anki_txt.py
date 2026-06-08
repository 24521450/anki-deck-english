"""Unify CEFR in the Anki export .txt (in-place, preserves review history).

Why a separate script from _unify_cefr_oxford.py:
  - _unify_cefr_oxford.py mutates data/notes.json (the build-time
    source of truth) and is paired with update_anki_deck.py to produce
    a fresh .apkg. Importing a new .apkg creates new note IDs and
    LOSES the user's Anki review history.
  - This script mutates data/English Academic Vocabulary.txt (the
    user's working Anki export). The .txt has GUIDs in column 1, so
    re-importing with Anki's "Update Existing Notes" enabled matches
    by GUID, overwrites only the changed fields, and preserves all
    review/scheduling state.

What it changes in each row (tab-separated, 16 cols):
  - col 15 (CEFR): overwrite with the unified value (lowest Oxford
    CEFR per matching POS, or current value if word is Cambridge-only).
  - col 16 (tags): rewrite the cefr::<src> and CEFR::<lvl> tokens to
    reflect the unified CEFR. Other tags (Audio::Cambridge, OPAL_W,
    Oxford_3000, Source::Oxford, subject labels, register tags, ...)
    are preserved verbatim.

Idempotent: re-running on an already-unified .txt is a no-op.

Usage:
  python tools/_unify_cefr_anki_txt.py --dry-run
  python tools/_unify_cefr_anki_txt.py
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

PR = Path(r"C:\Users\admin\Downloads\ielts-deck")
TXT = PR / "data" / "English Academic Vocabulary.txt"
VOCAB_DIR = PR / "vocab_list" / "Oxford"

CEFR_RANK: dict[str, int] = {
    "A1": 1, "A2": 2, "B1": 3, "B2": 4, "C1": 5, "C2": 6,
    "UNCLASSIFIED": 99,
}

# Token rewrites for the tag column
#  - cefr::<source> lowercase tags (added by build_notes.py)
#  - CEFR::<LEVEL> uppercase tags (the user's own Anki convention,
#    mirrors the CEFRLevel field; one per row, must reflect current level)
TAG_CEFR_SOURCE = re.compile(r"\bcefr::(oxford|cambridge)\b")
TAG_CEFR_LEVEL_UPPER = re.compile(r"\bCEFR::[ABC][12]\b")


def load_oxford_map(vocab_dir: Path) -> dict[str, dict[str, str]]:
    from src.scraper.cefr_chain import load_vocab_cefr
    return load_vocab_cefr(vocab_dir)


def pick_cefr_for_note(pos_to_cefr: dict[str, str], note_pos: str) -> str | None:
    """Per-POS first, then lowest across all POSes. Order-preserving."""
    if not pos_to_cefr:
        return None
    from src.scraper.cefr_chain import clean_pos
    pos_list: list[str] = []
    seen: set[str] = set()
    for raw in (note_pos or "").split(","):
        cp = clean_pos(raw)
        if cp and cp not in seen:
            seen.add(cp)
            pos_list.append(cp)
    for np in pos_list:
        if np in pos_to_cefr and pos_to_cefr[np] in CEFR_RANK and pos_to_cefr[np] != "UNCLASSIFIED":
            return pos_to_cefr[np]
    valid = [c for c in pos_to_cefr.values() if c in CEFR_RANK and c != "UNCLASSIFIED"]
    return min(valid, key=lambda c: CEFR_RANK[c]) if valid else None


def rewrite_tags(tags: str, new_source: str, new_level: str) -> str:
    """Update `cefr::<source>` and `CEFR::<LEVEL>` tokens in a space-separated tag string.

    Other tokens (Audio::*, OPAL_*, Oxford_3000, Source::*, subject labels,
    register tags, etc.) are preserved verbatim, in their original order.
    """
    tokens = tags.split() if tags else []
    out: list[str] = []
    had_upper = False
    for t in tokens:
        if TAG_CEFR_SOURCE.fullmatch(t):
            continue  # drop, will re-add below
        if TAG_CEFR_LEVEL_UPPER.fullmatch(t):
            had_upper = True
            continue  # drop, will re-add below
        out.append(t)
    if new_source in ("oxford", "cambridge"):
        out.append(f"cefr::{new_source}")
    if had_upper and new_level in CEFR_RANK and new_level != "UNCLASSIFIED":
        out.append(f"CEFR::{new_level}")
    return " ".join(out)


def split_tsv_line(line: str) -> list[str]:
    """Split a TSV line, preserving empty trailing columns.

    Anki exports preserve empty trailing fields by including the
    trailing tab, e.g. "...\t\t\t\n". str.split('\t') drops those
    unless we re-insert them. Detect by counting tabs.
    """
    trailing_tabs = len(line) - len(line.rstrip("\t").rstrip("\n").rstrip("\r")) - 1
    if trailing_tabs < 0:
        trailing_tabs = 0
    # Count leading tabs (rows always have at least 15)
    parts = line.rstrip("\r\n").split("\t")
    # If trailing_tabs is positive, fields were truncated
    if trailing_tabs and len(parts) < 16:
        # We can't perfectly recover what was in the truncated fields,
        # but Anki exports use empty strings for missing trailing cols.
        # Pad with empty strings up to 16.
        while len(parts) < 16:
            parts.append("")
    return parts


def main():
    p = argparse.ArgumentParser(description="Unify CEFR in Anki export .txt (preserves review history)")
    p.add_argument("--txt", default=str(TXT), help="Path to Anki .txt export")
    p.add_argument("--dry-run", action="store_true", help="Print plan, do not write")
    args = p.parse_args()

    txt_path = Path(args.txt)
    print(f"Loading {txt_path}...")
    raw = txt_path.read_text(encoding="utf-8", errors="replace")
    lines = raw.splitlines(keepends=True)
    print(f"  {len(lines)} lines")

    print(f"Loading Oxford vocab from {VOCAB_DIR}...")
    oxford_map = load_oxford_map(VOCAB_DIR)
    print(f"  {len(oxford_map)} words in Oxford 3000/5000")

    # Detect header lines (start with #)
    header_lines: list[str] = []
    body_lines: list[str] = []
    for line in lines:
        if line.startswith("#") or not line.strip():
            header_lines.append(line)
        else:
            body_lines.append(line)
    print(f"  {len(header_lines)} header lines, {len(body_lines)} data rows")

    # Audit + apply
    stats = {
        "in_oxford": 0,
        "in_cambridge_only": 0,
        "unclassified": 0,
        "changed_cefr": 0,
        "changed_tags": 0,
        "unchanged": 0,
    }
    cefr_deltas: list[tuple[str, str, str, str]] = []  # (guid, word, old, new)

    new_lines: list[str] = list(header_lines)
    for line in body_lines:
        # Split fields. Anki uses \n as the line terminator and \r\n
        # on Windows; we want to keep the original terminator.
        terminator = ""
        body = line
        if body.endswith("\r\n"):
            terminator = "\r\n"
            body = body[:-2]
        elif body.endswith("\n"):
            terminator = "\n"
            body = body[:-1]

        # Preserve trailing-tab truncation
        trailing_tabs = 0
        while body.endswith("\t"):
            trailing_tabs += 1
            body = body[:-1]

        parts = body.split("\t")
        # Pad to 16 if trailing tabs were stripped
        if trailing_tabs and len(parts) < 16:
            while len(parts) < 16:
                parts.append("")
        if len(parts) < 16:
            # Malformed row — leave alone
            new_lines.append(line)
            continue

        guid = parts[0]
        word = (parts[3] or "").strip().lower()
        pos = parts[4] or ""
        cur_cefr = (parts[14] or "").strip()
        cur_tags = parts[15] or ""

        pos_map = oxford_map.get(word, {})
        if pos_map:
            new_level = pick_cefr_for_note(pos_map, pos) or "UNCLASSIFIED"
            new_source = "oxford"
        else:
            new_level = cur_cefr or "UNCLASSIFIED"
            new_source = "cambridge" if new_level != "UNCLASSIFIED" else "unclassified"

        if new_source == "oxford":
            stats["in_oxford"] += 1
        elif new_source == "cambridge":
            stats["in_cambridge_only"] += 1
        else:
            stats["unclassified"] += 1

        new_tags = rewrite_tags(cur_tags, new_source, new_level)
        cefr_changed = (new_level != cur_cefr)
        tags_changed = (new_tags != cur_tags)
        if cefr_changed:
            stats["changed_cefr"] += 1
            cefr_deltas.append((guid, parts[3], cur_cefr, new_level))
        if tags_changed:
            stats["changed_tags"] += 1
        if not cefr_changed and not tags_changed:
            stats["unchanged"] += 1

        parts[14] = new_level
        parts[15] = new_tags
        # Reassemble with the original trailing-tab count
        joined = "\t".join(parts)
        if trailing_tabs:
            joined = joined + ("\t" * trailing_tabs)
        new_lines.append(joined + terminator)

    # Report
    print(f'\n{"="*70}')
    print("Plan:")
    for k, v in stats.items():
        print(f"  {k:25s} = {v}")
    print(f'\nTotal CEFR changes: {stats["changed_cefr"]}')
    print(f'Total tag rewrites: {stats["changed_tags"]}')

    if cefr_deltas:
        print(f'\n--- All {len(cefr_deltas)} CEFR changes ---')
        for guid, w, o, n in cefr_deltas:
            print(f"  {w:18s}  {o:12s} -> {n}")

    if args.dry_run:
        print(f'\n[DRY-RUN] No changes written. Re-run without --dry-run to apply.')
        return

    if stats["changed_cefr"] == 0 and stats["changed_tags"] == 0:
        print(f'\nNo changes to apply. Exiting.')
        return

    # Write back
    txt_path.write_text("".join(new_lines), encoding="utf-8")
    print(f'\nSaved {txt_path}')

    # Sanity: new distribution
    new_dist: Counter[str] = Counter()
    for line in new_lines[len(header_lines):]:
        parts = line.rstrip("\r\n").split("\t")
        if len(parts) >= 15:
            new_dist[(parts[14] or "").strip()] += 1
    print(f'\n--- New CEFR distribution ---')
    for lvl in ("A1", "A2", "B1", "B2", "C1", "C2", "UNCLASSIFIED"):
        if lvl in new_dist:
            print(f"  {lvl:13s} = {new_dist[lvl]}")


if __name__ == "__main__":
    main()
