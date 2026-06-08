"""Re-parse renamed Oxford cache files and update JSONL with per-POS defs.

Each cache file is named {word}_({pos}).html. We parse each, add 'pos' to every def,
and merge into the JSONL record for that word.

Dedupe: if {word}_({pos}).html and {word}_1_({pos}).html both exist, prefer the former
(Oxford's URL convention uses _1 as the "main" entry hash, but content is identical).
"""
import json
import re
import os
import time
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

DATA = Path(r'C:\Users\admin\Downloads\ielts-deck\data')
CACHE = DATA / '.cache_html'
JSONL = DATA / 'oxford_full.jsonl'

# Map file suffix → canonical POS name (matches what vocab_cefr uses)
SUFFIX_TO_POS = {
    'noun': 'noun', 'verb': 'verb', 'adj': 'adjective', 'adv': 'adverb',
    'prep': 'preposition', 'pron': 'pronoun', 'conj': 'conjunction',
    'det': 'determiner', 'modal': 'modal verb', 'aux': 'auxiliary verb',
    'excl': 'exclamation', 'num': 'number',
    'prefix': 'prefix', 'suffix': 'suffix', 'comb': 'combining form',
}


def parse_oxford_html_with_pos(text: str, word: str, pos_name: str) -> dict:
    """Like parse_oxford_html but tags every def with `pos`."""
    from bs4 import BeautifulSoup
    from scrape_with_fallback import parse_oxford_html
    # Use the v2 parser for consistency, then add pos to each def
    rec = parse_oxford_html(text, word)
    for d in rec.get('definitions', []):
        d['pos'] = pos_name
    # Set record's pos field to canonical name too
    if pos_name and not rec.get('pos'):
        rec['pos'] = [pos_name]
    return rec


def parse_file(name):
    """Worker: read file, parse, return (word, pos, defs, is_idiom count, etc)."""
    # Match both {word}_({pos}).html and {word}_N_({pos}).html (N=disambiguation)
    m = re.match(r'^(.+?)_(\d+)?_?\((\w+)\)\.html$', name)
    if not m:
        return (name, None, None, None, None, None)
    word = m.group(1)
    num = m.group(2)
    suffix = m.group(3)  # group 3 is the POS suffix, group 2 is optional disambig number
    pos_name = SUFFIX_TO_POS.get(suffix, suffix)
    path = CACHE / name
    try:
        text = path.read_text(encoding='utf-8', errors='replace')
    except Exception:
        return (name, word, pos_name, [], 0, 0)
    if 'oxfordlearnersdictionaries' not in text.lower():
        return (name, word, pos_name, [], 0, 0)
    try:
        rec = parse_oxford_html_with_pos(text, word, pos_name)
    except Exception as e:
        return (name, word, pos_name, [], 0, 0)
    defs = rec.get('definitions', [])
    return (name, word, pos_name, defs, len([d for d in defs if not d.get('is_idiom')]),
            len([d for d in defs if d.get('is_idiom')]))


def main():
    t0 = time.time()
    print('Loading JSONL...', flush=True)
    recs = {}
    for line in open(JSONL, encoding='utf-8'):
        rec = json.loads(line)
        recs[rec['word'].lower()] = rec
    print(f'  Loaded {len(recs)} records', flush=True)

    # Read all renamed files in parallel
    print('Reading cache files (parallel)...', flush=True)
    files = sorted([f for f in os.listdir(CACHE) if f.endswith('.html') and '(' in f])
    # Dedupe by (word, pos): prefer X_(pos).html over X_N_(pos).html
    # Regex matches both: rock_(noun).html AND rock_1_(noun).html
    by_word_pos = {}
    for f in files:
        m = re.match(r'^(.+?)_(\d+)?_?\((\w+)\)\.html$', f)
        if m:
            base, num, suf = m.group(1), m.group(2), m.group(3)
            key = (base, suf)
            if num is None:
                by_word_pos[key] = f
            elif key not in by_word_pos:
                by_word_pos[key] = f
    deduped = list(by_word_pos.values())
    print(f'  Total files: {len(files)}, deduped: {len(deduped)}', flush=True)

    with ThreadPoolExecutor(max_workers=16) as ex:
        results = list(ex.map(parse_file, deduped))
    print(f'  Parsed {len(results)} files in {time.time()-t0:.1f}s', flush=True)

    # Group by word
    word_files = defaultdict(list)  # word -> [(pos, defs), ...]
    for name, word, pos_name, defs, _, _ in results:
        if word and pos_name and defs is not None:
            if word == 'rock':
                print(f"  DEBUG: {name} -> word={word!r} pos_name={pos_name!r} n_defs={len(defs)}")
            word_files[word].append((pos_name, defs))

    # Merge into JSONL: for each word, replace its definitions with merged list
    print('\nMerging into JSONL...', flush=True)
    updated = 0
    no_change = 0
    missing = 0
    for word, lst in word_files.items():
        rec = recs.get(word)
        if rec is None:
            missing += 1
            continue
        # Merge defs from all POS files for this word
        merged_defs = []
        for pos_name, defs in lst:
            for d in defs:
                # Update n to be global counter
                d2 = dict(d)
                d2['pos'] = pos_name
                merged_defs.append(d2)
        if merged_defs:
            rec['definitions'] = merged_defs
            # Update pos field to include all POS
            all_pos = list(dict.fromkeys([d.get('pos') for d in merged_defs if d.get('pos')]))
            rec['pos'] = all_pos
            updated += 1
        else:
            no_change += 1

    # Save
    with open(JSONL, 'w', encoding='utf-8') as f:
        for word in sorted(recs.keys()):
            f.write(json.dumps(recs[word], ensure_ascii=False) + '\n')
    print(f'  Updated {updated} records, no_change {no_change}, missing {missing}', flush=True)
    print(f'  Saved {JSONL}', flush=True)

    # Sample
    print('\n=== Sample rock ===', flush=True)
    if 'rock' in recs:
        rec = recs['rock']
        print(f"  pos: {rec.get('pos')}", flush=True)
        print(f"  head_cefr: {rec.get('cefr')}", flush=True)
        for d in rec.get('definitions', [])[:8]:
            print(f"    [{d['n']}] pos={d.get('pos')} idiom={d.get('is_idiom')} def_cefr={d.get('def_cefr','')!r} text={d.get('text','')[:50]!r}", flush=True)

    print(f'\nTotal time: {time.time()-t0:.1f}s', flush=True)


if __name__ == '__main__':
    import sys
    sys.path.insert(0, r'C:\Users\admin\Downloads\ielts-deck\tools')
    main()
