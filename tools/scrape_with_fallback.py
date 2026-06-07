"""Scraper v2 for ielts-deck.

Re-scrapes Oxford 3000 + 5000 + AWL words with Cambridge as fallback for Oxford 404s.
Output: data/oxford_with_fallback.jsonl (one record per word, with 'source' field)

Differences from v1 (scrape_oxford_full.py):
- ssl=False on connector (Cambridge needs it; some Windows envs need it)
- Adds Cambridge fallback: if Oxford returns 404, try Cambridge dictionary
- Output records include 'source' field ('oxford' or 'cambridge')
- Skips words already in existing JSONL (idempotent incremental)
- Skips words already in cache (use cached HTML)
"""
from __future__ import annotations
import asyncio
import aiohttp
import json
import re
import time
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter

PR = Path(r"C:\Users\admin\Downloads\ielts-deck")
VOCAB = PR / "vocab_list"
CACHE = PR / "data" / ".cache_html"
OUT = PR / "data" / "oxford_with_fallback.jsonl"
EXISTING = PR / "data" / "oxford_full.jsonl"

OXFORD_URL = "https://www.oxfordlearnersdictionaries.com/definition/english/{word}"
CAMBRIDGE_URL = "https://dictionary.cambridge.org/dictionary/english/{word}"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}
SEM = asyncio.Semaphore(4)
THROTTLE = 0.25


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# ── Oxford parser (adapted from v1) ─────────────────────────────────────
def parse_oxford_html(text: str, word: str) -> dict:
    """Parse Oxford word page HTML → structured record."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(text, "lxml")
    entry = soup.find(id="entryContent")
    if not entry:
        return {"word": word, "error": "no #entryContent"}

    pos_list = [el.get_text(strip=True) for el in entry.find_all("span", class_="pos")]

    h1 = entry.find("h1", class_="headword")
    list_flags = {}
    if h1:
        for attr, targets in {
            "ox3000": ("Oxford 3000",), "ox5000": ("Oxford 5000",),
            "opal_written": ("OPAL written",), "opal_spoken": ("OPAL spoken",),
            "academic": ("AWL",), "awl": ("AWL",),
        }.items():
            if h1.get(attr) == "y":
                for t in targets:
                    list_flags[t] = True

    # Note: per-section sense numbering — use global counter, not raw sensenum
    sense_lis = entry.find_all("li", class_="sense")
    cefr_levels: list[str] = []
    register_tags: list[str] = []
    subject_labels: list[str] = []
    definitions: list[dict] = []

    for n, li in enumerate(sense_lis, start=1):
        # Detect idiom: walk up to see if any ancestor is <div class="idioms">
        is_idiom = False
        idm_phrase = None
        cur = li
        for _ in range(8):
            cur = cur.parent
            if not cur:
                break
            if cur.name == "div" and "idioms" in (cur.get("class") or []):
                is_idiom = True
                # Extract the italicized phrase: <span class="idm">text</span>
                # It's a sibling/ancestor of the sense within idm-g
                idm_span = li.find_parent("span", class_="idm-g")
                if idm_span:
                    ph = idm_span.find("span", class_="idm")
                    if ph:
                        idm_phrase = ph.get_text(" ", strip=True)
                break

        for attr in ("cefr", "fkcefr"):
            v = (li.get(attr) or "").upper()
            if v and v not in cefr_levels:
                cefr_levels.append(v)
        for la in li.find_all("span", class_="labels"):
            text_l = la.get_text(" ", strip=True).strip("()")
            for piece in re.split(r",\s*", text_l):
                piece = piece.strip()
                if piece and piece not in register_tags:
                    register_tags.append(piece)
        for ta in li.find_all("span", class_="topic"):
            href = (ta.get("href", "") or "")
            if href.startswith("l2:functions:"):
                continue
            tn = ta.find(class_="topic_name")
            if tn:
                t = tn.get_text(strip=True)
                if t and t not in subject_labels:
                    subject_labels.append(t)
        def_span = li.find("span", class_="def")
        def_text = def_span.get_text(" ", strip=True) if def_span else ""
        examples = [ex.get_text(" ", strip=True) for ex in li.find_all("span", class_="x") if ex.get_text(strip=True)]
        sensenum_local = li.get("sensenum")
        definitions.append({
            "n": n,
            "sensenum_local": sensenum_local,
            "is_idiom": is_idiom,
            "idm_phrase": idm_phrase,  # NEW: the actual idiom phrase like "at sb's discretion"
            "text": def_text,
            "examples": examples,
        })

    cefr_order = {"A1": 1, "A2": 2, "B1": 3, "B2": 4, "C1": 5, "C2": 6}
    head_cefr = min(cefr_levels, key=lambda c: cefr_order.get(c, 99)) if cefr_levels else None

    return {
        "word": word,
        "source": "oxford",
        "source_url": OXFORD_URL.format(word=word),
        "fetched_at": now_iso(),
        "cefr": head_cefr,
        "pos": pos_list,
        "register_tags": register_tags,
        "subject_labels": subject_labels,
        "oxford_lists": [name for name in ("Oxford 3000", "Oxford 5000") if list_flags.get(name)],
        "opal": "OPAL written" if list_flags.get("OPAL written") else ("OPAL spoken" if list_flags.get("OPAL spoken") else None),
        "awl": "AWL" if list_flags.get("AWL") else None,
        "definitions": definitions,
    }


# ── Cambridge parser ────────────────────────────────────────────────────
def parse_cambridge_html(text: str, word: str) -> dict:
    """Parse Cambridge dictionary page HTML → structured record.

    Cambridge HTML structure (verified on discretion):
    - POS:    <span class="pos dpos">noun</span>
    - Def:    <div class="def ddef_d">...</div>
    - Ex:     <div class="examp dexamp"><span class="eg deg">...</span></div>
    - CEFR:   <span class="epp-xref">A2</span>
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(text, "lxml")

    # POS — only top-level pos, not the navigation/sidebar ones
    pos_list = []
    for el in soup.find_all("span", class_=re.compile(r"\bpos\b")):
        t = el.get_text(strip=True)
        if t and t not in pos_list and t.lower() in {
            "noun", "verb", "adjective", "adverb", "preposition", "conjunction",
            "pronoun", "determiner", "exclamation", "number", "modal verb",
            "auxiliary verb", "idiom", "phrasal verb", "prefix", "suffix",
        }:
            pos_list.append(t)

    # CEFR — epp-xref spans
    cefr_levels = []
    for el in soup.find_all("span", class_=re.compile(r"\bepp-xref\b")):
        t = el.get_text(strip=True).upper()
        if re.match(r"^[A-C][12]$", t) and t not in cefr_levels:
            cefr_levels.append(t)

    # Definitions + examples per entry block (.entry-block__el or .pr dictionary-entry)
    # Cambridge groups senses in <div class="pr entry-body__el">. Inside: .ddef_block
    definitions = []
    n = 0
    for ddef_block in soup.find_all("div", class_=re.compile(r"\bddef_block\b")):
        n += 1
        def_div = ddef_block.find("div", class_=re.compile(r"\bddef_d\b"))
        def_text = re.sub(r"\s+", " ", def_div.get_text(" ", strip=True)).strip() if def_div else ""
        examples = []
        for ex in ddef_block.find_all("span", class_=re.compile(r"\bdeg\b")):
            t = re.sub(r"\s+", " ", ex.get_text(" ", strip=True)).strip()
            if t and t not in examples:
                examples.append(t)
        definitions.append({"n": n, "text": def_text, "examples": examples})

    cefr_order = {"A1": 1, "A2": 2, "B1": 3, "B2": 4, "C1": 5, "C2": 6}
    head_cefr = min(cefr_levels, key=lambda c: cefr_order.get(c, 99)) if cefr_levels else None

    return {
        "word": word,
        "source": "cambridge",
        "source_url": CAMBRIDGE_URL.format(word=word),
        "fetched_at": now_iso(),
        "cefr": head_cefr,
        "pos": pos_list,
        "register_tags": [],  # Cambridge doesn't have structured register labels
        "subject_labels": [],  # Cambridge doesn't have subject labels
        "oxford_lists": [],
        "opal": None,
        "awl": None,
        "definitions": definitions,
    }


# ── Fetch logic ─────────────────────────────────────────────────────────
async def fetch_one(session: aiohttp.ClientSession, word: str, out_fh) -> dict | None:
    """Try Oxford first, then Cambridge. Write to JSONL on success."""
    rec = None

    # 1. Try Oxford
    ox_cache = CACHE / f"{word}.html"
    if ox_cache.exists():
        text = ox_cache.read_text(encoding="utf-8", errors="replace")
        # quick check it's actually Oxford, not a stray Cambridge page
        if "oxfordlearnersdictionaries" in text.lower():
            try:
                rec = parse_oxford_html(text, word)
                if "error" not in rec:
                    out_fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    out_fh.flush()
                    return rec
            except Exception as e:
                rec = {"word": word, "source": "oxford", "error": f"parse: {e}"}

    if rec is None or "error" in rec:
        # 2. Try Oxford network
        try:
            async with SEM:
                async with session.get(OXFORD_URL.format(word=word), headers=HEADERS, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 200:
                        text = await resp.text(errors="replace")
                        CACHE.mkdir(parents=True, exist_ok=True)
                        ox_cache.write_text(text, encoding="utf-8")
                        await asyncio.sleep(THROTTLE)
                        try:
                            rec = parse_oxford_html(text, word)
                            if "error" not in rec:
                                out_fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                                out_fh.flush()
                                return rec
                        except Exception as e:
                            rec = {"word": word, "source": "oxford", "error": f"parse: {e}"}
                    else:
                        rec = {"word": word, "source": "oxford", "error": f"HTTP {resp.status}"}
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            rec = {"word": word, "source": "oxford", "error": str(e)}

    # 3. Cambridge fallback
    try:
        async with SEM:
            async with session.get(CAMBRIDGE_URL.format(word=word), headers=HEADERS, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    text = await resp.text(errors="replace")
                    await asyncio.sleep(THROTTLE)
                    try:
                        rec = parse_cambridge_html(text, word)
                        if "error" not in rec and rec.get("definitions"):
                            out_fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                            out_fh.flush()
                            return rec
                        else:
                            return {"word": word, "source": "cambridge", "error": rec.get("error", "no definitions")}
                    except Exception as e:
                        return {"word": word, "source": "cambridge", "error": f"parse: {e}"}
                else:
                    return {"word": word, "source": "cambridge", "error": f"HTTP {resp.status}"}
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        return {"word": word, "source": "cambridge", "error": str(e)}


def load_vocab() -> set[str]:
    words: set[str] = set()
    for md in VOCAB.glob("**/*.md"):
        text = md.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"\|\s*\*\*([^*]+)\*\*\s*\|", text):
            w = m.group(1).strip().lower()
            first = w.split(",")[0].split(" ")[0].strip()
            if first and len(first) >= 2:
                words.add(first)
    for awl in VOCAB.glob("AWL/AWL.json"):
        data = json.loads(awl.read_text(encoding="utf-8", errors="replace"))
        for v in data.values():
            if isinstance(v, dict):
                for head in v:
                    first = head.strip().lower().split(",")[0].split(" ")[0].strip()
                    if first and len(first) >= 2:
                        words.add(first)
    return words


def load_existing_words() -> set[str]:
    """Words already in oxford_full.jsonl or in cached Oxford pages."""
    out = set()
    if EXISTING.exists():
        for line in open(EXISTING, encoding="utf-8"):
            try:
                rec = json.loads(line)
                if rec.get("word"):
                    out.add(rec["word"].lower())
            except Exception:
                pass
    return out


async def main(test_only: list[str] | None = None, max_n: int | None = None, overwrite: bool = False):
    vocab = sorted(load_vocab())
    print(f"Vocab: {len(vocab)} words", flush=True)

    if not overwrite:
        existing = load_existing_words()
        missing = [w for w in vocab if w not in existing]
        print(f"Already in JSONL: {len(existing)}; To scrape: {len(missing)}", flush=True)
    else:
        missing = vocab
        print(f"Overwrite mode: scraping all {len(missing)} words", flush=True)

    if test_only:
        missing = [w for w in missing if w in test_only]
        print(f"Test mode: {len(missing)} words", flush=True)
    if max_n:
        missing = missing[:max_n]
        print(f"Limiting to first {max_n}", flush=True)

    if not missing:
        print("Nothing to do.", flush=True)
        return

    print(f"Output: {OUT}", flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)

    # open in 'w' (truncate) — fresh run
    mode = "w" if overwrite else "a"
    connector = aiohttp.TCPConnector(limit_per_host=4, ttl_dns_cache=300, ssl=False)
    timeout = aiohttp.ClientTimeout(total=60)
    written = 0
    errors = 0
    source_dist = Counter()
    started = time.time()
    with OUT.open(mode, encoding="utf-8") as fh:
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            tasks = [fetch_one(session, w, fh) for w in missing]
            for i, coro in enumerate(asyncio.as_completed(tasks), 1):
                rec = await coro
                if rec:
                    if "error" in rec:
                        errors += 1
                    else:
                        written += 1
                        source_dist[rec.get("source", "?")] += 1
                if i % 50 == 0 or i == len(tasks):
                    elapsed = time.time() - started
                    rate = i / elapsed if elapsed > 0 else 0
                    eta = (len(tasks) - i) / rate if rate > 0 else 0
                    print(f"  [{i}/{len(tasks)}] written={written} err={errors} sources={dict(source_dist)} rate={rate:.1f}/s eta={eta:.0f}s", flush=True)

    print(f"\nDone. Wrote {written} records, {errors} errors. Sources: {dict(source_dist)}. Total: {time.time()-started:.0f}s", flush=True)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        asyncio.run(main(test_only=["discretion", "negotiate", "yield", "aggregate", "sick"]))
    elif len(sys.argv) > 1 and sys.argv[1] == "overwrite":
        asyncio.run(main(overwrite=True))
    else:
        asyncio.run(main())
