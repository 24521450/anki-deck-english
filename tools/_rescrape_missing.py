"""Re-scrape 319 missing words + 3 scrape failures from Oxford.

Targets: words in study_split.tsv NOT in oxford_full.jsonl, PLUS 3 words in JSONL
with empty definitions (deprive, derive, devote).

Strategy: Oxford primary. For each word, check cache first, else fetch.
If Oxford returns <entryContent> or no senses -> mark as Oxford-failed for
Cambridge fallback.

Output: data/_rescrape_results.jsonl (one record per word, including errors).
Does NOT modify oxford_full.jsonl directly. Use _merge_rescraped.py after.

Multi-POS detection (per AGENTS.md):
  - After fetching main page, look for <a>{word}{pos}</a> link text (e.g. "rockverb").
  - If found, fetch the additional POS page too.
  - Save all as oxford_{word}_(pos).html in .cache_html/
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
JSONL = PR / "data" / "oxford_full.jsonl"
STUDY = PR / "data" / "study_split.tsv"
RESULTS = PR / "data" / "_rescrape_results.jsonl"

OXFORD_URL = "https://www.oxfordlearnersdictionaries.com/definition/english/{word}"
HEADERS = {"User-Agent": "Mozilla/5.0 (ielts-deck scraper; +https://github.com/user/ielts-deck)"}
SEM = asyncio.Semaphore(4)
THROTTLE = 0.25  # seconds between fetches

POS_SHORT = {
    "noun": "noun", "verb": "verb", "adjective": "adj", "adverb": "adv",
    "preposition": "prep", "pronoun": "pron", "conjunction": "conj",
    "determiner": "det", "modal verb": "modal", "auxiliary verb": "aux",
    "exclamation": "excl", "number": "num", "prefix": "prefix",
    "suffix": "suffix", "combining form": "comb",
}

POS_RE = re.compile(r"<span class=\"pos\"[^>]*>([^<]+)</span>")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def pos_short(pos: str) -> str:
    """Map full POS name to short code."""
    pos_lower = pos.strip().lower()
    return POS_SHORT.get(pos_lower, pos_lower[:8])


def cache_path_for(word: str, pos_short_code: str | None = None) -> Path:
    """Build cache path per AGENTS.md naming: oxford_{word}_(pos).html or oxford_{word}.html"""
    safe_word = word.replace("/", "_").replace(" ", "-")
    if pos_short_code:
        return CACHE / f"oxford_{safe_word}_({pos_short_code}).html"
    return CACHE / f"oxford_{safe_word}.html"


def _discover_additional_pos_pages(soup, word: str) -> list[dict]:
    """Find links to other POS pages (e.g. /english/rock_2 from /english/rock).

    Oxford sometimes puts the same word on multiple POS pages with
    /definition/english/{word}_{n} URLs. Returns [{pos, n, url}, ...].
    """
    additional_pos: list[dict] = []
    href_re = re.compile(r"/definition/english/" + re.escape(word) + r"_(\d+)")
    for a in soup.find_all("a", href=href_re):
        href = a.get("href", "")
        link_text = a.get_text(strip=True).lower()
        m = href_re.search(href)
        if not m or not link_text:
            continue
        # Extract POS from link text (e.g. "rockverb" -> "verb")
        for full_pos, short in POS_SHORT.items():
            if link_text.endswith(full_pos) and link_text != word:
                additional_pos.append({"pos": full_pos, "n": m.group(1), "url": href})
                break
    return additional_pos


def parse_html(text: str, word: str, source_url: str) -> dict:
    """Parse Oxford word page HTML → structured record (Oxford-only fields).

    Thin wrapper around the canonical parser in src.scraper.oxford (D
    in architecture review). Adds 3 fields the canonical doesn't track:
      - n_senses, n_idioms: counts for diagnostics
      - additional_pos_pages: list of URLs to fetch for multi-POS words

    All other fields (cefr, pos, register_tags, subject_labels, definitions
    with def_cefr, etc.) come from the canonical parser, so this stays
    in sync with the v2 logic automatically.
    """
    from src.scraper.oxford import parse_oxford_html as _parse
    rec = _parse(text, word)
    # The canonical sets source_url from OXFORD_URL. Override with caller's
    # URL (which may be a multi-POS page like /english/rock_2).
    if not rec.get("error"):
        rec["source_url"] = source_url
        # Re-parse the soup to discover additional POS pages — canonical
        # doesn't do this. The rec returned by canonical doesn't carry
        # the soup, so we re-parse.
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(text, "lxml")
        rec["additional_pos_pages"] = _discover_additional_pos_pages(soup, word)
        rec["n_senses"] = sum(1 for d in rec["definitions"] if not d["is_idiom"])
        rec["n_idioms"] = sum(1 for d in rec["definitions"] if d["is_idiom"])
    else:
        rec["source"] = "oxford"  # canonical leaves source out on error
        rec["source_url"] = source_url
        rec["fetched_at"] = now_iso()
        rec["additional_pos_pages"] = []
        rec["n_senses"] = 0
        rec["n_idioms"] = 0
    return rec


async def fetch_word_with_cache(session: aiohttp.ClientSession, word: str) -> tuple[dict, list[dict]]:
    """Fetch a word from Oxford, return (main_record, additional_pos_records).

    additional_pos_records: list of records from _2/_3 POS pages (or empty).
    """
    url = OXFORD_URL.format(word=word)
    cache_main = cache_path_for(word, None)

    if cache_main.exists():
        text = cache_main.read_text(encoding="utf-8", errors="replace")
    else:
        async with SEM:
            try:
                async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        return ({"word": word, "source": "oxford", "error": f"HTTP {resp.status}",
                                 "fetched_at": now_iso()}, [])
                    text = await resp.text()
                    CACHE.mkdir(parents=True, exist_ok=True)
                    cache_main.write_text(text, encoding="utf-8", errors="replace")
                    await asyncio.sleep(THROTTLE)
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                return ({"word": word, "source": "oxford", "error": str(e), "fetched_at": now_iso()}, [])

    try:
        main_rec = parse_html(text, word, url)
    except Exception as e:
        return ({"word": word, "source": "oxford", "error": f"parse: {e}", "fetched_at": now_iso()}, [])

    # If no defs but there are additional POS pages, try them
    additional_records = []
    if not main_rec.get("definitions"):
        for pos_info in main_rec.get("additional_pos_pages", []):
            n = pos_info["n"]
            pos_code = pos_short(pos_info["pos"])
            url_n = f"https://www.oxfordlearnersdictionaries.com/definition/english/{word}_{n}"
            cache_n = cache_path_for(word, pos_code)
            if cache_n.exists():
                text_n = cache_n.read_text(encoding="utf-8", errors="replace")
            else:
                async with SEM:
                    try:
                        async with session.get(url_n, headers=HEADERS,
                                                timeout=aiohttp.ClientTimeout(total=30)) as resp:
                            if resp.status != 200:
                                continue
                            text_n = await resp.text()
                            CACHE.mkdir(parents=True, exist_ok=True)
                            cache_n.write_text(text_n, encoding="utf-8", errors="replace")
                            await asyncio.sleep(THROTTLE)
                    except (aiohttp.ClientError, asyncio.TimeoutError):
                        continue
            try:
                rec_n = parse_html(text_n, word, url_n)
                if rec_n.get("definitions"):
                    # Attach POS code
                    rec_n["_rescraped_pos_page"] = pos_code
                    additional_records.append(rec_n)
            except Exception:
                pass

    return (main_rec, additional_records)


async def main():
    # 1. Build target word list
    #    a. Words in study_split.tsv NOT in oxford_full.jsonl
    #    b. 3 scrape failures: deprive, derive, devote
    print("Loading existing data...")
    existing_words: dict[str, dict] = {}
    with JSONL.open("r", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            existing_words[r["word"]] = r
    print(f"  oxford_full.jsonl: {len(existing_words)} records")

    study_words: set[str] = set()
    with STUDY.open("r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("#"):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 4:
                study_words.add(parts[3])
    print(f"  study_split.tsv: {len(study_words)} unique words")

    missing = sorted(study_words - set(existing_words.keys()))
    print(f"  Missing from JSONL: {len(missing)}")

    # Scrape failures: in JSONL but no defs
    failures = sorted(w for w in study_words
                       if w in existing_words and not existing_words[w].get("definitions"))
    print(f"  Scrape failures (in JSONL, no defs): {len(failures)} -> {failures}")

    targets = missing + failures
    print(f"\n  Total targets: {len(targets)}")

    if not targets:
        print("Nothing to do.")
        return

    # 2. Fetch
    print(f"\nFetching {len(targets)} words from Oxford...")
    connector = aiohttp.TCPConnector(limit_per_host=4, ttl_dns_cache=300)
    timeout = aiohttp.ClientTimeout(total=60)
    results_main: list[dict] = []
    results_additional: list[dict] = []
    started = time.time()
    written = 0
    errors = 0
    oxford_ok = 0
    oxford_failed = 0

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = [fetch_word_with_cache(session, w) for w in targets]
        for i, coro in enumerate(asyncio.as_completed(tasks), 1):
            main_rec, add_recs = await coro
            results_main.append(main_rec)
            results_additional.extend(add_recs)
            if "error" in main_rec or not main_rec.get("definitions"):
                errors += 1
                if not main_rec.get("definitions") and not add_recs:
                    oxford_failed += 1
            else:
                written += 1
                oxford_ok += 1
            if i % 25 == 0 or i == len(tasks):
                elapsed = time.time() - started
                rate = i / elapsed if elapsed > 0 else 0
                eta = (len(tasks) - i) / rate if rate > 0 else 0
                print(f"  [{i}/{len(tasks)}] ok={oxford_ok} failed={oxford_failed} "
                      f"add_pos={len(results_additional)} rate={rate:.1f}/s eta={eta:.0f}s", flush=True)

    print(f"\nDone. Oxford: {oxford_ok} ok, {oxford_failed} failed (need Cambridge fallback).")
    print(f"Additional POS pages found: {len(results_additional)}")
    print(f"Total time: {time.time()-started:.0f}s")

    # 3. Write results
    print(f"\nWriting {RESULTS}...")
    with RESULTS.open("w", encoding="utf-8") as f:
        for r in results_main:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        for r in results_additional:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"  Wrote {len(results_main) + len(results_additional)} records to {RESULTS}")

    # 4. Print Oxford-failed words (for Cambridge fallback)
    failed_words = [r["word"] for r in results_main
                    if (r.get("error") or not r.get("definitions"))]
    print(f"\n=== Oxford-failed words ({len(failed_words)}) — need Cambridge fallback ===")
    for w in failed_words[:20]:
        print(f"  {w}")
    if len(failed_words) > 20:
        print(f"  ... and {len(failed_words) - 20} more")

    failed_path = PR / "data" / "_rescrape_failed.txt"
    failed_path.write_text("\n".join(failed_words) + "\n", encoding="utf-8")
    print(f"  Saved failed list to {failed_path}")


if __name__ == "__main__":
    asyncio.run(main())
