"""Reorganize cache: rename {word}.html → {word}_({pos}).html, fetch additional POS pages.

For future reuse, every Oxford page is named with its POS suffix:
  - rock.html        → rock_(noun).html   (extracted from page)
  - rock_2.html      → rock_(verb).html   (newly fetched)
  - rock_3.html      → rock_(adj).html    (if exists)
"""
import asyncio
import aiohttp
import os
import re
import time
import shutil
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

CACHE = Path(r'C:\Users\admin\Downloads\ielts-deck\data\.cache_html')
OX_BASE = 'https://www.oxfordlearnersdictionaries.com'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
}
SEM = asyncio.Semaphore(4)
THROTTLE = 0.2

POS_SHORT = {
    'noun': 'noun', 'verb': 'verb', 'adjective': 'adj', 'adverb': 'adv',
    'preposition': 'prep', 'pronoun': 'pron', 'conjunction': 'conj',
    'determiner': 'det', 'modal verb': 'modal', 'auxiliary verb': 'aux',
    'exclamation': 'excl', 'number': 'num', 'prefix': 'prefix',
    'suffix': 'suffix', 'combining form': 'comb',
}


def detect_primary_pos(html: str) -> str:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'lxml')
    pos_el = soup.find('span', class_='pos')
    if pos_el:
        t = pos_el.get_text(strip=True).lower()
        return POS_SHORT.get(t, t.replace(' ', '_'))
    title = soup.find('title')
    if title:
        t = title.get_text().lower()
        for pos_name, short in POS_SHORT.items():
            if f' {pos_name} ' in t or f' {pos_name}-' in t or t.startswith(pos_name):
                return short
    return 'noun'


def find_additional_pos_links(html: str, word: str):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'lxml')
    found = []
    seen_suffixes = set()
    for a in soup.find_all('a', href=True):
        href = a.get('href', '')
        atxt = a.get_text(strip=True).lower()
        m = re.search(rf'/definition/english/{re.escape(word)}_(\d+)(?:#.*)?$', href)
        if m and atxt:
            if atxt.startswith(word.lower()):
                pos_part = atxt[len(word):]
                for pos_name, short in POS_SHORT.items():
                    if pos_part == pos_name or pos_part.startswith(pos_name):
                        if short not in seen_suffixes:
                            full_url = OX_BASE + href if not href.startswith('http') else href
                            found.append((short, full_url))
                            seen_suffixes.add(short)
                        break
    return found


def read_and_detect(name):
    """Worker: read file, return (name, html, primary_pos, additional_links)."""
    path = CACHE / name
    try:
        text = path.read_text(encoding='utf-8', errors='replace')
    except Exception:
        return (name, None, None, [])
    if 'oxfordlearnersdictionaries' not in text.lower():
        return (name, None, None, [])
    word = name[:-5]  # strip .html
    pos = detect_primary_pos(text)
    addl = find_additional_pos_links(text, word)
    return (name, text, pos, addl)


async def fetch_page(session, url, save_path: Path):
    async with SEM:
        try:
            async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=30), ssl=False) as resp:
                if resp.status == 200:
                    text = await resp.text(errors='replace')
                    save_path.write_text(text, encoding='utf-8')
                    await asyncio.sleep(THROTTLE)
                    return True
                return False
        except Exception:
            return False


async def main():
    t0 = time.time()
    print('Step 1: Read + detect primary POS (parallel)...', flush=True)
    files = [f for f in os.listdir(CACHE) if f.endswith('.html') and '(' not in f]
    with ThreadPoolExecutor(max_workers=16) as ex:
        results = list(ex.map(read_and_detect, files))
    print(f'  Read {len(results)} files in {time.time()-t0:.1f}s', flush=True)

    # Step 1b: Rename (no I/O contention with reads)
    print('Step 1b: Rename files...', flush=True)
    rename_count = 0
    word_pos = {}
    for name, text, pos, _ in results:
        if text is None: continue
        word = name[:-5]
        new_name = f'{word}_({pos}).html'
        word_pos[word] = pos
        if name != new_name:
            new_path = CACHE / new_name
            if not new_path.exists():
                try:
                    (CACHE / name).rename(new_path)
                    rename_count += 1
                except Exception:
                    pass
    print(f'  Renamed {rename_count}', flush=True)

    # Step 2: Multi-POS detection (need to re-list since names changed)
    print('\nStep 2: Detect multi-POS + fetch additional pages...', flush=True)
    final_files = [f for f in os.listdir(CACHE) if f.endswith('.html') and '(' in f]

    # Build multi-POS words map
    multi_pos_addl = defaultdict(list)  # word -> list of (suffix, url) to fetch
    for name, _, _, addl in results:
        if not addl: continue
        word = name[:-5]
        for suffix, url in addl:
            target = CACHE / f'{word}_({suffix}).html'
            if not target.exists():
                multi_pos_addl[word].append((suffix, url))

    # Dedupe
    fetch_jobs = []
    for word, lst in multi_pos_addl.items():
        for suffix, url in lst:
            target = CACHE / f'{word}_({suffix}).html'
            if not target.exists():
                fetch_jobs.append((word, suffix, url, target))
    print(f'  Additional pages to fetch: {len(fetch_jobs)}', flush=True)

    if fetch_jobs:
        connector = aiohttp.TCPConnector(limit_per_host=4, ttl_dns_cache=300, ssl=False)
        timeout = aiohttp.ClientTimeout(total=60)
        started = time.time()
        ok = 0
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            tasks = [fetch_page(session, url, target) for _, _, url, target in fetch_jobs]
            for i, coro in enumerate(asyncio.as_completed(tasks), 1):
                result = await coro
                if result: ok += 1
                if i % 20 == 0 or i == len(tasks):
                    print(f'    [{i}/{len(tasks)}] ok={ok} elapsed={time.time()-started:.0f}s', flush=True)
        print(f'  Fetched {ok}/{len(fetch_jobs)}', flush=True)

    # Step 3: Final summary
    print('\nStep 3: Summary', flush=True)
    final_files = [f for f in os.listdir(CACHE) if f.endswith('.html') and '(' in f]
    by_word = defaultdict(set)
    for f in final_files:
        m = re.match(r'^(.+?)_\((\w+)\)\.html$', f)
        if m: by_word[m.group(1)].add(m.group(2))
    multi = {w: sorted(p) for w, p in by_word.items() if len(p) > 1}
    print(f'  Total renamed Oxford pages: {len(final_files)}', flush=True)
    print(f'  Multi-POS words: {len(multi)}', flush=True)
    print(f'\n  Sample multi-POS:')
    for w, lst in sorted(multi.items())[:20]:
        print(f'    {w:20} POS: {lst}')

    # Cleanup: any remaining {word}.html without suffix?
    leftover = [f for f in os.listdir(CACHE) if f.endswith('.html') and '(' not in f]
    if leftover:
        print(f'\n  Leftover files (Oxford, no suffix): {len(leftover)}')
        for f in leftover[:5]:
            print(f'    {f}')

    print(f'\nTotal time: {time.time()-t0:.1f}s', flush=True)


asyncio.run(main())
