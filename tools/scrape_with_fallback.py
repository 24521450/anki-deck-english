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

# Fetcher seam (B in architecture review, proof of concept). The script
# keeps its aiohttp event loop + parallel as_completed driver, but the
# actual HTTP/cache/throttle mechanics are delegated to the new module
# via asyncio.to_thread(). Migrating other 5 call sites deferred.
from src.scraper.fetch import oxford_cached, cambridge_cached
OXFORD_FETCHER = oxford_cached(cache_dir=CACHE, throttle=THROTTLE)
CAMBRIDGE_FETCHER = cambridge_cached(cache_dir=CACHE, throttle=THROTTLE)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# ── Oxford parser (thin shim around the canonical parser) ────────────────
def parse_oxford_html(text: str, word: str) -> dict:
    """Thin shim — canonical parser lives in src.scraper.oxford (D in
    architecture review). Kept here for backwards compat with callers
    that imported from this module.
    """
    from src.scraper.oxford import parse_oxford_html as _parse
    return _parse(text, word)


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
    """Try Oxford first, then Cambridge. Write to JSONL on success.

    Migrated to the Fetcher seam (B in architecture review, PoC):
    the actual HTTP/cache/throttle mechanics live in
    src.scraper.fetch. We keep the script's aiohttp event loop and
    parallel as_completed driver, delegating sync fetcher calls via
    asyncio.to_thread(). The function's external contract is unchanged.
    """
    rec = None

    # 1. Try Oxford (cache or network)
    ox_result = await asyncio.to_thread(OXFORD_FETCHER.fetch, word)
    if ox_result.ok and ox_result.text:
        # quick check it's actually Oxford, not a stray Cambridge page
        if "oxfordlearnersdictionaries" in ox_result.text.lower():
            try:
                rec = parse_oxford_html(ox_result.text, word)
                if "error" not in rec:
                    out_fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    out_fh.flush()
                    return rec
            except Exception as e:
                rec = {"word": word, "source": "oxford", "error": f"parse: {e}"}
        else:
            rec = {"word": word, "source": "oxford", "error": "cache contains non-Oxford content"}
    else:
        # error string from Fetcher (network/HTTP)
        rec = {"word": word, "source": "oxford", "error": ox_result.error or "unknown"}

    # 2. Cambridge fallback
    cam_result = await asyncio.to_thread(CAMBRIDGE_FETCHER.fetch, word)
    if not cam_result.ok or not cam_result.text:
        return {"word": word, "source": "cambridge",
                "error": cam_result.error or "unknown"}
    try:
        rec = parse_cambridge_html(cam_result.text, word)
        if "error" not in rec and rec.get("definitions"):
            out_fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out_fh.flush()
            return rec
        return {"word": word, "source": "cambridge",
                "error": rec.get("error", "no definitions")}
    except Exception as e:
        return {"word": word, "source": "cambridge", "error": f"parse: {e}"}


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
