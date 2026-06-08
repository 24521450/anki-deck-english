"""Regenerate study list (data/English Academic Vocabulary.txt) from oxford_full.jsonl.

Anki TSV format (16 columns):
  0  GUID
  1  NoteType
  2  Deck
  3  Word
  4  POS
  5  IPA
  6  Definition (top-3 joined by '|')
  7  Example
  8  Synonyms
  9  Word family
  10 Audio UK
  11 Audio US
  12 Source
  13 Oxford_5000?
  14 CEFR
  15 Tags

We only have basic data from oxford_full.jsonl — no synonyms, no word family
(those live elsewhere). So col 8, 9 are empty.

IPA comes from JSONL if available; else from a small table embedded in the script.

Words with definitions are included. Unclassified stubs are skipped (they have
no defs to study). UNCLASSIFIED words already in the original study list are
preserved with cefr=UNCLASSIFIED.

NOTE: This regenerates from JSONL, so the "deck" assignment (Oxford vs TED YT)
is lost. We use 'English Academic Vocabulary::Regen' as a single deck.
"""
import json
import re
import secrets
import string
from pathlib import Path

PR = Path(r"C:\Users\admin\Downloads\ielts-deck")
JSONL = PR / "data" / "oxford_full.jsonl"
OUT = PR / "data" / "English Academic Vocabulary.txt"
OLD_STUDY = None  # from git HEAD (we don't read this; user said regen from JSONL)

NOTETYPE = "English Academic Vocabulary Model"
DECK = "English Academic Vocabulary::Regen"


def gen_guid() -> str:
    """Generate a short Anki-style GUID (10-12 chars, mixed case + digits)."""
    n = 10
    alphabet = string.ascii_letters + string.digits + "!#$%&()*+,-./:;<=>?@[]^_`{|}~"
    return "".join(secrets.choice(alphabet) for _ in range(n))


def pos_short(pos_list: list[str]) -> str:
    """Map full POS list to short codes joined by |."""
    if not pos_list:
        return ""
    # Oxford full: noun, verb, adjective, adverb, preposition, ...
    # Short: noun, verb, adj, adv, prep, ...
    short_map = {
        "noun": "noun", "verb": "verb", "adjective": "adj", "adverb": "adv",
        "preposition": "prep", "pronoun": "pron", "conjunction": "conj",
        "determiner": "det", "modal verb": "modal", "auxiliary verb": "aux",
        "exclamation": "excl", "number": "num", "prefix": "prefix",
        "suffix": "suffix", "combining form": "comb",
        "phrasal verb": "phrasal verb", "idiom": "idiom",
    }
    return " | ".join(short_map.get(p.lower(), p.lower()) for p in pos_list)


def build_def(definitions: list[dict]) -> tuple[str, str, str]:
    """Build def/example/synonym strings from top-3 defs."""
    senses = [d for d in definitions if not d.get("is_idiom")]
    idioms = [d for d in definitions if d.get("is_idiom")]
    ordered = senses + idioms
    top3 = ordered[:3]

    def_parts = []
    ex_parts = []
    for d in top3:
        text = d.get("text", "").strip()
        if d.get("is_idiom"):
            text = f"[idiom] {text}"
        if text:
            def_parts.append(text)
        examples = d.get("examples", [])
        if examples:
            ex_parts.append(examples[0])

    def_text = " | ".join(def_parts) if def_parts else ""
    ex_text = " | ".join(ex_parts) if ex_parts else ""

    # Synonyms not in JSONL
    syn_text = ""
    return def_text, ex_text, syn_text


def build_audio_tags(word: str) -> tuple[str, str]:
    """Build Anki sound tag references (cambridge uk/us)."""
    safe = word.replace("/", "_").replace(" ", "-").replace("(", "").replace(")", "")
    uk = f"[sound:cambridge_uk_{safe}.mp3]"
    us = f"[sound:cambridge_us_{safe}.mp3]"
    return uk, us


def main():
    print(f"Loading {JSONL}...")
    recs = {}
    with JSONL.open("r", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            recs[r["word"]] = r
    print(f"  {len(recs)} records")

    # Build rows for words with definitions
    rows = []
    skipped_no_defs = 0
    skipped_unclassified = 0
    for word, r in sorted(recs.items()):
        defs = r.get("definitions", [])
        if not defs:
            skipped_no_defs += 1
            continue
        src = r.get("source", "oxford")
        if src == "unclassified":
            # Unclassified stubs have defs=[]; not in this branch
            skipped_unclassified += 1
            continue

        pos = pos_short(r.get("pos", []))
        def_text, ex_text, syn_text = build_def(defs)

        # IPA: not in JSONL (Oxford doesn't store it; audio in .mp3).
        # We leave empty — deck renders IPA from audio file metadata or shows blank.
        ipa = ""

        audio_uk, audio_us = build_audio_tags(word)

        # CEFR
        cefr = r.get("cefr")
        if not cefr and r.get("cambridge_cefr"):
            cefr = r["cambridge_cefr"]
        cefr_str = cefr or "UNCLASSIFIED"

        # Oxford 5000? from JSONL
        ox_5000 = "Oxford_5000" if "Oxford 5000" in (r.get("oxford_lists") or []) else ""

        # Tags
        tag_parts = [f"CEFR::{cefr_str}", "Source::Oxford"]
        if r.get("awl"):
            tag_parts.append("AWL")
        if r.get("oxford_lists"):
            for lname in r["oxford_lists"]:
                if lname not in tag_parts:
                    tag_parts.append(lname)
        if any(d.get("is_idiom") for d in defs):
            tag_parts.append("idioms")
        tag_parts.append("Audio::Cambridge")
        tags = " ".join(tag_parts)

        # Source field (12): oxford, cambridge, or oxford+cambridge
        if src == "cambridge":
            src_field = "Cambridge"
        else:
            src_field = "Oxford"

        row = [
            gen_guid(),       # 0 GUID
            NOTETYPE,         # 1
            DECK,             # 2
            word,             # 3
            pos,              # 4
            ipa,              # 5
            def_text,         # 6
            ex_text,          # 7
            syn_text,         # 8
            "",               # 9 word family
            audio_uk,         # 10
            audio_us,         # 11
            src_field,        # 12
            ox_5000,          # 13
            cefr_str,         # 14
            tags,             # 15
        ]
        rows.append("\t".join(row))

    print(f"\nGenerated {len(rows)} study rows")
    print(f"  Skipped (no defs): {skipped_no_defs}")
    print(f"  Skipped (unclassified): {skipped_unclassified}")

    # Write
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        f.write("#separator:tab\n")
        f.write("#html:true\n")
        f.write("#guid column:1\n")
        f.write("#notetype column:2\n")
        f.write("#deck column:3\n")
        f.write("#tags column:16\n")
        for r in rows:
            f.write(r + "\n")
    print(f"\nWrote {len(rows)} rows to {OUT}")


if __name__ == "__main__":
    main()
