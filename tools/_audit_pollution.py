"""Categorize pollution patterns in oxford_full.jsonl."""
import json
from collections import Counter

JSONL = r'C:\Users\admin\Downloads\ielts-deck\data\oxford_full.jsonl'
recs = [json.loads(l) for l in open(JSONL, encoding='utf-8')]
print(f'Total records: {len(recs)}')

# Source distribution
src_dist = Counter(r.get('source', 'MISSING') for r in recs)
print(f'Source distribution: {dict(src_dist)}')

# Group by pollution pattern
pat_a = [r for r in recs if r.get('source','') == 'cambridge' and r.get('cefr')]
pat_b = [r for r in recs if r.get('source','') == 'cambridge' and r.get('cefr') and r.get('cambridge_cefr') and r['cefr'] == r['cambridge_cefr']]
pat_c = [r for r in recs if r.get('source','') != 'cambridge' and r.get('cefr') and r.get('cambridge_cefr') and r['cefr'] == r['cambridge_cefr']]
pat_d = []
for r in recs:
    for d in r.get('definitions', []):
        if d.get('def_cefr') and r.get('cambridge_cefr') and d['def_cefr'] == r['cambridge_cefr']:
            pat_d.append((r['word'], d.get('n')))

print(f'\nPattern A (cambridge-source WITH head_cefr): {len(pat_a)}')
print(f'Pattern B (cambridge-source head==cam): {len(pat_b)}')
print(f'Pattern C (oxford-source head==cam, suspicious): {len(pat_c)}')
print(f'Pattern D (any def with def_cefr==cam, per-def pollution): {len(pat_d)}')

print('\nPattern A words (head set on cambridge-source recs):')
for r in pat_a:
    head = r.get('cefr') or 'None'
    cam = r.get('cambridge_cefr') or 'None'
    print(f'  {r["word"]:20s} src={r["source"]:10s} head={str(head):4s} cam={str(cam):4s}')

print('\nPattern C words (oxford-source but head matches cambridge):')
for r in pat_c:
    head = r.get('cefr') or 'None'
    cam = r.get('cambridge_cefr') or 'None'
    print(f'  {r["word"]:20s} src={r["source"]:10s} head={str(head):4s} cam={str(cam):4s}')
