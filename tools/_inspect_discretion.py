#!/usr/bin/env python3
"""Deeper inspection of discretion.html and audit all cards in deck."""
import os
import re
import json

# 1. Inspect discretion.html
p = r'C:\Users\admin\Downloads\ielts-deck\data\.cache_html\discretion.html'
with open(p, encoding='utf-8') as f:
    content = f.read()

print('=== discretion.html ===')
print('size:', len(content))

# Title
m = re.search(r'<title>([^<]+)</title>', content)
print('title:', m.group(1) if m else None)

# Cambridge page type
print('synonyms page?', 'synonym' in content.lower()[:5000])
print('antonyms page?', 'antonym' in content.lower()[:5000])

# Find the first h1/h2 in content
for tag in ['h1', 'h2']:
    for m in re.finditer(f'<{tag}[^>]*>([^<]+)<', content):
        text = m.group(1).strip()
        if text and len(text) < 80:
            print(f'  {tag}:', text)
            break

# All h1 (top of page)
print()
print('--- page structure ---')
# Look for "Definition of" or main content
for m in re.finditer(r'<(?:section|div)[^>]*class="[^"]*"[^>]*>', content):
    cls = re.search(r'class="([^"]+)"', m.group(0))
    if cls:
        text = cls.group(1)
        if 'synonym' in text.lower() or 'definition' in text.lower() or 'header' in text.lower() or 'main' in text.lower():
            print('  div/section:', text)

# 2. Check what words are in oxford_full.jsonl vs vocab_list
import os
ox_words = set()
for line in open(r'C:\Users\admin\Downloads\ielts-deck\data\oxford_full.jsonl', encoding='utf-8'):
    rec = json.loads(line)
    ox_words.add(rec.get('word', '').lower())

vocab = set()
for f in os.listdir(r'C:\Users\admin\Downloads\ielts-deck\vocab_list\Oxford'):
    if f.endswith('.md'):
        for line in open(os.path.join(r'C:\Users\admin\Downloads\ielts-deck\vocab_list\Oxford', f), encoding='utf-8'):
            m = re.search(r'\*\*([^*]+)\*\*', line)
            if m:
                vocab.add(m.group(1).strip().lower())

missing = sorted(vocab - ox_words)
print()
print('=== vocab_list - oxford_full gap ===')
print('vocab size:', len(vocab))
print('oxford jsonl size:', len(ox_words))
print('vocab NOT in oxford jsonl:', len(missing))
print('first 30 missing:', missing[:30])
print('discretion in vocab?', 'discretion' in vocab)
print('discretion in oxford jsonl?', 'discretion' in ox_words)

# 3. Check the oxford_labels / subject_labels / register_labels counts
labels = json.load(open(r'C:\Users\admin\Downloads\ielts-deck\data\oxford_labels.json', encoding='utf-8'))
print()
print('=== oxford_labels.json ===')
for k, v in labels.items():
    print(f'  {k}: {len(v)} entries')
    if k == 'register_labels' and len(v) <= 15:
        for x in v: print(f'    - {x}')

# 4. Find words with multi-sense / rare subject labels
print()
print('=== multi-sense / rare words in jsonl ===')
for line in open(r'C:\Users\admin\Downloads\ielts-deck\data\oxford_full.jsonl', encoding='utf-8'):
    rec = json.loads(line)
    n_def = len(rec.get('definitions', []))
    if n_def >= 3 and rec['word'].lower() in {'discretion', 'negotiate', 'yield', 'aggregate', 'sick', 'paradigm'}:
        print(f"  {rec['word']}: {n_def} definitions, labels={rec.get('subject_labels', [])}")
        for d in rec['definitions'][:3]:
            print(f"    - {d.get('pos', '?')}: {d.get('definition', '')[:80]}")
