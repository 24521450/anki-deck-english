"""Strict mode: set fabricated + stale-scrape CEFRs to UNCLASSIFIED in the Anki .txt.

Why "strict":
  - 203 cards (135 unique words) have CEFR but no source on any current
    Oxford/Cambridge page. They were added to the deck from AWL/OPAL/manual
    lists without a verifiable CEFR. Audit: data/_audit_fabricated_cefr.json
  - 64 cards have an Oxford head_cefr in oxford_full.jsonl, but their
    words aren't in Oxford 3000/5000 and the current Oxford page may or
    may not still carry that CEFR (the "concurrent" case showed the
    page can drop CEFR over time). These are flagged as "stale candidates"
    and cleared under strict mode.
  - Total: 267 cards → CEFR = UNCLASSIFIED, tags cleared.

In-place edit (preserves review history):
  - Reads data/English Academic Vocabulary.txt, rewrites col 15 (CEFR)
    and col 16 (tags) per row. Other fields (definition, audio, example)
    are untouched. When the user re-imports into Anki with "Update
    Existing Notes", Anki matches by GUID and updates only CEFR + tags,
    preserving all review/scheduling state.

Idempotent. Re-running on already-cleared .txt is a no-op.

Recovery path (later):
  - Re-scrape the 64 stale candidates to verify if their Oxford page
    still has the CEFR. Legitimate ones can be re-applied via the
    unification fixer. Words confirmed fabricated stay UNCLASSIFIED
    until a reliable source is found (Cambridge scrape, manual review,
    or a curated academic-vocab list).

Usage:
  python tools/_clear_fabricated_cefr.py --dry-run
  python tools/_clear_fabricated_cefr.py
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

PR = Path(r"C:\Users\admin\Downloads\ielts-deck")
TXT = PR / "data" / "English Academic Vocabulary.txt"
JSONL = PR / "data" / "oxford_full.jsonl"
OX3 = PR / "vocab_list" / "Oxford" / "Oxford_3000.md"
OX5 = PR / "vocab_list" / "Oxford" / "Oxford_5000.md"

CEFR_LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2")
TAG_CEFR_SOURCE = re.compile(r"\bcefr::(oxford|cambridge)\b")
TAG_CEFR_LEVEL_UPPER = re.compile(r"\bCEFR::[ABC][12]\b")


def load_oxford_map() -> dict[str, str]:
    """word -> lowest CEFR from Oxford 3000/5000 md."""
    ox: dict[str, str] = {}
    for md in (OX3, OX5):
        text = md.read_text(encoding="utf-8")
        for m in re.finditer(r'\|\s*\*\*([^*]+)\*\*\s*\|[^|]*\|\s*([ABC][12])\s*\|', text):
            w = m.group(1).strip().lower()
            c = m.group(2)
            if w not in ox:
                ox[w] = c
    return ox


def load_jsonl_records() -> dict[str, dict]:
    recs: dict[str, dict] = {}
    with JSONL.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            recs[r["word"].lower()] = r
    return recs


def clear_tags(tags: str) -> str:
    """Strip all `cefr::*` and `CEFR::*` tokens from a space-separated tag string.

    Other tags (Audio::*, OPAL_*, Oxford_3000, Source::*, subject labels,
    register tags, ...) are preserved verbatim, in their original order.
    """
    tokens = tags.split() if tags else []
    return " ".join(
        t for t in tokens
        if not TAG_CEFR_SOURCE.fullmatch(t) and not TAG_CEFR_LEVEL_UPPER.fullmatch(t)
    )


def main():
    p = argparse.ArgumentParser(description="Strict-mode clear of fabricated + stale CEFRs in Anki .txt")
    p.add_argument("--txt", default=str(TXT), help="Path to Anki .txt export")
    p.add_argument("--dry-run", action="store_true", help="Print plan, do not write")
    args = p.parse_args()

    txt_path = Path(args.txt)
    print(f"Loading {txt_path}...")
    raw = txt_path.read_text(encoding="utf-8", errors="replace")
    lines = raw.splitlines(keepends=True)
    print(f"  {len(lines)} lines")

    print(f"Loading Oxford 3000/5000 md...")
    ox = load_oxford_map()
    print(f"  {len(ox)} words")

    print(f"Loading oxford_full.jsonl...")
    recs = load_jsonl_records()
    print(f"  {len(recs)} records")

    # Header / body split
    header_lines: list[str] = []
    body_lines: list[str] = []
    for line in lines:
        if line.startswith("#") or not line.strip():
            header_lines.append(line)
        else:
            body_lines.append(line)
    print(f"  {len(header_lines)} header lines, {len(body_lines)} data rows")

    # Walk: classify each row
    stats = {
        "fabricated": 0,
        "stale_candidate": 0,
        "oxford_md": 0,
        "cambridge_only": 0,
        "unclassified": 0,
        "kept": 0,
        "cleared_cefr": 0,
        "cleared_tags": 0,
    }
    clear_deltas: list[tuple[str, str, str, str, str]] = []  # (word, old_cefr, new_cefr, old_tags, new_tags)

    new_lines: list[str] = list(header_lines)
    for line in body_lines:
        terminator = ""
        body = line
        if body.endswith("\r\n"):
            terminator = "\r\n"
            body = body[:-2]
        elif body.endswith("\n"):
            terminator = "\n"
            body = body[:-1]

        trailing_tabs = 0
        while body.endswith("\t"):
            trailing_tabs += 1
            body = body[:-1]

        parts = body.split("\t")
        if trailing_tabs and len(parts) < 16:
            while len(parts) < 16:
                parts.append("")
        if len(parts) < 16:
            new_lines.append(line)
            continue

        word = (parts[3] or "").strip()
        wl = word.lower()
        cur_cefr = (parts[14] or "").strip()
        cur_tags = parts[15] or ""

        # Classify
        in_ox_md = wl in ox
        rec = recs.get(wl)
        ox_def_cefr = any(d.get("def_cefr") for d in (rec.get("definitions") or [])) if rec else False
        ox_head_cefr = bool(rec and rec.get("cefr")) if rec else False
        in_cambridge = bool(rec and rec.get("cambridge_cefr"))

        if cur_cefr == "UNCLASSIFIED":
            stats["unclassified"] += 1
        elif in_ox_md:
            stats["oxford_md"] += 1
        elif in_cambridge:
            stats["cambridge_only"] += 1
        elif ox_def_cefr or ox_head_cefr:
            # Oxford scrape has a CEFR but word not in md → stale candidate
            stats["stale_candidate"] += 1
        else:
            # No source anywhere → fabricated
            stats["fabricated"] += 1

        # Strict mode rule: clear CEFR if the word is not in Oxford 3000/5000
        # md. We do NOT trust cambridge_cefr (field has been historically
        # empty, and live Cambridge pages may have dropped CEFR). Words
        # with an oxford head_cefr (the 64 stale candidates) are also
        # cleared because the scrape may be stale (the "concurrent" case
        # showed the live Oxford page now has 0 CEFR attrs even though
        # the cached scrape said B1).
        should_clear = (cur_cefr != "UNCLASSIFIED") and (not in_ox_md)

        if should_clear:
            new_cefr = "UNCLASSIFIED"
            new_tags = clear_tags(cur_tags)
            if cur_cefr != "UNCLASSIFIED":
                stats["cleared_cefr"] += 1
                clear_deltas.append((word, cur_cefr, new_cefr, cur_tags, new_tags))
            if new_tags != cur_tags:
                stats["cleared_tags"] += 1
            parts[14] = new_cefr
            parts[15] = new_tags
        else:
            stats["kept"] += 1

        joined = "\t".join(parts)
        if trailing_tabs:
            joined = joined + ("\t" * trailing_tabs)
        new_lines.append(joined + terminator)

    # Report
    print(f'\n{"="*70}')
    print("Plan (strict mode):")
    for k, v in stats.items():
        print(f"  {k:25s} = {v}")
    print(f'\nTotal CEFRs to clear: {stats["cleared_cefr"]}')
    print(f'Total tag cleanups:   {stats["cleared_tags"]}')

    if clear_deltas:
        print(f'\n--- All {len(clear_deltas)} CEFRs to clear ---')
        for word, o, n, ot, nt in clear_deltas:
            print(f"  {word:18s}  {o:12s} -> {n}")

    if args.dry_run:
        print(f'\n[DRY-RUN] No changes written. Re-run without --dry-run to apply.')
        return

    if stats["cleared_cefr"] == 0 and stats["cleared_tags"] == 0:
        print(f'\nNo changes to apply. Exiting.')
        return

    # Backup
    from datetime import datetime, timezone
    from shutil import copy2
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bak = txt_path.with_suffix(f".{ts}.txt.bak")
    copy2(txt_path, bak)
    print(f'\nBackup written: {bak}')

    # Write
    txt_path.write_text("".join(new_lines), encoding="utf-8")
    print(f'Saved {txt_path}')

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
