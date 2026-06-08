"""Cleanup Oxford pollution: revert 32 records' `cefr` field to Oxford vocab value or None.

Background: `_fetch_cambridge_cefr.py` previously wrote Cambridge CEFR values into
Oxford-specific `cefr` and `def_cefr` fields. This polluted 32 records (all source=oxford
with `rec['cefr'] == rec['cambridge_cefr']`). The chain resolution Step 4 (head_cefr)
would then return the Cambridge value and tag the card `cefr::oxford` — incorrect.

This script reverts the 32 records' `cefr` field:
  - 13 records with Oxford vocab value -> revert to vocab value
  - 19 records without Oxford vocab -> revert to None

Expected outcome: 19 records fall through to Step 5 (cambridge_cefr) and get tagged
`cefr::cambridge`. 13 records keep `cefr::oxford` tag with correct Oxford value.

The 8 disputed records (source=cambridge with cefr != cambridge_cefr) are NOT touched
here — see disputed_audit.md for the follow-up ticket.

Idempotent: re-running is safe because:
  1. Pollution signature check: skip records where cefr != cambridge_cefr
  2. Match word in revert map: only revert 32 specific words
  3. Skip records that already have the target value

Usage:
  python tools/_cleanup_oxford_pollution.py --dry-run
  python tools/_cleanup_oxford_pollution.py
"""
import json
import re
import shutil
import sys
from pathlib import Path
from datetime import datetime, timezone

DATA = Path(r'C:\Users\admin\Downloads\ielts-deck\data')
JSONL = DATA / 'oxford_full.jsonl'
VOCAB = Path(r'C:\Users\admin\Downloads\ielts-deck\vocab_list\Oxford')

# 32 polluted words. Target value = lowest Oxford CEFR across POSes,
# or None if word is not in Oxford 3000/5000 vocab.
# Filled in main() from vocab markdown — but we hard-code the word list
# (safety: we ONLY touch these 32 words, even if the pollution check would
# catch more in a future data state).
POLLUTED_WORDS = {
    # 13 with Oxford vocab value
    'alongside': 'B2', 'deed': 'C1', 'deprive': 'C1', 'derive': 'B2',
    'devote': 'B2', 'dispose': 'C1', 'full-time': 'B2', 'halfway': 'C1',
    'line-up': 'C1', 'mainland': 'C1', 'marathon': 'B2', 'pace': 'B2',
    'solo': 'C1',
    # 19 without Oxford vocab (revert to None)
    'ambiguous': None, 'concurrent': None, 'constrain': None, 'denote': None,
    'deviate': None, 'discrete': None, 'equate': None, 'finite': None,
    'id': None, 'ignorant': None, 'implicate': None, 'innovate': None,
    'intrinsic': None, 'levy': None, 'notwithstanding': None, 'orient': None,
    'qualitative': None, 'reluctance': None, 'subordinate': None,
}


def load_jsonl(path: Path) -> list[dict]:
    records = []
    with path.open('r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def save_jsonl(path: Path, records: list[dict]):
    with path.open('w', encoding='utf-8') as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')


def main():
    dry_run = '--dry-run' in sys.argv

    print(f'Loading {JSONL}...')
    records = load_jsonl(JSONL)
    print(f'  {len(records)} records loaded')

    # Build word -> record map
    by_word = {r['word']: r for r in records}

    # Audit + apply
    stats = {
        'reverted_to_vocab': 0,
        'reverted_to_none': 0,
        'skipped_not_polluted': 0,
        'skipped_not_in_map': 0,
        'skipped_already_correct': 0,
        'missing_word': 0,
    }
    changes = []

    for word, target_cefr in POLLUTED_WORDS.items():
        rec = by_word.get(word)
        if rec is None:
            print(f'  WARN: word "{word}" not found in JSONL')
            stats['missing_word'] += 1
            continue

        cur_cefr = rec.get('cefr')
        cam_cefr = rec.get('cambridge_cefr')

        # Pollution signature: cur_cefr should match cam_cefr
        if cam_cefr and cur_cefr != cam_cefr:
            # This is one of the 8 disputed words (source=cambridge, cur != cam)
            # We deliberately skip it
            print(f'  SKIP disputed: {word} (cur={cur_cefr}, cam={cam_cefr})')
            stats['skipped_not_polluted'] += 1
            continue

        # Already at target value
        if cur_cefr == target_cefr:
            stats['skipped_already_correct'] += 1
            continue

        # Revert
        old_cefr = cur_cefr
        rec['cefr'] = target_cefr
        changes.append((word, old_cefr, target_cefr))
        if target_cefr is None:
            stats['reverted_to_none'] += 1
        else:
            stats['reverted_to_vocab'] += 1

    # Print changes
    print(f'\n{"="*60}')
    print(f'Changes ({len(changes)} total):')
    for word, old, new in changes:
        print(f'  {word:18s} {old!s:>4s} -> {new!s}')

    print(f'\n{"="*60}')
    print('Stats:')
    for k, v in stats.items():
        print(f'  {k:30s} = {v}')

    if dry_run:
        print(f'\n[DRY-RUN] No changes written. Re-run without --dry-run to apply.')
        return

    if not changes:
        print(f'\nNo changes to apply. Exiting.')
        return

    # Backup before write
    ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    bak = JSONL.with_suffix(f'.{ts}.bak')
    shutil.copy2(JSONL, bak)
    print(f'\nBackup written: {bak}')

    # Write
    save_jsonl(JSONL, records)
    print(f'Saved {JSONL}')

    # Sanity: verify pollution signature is now broken for the 19 None-reverts
    print(f'\n--- Post-write verification ---')
    for word, target in POLLUTED_WORDS.items():
        if target is None and word in by_word:
            rec = by_word[word]
            cam = rec.get('cambridge_cefr', '')
            cef = rec.get('cefr')
            if cam and cef is None:
                # Now Step 4 (head_cefr=None) will skip, Step 5 (cambridge_cefr) will win
                print(f'  OK  {word:18s} cefr=None, cambridge_cefr={cam} -> Step 5 wins -> cefr::cambridge')
            elif cam and cef == cam:
                print(f'  WARN {word:18s} cefr still = cambridge_cefr ({cam}) — bug in logic?')


if __name__ == '__main__':
    main()
