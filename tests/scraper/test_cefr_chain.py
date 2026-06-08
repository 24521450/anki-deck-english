"""Tests for src.scraper.cefr_chain.

Covers:
- Chain order: def_cefr > vocab_per_pos > head_cefr > cambridge_cefr > unclassified
- POS cleaning (raw "Verb" / "adjective" -> cleaned short form matches vocab key)
- load_vocab_cefr: comma-separated POS cells, multi-POS rows, invalid CEFR skipped
- Disputed-records invariant: chain reads rec honestly, no defensive pollution hack
"""
from __future__ import annotations

from pathlib import Path

from src.scraper.cefr_chain import (
    CefrContext,
    clean_pos,
    load_vocab_cefr,
    resolve_def,
)


def ctx_with(
    word: str = "test",
    head_cefr: str = "",
    cambridge_cefr: str = "",
    vocab_cefr: dict | None = None,
) -> CefrContext:
    return CefrContext(
        word=word,
        head_cefr=head_cefr,
        cambridge_cefr=cambridge_cefr,
        vocab_cefr=vocab_cefr if vocab_cefr is not None else {},
    )


# ── chain order ────────────────────────────────────────────────────


def test_def_cefr_wins_over_head_cefr():
    """Step 1 beats Step 4 even when head is higher-ranked."""
    ctx = ctx_with(head_cefr="C2")
    assert resolve_def({"def_cefr": "B2"}, ctx) == ("B2", "oxford")


def test_vocab_per_pos_beats_head_cefr():
    """Step 2 beats Step 4 when def has POS that matches vocab key."""
    vocab = {"run": {"v": "B2"}}
    ctx = ctx_with(word="run", head_cefr="C1", vocab_cefr=vocab)
    assert resolve_def({"pos": "v"}, ctx) == ("B2", "oxford")


def test_head_cefr_fallback_when_no_def_no_vocab():
    """Step 4 wins when def has no def_cefr and no vocab match."""
    ctx = ctx_with(head_cefr="B2")
    assert resolve_def({"pos": "noun"}, ctx) == ("B2", "oxford")


def test_cambridge_only_when_oxford_exhausted():
    """Step 5 wins only when Steps 1, 2, 4 have no signal."""
    ctx = ctx_with(cambridge_cefr="B2")
    assert resolve_def({"pos": ""}, ctx) == ("B2", "cambridge")


def test_unclassified_when_all_empty():
    """Step 6 when everything is empty."""
    assert resolve_def({}, ctx_with()) == ("UNCLASSIFIED", "unclassified")


# ── POS cleaning ───────────────────────────────────────────────────


def test_pos_cleaning_capitalized_verb():
    """Raw 'Verb' cleans to 'v' and matches vocab key."""
    vocab = {"run": {"v": "B2"}}
    ctx = ctx_with(word="run", vocab_cefr=vocab)
    assert resolve_def({"pos": "Verb"}, ctx) == ("B2", "oxford")


def test_pos_cleaning_long_form_adjective():
    """Long-form 'adjective' cleans to 'adj'."""
    vocab = {"happy": {"adj": "A2"}}
    ctx = ctx_with(word="happy", vocab_cefr=vocab)
    assert resolve_def({"pos": "adjective"}, ctx) == ("A2", "oxford")


def test_pos_cleaning_no_match_falls_through_to_head():
    """Unrecognized POS misses Step 2, falls to Step 4."""
    ctx = ctx_with(head_cefr="B2")
    assert resolve_def({"pos": "interjection"}, ctx) == ("B2", "oxford")


def test_pos_cleaning_trailing_period_stripped():
    """POS strings with trailing period (e.g. 'verb.') still match."""
    vocab = {"run": {"v": "B2"}}
    ctx = ctx_with(word="run", vocab_cefr=vocab)
    assert resolve_def({"pos": "verb."}, ctx) == ("B2", "oxford")


# ── load_vocab_cefr ────────────────────────────────────────────────


def test_load_vocab_cleans_and_splits_comma_pos(tmp_path: Path):
    md = tmp_path / "Oxford_3000.md"
    md.write_text(
        "| **run** | verb, noun | B2 | Oxford 3000 |\n"
        "| **happy** | adjective | A2 | Oxford 3000 |\n",
        encoding="utf-8",
    )
    out = load_vocab_cefr(tmp_path)
    assert out == {
        "run": {"v": "B2", "n": "B2"},
        "happy": {"adj": "A2"},
    }


def test_load_vocab_skips_invalid_cefr(tmp_path: Path):
    md = tmp_path / "Oxford_3000.md"
    md.write_text(
        "| **weird** | noun | Z9 | Oxford 3000 |\n",
        encoding="utf-8",
    )
    assert load_vocab_cefr(tmp_path) == {}


def test_load_vocab_lowercases_word_keys(tmp_path: Path):
    md = tmp_path / "Oxford_3000.md"
    md.write_text(
        "| **Run** | verb | B2 | Oxford 3000 |\n",
        encoding="utf-8",
    )
    out = load_vocab_cefr(tmp_path)
    assert "run" in out
    assert "Run" not in out


def test_clean_pos_unit_table():
    assert clean_pos("adjective") == "adj"
    assert clean_pos("Adjective") == "adj"
    assert clean_pos("adjective.") == "adj"
    assert clean_pos("verb") == "v"
    assert clean_pos("noun") == "n"
    assert clean_pos("adverb") == "adv"
    assert clean_pos("preposition") == "prep"
    assert clean_pos("unknownpos") == "unknownpos"


# ── disputed-records invariant ─────────────────────────────────────


def test_chain_reads_rec_honestly_no_pollution_detection():
    """Chain is NOT defensive against pollution: if rec['cefr'] (head)
    and rec['cambridge_cefr'] carry the same value, Step 4 still
    tags 'oxford'. Pollution is an upstream write concern (see
    _cleanup_oxford_pollution.py), not a chain read concern.
    """
    polluted = ctx_with(head_cefr="B2", cambridge_cefr="B2")
    assert resolve_def({"pos": ""}, polluted) == ("B2", "oxford")


def test_chain_prefers_cambridge_only_when_no_head():
    """When head is empty, cambridge wins. Inverse of above."""
    ctx = ctx_with(head_cefr="", cambridge_cefr="B2")
    assert resolve_def({"pos": ""}, ctx) == ("B2", "cambridge")
