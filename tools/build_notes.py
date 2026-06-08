"""Build Anki notes from oxford_full.jsonl + card_synonyms.cleaned.json + audio manifest.

Output: data/notes.json (list of dict, one per Anki note)
Output: data/notes.tsv (tab-separated for direct Anki import)

Note fields (13, in order):
  Word, IPA, PartOfSpeech, CEFRLevel, Tags,
  Definition, Example, Idioms, Collocations, WordFamily,
  Synonym, AudioUK, AudioUS

Idiom handling:
  - JSONL definitions split into `senses` (sensenum_local != null) and `idioms` (sensenum_local == null)
  - `Definition`: pipe-separated regular senses
  - `Example`: pipe-separated examples, indexed to defs
  - `Idioms`: pipe-separated idioms, each with optional `; example` suffix

CEFR filter (default B2/C1/C2 only — per user instruction 2026-06-08):
  - Cards with A1/A2/B1 CEFR are SKIPPED.
  - Override with --cefr "A1,A2,B1,B2,C1,C2" to include all.
"""
from __future__ import annotations
import argparse
import json
import re
import sqlite3
from pathlib import Path
from collections import defaultdict

DATA = Path(r'C:\Users\admin\Downloads\ielts-deck\data')
PR = Path(r'C:\Users\admin\Downloads\ielts-deck')
AUDIO = PR / 'audio'
JSONL = DATA / 'oxford_full.jsonl'
DB = DATA / 'anki_vocab.db'
SYNONYMS = DATA / 'card_synonyms.cleaned.json'
NOTES_JSON = DATA / 'notes.json'
NOTES_TSV = DATA / 'notes.tsv'
MISSING_AUDIO = DATA / 'missing_audio.json'
VOCAB_DIR = PR / 'vocab_list' / 'Oxford'

# Default filter: B2/C1/C2 only (per user instruction 2026-06-08).
# Use --cefr to override (e.g. --cefr "A1,A2,B1,B2,C1,C2" for full deck).
DEFAULT_CEFR_FILTER = ['B2', 'C1', 'C2']

# Audio file prefixes (we have 3 sources: oxford, cambridge, tts)
AUDIO_PREFIX = {
    'oxford': 'oxford_{accent}_{word}.mp3',
    'cambridge': 'cambridge_{accent}_{word}.mp3',
    'tts': '{accent}_{word}.mp3',  # raw tts has no source prefix
}


def split_definitions(rec: dict) -> tuple[list[dict], list[dict]]:
    """Split definitions into (senses, idioms) using is_idiom flag from parser."""
    senses: list[dict] = []
    idioms: list[dict] = []
    for d in rec.get('definitions', []):
        if d.get('is_idiom') and d.get('text', '').strip():
            idioms.append(d)
        else:
            senses.append(d)
    return senses, idioms


def format_idioms(idioms: list[dict]) -> str:
    """Format idioms field: 'PHRASE : explanation ; example1 ; example2 | next_idiom'.

    If idm_phrase is present, prefix with phrase. Otherwise just the explanation.
    """
    parts = []
    for d in idioms:
        phrase = (d.get('idm_phrase') or '').strip()
        text = d.get('text', '').strip()
        if not text and not phrase:
            continue
        # Combine phrase + explanation
        if phrase and text:
            head = f"{phrase} : {text}"
        else:
            head = phrase or text
        examples = d.get('examples', [])
        if examples:
            head = head + ' ; ' + ' ; '.join(e.strip() for e in examples if e.strip())
        parts.append(head)
    return ' | '.join(parts)


def find_audio(word: str) -> tuple[str, str]:
    """Return (audioUK, audioUS) Anki field values. Empty string if not found.

    Looks in audio/ for {source}_{accent}_{word}.mp3 across all 3 source prefixes.
    Returns '[sound:filename.mp3]' if found, '' otherwise.
    """
    audio_uk, audio_us = '', ''
    for src in ('oxford', 'cambridge', 'tts'):
        if not audio_uk:
            for accent in ('uk',):
                fn = AUDIO_PREFIX[src].format(accent=accent, word=word)
                if (AUDIO / fn).exists():
                    audio_uk = f'[sound:{fn}]'
                    break
        if not audio_us:
            for accent in ('us',):
                fn = AUDIO_PREFIX[src].format(accent=accent, word=word)
                if (AUDIO / fn).exists():
                    audio_us = f'[sound:{fn}]'
                    break
        if audio_uk and audio_us:
            break
    return audio_uk, audio_us


def load_synonyms() -> dict[str, list[str]]:
    """word → list of {definition, synonym} dicts (may have multiple per word)."""
    out: dict[str, list[str]] = defaultdict(list)
    if not SYNONYMS.exists():
        return dict(out)
    for r in json.load(open(SYNONYMS, encoding='utf-8')):
        syn = (r.get('synonym') or '').strip()
        if syn:
            out[r['word'].lower()].append(syn)
    return dict(out)


def build_tags(rec: dict, cefr_source: str = 'oxford') -> str:
    """Build Tags field: corpus memberships + register tags + subject labels + idiom flag.

    `cefr_source` is the source of the chain-resolved CEFR (e.g. 'oxford' for
    def_cefr/vocab/head_cefr, 'cambridge' for cambridge_cefr). Used to add
    the `cefr::<source>` tag so user can tell where the CEFR came from.
    """
    tags = []
    # Corpus
    if rec.get('oxford_lists'):
        for x in rec['oxford_lists']:
            slug = x.replace(' ', '_')
            if slug not in tags:
                tags.append(slug)
    if rec.get('opal'):
        for part in rec['opal'].split(' + '):
            slug = part.replace(' ', '_')
            if slug not in tags:
                tags.append(slug)
    if rec.get('awl'):
        if 'AWL' not in tags:
            tags.append('AWL')
    # Source (record-level scrape source)
    if rec.get('source') == 'cambridge':
        tags.append('cambridge_fallback')
    # CEFR provenance tag — the chain told us this level came from <source>.
    # Tag name: `cefr::oxford` (def_cefr / vocab / head) or `cefr::cambridge`
    # (cambridge_cefr). This replaces the old "derive tag from level value"
    # approach that silently mis-tagged polluted records.
    if cefr_source in ('oxford', 'cambridge'):
        tag = f'cefr::{cefr_source}'
        if tag not in tags:
            tags.append(tag)
    # Register + subject
    for t in rec.get('register_tags', []):
        slug = t.replace(' ', '_')
        if slug not in tags:
            tags.append(slug)
    for t in rec.get('subject_labels', []):
        slug = t.replace(' ', '_')
        if slug not in tags:
            tags.append(slug)
    return ' '.join(tags)


def build_note(rec: dict, syn_map: dict, vocab_cefr: dict) -> dict:
    """Build one Anki note dict from one JSONL record."""
    word = rec['word']
    senses, idioms = split_definitions(rec)
    definitions_text = ' | '.join(d.get('text', '').strip() for d in senses if d.get('text', '').strip())
    examples_text = ' | '.join(
        (d.get('examples', [''])[0] or '').strip() if d.get('examples') else ''
        for d in senses
    )
    idioms_text = format_idioms(idioms)
    # Synonym — take first if multiple (most words have 1-2)
    syn_list = syn_map.get(word.lower(), [])
    syn_text = ' | '.join(syn_list[:3]) if syn_list else ''

    audio_uk, audio_us = find_audio(word)

    # POS — pipe-separated if multiple
    pos = rec.get('pos', [])
    # Filter out "idiom" and "phrasal verb" from POS chips — they're not lexical POS
    lexical_pos = [p for p in pos if p.lower() not in ('idiom', 'phrasal verb', 'phrase')]

    # CEFR — chain-resolved (so Cambridge-only words get the right level
    # and the right source tag, not the empty/oxford value from flat read).
    cefr_level, cefr_source = resolve_record_cefr(rec, vocab_cefr)

    return {
        'Word': word,
        'IPA': '',  # TODO: extract from cached HTML
        'PartOfSpeech': ', '.join(lexical_pos) if lexical_pos else ', '.join(pos),
        'CEFRLevel': cefr_level,
        'Tags': build_tags(rec, cefr_source=cefr_source),
        'Definition': definitions_text,
        'Example': examples_text,
        'Idioms': idioms_text,
        'Collocations': '',  # not in JSONL; would need Oxford Collocations Dictionary scrape
        'WordFamily': '',   # not in JSONL; would need WordNet + Oxford derivatives
        'Synonym': syn_text,
        'AudioUK': audio_uk,
        'AudioUS': audio_us,
        # extra metadata (not in note model) for debugging
        '_meta': {
            'source': rec.get('source'),
            'cefr': rec.get('cefr'),
            'cefr_resolved': cefr_level,
            'cefr_source': cefr_source,
            'n_senses': len(senses),
            'n_idioms': len(idioms),
            'oxford_lists': rec.get('oxford_lists', []),
        },
    }


# CEFR resolution chain — extracted to src/scraper/cefr_chain.py (A in
# architecture review). Per-def chain gives (level, source); we pick the
# primary (lowest non-UNCLASSIFIED) for the card-level CEFRLevel field.
def resolve_record_cefr(rec: dict, vocab_cefr: dict) -> tuple[str, str]:
    """Resolve one record's primary CEFR via the chain. Returns (level, source)."""
    from src.scraper.cefr_chain import CefrContext, resolve_def
    ctx = CefrContext(
        word=rec['word'],
        head_cefr=rec.get('cefr', '') or '',
        cambridge_cefr=rec.get('cambridge_cefr', '') or '',
        vocab_cefr=vocab_cefr,
    )
    defs = rec.get('definitions', []) or [{}]
    resolved = [resolve_def(d, ctx) for d in defs]
    valid = [(lvl, src) for lvl, src in resolved
             if lvl and lvl != 'UNCLASSIFIED']
    if valid:
        from src.scraper.cefr_chain import CEFR_RANK
        return min(valid, key=lambda x: CEFR_RANK.get(x[0], 99))
    return ('UNCLASSIFIED', 'unclassified')


def main():
    # Parse args
    p = argparse.ArgumentParser()
    p.add_argument('--cefr', default=','.join(DEFAULT_CEFR_FILTER),
                   help=f'Comma-separated CEFR levels to include (default: {",".join(DEFAULT_CEFR_FILTER)})')
    p.add_argument('--notes', default=str(NOTES_JSON), help='Output notes.json path')
    p.add_argument('--tsv', default=str(NOTES_TSV), help='Output notes.tsv path')
    args = p.parse_args()
    cefr_filter = [c.strip().upper() for c in args.cefr.split(',') if c.strip()]

    # Load JSONL
    recs = [json.loads(l) for l in open(JSONL, encoding='utf-8')]
    print(f'Loaded {len(recs)} records from {JSONL}')

    # Load vocab_cefr (used by resolve_record_cefr below)
    from src.scraper.cefr_chain import load_vocab_cefr
    vocab_cefr = load_vocab_cefr(VOCAB_DIR)
    print(f'Loaded vocab_cefr for {len(vocab_cefr)} words')

    # CEFR filter — uses the chain (not flat rec['cefr']) so Cambridge-only
    # words with no Oxford head_cefr are still filterable by their chain-resolved
    # level. build_note() also writes the chain-resolved CEFRLevel into each note.
    if cefr_filter:
        before = len(recs)
        kept = []
        for r in recs:
            level, _src = resolve_record_cefr(r, vocab_cefr)
            if level.upper() in cefr_filter:
                kept.append(r)
        recs = kept
        print(f'CEFR filter {cefr_filter}: kept {len(recs)}/{before}')

    # Load synonyms
    syn_map = load_synonyms()
    print(f'Loaded synonyms for {len(syn_map)} words')

    # Build notes
    notes = []
    stats = {
        'with_idioms': 0,
        'with_audio_uk': 0,
        'with_audio_us': 0,
        'with_synonyms': 0,
        'with_empty_defs': 0,
        'cambridge_fallback': 0,
    }
    for r in recs:
        n = build_note(r, syn_map, vocab_cefr)
        notes.append(n)
        if n['Idioms']: stats['with_idioms'] += 1
        if n['AudioUK']: stats['with_audio_uk'] += 1
        if n['AudioUS']: stats['with_audio_us'] += 1
        if n['Synonym']: stats['with_synonyms'] += 1
        if not n['Definition']: stats['with_empty_defs'] += 1
        if r.get('source') == 'cambridge': stats['cambridge_fallback'] += 1

    # Write JSON
    out_json = Path(args.notes)
    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump(notes, f, ensure_ascii=False, indent=2)
    print(f'Wrote {len(notes)} notes → {out_json}')

    # Write TSV (Anki import format: 13 fields, tab-separated)
    out_tsv = Path(args.tsv)
    fields = ['Word', 'IPA', 'PartOfSpeech', 'CEFRLevel', 'Tags',
              'Definition', 'Example', 'Idioms', 'Collocations', 'WordFamily',
              'Synonym', 'AudioUK', 'AudioUS']
    with open(out_tsv, 'w', encoding='utf-8', newline='') as f:
        f.write('#separator:tab\n#html:true\n')
        # Column headers as comment for Anki
        for n in notes:
            row = [str(n.get(k, '')) for k in fields]
            # Anki TSV: replace newlines within field with <br>
            row = [r.replace('\r', '').replace('\n', '<br>').replace('\t', ' ') for r in row]
            f.write('\t'.join(row) + '\n')
    print(f'Wrote {out_tsv}')

    # Stats
    print()
    print('=== Stats ===')
    for k, v in stats.items():
        print(f'  {k:25} {v}/{len(notes)} ({v*100/len(notes):.1f}%)')

    # Missing audio (words with no UK or US audio)
    missing_uk = [n['Word'] for n in notes if not n['AudioUK']]
    missing_us = [n['Word'] for n in notes if not n['AudioUS']]
    if missing_uk or missing_us:
        out = {
            'generated_at': __import__('datetime').datetime.now().isoformat(),
            'missing_uk': missing_uk,
            'missing_us': missing_us,
        }
        with open(MISSING_AUDIO, 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f'\nWrote missing audio: {len(missing_uk)} missing UK, {len(missing_us)} missing US → {MISSING_AUDIO}')


if __name__ == '__main__':
    main()
