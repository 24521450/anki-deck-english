"""Verify sick sense numbering is unique and global."""
import json
with open(r'C:\Users\admin\Downloads\ielts-deck\data\oxford_samples.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
for s in data['samples']:
    if s['word'] == 'sick':
        ns = [d['n'] for d in s['definitions']]
        print(f"sick: total={len(ns)} unique={len(set(ns))} min={min(ns)} max={max(ns)}")
        if len(set(ns)) != len(ns):
            print("DUPLICATE n values detected!")
        # Show the n and sensenum_local for each
        for d in s['definitions']:
            n = d['n']
            sl = d.get('sensenum_local', '-')
            text = d['text'][:50]
            print(f"  n={n:2} sensenum_local={sl!r:3} text={text!r}")
        break
