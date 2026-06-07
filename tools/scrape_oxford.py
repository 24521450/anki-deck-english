"""Scrape Oxford Learner's Dictionary for ielts-deck design system.

Sources:
  1. https://www.oxfordlearnersdictionaries.com/about/english/labels  (labels taxonomy)
  2-6. Word pages for design pattern examples:
      rigorous, yield, aggregate, sick, paradigm

Outputs:
  data/.cache_html/oxford_<slug>.html   raw cached HTML
  data/oxford_labels.json                parsed labels taxonomy
  data/oxford_samples.json               parsed word samples
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

# --------------------------------------------------------------------------- #
# Paths and constants
# --------------------------------------------------------------------------- #
REPO = Path(r"C:\Users\admin\Downloads\ielts-deck")
CACHE_DIR = REPO / "data" / ".cache_html"
DATA_DIR = REPO / "data"
VOCAB_DIR = REPO / "vocab_list"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

LABELS_URL = "https://www.oxfordlearnersdictionaries.com/about/english/labels"
WORD_URLS = {
    "rigorous": "https://www.oxfordlearnersdictionaries.com/definition/english/rigorous",
    "yield":    "https://www.oxfordlearnersdictionaries.com/definition/english/yield",
    "aggregate":"https://www.oxfordlearnersdictionaries.com/definition/english/aggregate",
    "sick":     "https://www.oxfordlearnersdictionaries.com/definition/english/sick",
    "paradigm": "https://www.oxfordlearnersdictionaries.com/definition/english/paradigm",
}

# Word families — hard-coded (Oxford JS-renders these as derivative icons, not in static HTML)
WORD_FAMILIES = {
    "rigorous": ["rigor (n.)", "rigorously (adv.)", "rigorousness (n.)"],
    "yield":    ["yield (v.)", "yielding (adj.)", "yield (n.)"],
    "aggregate":["aggregate (n.)", "aggregate (v.)", "aggregate (adj.)",
                 "aggregation (n.)", "aggregated (adj.)", "aggregator (n.)"],
    "sick":     ["sick (adj.)", "sick (n.)", "sicken (v.)", "sickening (adj.)",
                 "sickly (adj.)", "sickness (n.)"],
    "paradigm": ["paradigm (n.)", "paradigmatic (adj.)", "paradigmatically (adv.)"],
}

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def fetch(url: str, cache_path: Path) -> str:
    """Fetch URL with throttle; cache raw HTML."""
    if cache_path.exists():
        text = cache_path.read_text(encoding="utf-8")
        return text
    print(f"  GET {url}", flush=True)
    r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(r.text, encoding="utf-8")
    time.sleep(1.0)  # throttle ≤1 req/sec
    return r.text


# --------------------------------------------------------------------------- #
# Labels page parsing
# --------------------------------------------------------------------------- #
def parse_labels(html: str, source_url: str) -> dict:
    soup = BeautifulSoup(html, "lxml")

    # 1. Symbols table: each row has icon <img>/<span class="..."> + description
    symbols: list[dict] = []
    sym_table = soup.find("table")
    if sym_table:
        for tr in sym_table.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 2:
                continue
            icon_cell = tds[0]
            desc_cell = tds[1]
            desc_text = desc_cell.get_text(" ", strip=True)

            # Try to derive a short name from the icon
            name = None
            img = icon_cell.find("img")
            if img:
                alt = img.get("alt", "").strip()
                if alt:
                    name = alt
            if not name:
                span = icon_cell.find("span")
                if span:
                    cls = " ".join(span.get("class", []))
                    # Map class names to readable names
                    if "oxford3000" in cls.lower():
                        name = "Oxford 3000"
                    elif "oxford5000" in cls.lower():
                        name = "Oxford 5000"
                    elif "academic" in cls.lower():
                        name = "Academic Word List"
            # Derive a human-readable name from the description if we still don't have one
            if not name:
                # First non-article noun phrase in the description
                first_clause = desc_text.split(",")[0]
                # Clean up: remove leading "in the Oxford ..."
                name = re.sub(r"^in the (Oxford [^,]+),\s*", "", first_clause).strip()
                # Truncate at sentence boundary
                if len(name) > 80:
                    name = name[:80].rsplit(" ", 1)[0]
            symbols.append({"name": name, "description": desc_text})

    # 2. Register labels: first <ul class="disc">
    register_labels: list[dict] = []
    usage_restrictions: list[dict] = []

    disc_uls = soup.find_all("ul", class_="disc")
    # First 12-item ul = register labels
    # Second 5-item ul = usage restrictions
    for ul_idx, ul in enumerate(disc_uls):
        items = ul.find_all("li", recursive=False)
        for li in items:
            # First child: <span class="lb">bold name</span> then description
            name_span = li.find("span", class_="lb") or li.find(["b", "strong"])
            if not name_span:
                # Some have <em> or just text. Take first word.
                txt = li.get_text(" ", strip=True)
                first_word = txt.split()[0] if txt.split() else ""
                name = first_word
                description = txt
            else:
                name = name_span.get_text(strip=True)
                # Description = whole li text minus the name
                full = li.get_text(" ", strip=True)
                if full.startswith(name):
                    description = full[len(name):].lstrip(" .,")
                else:
                    description = full
            # Extract examples. Priority order: "Examples are" / "Example:" >
            # "as in" > "for example". The first two are almost always a list of
            # example words; "for example" sometimes continues the description
            # (e.g. "for example people of the same age...").
            examples: list[str] = []
            for marker in ("Examples are", "Example:", "as in", "for example"):
                m = re.search(re.escape(marker) + r"\s+(.+?)\.(?:\s|\(|$)",
                              description, re.IGNORECASE | re.DOTALL)
                if m:
                    ex_text = m.group(1).strip()
                    tokens = [t.strip() for t in ex_text.split(",") if t.strip()]
                    short_tokens = [t for t in tokens if " " not in t and len(t) < 30]
                    if short_tokens and len(short_tokens) == len(tokens):
                        examples = short_tokens
                    elif tokens:
                        examples = [ex_text]
                    break
            record = {"name": name, "description": description, "examples_given": examples}
            if ul_idx == 0:
                register_labels.append(record)
            else:
                usage_restrictions.append(record)

    # 3. Subject labels: paragraph mentioning OLDAE
    subject_labels: list[str] = []
    for p in soup.find_all("p"):
        txt = p.get_text(" ", strip=True)
        if "OLDAE" in txt and "subject area" in txt.lower():
            colon = txt.find(":")
            if colon > 0:
                list_text = txt[colon + 1:].rstrip(" .")
                for token in list_text.split(","):
                    tok = token.strip()
                    if tok:
                        subject_labels.append(tok)
            break

    # The labels page intentionally puts 23 academic subject names in the OLDAE
    # paragraph. Sanity check.
    if len(subject_labels) != 23:
        print(f"  WARN: expected 23 subject labels, got {len(subject_labels)}", file=sys.stderr)

    return {
        "source_url": source_url,
        "fetched_at": now_iso(),
        "symbols": symbols,
        "register_labels": register_labels,
        "usage_restrictions": usage_restrictions,
        "subject_labels": subject_labels,
    }


# --------------------------------------------------------------------------- #
# Word page parsing
# --------------------------------------------------------------------------- #
# Oxford puts list-membership flags on the headword <h1> as bare attributes, and
# on individual sense <li>s as either bare or `fk`-prefixed attributes. The
# flags we care about:
#   ox3000 / ox5000 / fkox3000 / fkox5000    — Oxford 3000 / 5000 membership
#   opal_written / opal_spoken / fkopalwritten / fkopalspoken — OPAL lists
#   academic / awl                             — Academic Word List (AWL)
# CEFR appears as a bare `cefr=` attribute or as `fkcefr=`. The `random`
# attribute is unrelated (it's for the "random word" feature) and is ignored.
LIST_ATTRS_HEAD: dict[str, tuple[str, ...]] = {
    "ox3000":      ("Oxford 3000",),
    "ox5000":      ("Oxford 5000",),
    "opal_written":("OPAL written",),
    "opal_spoken": ("OPAL spoken",),
    "academic":    ("AWL",),
    "awl":         ("AWL",),
}
LIST_ATTRS_SENSE: dict[str, tuple[str, ...]] = {
    "ox3000":      ("Oxford 3000",),
    "ox5000":      ("Oxford 5000",),
    "fkox3000":    ("Oxford 3000",),
    "fkox5000":    ("Oxford 5000",),
    # Oxford 5000 always implies Oxford 3000 (per labels description)
    "opal_written":("OPAL written",),
    "opal_spoken": ("OPAL spoken",),
    "fkopalwritten":("OPAL written",),
    "fkopalspoken":("OPAL spoken",),
    "academic":    ("AWL",),
    "awl":         ("AWL",),
}


def _collect_list_flags(el, mapping: dict[str, tuple[str, ...]],
                        flags: dict[str, bool]) -> None:
    for attr, targets in mapping.items():
        if el.get(attr) == "y":
            for t in targets:
                flags[t] = True


def parse_word_page(html: str, word: str, source_url: str,
                    awl_words: set[str]) -> dict:
    soup = BeautifulSoup(html, "lxml")
    entry = soup.find(id="entryContent")
    if not entry:
        return {
            "word": word, "source_url": source_url,
            "cefr": None, "pos": [], "register_tags": [],
            "subject_labels": [], "oxford_lists": [],
            "opal": None, "awl": None,
            "definitions": [], "word_family": WORD_FAMILIES.get(word, []),
            "error": "no #entryContent",
        }

    # POS — one <span class="pos"> per visible POS group
    pos_list = [el.get_text(strip=True)
                for el in entry.find_all("span", class_="pos")]

    # Headword list-membership flags (ox5000 / ox3000 / opal_*/academic on h1)
    h1 = entry.find("h1", class_="headword")
    list_flags: dict[str, bool] = {t: False for targets in
                                   LIST_ATTRS_HEAD.values() for t in targets}
    if h1:
        _collect_list_flags(h1, LIST_ATTRS_HEAD, list_flags)
        # also walk the parent container — some attributes live on the entry <div>
        parent = h1.find_parent("div", class_="entry") or h1.parent
        if parent is not None:
            _collect_list_flags(parent, LIST_ATTRS_HEAD, list_flags)

    # AWL: also cross-reference with local vocab_list (the `academic` attribute is
    # sometimes missing, but the word is still in our local AWL.json).
    if word.lower() in awl_words:
        list_flags["AWL"] = True

    # All sense elements (in document order across POS groups)
    senses = entry.find_all("li", class_="sense")

    cefr_levels: list[str] = []
    register_tags: list[str] = []
    subject_labels: list[str] = []
    definitions: list[dict] = []

    for global_idx, li in enumerate(senses, start=1):
        # Sense-level list flags
        _collect_list_flags(li, LIST_ATTRS_SENSE, list_flags)

        # CEFR — normalize to uppercase ("c1" → "C1") per the schema example.
        cefr = (li.get("cefr") or li.get("fkcefr") or "").upper() or None
        if cefr and cefr not in cefr_levels:
            cefr_levels.append(cefr)

        # Register tags — text in <span class="labels"> inside the sense
        for la in li.find_all("span", class_="labels"):
            text = la.get_text(" ", strip=True).strip("()")
            if text:
                for piece in re.split(r",\s*", text):
                    piece = piece.strip()
                    if piece and piece not in register_tags:
                        register_tags.append(piece)

        # Subject labels — <span class="topic"><span class="topic_name">Name</span>
        # Skip grammar "function" topics (href starts with l2:functions:) — those
        # are usage functions, not academic subject areas.
        for ta in li.find_all("span", class_="topic"):
            href = ta.get("href", "")
            if href.startswith("l2:functions:"):
                continue
            tn = ta.find(class_="topic_name")
            if tn:
                t = tn.get_text(strip=True)
                if t and t not in subject_labels:
                    subject_labels.append(t)

        # Definition text + examples
        def_span = li.find("span", class_="def")
        def_text = def_span.get_text(" ", strip=True) if def_span else ""
        examples: list[str] = []
        for ex in li.find_all("span", class_="x"):
            ex_text = ex.get_text(" ", strip=True)
            if ex_text:
                examples.append(ex_text)

        # Use a GLOBAL counter for `n`. Oxford's `sensenum=` attribute is a
        # per-section label (e.g. main adjective senses 1-7, verb sub-section
        # senses 1-7 again). If we used sensenum verbatim, words with multiple
        # POS groups (e.g. `sick`) would have duplicate n values. The global
        # counter guarantees unique, monotonically increasing n.
        n = global_idx

        # Preserve the local sensenum as supplementary metadata for the design
        # system; it may be useful but is not the canonical ordering.
        local_sensenum: int | None = None
        raw_local = li.get("sensenum")
        if raw_local is not None:
            try:
                local_sensenum = int(raw_local)
            except ValueError:
                local_sensenum = None

        entry_def = {
            "n": n,
            "text": def_text,
            "examples": examples,
        }
        if local_sensenum is not None:
            entry_def["sensenum_local"] = local_sensenum
        definitions.append(entry_def)

    # Headword CEFR — take the lowest level across senses (a1 < a2 < b1 < b2 < c1 < c2)
    cefr_order = {"A1": 1, "A2": 2, "B1": 3, "B2": 4, "C1": 5, "C2": 6}
    head_cefr = None
    if cefr_levels:
        head_cefr = min(cefr_levels, key=lambda c: cefr_order.get(c, 99))

    # Oxford lists (preserve discovery order: 3000 before 5000)
    oxford_lists: list[str] = []
    for name in ("Oxford 3000", "Oxford 5000"):
        if list_flags.get(name) and name not in oxford_lists:
            oxford_lists.append(name)
    # Fallback: if no ox* attribute is present anywhere, infer from CEFR
    # (per labels description: "shows a word from the Oxford 5000 with its CEFR
    # level" — C1/C2 → Oxford 5000, A1-B2 → Oxford 3000).
    if not oxford_lists and head_cefr:
        rank = cefr_order.get(head_cefr, 99)
        if rank <= 4:
            oxford_lists.append("Oxford 3000")
        if rank >= 5:
            oxford_lists.append("Oxford 5000")

    # OPAL — read flags set on h1 or any sense. If both written and spoken,
    # combine. (We only set if Oxford actually flags it — null otherwise.)
    opal: str | None = None
    opal_parts: list[str] = []
    if list_flags.get("OPAL written"):
        opal_parts.append("OPAL written")
    if list_flags.get("OPAL spoken"):
        opal_parts.append("OPAL spoken")
    if opal_parts:
        opal = " + ".join(opal_parts)

    # AWL
    awl_value = "AWL" if list_flags.get("AWL") else None

    return {
        "word": word,
        "source_url": source_url,
        "cefr": head_cefr,
        "pos": pos_list,
        "register_tags": register_tags,
        "subject_labels": subject_labels,
        "oxford_lists": oxford_lists,
        "opal": opal,
        "awl": awl_value,
        "definitions": definitions,
        "word_family": WORD_FAMILIES.get(word, []),
    }


# --------------------------------------------------------------------------- #
# AWL cross-reference
# --------------------------------------------------------------------------- #
def load_awl_words() -> set[str]:
    awl_path = VOCAB_DIR / "AWL" / "AWL.json"
    if not awl_path.exists():
        print(f"WARN: AWL.json not found at {awl_path}", file=sys.stderr)
        return set()
    data = json.loads(awl_path.read_text(encoding="utf-8"))
    words: set[str] = set()
    if isinstance(data, dict):
        for subl, sub in data.items():
            if isinstance(sub, dict):
                words.update(w.lower() for w in sub.keys())
            elif isinstance(sub, list):
                words.update(w.lower() for w in sub)
    return words


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Fetch all 6 URLs
    print("=== Fetching URLs ===")
    pages: dict[str, str] = {}
    pages["labels"] = (LABELS_URL, fetch(LABELS_URL, CACHE_DIR / "oxford_labels.html"))
    for word, url in WORD_URLS.items():
        pages[word] = (url, fetch(url, CACHE_DIR / f"oxford_{word}.html"))

    # 2. Parse labels
    print("=== Parsing labels ===")
    labels_url, labels_html = pages["labels"]
    labels_data = parse_labels(labels_html, labels_url)
    out_labels = DATA_DIR / "oxford_labels.json"
    out_labels.write_text(
        json.dumps(labels_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  → {out_labels}")
    print(f"  symbols: {len(labels_data['symbols'])}")
    print(f"  register_labels: {len(labels_data['register_labels'])}")
    print(f"  usage_restrictions: {len(labels_data['usage_restrictions'])}")
    print(f"  subject_labels: {len(labels_data['subject_labels'])}")

    # 3. Parse word pages
    print("=== Parsing word pages ===")
    awl_words = load_awl_words()
    print(f"  AWL vocab: {len(awl_words)} words")
    samples: list[dict] = []
    for word, (url, html) in pages.items():
        if word == "labels":
            continue
        sample = parse_word_page(html, word, url, awl_words)
        samples.append(sample)
        print(f"  {word}: cefr={sample['cefr']} pos={sample['pos']} "
              f"senses={len(sample['definitions'])} lists={sample['oxford_lists']} "
              f"awl={sample['awl']}")

    samples_data = {
        "fetched_at": now_iso(),
        "samples": samples,
    }
    out_samples = DATA_DIR / "oxford_samples.json"
    out_samples.write_text(
        json.dumps(samples_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  → {out_samples}")

    # 4. Summary
    print()
    print("=== Summary ===")
    print(f"Labels parsed: {len(labels_data['symbols'])} symbols, "
          f"{len(labels_data['register_labels'])} register, "
          f"{len(labels_data['usage_restrictions'])} usage, "
          f"{len(labels_data['subject_labels'])} subjects")
    print(f"Samples parsed: {len(samples)} ({', '.join(s['word'] for s in samples)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
