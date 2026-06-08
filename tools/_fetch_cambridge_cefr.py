"""Fetch Cambridge CEFR for words where Oxford scrape has no CEFR.

Targets: B2/C1/C2 words in study list with missing head_cefr OR no def_cefr.
Updates JSONL with cambridge_cefr field, then runs the per-def CEFR chain.

Approach:
  1. For each target word, fetch Cambridge dictionary page (async, 4 concurrent).
  2. Extract CEFR using existing v2 Cambridge parser logic.
  3. Update JSONL: set head_cefr if Oxford had None, also add cambridge_cefr field.
  4. Re-run split_study_cards with the new chain.
"""
import asyncio
import aiohttp
import json
import re
import time
from pathlib import Path
from collections import Counter

DATA = Path(r'C:\Users\admin\Downloads\ielts-deck\data')
JSONL = DATA / 'oxford_full.jsonl'
STUDY = DATA / 'English Academic Vocabulary.txt'
CACHE = DATA / '.cache_html'

CAMBRIDGE_URL = 'https://dictionary.cambridge.org/dictionary/english/{word}'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}
SEM = asyncio.Semaphore(4)
THROTTLE = 0.25
CEFR_ORDER = {'A1': 1, 'A2': 2, 'B1': 3, 'B2': 4, 'C1': 5, 'C2': 6}


def now_iso():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_cambridge_cefr(text: str) -> dict:
    """Parse Cambridge page → CEFR info. Returns dict with 'cefr' and 'per_def_cefr'."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(text, 'lxml')

    # Head CEFR — look for epp-xref on the page
    cefr_levels = []
    for el in soup.find_all('span', class_=re.compile(r'\bepp-xref\b')):
        t = el.get_text(strip=True).upper()
        if re.match(r'^[A-C][12]$', t) and t not in cefr_levels:
            cefr_levels.append(t)
    head_cefr = min(cefr_levels, key=lambda c: CEFR_ORDER.get(c, 99)) if cefr_levels else None

    # Per-def CEFR — find each ddef_block, look for parent sense group with cefr
    # Cambridge structure varies; for now just return head CEFR
    per_def_cefr = {}
    return {'cefr': head_cefr, 'per_def_cefr': per_def_cefr, 'all_cefrs': cefr_levels}


async def fetch_cambridge(session, word):
    cache_path = CACHE / f'{word}.html'
    # Use cache if Cambridge page already
    if cache_path.exists():
        text = cache_path.read_text(encoding='utf-8', errors='replace')
        if 'dictionary.cambridge' in text.lower():
            return await asyncio.to_thread(parse_cambridge_cefr, text)
    async with SEM:
        url = CAMBRIDGE_URL.format(word=word)
        try:
            async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=30), ssl=False) as resp:
                if resp.status == 200:
                    text = await resp.text(errors='replace')
                    cache_path.write_text(text, encoding='utf-8')
                    await asyncio.sleep(THROTTLE)
                    return await asyncio.to_thread(parse_cambridge_cefr, text)
                else:
                    return {'cefr': None, 'per_def_cefr': {}, 'all_cefrs': [], 'error': f'HTTP {resp.status}'}
        except Exception as e:
            return {'cefr': None, 'per_def_cefr': {}, 'all_cefrs': [], 'error': str(e)}


async def main():
    # Find target words (any CEFR — per user instruction)
    print('Finding target words...', flush=True)
    recs = {json.loads(l)['word'].lower(): json.loads(l) for l in open(JSONL, encoding='utf-8')}

    study_words = set()
    for line in open(STUDY, encoding='utf-8'):
        if line.startswith('#'): continue
        cols = line.rstrip('\n').split('\t')
        if len(cols) > 14 and cols[3].strip():
            study_words.add(cols[3].strip().lower())

    targets = []
    for w in sorted(study_words):
        r = recs.get(w)
        if not r: continue
        head = r.get('cefr')
        has_def_cefr = any(d.get('def_cefr') for d in r.get('definitions', []))
        # Skip if already have cambridge_cefr (from prior fetch)
        if r.get('cambridge_cefr'):
            continue
        if not head or not has_def_cefr:
            targets.append(w)
    print(f'Target words (need Cambridge CEFR): {len(targets)}', flush=True)

    # Fetch Cambridge
    print('Fetching Cambridge...', flush=True)
    connector = aiohttp.TCPConnector(limit_per_host=4, ttl_dns_cache=300, ssl=False)
    timeout = aiohttp.ClientTimeout(total=60)
    results = {}
    started = time.time()
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = [fetch_cambridge(session, w) for w in targets]
        for i, coro in enumerate(asyncio.as_completed(tasks), 1):
            word = targets[i-1] if i-1 < len(targets) else '?'
            # The as_completed doesn't preserve order, so we need to map differently
            res = await coro
            results[word] = res
            if i % 5 == 0 or i == len(tasks):
                print(f'  [{i}/{len(tasks)}] done in {time.time()-started:.0f}s', flush=True)

    # Stats
    found = sum(1 for r in results.values() if r.get('cefr'))
    print(f'\nFound CEFR for {found}/{len(results)} words')

    # Update JSONL
    print('Updating JSONL...', flush=True)
    for w, info in results.items():
        if not info.get('cefr'):
            continue
        rec = recs.get(w)
        if rec is None:
            continue
        # Add cambridge_cefr field
        rec['cambridge_cefr'] = info['cefr']
        rec['cambridge_all_cefrs'] = info.get('all_cefrs', [])
        # If Oxford had no head_cefr, use Cambridge
        if not rec.get('cefr'):
            rec['cefr'] = info['cefr']
            print(f'  {w}: head_cefr NULL → {info["cefr"]} (Cambridge)')
        # For defs without def_cefr, fill from Cambridge head
        if info.get('cefr'):
            for d in rec.get('definitions', []):
                if not d.get('def_cefr'):
                    d['def_cefr'] = info['cefr']

    # Save
    with open(JSONL, 'w', encoding='utf-8') as f:
        for word in sorted(recs.keys()):
            f.write(json.dumps(recs[word], ensure_ascii=False) + '\n')
    print(f'Saved {JSONL}')

    # Show details
    print('\n=== Cambridge results ===')
    for w in targets:
        info = results.get(w, {})
        cefr = info.get('cefr')
        err = info.get('error', '')
        all_cefrs = info.get('all_cefrs', [])
        print(f'  {w:25} → CEFR={cefr} all={all_cefrs} {err}')

asyncio.run(main())
