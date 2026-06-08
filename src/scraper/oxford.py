"""Oxford Learner's Dictionary HTML parser for ielts-deck.

Single source of truth for parsing Oxford word pages. The previous
codebase had 3 nearly-identical parsers (scrape_oxford.parse_word_page,
scrape_oxford_full.parse_html, scrape_with_fallback.parse_oxford_html)
with subtle field drift. This module is the canonical v2 parser
(idiom-aware: walks parent chain to detect <div class="idioms">
ancestors and extracts the italicized <span class="idm"> phrase).

D in architecture review.

The parser is pure: takes (text: str, word: str) -> dict. It is
trivially unit-testable (no I/O, no Fetcher, no cache). Caller is
responsible for fetching the HTML and writing the result.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from src.scraper.fetch import OXFORD_URL

# CEFR ordering for head_cefr selection (lowest level wins — A1 < C2)
_CEFR_ORDER = {"A1": 1, "A2": 2, "B1": 3, "B2": 4, "C1": 5, "C2": 6}

# h1 attributes (Oxford 3000/5000 + OPAL + AWL) → list-membership flag name
_H1_ATTRS = {
    "ox3000": "Oxford 3000",
    "ox5000": "Oxford 5000",
    "opal_written": "OPAL written",
    "opal_spoken": "OPAL spoken",
    "academic": "AWL",
    "awl": "AWL",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _is_idiom_and_phrase(li) -> tuple[bool, str | None]:
    """Detect whether a sense `li` is inside an idioms block.

    Walks up to 8 ancestors looking for <div class="idioms">. If found,
    also extracts the italicized phrase from <span class="idm"> within
    the surrounding <span class="idm-g">.

    Oxford's DOM places idioms under a dedicated div, so this is the
    signal we have. The walk is bounded (8 levels) to avoid infinite
    loops in malformed HTML.
    """
    cur = li
    for _ in range(8):
        cur = cur.parent
        if not cur:
            return False, None
        if cur.name == "div" and "idioms" in (cur.get("class") or []):
            idm_span = li.find_parent("span", class_="idm-g")
            phrase = None
            if idm_span:
                ph = idm_span.find("span", class_="idm")
                if ph:
                    phrase = ph.get_text(" ", strip=True)
            return True, phrase
    return False, None


def _list_flags_from_h1(h1) -> dict[str, bool]:
    """Read Oxford list-membership flags (ox3000/ox5000/OPAL/AWL) from h1 attrs."""
    flags: dict[str, bool] = {}
    if not h1:
        return flags
    for attr, target in _H1_ATTRS.items():
        if h1.get(attr) == "y":
            flags[target] = True
    return flags


def parse_oxford_html(text: str, word: str) -> dict:
    """Parse Oxford word page HTML → structured record.

    Returns a dict with fields:
      word, source ('oxford'), source_url, fetched_at,
      cefr (head_cefr, lowest across senses), pos, register_tags,
      subject_labels, oxford_lists, opal, awl,
      definitions: list of {n, sensenum_local, is_idiom, idm_phrase,
                            text, examples}

    On missing #entryContent, returns {'word': word, 'error': '...'} —
    callers should check for 'error' key.
    """
    soup = BeautifulSoup(text, "lxml")
    entry = soup.find(id="entryContent")
    if not entry:
        return {"word": word, "error": "no #entryContent"}

    pos_list = [el.get_text(strip=True) for el in entry.find_all("span", class_="pos")]
    list_flags = _list_flags_from_h1(entry.find("h1", class_="headword"))

    sense_lis = entry.find_all("li", class_="sense")
    cefr_levels: list[str] = []
    register_tags: list[str] = []
    subject_labels: list[str] = []
    definitions: list[dict] = []

    for n, li in enumerate(sense_lis, start=1):
        is_idiom, idm_phrase = _is_idiom_and_phrase(li)

        # Per-def CEFR (prefer fkcefr, fall back to cefr). Validated to be
        # one of the 6 standard levels — invalid values are ignored.
        sense_cefr = ""
        for attr in ("fkcefr", "cefr"):
            v = (li.get(attr) or "").upper()
            if v in _CEFR_ORDER:
                sense_cefr = v
                break
        if sense_cefr and sense_cefr not in cefr_levels:
            cefr_levels.append(sense_cefr)

        for la in li.find_all("span", class_="labels"):
            text_l = la.get_text(" ", strip=True).strip("()")
            for piece in re.split(r",\s*", text_l):
                piece = piece.strip()
                if piece and piece not in register_tags:
                    register_tags.append(piece)
        for ta in li.find_all("span", class_="topic"):
            # Topic anchors live on the inner <a>, not the span. Skip the
            # "l2:functions:" noise (function-word list).
            anchor = ta.find("a")
            href = (anchor.get("href", "") if anchor else "")
            if href.startswith("l2:functions:"):
                continue
            tn = ta.find(class_="topic_name")
            if tn:
                t = tn.get_text(strip=True)
                if t and t not in subject_labels:
                    subject_labels.append(t)
        def_span = li.find("span", class_="def")
        def_text = def_span.get_text(" ", strip=True) if def_span else ""
        examples = [
            ex.get_text(" ", strip=True)
            for ex in li.find_all("span", class_="x")
            if ex.get_text(strip=True)
        ]
        sensenum_local = li.get("sensenum")
        definitions.append({
            "n": n,
            "sensenum_local": sensenum_local,
            "is_idiom": is_idiom,
            "idm_phrase": idm_phrase,
            "text": def_text,
            "examples": examples,
            "def_cefr": sense_cefr,
        })

    head_cefr = (
        min(cefr_levels, key=lambda c: _CEFR_ORDER.get(c, 99))
        if cefr_levels else None
    )

    return {
        "word": word,
        "source": "oxford",
        "source_url": OXFORD_URL.format(word=word),
        "fetched_at": _now_iso(),
        "cefr": head_cefr,
        "pos": pos_list,
        "register_tags": register_tags,
        "subject_labels": subject_labels,
        "oxford_lists": [name for name in ("Oxford 3000", "Oxford 5000") if list_flags.get(name)],
        "opal": "OPAL written" if list_flags.get("OPAL written")
                else ("OPAL spoken" if list_flags.get("OPAL spoken") else None),
        "awl": "AWL" if list_flags.get("AWL") else None,
        "definitions": definitions,
    }
