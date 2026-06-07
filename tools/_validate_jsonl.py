"""Validate merged JSONL: check data quality."""
import json
from pathlib import Path
from collections import Counter

DATA = Path(r'C:\Users\admin\Downloads\ielts-deck\data')
JSONL = DATA / 'oxford_full.jsonl'

recs = [json.loads(l) for l in open(JSONL, encoding='utf-8')]
print(f'Total records: {len(recs)}')
print()

# 1. Definitions quality
print('=== 1. Definitions quality ===')
empty_defs = [r for r in recs if not r.get('definitions') or all(not d.get('text', '').strip() for d in r.get('definitions', []))]
print(f'  records with 0/empty defs: {len(empty_defs)}')
if empty_defs:
    for r in empty_defs[:3]:
        print(f'    - {r["word"]} (source={r.get("source")}, n_defs={len(r.get("definitions", []))})')

# 2. Idiom detection via sensenum_local
print()
print('=== 2. Idiom detection (sensenum_local=null) ===')
idiom_count = 0
word_with_idiom = 0
for r in recs:
    has_idiom = False
    for d in r.get('definitions', []):
        if d.get('sensenum_local') is None and d.get('text', '').strip():
            idiom_count += 1
            has_idiom = True
    if has_idiom:
        word_with_idiom += 1
print(f'  total idiom entries: {idiom_count}')
print(f'  words with ≥1 idiom: {word_with_idiom}')

# 3. Cambridge records sanity
print()
print('=== 3. Cambridge records ===')
cam_recs = [r for r in recs if r.get('source') == 'cambridge']
print(f'  count: {len(cam_recs)}')
defs_dist = Counter(len(r.get('definitions', [])) for r in cam_recs)
print(f'  def-count distribution: {dict(defs_dist)}')
print(f'  sample words: {[r["word"] for r in cam_recs[:5]]}')
# Check a Cambridge record
for r in cam_recs[:1]:
    print(f'  sample: {r["word"]} pos={r.get("pos")} cefr={r.get("cefr")} defs={len(r.get("definitions", []))}')

# 4. No CEFR words
print()
print('=== 4. Words with no CEFR ===')
no_cefr = [r for r in recs if not r.get('cefr')]
print(f'  count: {len(no_cefr)}')
if no_cefr:
    for r in no_cefr[:10]:
        print(f'    - {r["word"]} (source={r.get("source")}, lists={r.get("oxford_lists",[])})')

# 5. Register tags distribution
print()
print('=== 5. Register tag distribution ===')
reg_counter = Counter()
for r in recs:
    for t in r.get('register_tags', []):
        reg_counter[t] += 1
for t, n in reg_counter.most_common(20):
    print(f'  {t:25} {n}')
