"""Re-parse Oxford HTML in parallel to extract per-def fkcefr. Skip non-Oxford pages."""
import json
import re
import time
import os
from pathlib import Path
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

DATA = Path(r'C:\Users\admin\Downloads\ielts-deck\data')
CACHE = DATA / '.cache_html'
JSONL = DATA / 'oxford_full.jsonl'

# Load JSONL
recs = []
for line in open(JSONL, encoding='utf-8'):
    recs.append(json.loads(line))
print(f'Loaded {len(recs)} records', flush=True)

# Build word → record map
rec_by_word = {r['word'].lower(): r for r in recs}

# Pre-fetch only Oxford pages (parallel) and parse in worker
from bs4 import BeautifulSoup

def fetch_and_parse(word_lower: str) -> tuple[str, dict | None]:
    """Return (word_lower, (n_html, {n: cefr})) or (word_lower, None) if no Oxford cache.

    Tries multiple naming conventions: {word}.html, {word}_({pos}).html, {word}_N_({pos}).html.
    """
    candidates = [
        CACHE / f'{word_lower}.html',
    ]
    # Also try {word}_(pos).html and {word}_N_(pos).html patterns
    for f in os.listdir(CACHE):
        m = re.match(rf'^{re.escape(word_lower)}_(\d+)?_?\((\w+)\)\.html$', f)
        if m:
            candidates.append(CACHE / f)

    n_html = 0
    cefr_by_idx = {}
    for fp in candidates:
        if not fp.exists():
            continue
        try:
            text = fp.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue
        if 'oxfordlearnersdictionaries' not in text.lower():
            continue
        try:
            soup = BeautifulSoup(text, 'lxml')
        except Exception:
            continue
        entry = soup.find(id='entryContent')
        if not entry:
            continue
        sense_lis = entry.find_all('li', class_='sense')
        n_html = len(sense_lis)
        for i, li in enumerate(sense_lis):
            cefr_raw = li.get('fkcefr') or li.get('cefr')
            if cefr_raw and i not in cefr_by_idx:
                cefr_by_idx[i] = cefr_raw.upper()
        # Use the first matching cache (primary POS, no disambig)
        break
    if n_html == 0:
        return word_lower, None
    return word_lower, (n_html, cefr_by_idx)


t0 = time.time()
print('Parallel parse Oxford cache...', flush=True)
with ThreadPoolExecutor(max_workers=16) as ex:
    results = list(ex.map(fetch_and_parse, list(rec_by_word.keys())))
print(f'  done in {time.time()-t0:.1f}s', flush=True)

fkcefr_distribution = Counter()
fkcefr_set = 0
no_ox_cache = 0
no_defs_mismatch = 0

for word_lower, result in results:
    rec = rec_by_word.get(word_lower)
    if not rec:
        continue
    defs = rec.get('definitions', [])
    if result is None:
        # No Oxford cache (Cambridge fallback) — leave def_cefr empty
        for d in defs:
            d['def_cefr'] = ''
        no_ox_cache += 1
        continue
    n_html, cefr_by_idx = result
    if n_html != len(defs):
        no_defs_mismatch += 1
        for d in defs:
            d['def_cefr'] = ''
        continue
    for i, d in enumerate(defs):
        if i in cefr_by_idx:
            d['def_cefr'] = cefr_by_idx[i]
            fkcefr_set += 1
            fkcefr_distribution[cefr_by_idx[i]] += 1
        else:
            d['def_cefr'] = ''

# Write back
with open(JSONL, 'w', encoding='utf-8') as f:
    for rec in recs:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')

print(f'\nRe-parsed: {len(recs) - no_ox_cache} Oxford records')
print(f'  No Oxford cache (Cambridge fallback): {no_ox_cache}')
print(f'  Def count mismatch: {no_defs_mismatch}')
print(f'\nDefs with fkcefr: {fkcefr_set}')
print(f'fkcefr distribution:')
for k, v in sorted(fkcefr_distribution.items()):
    print(f'  {k}: {v}')
