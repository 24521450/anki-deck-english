"""Cross-cutting tests for the CEFR resolution chain.

This file lives at tests/ root (non-mirrored) per AGENTS.md convention
for cross-cutting infra. The bulk of chain tests live in
tests/scraper/test_cefr_chain.py (mirrored). This file captures the
behaviour the previous chain_resolve() in _fix_study_list_cefr.py
asserted, migrated to the new module's interface.
"""
from src.scraper.cefr_chain import CefrContext, resolve_def, load_vocab_cefr


def _ctx(word, head_cefr="", cambridge_cefr="", vocab_cefr=None):
    return CefrContext(
        word=word,
        head_cefr=head_cefr,
        cambridge_cefr=cambridge_cefr,
        vocab_cefr=vocab_cefr if vocab_cefr is not None else {},
    )


def test_chain_resolve_basic_head_cefr():
    """Word with head_cefr and a single def resolves to (head, oxford)."""
    rec_cefr = "B2"
    defs = [{"text": "some def"}]
    ctx = _ctx("testword", head_cefr=rec_cefr)
    result = [resolve_def(d, ctx) for d in defs]
    assert result == [("B2", "oxford")]


def test_chain_resolve_cambridge_fallback():
    """No head_cefr + no def_cefr → cambridge wins (Step 5)."""
    defs = [{"text": "some def"}]
    ctx = _ctx("constrain", cambridge_cefr="C2")
    result = [resolve_def(d, ctx) for d in defs]
    assert result == [("C2", "cambridge")]


def test_chain_resolve_def_cefr_beats_cambridge():
    """Step 1 (def_cefr) wins even when cambridge_cefr has a value.

    The old test_chain_resolve_non_official_prefers_cambridge asserted
    cambridge_cefr beats def_cefr. That was a defensive hack — the new
    chain is honest: it reads rec as-is. Step 1 wins. This test
    documents the corrected behaviour.
    """
    defs = [{"text": "some def", "def_cefr": "B1"}]
    ctx = _ctx("chore", head_cefr="B1", cambridge_cefr="C1")
    result = [resolve_def(d, ctx) for d in defs]
    assert result == [("B1", "oxford")]


def test_chain_resolve_chore_no_def_cefr_prefers_head_over_cambridge():
    """No def_cefr, head_cefr present → head wins (Step 4 beats Step 5).

    The old test_chain_resolve_non_official_prefers_cambridge asserted
    cambridge beats def_cefr. The new chain is honest and order-stable:
    head_cefr (Step 4) beats cambridge_cefr (Step 5). For a word to
    land on cambridge in the new chain, both Step 1 (def_cefr) and
    Step 4 (head_cefr) must be empty. This test pins that contract.
    """
    defs = [{"text": "some def"}]
    ctx = _ctx("chore", head_cefr="B1", cambridge_cefr="C1")
    result = [resolve_def(d, ctx) for d in defs]
    assert result == [("B1", "oxford")]


def test_chain_resolve_chore_only_cambridge():
    """Pure cambridge-only word (no def_cefr, no head_cefr) → cambridge wins.

    This is the 'cambridge wins for non-official words' intent from
    the old test, now expressed correctly: head_cefr is empty, so
    the chain falls through to Step 5.
    """
    defs = [{"text": "some def"}]
    ctx = _ctx("chore", head_cefr="", cambridge_cefr="C1")
    result = [resolve_def(d, ctx) for d in defs]
    assert result == [("C1", "cambridge")]
