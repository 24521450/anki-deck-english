"""Top-level deck builder for ielts-deck.

Reads:
  - data/notes.json         (5,002 notes, 13 fields)
  - design/EAVM/styling.txt (CSS)
  - design/EAVM/front_template.txt (Front HTML+JS)
  - design/EAVM/back_template.txt  (Back HTML+JS)
  - audio/                  (UK/US mp3 files)

Writes:
  - ielts_deck.apkg         (genanki deck, importable into Anki)

Note model fields (13, in this exact order — matches data/notes.json keys):
  1.  Word          2.  IPA              3.  PartOfSpeech
  4.  CEFRLevel     5.  Tags
  6.  Definition    7.  Example          8.  Idioms
  9.  Collocations  10. WordFamily       11. Synonym
  12. AudioUK       13. AudioUS

Usage:
  python update_anki_deck.py             # build default deck
  python update_anki_deck.py --out deck.apkg --notes data/notes.json
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path
from datetime import datetime, timezone

import genanki

# ── Paths ─────────────────────────────────────────────────────────────
PR = Path(r"C:\Users\admin\Downloads\ielts-deck")
DATA = PR / "data"
DESIGN = PR / "design" / "EAVM"
AUDIO = PR / "audio"

# ── Note model (English Academic Vocabulary Model) ──────────────────
# genanki requires stable model IDs. If you change the schema (fields,
# templates, css), bump the model version. Old decks imported under the
# previous model ID will keep using their old model — that is desired
# behavior (Anki will not overwrite a manually-edited model).
EAVM_MODEL_ID = 1607392319  # change when schema changes
EAVM_DECK_ID = 2059400110   # change when you want a fresh deck

EAVM_FIELDS = [
    {"name": "Word"},
    {"name": "IPA"},
    {"name": "PartOfSpeech"},
    {"name": "CEFRLevel"},
    {"name": "Tags"},
    {"name": "Definition"},
    {"name": "Example"},
    {"name": "Idioms"},
    {"name": "Collocations"},
    {"name": "WordFamily"},
    {"name": "Synonym"},
    {"name": "AudioUK"},
    {"name": "AudioUS"},
]

# Card templates — order matches the field list above
FRONT_TMPL = (DESIGN / "front_template.txt").read_text(encoding="utf-8")
BACK_TMPL  = (DESIGN / "back_template.txt").read_text(encoding="utf-8")
CSS        = (DESIGN / "styling.txt").read_text(encoding="utf-8")


# ── Audio handling ──────────────────────────────────────────────────
# Anki expects audio as [sound:filename.mp3] field references + the
# actual files added to the package media. We extract referenced
# filenames from each note's AudioUK / AudioUS fields and dedupe.
SOUND_RE = re.compile(r"\[sound:([^\]]+)\]")


def collect_media(notes: list[dict], audio_dir: Path) -> list[str]:
    """Walk all notes for [sound:xxx.mp3] refs, return deduped list of files
    that exist on disk under audio_dir."""
    seen: set[str] = set()
    out: list[str] = []
    for n in notes:
        for field in ("AudioUK", "AudioUS"):
            text = n.get(field, "") or ""
            for m in SOUND_RE.finditer(text):
                fn = m.group(1)
                if fn in seen:
                    continue
                if (audio_dir / fn).exists():
                    seen.add(fn)
                    out.append(fn)
                else:
                    # Missing file — leave ref intact so user can see what's wrong
                    pass
    return out


# ── Build ───────────────────────────────────────────────────────────
def build(notes_path: Path, out_path: Path, include_audio: bool = True) -> Path:
    print(f"Reading notes: {notes_path}")
    notes_raw = json.load(open(notes_path, encoding="utf-8"))
    print(f"  {len(notes_raw)} notes")

    # Build genanki model
    model = genanki.Model(
        EAVM_MODEL_ID,
        "English Academic Vocabulary Model",
        fields=EAVM_FIELDS,
        templates=[
            {
                "name": "Word → Definition",
                "qfmt": FRONT_TMPL,
                "afmt": BACK_TMPL,
            }
        ],
        css=CSS,
        model_type=genanki.Model.FRONT_BACK,
    )

    # Build genanki notes (one per record). Only include the 13 EAVM fields.
    field_names = [f["name"] for f in EAVM_FIELDS]
    anki_notes = []
    skipped = 0
    for r in notes_raw:
        try:
            values = [str(r.get(f, "") or "") for f in field_names]
            anki_notes.append(genanki.Note(model=model, fields=values))
        except Exception as e:
            skipped += 1
            if skipped <= 3:
                print(f"  ! skip {r.get('Word','?')}: {e}")
    print(f"  built {len(anki_notes)} anki notes ({skipped} skipped)")

    # Collect media (audio files referenced)
    media: list[str] = []
    if include_audio:
        media = collect_media(notes_raw, AUDIO)
        print(f"  collected {len(media)} audio files")

    # Build deck
    deck = genanki.Deck(EAVM_DECK_ID, "IELTS Academic Vocabulary")
    for n in anki_notes:
        deck.add_note(n)
    print(f"  deck: {len(deck.notes)} notes")

    # Write package
    out_path.parent.mkdir(parents=True, exist_ok=True)
    genanki.Package(deck, media_files=[AUDIO / m for m in media]).write_to_file(str(out_path))
    print(f"\nWrote {out_path}  ({out_path.stat().st_size:,} bytes)")
    return out_path


def main():
    p = argparse.ArgumentParser(description="Build IELTS Anki deck from notes.json + design templates")
    p.add_argument("--notes", default=str(DATA / "notes.json"), help="Input notes.json path")
    p.add_argument("--out", default=str(PR / "ielts_deck.apkg"), help="Output .apkg path")
    p.add_argument("--no-audio", action="store_true", help="Skip audio media (for fast rebuild)")
    args = p.parse_args()

    build(Path(args.notes), Path(args.out), include_audio=not args.no_audio)


if __name__ == "__main__":
    main()
