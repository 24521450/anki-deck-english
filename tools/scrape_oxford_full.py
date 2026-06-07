"""Incremental Oxford scraper for ielts-deck.

Reads vocab_list/ (Oxford 3000 + 5000 + AWL), compares against data/.cache_html/,
scrapes only the missing words from Oxford, parses, and appends to a JSONL file.

Uses async + aiohttp with 4 concurrent requests (well under Oxford's rate limit).
1 req/sec throttle via semaphore to be polite.

Output: data/oxford_full.jsonl (one record per word)
"""
from __future__ import annotations
import asyncio
import aiohttp
import json
import re
import time
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

PR = Path(r"C:\Users\admin\Downloads\ielts-deck")
VOCAB = PR / "vocab_list"
CACHE = PR / "data" / ".cache_html"
OUT = PR / "data" / "oxford_full.jsonl"

OXFORD_URL = "https://www.oxfordlearnersdictionaries.com/definition/english/{word}"
HEADERS = {"User-Agent": "Mozilla/5.0 (ielts-deck scraper; +https://github.com/user/ielts-deck)"}
SEM = asyncio.Semaphore(4)
THROTTLE = 0.25  # 4 concurrent = ~4 req/sec at full speed; throttle 0.25s between starts

def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_html(text: str, word: str) -> dict:
    """Parse Oxford word page HTML → structured record.

    Adapted from tools/scrape_oxford.py:parse_word_page() — kept minimal.
    """
    from bs4 import BeautifulSoup, NavigableString
    soup = BeautifulSoup(text, "lxml")
    entry = soup.find(id="entryContent")
    if not entry:
        return {"word": word, "error": "no #entryContent", "fetched_at": now_iso()}

    pos_list = [el.get_text(strip=True) for el in entry.find_all("span", class_="pos")]

    # List-membership flags from h1 (Oxford 3000/5000/OPAL/AWL)
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

    senses = entry.find_all("li", class_="sense")
    cefr_levels: list[str] = []
    register_tags: list[str] = []
    subject_labels: list[str] = []
    definitions: list[dict] = []

    for n, li in enumerate(senses, start=1):
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
            if (ta.get("href", "") or "").startswith("l2:functions:"):
                continue
            tn = ta.find(class_="topic_name")
            if tn:
                t = tn.get_text(strip=True)
                if t and t not in subject_labels:
                    subject_labels.append(t)
        def_span = li.find("span", class_="def")
        def_text = def_span.get_text(" ", strip=True) if def_span else ""
        examples = [ex.get_text(" ", strip=True) for ex in li.find_all("span", class_="x") if ex.get_text(strip=True)]
        definitions.append({"n": n, "text": def_text, "examples": examples})

    cefr_order = {"A1": 1, "A2": 2, "B1": 3, "B2": 4, "C1": 5, "C2": 6}
    head_cefr = min(cefr_levels, key=lambda c: cefr_order.get(c, 99)) if cefr_levels else None

    return {
        "word": word,
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


async def fetch_word(session: aiohttp.ClientSession, word: str, out_fh) -> dict | None:
    cache_path = CACHE / f"{word}.html"
    if cache_path.exists():
        text = cache_path.read_text(encoding="utf-8", errors="replace")
    else:
        async with SEM:
            url = OXFORD_URL.format(word=word)
            try:
                async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        return {"word": word, "error": f"HTTP {resp.status}", "fetched_at": now_iso()}
                    text = await resp.text()
                    CACHE.mkdir(parents=True, exist_ok=True)
                    cache_path.write_text(text, encoding="utf-8")
                    await asyncio.sleep(THROTTLE)
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                return {"word": word, "error": str(e), "fetched_at": now_iso()}
    try:
        rec = parse_html(text, word)
    except Exception as e:
        return {"word": word, "error": f"parse: {e}", "fetched_at": now_iso()}
    out_fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    out_fh.flush()
    return rec


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


def load_cached() -> set[str]:
    return {p.stem for p in CACHE.glob("*.html")}


async def main(test_only: list[str] | None = None, max_n: int | None = None):
    vocab = sorted(load_vocab())
    cached = load_cached()
    missing = [w for w in vocab if w not in cached]
    print(f"Vocab: {len(vocab)} words; Cached: {len(cached)}; Missing: {len(missing)}")

    if test_only:
        missing = [w for w in missing if w in test_only]
        print(f"Test mode: only scraping {len(missing)} specified words")
    if max_n:
        missing = missing[:max_n]
        print(f"Limiting to first {max_n} words")

    if not missing:
        print("Nothing to do.")
        return

    print(f"Will write to {OUT} (one JSONL record per word)")
    OUT.parent.mkdir(parents=True, exist_ok=True)

    connector = aiohttp.TCPConnector(limit_per_host=4, ttl_dns_cache=300)
    timeout = aiohttp.ClientTimeout(total=60)
    written = 0
    errors = 0
    started = time.time()
    with OUT.open("a", encoding="utf-8") as fh:
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            tasks = [fetch_word(session, w, fh) for w in missing]
            for i, coro in enumerate(asyncio.as_completed(tasks), 1):
                rec = await coro
                if rec and "error" in rec:
                    errors += 1
                else:
                    written += 1
                if i % 50 == 0 or i == len(tasks):
                    elapsed = time.time() - started
                    rate = i / elapsed if elapsed > 0 else 0
                    eta = (len(tasks) - i) / rate if rate > 0 else 0
                    print(f"  [{i}/{len(tasks)}] written={written} errors={errors} rate={rate:.1f}/s eta={eta:.0f}s", flush=True)

    print(f"\nDone. Wrote {written} records, {errors} errors. Total time: {time.time()-started:.0f}s")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # Quick test with 5 words
        asyncio.run(main(test_only=["abandon", "ability", "able", "about", "above"]))
    else:
        asyncio.run(main())
