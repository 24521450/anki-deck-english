"""Regenerate notes.tsv from notes.json (no chain re-run).

Why: tools/build_notes.py reads from oxford_full.jsonl, runs the
cefr_chain, and writes notes.json + notes.tsv together. Re-running
build_notes.py would re-apply the (potentially polluted) chain and
overwrite the unified CEFRLevel values written by _unify_cefr_oxford.py.

This script is the minimal "json -> tsv" dump that build_notes.py would
do, but skips the chain. Idempotent.

Usage:
  python tools/_regen_tsv.py
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

PR = Path(r"C:\Users\admin\Downloads\ielts-deck")
DATA = PR / "data"
NOTES_JSON = DATA / "notes.json"
NOTES_TSV = DATA / "notes.tsv"

# Field order must match EAVM_FIELDS in update_anki_deck.py
FIELDS = [
    "Word", "IPA", "PartOfSpeech", "CEFRLevel", "Tags",
    "Definition", "Example", "Idioms", "Collocations", "WordFamily",
    "Synonym", "AudioUK", "AudioUS",
]


def main():
    if not NOTES_JSON.exists():
        print(f"ERROR: {NOTES_JSON} not found", file=sys.stderr)
        sys.exit(1)
    notes = json.load(open(NOTES_JSON, encoding="utf-8"))
    print(f"Read {len(notes)} notes from {NOTES_JSON}")

    with NOTES_TSV.open("w", encoding="utf-8", newline="") as f:
        f.write("#separator:tab\n#html:true\n")
        for n in notes:
            row = [str(n.get(k, "") or "") for k in FIELDS]
            # Anki TSV: newlines -> <br>, tabs -> space (matches build_notes.py)
            row = [r.replace("\r", "").replace("\n", "<br>").replace("\t", " ") for r in row]
            f.write("\t".join(row) + "\n")
    print(f"Wrote {NOTES_TSV}")


if __name__ == "__main__":
    main()
