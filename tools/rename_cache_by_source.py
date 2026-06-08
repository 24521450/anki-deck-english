"""Rename cache files with source prefix: oxford_*.html, cambridge_*.html.

For each {name}.html in data/.cache_html/, detect source by reading first 2KB:
  - "oxfordlearnersdictionaries" → prefix "oxford_"
  - "dictionary.cambridge"       → prefix "cambridge_"
  - else                          → leave (or prefix "unknown_")

Idempotent: skips files that already have a valid prefix.
"""
import os
import re
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

CACHE = Path(r'C:\Users\admin\Downloads\ielts-deck\data\.cache_html')
KNOWN_PREFIXES = ('oxford_', 'cambridge_')


def detect_source(name: str) -> str | None:
    """Worker: read first 2KB, return 'oxford' / 'cambridge' / None."""
    fp = CACHE / name
    try:
        with open(fp, 'rb') as f:
            head = f.read(2048).decode('utf-8', errors='replace').lower()
    except Exception:
        return None
    if 'oxfordlearnersdictionaries' in head:
        return 'oxford'
    if 'dictionary.cambridge' in head:
        return 'cambridge'
    return None


def main():
    t0 = time.time()
    files = [f for f in os.listdir(CACHE) if f.endswith('.html')]
    print(f'Total files: {len(files)}', flush=True)

    # Detect sources in parallel
    print('Detecting sources (parallel)...', flush=True)
    with ThreadPoolExecutor(max_workers=16) as ex:
        sources = list(ex.map(detect_source, files))
    print(f'  done in {time.time()-t0:.1f}s', flush=True)

    # Stats
    src_count = {'oxford': 0, 'cambridge': 0, None: 0}
    for s in sources:
        src_count[s if s else None] = src_count.get(s if s else None, 0) + 1
    print(f'  Source distribution: {src_count}', flush=True)

    # Rename
    print('Renaming...', flush=True)
    renamed = 0
    skipped = 0
    for f, src in zip(files, sources):
        if src is None:
            continue  # unknown source, skip
        if f.startswith(KNOWN_PREFIXES):
            skipped += 1
            continue
        new_name = f'{src}_{f}'
        new_path = CACHE / new_name
        if new_path.exists():
            skipped += 1
            continue
        try:
            (CACHE / f).rename(new_path)
            renamed += 1
        except Exception:
            pass
    print(f'  Renamed: {renamed}, Skipped: {skipped}', flush=True)

    # Final summary
    final = [f for f in os.listdir(CACHE) if f.endswith('.html')]
    ox = sum(1 for f in final if f.startswith('oxford_'))
    cam = sum(1 for f in final if f.startswith('cambridge_'))
    unk = sum(1 for f in final if f.endswith('.html') and not f.startswith(KNOWN_PREFIXES))
    print(f'\nFinal: oxford={ox}, cambridge={cam}, unprefixed={unk}', flush=True)
    print(f'Total time: {time.time()-t0:.1f}s', flush=True)


if __name__ == '__main__':
    main()
