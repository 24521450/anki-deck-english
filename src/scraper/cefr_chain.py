"""CEFR resolution chain for ielts-deck.

Resolves the CEFR level for an Oxford Learner's Dictionary definition
using a 5-step chain. Single source of truth for CEFR tagging on cards.

Chain (priority order, first match wins):
    1. d['def_cefr']              (per-def, from fkcefr/cefr attr at scrape time)
    2. vocab_cefr[word][d.pos]    (per-POS from vocab_list/Oxford/*.md)
    3. ctx.head_cefr              (record-level Oxford head_cefr = rec['cefr'])
    4. ctx.cambridge_cefr         (record-level = rec['cambridge_cefr'])
    5. UNCLASSIFIED               (no signal)

Step 3 (per-word lowest CEFR fallback) was REMOVED 2026-06-08: it was
incorrect for multi-POS words (e.g. just/adv=A1 made Step 3 return A1
even when the adjective sense should be C1). Step 4 (head_cefr) handles
multi-POS coverage instead; the scraper multi-POS pass populates extra
senses with their own def_cefr.

The chain is honest: it reads rec as-is. If `rec['cefr']` is polluted
with a Cambridge value (the bug fixed by _cleanup_oxford_pollution.py),
the chain still tags Step 4 as 'oxford'. Pollution is an upstream
write concern, not a chain read concern.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

CEFR_LEVELS: tuple[str, ...] = ("A1", "A2", "B1", "B2", "C1", "C2")
CEFR_RANK: dict[str, int] = {lvl: i + 1 for i, lvl in enumerate(CEFR_LEVELS)}
CEFR_RANK["UNCLASSIFIED"] = 99
CEFR_RANK[""] = 99

SOURCE_OXFORD = "oxford"
SOURCE_CAMBRIDGE = "cambridge"
SOURCE_UNCLASSIFIED = "unclassified"


def clean_pos(p: str) -> str:
    """Normalize POS string to short form used in vocab tables.

    "adjective" -> "adj", "verb" -> "v", etc. Unknown forms pass through
    lowercased and stripped.
    """
    p = p.strip().lower().rstrip(".")
    mapping = {
        "adjective": "adj",
        "adverb": "adv",
        "noun": "n",
        "verb": "v",
        "preposition": "prep",
        "pronoun": "pron",
        "conjunction": "conj",
        "determiner": "det",
    }
    return mapping.get(p, p)


def load_vocab_cefr(vocab_dir: Path) -> dict[str, dict[str, str]]:
    """Parse markdown tables in `vocab_dir` into word -> {pos: cefr} map.

    Caller passes the directory containing the .md files (e.g.
    `vocab_list/Oxford/`). POS cells are comma-separated; each POS is
    cleaned via clean_pos(). CEFR values not in CEFR_LEVELS are skipped.
    """
    table_re = re.compile(
        r"\|\s*\*\*([^*]+)\*\*\s*\|\s*([^|]+)\|\s*([ABC][12])\s*\|"
    )
    out: dict[str, dict[str, str]] = {}
    for md in sorted(vocab_dir.glob("*.md")):
        text = md.read_text(encoding="utf-8", errors="replace")
        for m in table_re.finditer(text):
            word_raw, pos_raw, cefr = (g.strip() for g in m.groups())
            if cefr not in CEFR_LEVELS:
                continue
            word = word_raw.lower()
            for p in pos_raw.split(","):
                cp = clean_pos(p)
                if cp:
                    out.setdefault(word, {})[cp] = cefr
    return out


@dataclass(frozen=True)
class CefrContext:
    """Per-record inputs to the CEFR chain. Build once per record,
    reuse across all defs in the record.
    """
    word: str
    head_cefr: str            # rec['cefr']  (Oxford scrape)
    cambridge_cefr: str       # rec['cambridge_cefr']
    vocab_cefr: dict          # word -> {pos: cefr}, from load_vocab_cefr


def resolve_def(defn: dict, ctx: CefrContext) -> tuple[str, str]:
    """Apply CEFR resolution chain to one definition.

    Returns (level, source) where:
      - level ∈ {A1..C2, 'UNCLASSIFIED'}
      - source ∈ {'oxford', 'cambridge', 'unclassified'}

    Chain (priority order, first match wins):
      1. defn['def_cefr']            → (level, 'oxford')
      2. vocab_cefr[word][d.pos]     → (level, 'oxford')
      3. ctx.head_cefr               → (level, 'oxford')
      4. ctx.cambridge_cefr          → (level, 'cambridge')
      5. fallback                    → ('UNCLASSIFIED', 'unclassified')
    """
    # Step 1: per-def CEFR (most accurate — set by parser from fkcefr/cefr attr)
    def_cefr = defn.get("def_cefr") or ""
    if def_cefr:
        return (def_cefr, SOURCE_OXFORD)

    # Step 2: per-POS vocab lookup
    d_pos = clean_pos(defn.get("pos", "") or "")
    word_pos_map = ctx.vocab_cefr.get(ctx.word.lower(), {})
    if d_pos and d_pos in word_pos_map:
        return (word_pos_map[d_pos], SOURCE_OXFORD)

    # Step 3 (REMOVED): per-word lowest CEFR fallback. See module docstring.

    # Step 4: record-level Oxford head CEFR
    if ctx.head_cefr:
        return (ctx.head_cefr, SOURCE_OXFORD)

    # Step 5: record-level Cambridge CEFR
    if ctx.cambridge_cefr:
        return (ctx.cambridge_cefr, SOURCE_CAMBRIDGE)

    # Step 6: unclassified
    return ("UNCLASSIFIED", SOURCE_UNCLASSIFIED)
