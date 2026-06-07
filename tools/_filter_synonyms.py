#!/usr/bin/env python3
"""Filter card_synonyms.json: remove records with empty 'synonym' field, log missing words."""
import json
from pathlib import Path

DATA = Path(r'C:\Users\admin\Downloads\ielts-deck\data')
src = DATA / 'card_synonyms.json'
dst = DATA / 'card_synonyms.cleaned.json'
log = DATA / 'missing_synonyms.txt'

records = json.load(open(src, encoding='utf-8'))
print(f'source: {len(records)} records')

kept, dropped = [], []
for r in records:
    syn = (r.get('synonym') or '').strip()
    if syn:
        kept.append(r)
    else:
        dropped.append(r)

print(f'kept:   {len(kept)}')
print(f'dropped: {len(dropped)}')

# Write cleaned
with open(dst, 'w', encoding='utf-8', newline='') as f:
    json.dump(kept, f, ensure_ascii=False, indent=2)
print(f'wrote:  {dst}')

# Log missing words (sorted, dedup)
missing = sorted({r['word'].strip() for r in dropped if r.get('word', '').strip()})
with open(log, 'w', encoding='utf-8', newline='') as f:
    f.write('# Words with no NLTK-derived synonyms in card_synonyms.json\n')
    f.write(f'# Total missing: {len(missing)}\n')
    f.write(f'# Total source records: {len(records)}\n')
    f.write(f'# Total dropped: {len(dropped)}\n\n')
    for w in missing:
        f.write(w + '\n')
print(f'wrote:  {log}  ({len(missing)} unique words)')
