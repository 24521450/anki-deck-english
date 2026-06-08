"""Fetch Cambridge fallback for Oxford-failed words.

Reads: data/_rescrape_failed.txt (one word per line, may have "word (note)" format)
Writes: data/_rescraped_cambridge.jsonl (one record per word, source=cambridge)
"""
from __future__ import annotations
import asyncio
import aiohttp
import json
import re
import time
from pathlib import Path
from datetime import datetime, timezone
from bs4 import BeautifulSoup

PR = Path(r"C:\Users\admin\Downloads\ielts-deck")
INPUT = PR / "data" / "_cambridge_gap.txt"  # 173 words needing Cambridge CEFR
CACHE = PR / "data" / ".cache_html"
OUT = PR / "data" / "_cambridge_gap_results.jsonl"

CAMBRIDGE_URL = "https://dictionary.cambridge.org/dictionary/english/{word}"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}
SEM = asyncio.Semaphore(4)
THROTTLE = 0.3

CEFR_ORDER = {"A1": 1, "A2": 2, "B1": 3, "B2": 4, "C1": 5, "C2": 6}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def strip_paren(word: str) -> str:
    """Remove ' (note)' suffix from word."""
    return re.sub(r"\s*\(.*\)\s*$", "", word).strip()


def parse_cambridge(text: str, word: str) -> dict:
    """Parse Cambridge page -> structured record (Cambridge-style)."""
    soup = BeautifulSoup(text, "lxml")

    # Head CEFR (epp-xref spans)
    cefr_levels = []
    for el in soup.find_all("span", class_=re.compile(r"\bepp-xref\b")):
        t = el.get_text(strip=True).upper()
        if re.match(r"^[A-C][12]$", t) and t not in cefr_levels:
            cefr_levels.append(t)
    head_cefr = cefr_levels[0] if cefr_levels else None  # Cambridge's primary

    # POS list
    pos_list = []
    for el in soup.find_all("span", class_="pos"):
        t = el.get_text(strip=True)
        if t and t not in pos_list:
            pos_list.append(t)

    # Per-def CEFR (dentry blocks)
    definitions = []
    for n, block in enumerate(soup.find_all("div", class_=re.compile(r"\bentry-body__el\b")), 1):
        # Def text (cleaned: remove "Add to word list" noise)
        def_el = block.find("div", class_=re.compile(r"\bdef\b"))
        def_text = ""
        if def_el:
            # Remove "Add to word list" button if present
            for btn in def_el.find_all(string=re.compile(r"Add to word list", re.I)):
                btn.replace_with("")
            def_text = def_el.get_text(" ", strip=True)
            # Also strip CEFR tag prefix that Cambridge prepends (e.g. "B2 to prevent...")
            def_text = re.sub(r"^[A-C][12]\s+", "", def_text)

        # Per-def CEFR
        def_cefr = ""
        for el in block.find_all("span", class_=re.compile(r"\bepp-xref\b")):
            t = el.get_text(strip=True).upper()
            if re.match(r"^[A-C][12]$", t):
                def_cefr = t
                break

        # POS for this block
        pos_el = block.find("span", class_="pos")
        pos = pos_el.get_text(strip=True) if pos_el else ""

        # Examples
        examples = [ex.get_text(" ", strip=True) for ex in block.find_all("div", class_="examp")
                    if ex.get_text(strip=True)]

        if def_text or def_cefr or pos:
            definitions.append({
                "n": n,
                "text": def_text,
                "pos": pos,
                "def_cefr": def_cefr,
                "examples": examples,
            })

    return {
        "word": word,
        "source": "cambridge",
        "source_url": CAMBRIDGE_URL.format(word=word),
        "fetched_at": now_iso(),
        "cefr": head_cefr,
        "pos": pos_list,
        "cambridge_cefr": head_cefr,
        "cambridge_all_cefrs": cefr_levels,
        "definitions": definitions,
    }


async def fetch_one(session: aiohttp.ClientSession, raw_word: str) -> dict:
    word = strip_paren(raw_word)
    cache_path = CACHE / f"cambridge_{word}.html"
    if cache_path.exists():
        text = cache_path.read_text(encoding="utf-8", errors="replace")
    else:
        url = CAMBRIDGE_URL.format(word=word)
        async with SEM:
            try:
                async with session.get(url, headers=HEADERS,
                                       timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        return {"word": word, "source": "cambridge",
                                "raw_input": raw_word,
                                "error": f"HTTP {resp.status}", "fetched_at": now_iso()}
                    text = await resp.text()
                    CACHE.mkdir(parents=True, exist_ok=True)
                    cache_path.write_text(text, encoding="utf-8", errors="replace")
                    await asyncio.sleep(THROTTLE)
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                return {"word": word, "source": "cambridge",
                        "raw_input": raw_word,
                        "error": str(e), "fetched_at": now_iso()}
    try:
        rec = parse_cambridge(text, word)
        rec["raw_input"] = raw_word
        return rec
    except Exception as e:
        return {"word": word, "source": "cambridge",
                "raw_input": raw_word,
                "error": f"parse: {e}", "fetched_at": now_iso()}


async def main():
    raw_words = [w.strip() for w in INPUT.read_text(encoding="utf-8").splitlines() if w.strip()]
    print(f"Cambridge gap fill: {len(raw_words)} words")

    connector = aiohttp.TCPConnector(limit_per_host=4, ttl_dns_cache=300)
    timeout = aiohttp.ClientTimeout(total=60)
    started = time.time()
    written = 0
    errors = 0
    no_cefr = 0
    results = []

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = [fetch_one(session, w) for w in raw_words]
        for i, coro in enumerate(asyncio.as_completed(tasks), 1):
            rec = await coro
            results.append(rec)
            if rec.get("error"):
                errors += 1
            elif not rec.get("cambridge_cefr"):
                no_cefr += 1
            else:
                written += 1
            if i % 10 == 0 or i == len(tasks):
                elapsed = time.time() - started
                rate = i / elapsed if elapsed > 0 else 0
                eta = (len(tasks) - i) / rate if rate > 0 else 0
                print(f"  [{i}/{len(tasks)}] ok={written} no_cefr={no_cefr} err={errors} "
                      f"rate={rate:.1f}/s eta={eta:.0f}s", flush=True)

    print(f"\nCambridge: {written} ok, {no_cefr} no_cefr (UNCLASSIFIED), {errors} errors")
    print(f"Total time: {time.time()-started:.0f}s")

    # Write
    with OUT.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"Wrote {len(results)} records to {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
