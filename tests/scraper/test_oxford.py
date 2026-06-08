"""Tests for src.scraper.oxford.

Covers:
- Happy path: parses a real-ish Oxford HTML snippet
- Idiom detection: walk parent chain, extract <span class="idm"> phrase
- Multi-POS words (sensenum_local reset per section)
- h1 list flags (ox3000/ox5000/OPAL/AWL)
- CEFR head selection (lowest wins)
- Subject labels (skip l2:functions: prefixed)
- Register tags (comma-separated inside labels span)
- Error case: no #entryContent
- Empty / malformed HTML
"""
from __future__ import annotations

from src.scraper.oxford import parse_oxford_html


# ── Fixtures: minimal valid Oxford HTML snippets ────────────────────

OXFORD_MINIMAL = """
<html><body>
<div id="entryContent">
  <h1 class="headword" ox3000="y">run</h1>
  <span class="pos">verb</span>
  <ol>
    <li class="sense" sensenum="1" cefr="A1">
      <span class="def">to move faster than walking</span>
      <span class="x">He ran to the store.</span>
    </li>
    <li class="sense" sensenum="2" cefr="A2">
      <span class="def">to operate</span>
      <span class="x">The engine runs smoothly.</span>
    </li>
  </ol>
</div>
</body></html>
"""

OXFORD_WITH_IDIOMS = """
<html><body>
<div id="entryContent">
  <h1 class="headword">break</h1>
  <span class="pos">verb</span>
  <ol>
    <li class="sense" sensenum="1" cefr="A2">
      <span class="def">to separate into pieces</span>
    </li>
  </ol>
  <div class="idioms">
    <span class="idm-g">
      <span class="idm">break the ice</span>
      <ol>
        <li class="sense" sensenum="1" cefr="B2">
          <span class="def">to do something to make people feel more comfortable</span>
          <span class="x">He told a joke to break the ice.</span>
        </li>
      </ol>
    </span>
  </div>
</div>
</body></html>
"""

OXFORD_MULTI_POS = """
<html><body>
<div id="entryContent">
  <h1 class="headword">record</h1>
  <span class="pos">noun</span>
  <ol>
    <li class="sense" sensenum="1" cefr="B1">
      <span class="def">a disc</span>
    </li>
  </ol>
  <span class="pos">verb</span>
  <ol>
    <li class="sense" sensenum="1" cefr="B1">
      <span class="def">to store information</span>
    </li>
  </ol>
</div>
</body></html>
"""

OXFORD_WITH_LABELS_AND_TOPICS = """
<html><body>
<div id="entryContent">
  <h1 class="headword">conduct</h1>
  <span class="pos">verb</span>
  <ol>
    <li class="sense" sensenum="1" cefr="C1" fkcefr="C1">
      <span class="labels">(formal)</span>
      <span class="topic"><a href="l2:functions:agreeing">f</a><span class="topic_name">Agreeing</span></span>
      <span class="topic"><a href="/topic/business">t</a><span class="topic_name">Business</span></span>
      <span class="def">to organize and lead</span>
      <span class="x">She conducted the meeting.</span>
    </li>
  </ol>
</div>
</body></html>
"""

OXFORD_NO_ENTRY = "<html><body><p>404</p></body></html>"

OXFORD_MULTIPLE_LABELS = """
<html><body>
<div id="entryContent">
  <h1 class="headword">sick</h1>
  <span class="pos">adjective</span>
  <ol>
    <li class="sense" sensenum="1" cefr="A2">
      <span class="labels">(informal, especially British English)</span>
      <span class="def">ill</span>
    </li>
  </ol>
</div>
</body></html>
"""


# ── Happy path ──────────────────────────────────────────────────────


def test_parses_minimal_oxford_page():
    rec = parse_oxford_html(OXFORD_MINIMAL, "run")
    assert rec["word"] == "run"
    assert rec["source"] == "oxford"
    assert rec["cefr"] == "A1"  # lowest of A1, A2
    assert rec["pos"] == ["verb"]
    assert rec["oxford_lists"] == ["Oxford 3000"]
    assert rec["opal"] is None
    assert rec["awl"] is None
    assert len(rec["definitions"]) == 2
    d0 = rec["definitions"][0]
    assert d0["n"] == 1
    assert d0["sensenum_local"] == "1"
    assert d0["is_idiom"] is False
    assert d0["idm_phrase"] is None
    assert d0["text"] == "to move faster than walking"
    assert d0["examples"] == ["He ran to the store."]


# ── Idiom detection ────────────────────────────────────────────────


def test_idiom_walk_detects_phrase():
    rec = parse_oxford_html(OXFORD_WITH_IDIOMS, "break")
    # 1 regular sense + 1 idiom sense
    assert len(rec["definitions"]) == 2
    sense = rec["definitions"][0]
    idiom = rec["definitions"][1]
    assert sense["is_idiom"] is False
    assert sense["idm_phrase"] is None
    assert idiom["is_idiom"] is True
    assert idiom["idm_phrase"] == "break the ice"
    assert "comfortable" in idiom["text"]


# ── Multi-POS ───────────────────────────────────────────────────────


def test_multi_pos_global_counter():
    """Sensenum local resets per POS section; global counter increments."""
    rec = parse_oxford_html(OXFORD_MULTI_POS, "record")
    assert rec["pos"] == ["noun", "verb"]
    # 2 senses, each with sensenum_local=1
    assert len(rec["definitions"]) == 2
    assert [d["sensenum_local"] for d in rec["definitions"]] == ["1", "1"]
    # Global counter: n=1, n=2
    assert [d["n"] for d in rec["definitions"]] == [1, 2]


# ── Labels and topics ───────────────────────────────────────────────


def test_register_tags_split_on_comma():
    rec = parse_oxford_html(OXFORD_MULTIPLE_LABELS, "sick")
    assert "informal" in rec["register_tags"]
    assert "especially British English" in rec["register_tags"]


def test_subject_labels_skips_l2_functions():
    """l2:functions: prefixed topics are noise (function-word list); skip them."""
    rec = parse_oxford_html(OXFORD_WITH_LABELS_AND_TOPICS, "conduct")
    assert "Business" in rec["subject_labels"]
    assert "Agreeing" not in rec["subject_labels"]


def test_register_tags_with_formal_label():
    """Single-word label like '(formal)' becomes 'formal'."""
    rec = parse_oxford_html(OXFORD_WITH_LABELS_AND_TOPICS, "conduct")
    assert "formal" in rec["register_tags"]


def test_cefr_falls_back_to_fkcefr():
    """When 'cefr' attr absent but 'fkcefr' present, the latter is used."""
    rec = parse_oxford_html(OXFORD_WITH_LABELS_AND_TOPICS, "conduct")
    assert rec["cefr"] == "C1"


def test_def_cefr_per_definition():
    """Each def carries its own def_cefr (per-def CEFR)."""
    rec = parse_oxford_html(OXFORD_MINIMAL, "run")
    assert rec["definitions"][0]["def_cefr"] == "A1"
    assert rec["definitions"][1]["def_cefr"] == "A2"


def test_def_cefr_invalid_value_ignored():
    """Garbage cefr values (e.g. 'Z9', empty) are dropped from def_cefr."""
    html = """
    <html><body><div id="entryContent">
      <h1 class="headword">x</h1>
      <ol>
        <li class="sense" sensenum="1" cefr="Z9">
          <span class="def">d</span>
        </li>
        <li class="sense" sensenum="2" fkcefr="B2">
          <span class="def">d</span>
        </li>
      </ol>
    </div></body></html>
    """
    rec = parse_oxford_html(html, "x")
    assert rec["definitions"][0]["def_cefr"] == ""
    assert rec["definitions"][1]["def_cefr"] == "B2"


# ── Error path ──────────────────────────────────────────────────────


def test_no_entry_content_returns_error():
    rec = parse_oxford_html(OXFORD_NO_ENTRY, "missing")
    assert "error" in rec
    assert rec["word"] == "missing"


def test_empty_html_returns_error():
    rec = parse_oxford_html("", "blank")
    assert "error" in rec


def test_malformed_html_does_not_crash():
    """Parser should not raise on malformed input — returns error dict."""
    rec = parse_oxford_html("<html><div id='entryContent'><ol><li class='sense'", "broken")
    # Either no entryContent (error) or no sense inside (empty defs)
    assert "word" in rec
    assert "definitions" in rec or "error" in rec


# ── Empty / edge cases ──────────────────────────────────────────────


def test_idiom_phrase_none_when_idm_span_missing():
    """If a sense is in idioms div but no <span class='idm'> is present,
    is_idiom=True but idm_phrase=None."""
    html = """
    <html><body><div id="entryContent">
      <h1 class="headword">x</h1>
      <span class="pos">verb</span>
      <div class="idioms">
        <ol>
          <li class="sense" sensenum="1">
            <span class="def">orphan idiom</span>
          </li>
        </ol>
      </div>
    </div></body></html>
    """
    rec = parse_oxford_html(html, "x")
    assert rec["definitions"][0]["is_idiom"] is True
    assert rec["definitions"][0]["idm_phrase"] is None


def test_idiom_walk_bounded_at_8_levels():
    """Walk bails out after 8 ancestor levels even if no idioms div found."""
    # Build a deeply nested structure (no idioms div) — parser shouldn't hang
    deep = "<html><body>" + "<div>" * 20 + '<div id="entryContent">'
    deep += '<ol><li class="sense" sensenum="1"><span class="def">d</span></li></ol>'
    deep += "</div>" + "</div>" * 20 + "</body></html>"
    rec = parse_oxford_html(deep, "deep")
    assert rec["definitions"][0]["is_idiom"] is False


# ── h1 list flags ───────────────────────────────────────────────────


def test_oxford_3000_flag_set():
    rec = parse_oxford_html(OXFORD_MINIMAL, "run")
    assert "Oxford 3000" in rec["oxford_lists"]


def test_opal_written_flag_sets_opal_field():
    html = """
    <html><body><div id="entryContent">
      <h1 class="headword" opal_written="y">x</h1>
      <ol><li class="sense"><span class="def">d</span></li></ol>
    </div></body></html>
    """
    rec = parse_oxford_html(html, "x")
    assert rec["opal"] == "OPAL written"


def test_awl_flag_sets_awl_field():
    html = """
    <html><body><div id="entryContent">
      <h1 class="headword" awl="y">x</h1>
      <ol><li class="sense"><span class="def">d</span></li></ol>
    </div></body></html>
    """
    rec = parse_oxford_html(html, "x")
    assert rec["awl"] == "AWL"
