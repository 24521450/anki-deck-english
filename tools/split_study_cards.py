"""Build split-card TSV for B2/C1/C2 of study list.

Inputs:
  - data/oxford_full.jsonl      (5,002 records with def_cefr)
  - data/English Academic Vocabulary.txt  (existing study list, 3,020 rows)
  - vocab_list/Oxford/Oxford_3000.md, Oxford_5000.md  (per-word CEFR)
  - audio/  (UK/US mp3)

Output:
  - data/study_split.tsv  (Anki-import TSV, ready to replace original)

Algorithm:
  1. For each row in study list, get word + current CEFR (col 15).
  2. Filter to B2/C1/C2 CEFRs only.
  3. For each word, look up record in oxford_full.jsonl.
  4. For each def, resolve CEFR via chain:
     - def_cefr (from fkcefr/cefr attr on Oxford HTML)
     - else vocab_list (Oxford_3000.md / Oxford_5000.md)
     - else Oxford web (head_cefr)
     - else Cambridge
     - else UNCLASSIFIED
  5. Group defs by resolved CEFR.
  6. For each CEFR group:
     - Sort: senses first (is_idiom=False), then idioms, in source order (n asc).
     - Take top 3 (user rule: max 3 defs per card).
     - Generate 1 card with: Word, IPA, POS, top-3 defs, top-3 examples,
       idioms of same CEFR (filtered), audio, source, new tags.
  7. A1/A2/B1 cards: keep as-is from original TSV.
  8. Output: same 16-column TSV format as input.

Card deck name: same as original row's deck (e.g., "::Oxford", "::TED YT").
New GUIDs generated for additional split cards.
"""
import json
import re
import uuid
from pathlib import Path
from collections import defaultdict

DATA = Path(r'C:\Users\admin\Downloads\ielts-deck\data')
VOCAB = Path(r'C:\Users\admin\Downloads\ielts-deck\vocab_list')
JSONL = DATA / 'oxford_full.jsonl'
STUDY = DATA / 'English Academic Vocabulary.txt'
OUT = DATA / 'study_split.tsv'

# CEFR chain sources
CEFR_RANK = {'A1': 1, 'A2': 2, 'B1': 3, 'B2': 4, 'C1': 5, 'C2': 6,
             'UNCLASSIFIED': 99, '': 99, None: 99}

# Load vocab_list → word → pos → CEFR map (per-POS)
vocab_cefr = {}  # word -> {pos: cefr}
for md in VOCAB.glob('Oxford/*.md'):
    text = md.read_text(encoding='utf-8', errors='replace')
    for m in re.finditer(r'\|\s*\*\*([^*]+)\*\*\s*\|\s*([^|]+)\|\s*([ABC][12])\s*\|', text):
        w = m.group(1).strip().lower()
        pos = m.group(2).strip()
        lvl = m.group(3)
        if w not in vocab_cefr:
            vocab_cefr[w] = {}
        # If multiple POS entries for same word, prefer the first (or override if missing)
        if pos not in vocab_cefr[w]:
            vocab_cefr[w][pos] = lvl
# For backward compat, also build vocab_cefr_word = word -> cefr (lowest across POS)
vocab_cefr_word = {}
for w, pos_map in vocab_cefr.items():
    if pos_map:
        vocab_cefr_word[w] = min(pos_map.values(), key=lambda c: CEFR_RANK.get(c, 99))

# Load JSONL
print('Loading JSONL...', flush=True)
recs = {json.loads(l)['word'].lower(): json.loads(l) for l in open(JSONL, encoding='utf-8')}

# Read study list
print('Reading study list...', flush=True)
header_lines = []
data_lines = []
with open(STUDY, encoding='utf-8') as f:
    for line in f:
        if line.startswith('#'):
            header_lines.append(line.rstrip('\n'))
        elif line.strip():
            data_lines.append(line.rstrip('\n'))

print(f'Study list: {len(data_lines)} cards')

# Process each row
# DEDUPE: keep only the FIRST row per (word, CEFR) for A1/A2/B1.
# For B2/C1/C2, we split by CEFR — so dedupe by word (keep first row's GUID for the lowest-CEFR split card).
out_rows = []
stats = defaultdict(int)
new_card_count = 0

# First pass: dedupe by word, keep first occurrence
seen_words = set()
deduped_rows = []  # (word_lower, original_cols)
skipped_dupes = 0
for line in data_lines:
    cols = line.split('\t')
    if len(cols) < 16:
        out_rows.append(cols + [''] * (16 - len(cols)))
        continue
    word_lower = cols[3].strip().lower()
    if word_lower in seen_words:
        skipped_dupes += 1
        continue
    seen_words.add(word_lower)
    deduped_rows.append((word_lower, cols))

stats['skipped_duplicates'] = skipped_dupes

# Second pass: process deduped rows
for word_lower, cols in deduped_rows:
    guid, notetype, deck, word, pos, ipa, defn, ex, _, _, auk, aus, src, _, cefr, tags = cols[:16]
    cefr_norm = cefr.strip()

    rec = recs.get(word_lower)
    if not rec:
        # No JSONL record — keep original (no chain possible)
        out_rows.append(cols[:16])
        stats['no_jsonl'] += 1
        continue

    defs = rec.get('definitions', [])
    if not defs:
        # No defs — keep original
        out_rows.append(cols[:16])
        stats['no_defs'] += 1
        continue

    # Resolve CEFR for each def
    word_head_cefr = rec.get('cefr', '')
    word_source = rec.get('source', 'oxford')
    word_cambridge_cefr = rec.get('cambridge_cefr', '')
    word_pos_map = vocab_cefr.get(word_lower, {})  # per-POS from vocab_cefr
    # Build per-def CEFR using chain: def_cefr -> vocab_cefr[word][def.pos] -> vocab_cefr[word] -> head_cefr -> cambridge_cefr -> UNCLASSIFIED
    def_cefrs = []
    for d in defs:
        cefr_resolved = ''
        def_pos = d.get('pos', '')
        # Step 1: def_cefr from fkcefr attribute (per-def, most accurate)
        if d.get('def_cefr'):
            cefr_resolved = d['def_cefr']
        # Step 2: vocab_cefr[word][def.pos] (per-POS)
        elif def_pos and def_pos in word_pos_map:
            cefr_resolved = word_pos_map[def_pos]
        # Step 3: vocab_cefr[word] (per-word fallback — lowest CEFR across all POSes)
        elif word_pos_map:
            # Pick the LOWEST CEFR across all known POSes
            cefr_resolved = min(word_pos_map.values(), key=lambda c: CEFR_RANK.get(c, 99))
        # Step 4: oxford web head_cefr
        elif word_head_cefr:
            cefr_resolved = word_head_cefr
        # Step 5: cambridge web
        elif word_cambridge_cefr:
            cefr_resolved = word_cambridge_cefr
        # Step 6: unclassified
        else:
            cefr_resolved = 'UNCLASSIFIED'
        def_cefrs.append(cefr_resolved)

    # Group by CEFR
    by_cefr = defaultdict(list)
    for i, d in enumerate(defs):
        by_cefr[def_cefrs[i]].append((i, d))

    # For each CEFR group, create 1 card
    n_groups = len([c for c in by_cefr.keys() if c])  # skip UNCLASSIFIED for counting
    if n_groups == 0:
        # All defs are UNCLASSIFIED — keep original
        out_rows.append(cols[:16])
        stats['all_unclassified'] += 1
        continue

    # Sort groups by CEFR rank (lowest first)
    sorted_cefrs = sorted(by_cefr.keys(), key=lambda c: (CEFR_RANK.get(c, 99), c))

    # For A1/A2/B1 cards: keep 1 card, but update CEFR field with chain-resolved value
    if cefr_norm not in ('B2', 'C1', 'C2'):
        # Pick primary CEFR (lowest in CEFR_RANK among def_cefrs, skip UNCLASSIFIED)
        primary_cefr = ''
        for dc in def_cefrs:
            if dc and dc != 'UNCLASSIFIED':
                if not primary_cefr or CEFR_RANK.get(dc, 99) < CEFR_RANK.get(primary_cefr, 99):
                    primary_cefr = dc
        if not primary_cefr:
            primary_cefr = 'UNCLASSIFIED'
        # Update only the CEFR field (col 14), keep everything else as original
        new_row = list(cols[:16])
        new_row[14] = primary_cefr
        # Strip ALL old CEFR::X tags from existing tags (replace, not append)
        existing_tags = new_row[15] or ''
        cleaned_tags = ' '.join(t for t in existing_tags.split() if not t.startswith('CEFR::'))
        # Add the new CEFR tag
        if primary_cefr and primary_cefr != 'UNCLASSIFIED':
            if cleaned_tags:
                cleaned_tags = cleaned_tags + ' CEFR::' + primary_cefr
            else:
                cleaned_tags = 'CEFR::' + primary_cefr
        new_row[15] = cleaned_tags
        out_rows.append(new_row)
        stats['a1_a2_b1_cefr_updated'] += 1
        continue

    first_card = True
    for group_cefr in sorted_cefrs:
        group = by_cefr[group_cefr]
        # Sort: senses first (is_idiom=False), then idioms, both in source order
        senses = [(i, d) for i, d in group if not d.get('is_idiom')]
        idioms = [(i, d) for i, d in group if d.get('is_idiom')]
        senses.sort(key=lambda x: x[0])
        idioms.sort(key=lambda x: x[0])
        ordered = senses + idioms
        # Take top 3
        top3 = ordered[:3]
        # Build per-card definition and example
        def_parts = []
        ex_parts = []
        for _, d in top3:
            txt = d.get('text', '').strip()
            if not txt:
                continue
            def_parts.append(txt)
            examples = d.get('examples', [])
            if examples:
                ex_parts.append(examples[0])
            else:
                ex_parts.append('')
        card_def = ' | '.join(def_parts)
        card_ex = ' | '.join(ex_parts)

        # Idioms field: idioms of same group CEFR
        idm_texts = []
        for i, d in idioms:
            phrase = (d.get('idm_phrase') or '').strip()
            txt = d.get('text', '').strip()
            if phrase and txt:
                head = f"{phrase} : {txt}"
            else:
                head = phrase or txt
            examples = d.get('examples', [])
            if examples:
                head = head + ' ; ' + ' ; '.join(e.strip() for e in examples if e.strip())
            if head:
                idm_texts.append(head)
        card_idioms = ' | '.join(idm_texts)

        # New GUID
        if first_card:
            new_guid = guid
            first_card = False
        else:
            new_guid = str(uuid.uuid4().int)[:10] + ''.join(chr((i % 26) + 65) for i in range(2))

        # Tags: strip ALL old CEFR::X tags, then add the per-card CEFR (replace, not append)
        cleaned_tags = ' '.join(t for t in tags.split() if not t.startswith('CEFR::'))
        if group_cefr and group_cefr != 'UNCLASSIFIED':
            if cleaned_tags:
                cleaned_tags = cleaned_tags + ' CEFR::' + group_cefr
            else:
                cleaned_tags = 'CEFR::' + group_cefr
        new_tags = cleaned_tags

        # Build row
        # cols: 0=GUID, 1=NoteType, 2=Deck, 3=Word, 4=POS, 5=IPA,
        #       6=Def, 7=Ex, 8=Synonym, 9=WordFamily, 10=AudioUK, 11=AudioUS,
        #       12=Source, 13=Oxford_5000?, 14=CEFR, 15=Tags
        # We don't have Synonym/WordFamily here — keep empty
        new_row = [
            new_guid,    # 0 GUID
            notetype,    # 1 NoteType
            deck,        # 2 Deck
            word,        # 3 Word
            pos,         # 4 POS
            ipa,         # 5 IPA
            card_def,    # 6 Def (top-3)
            card_ex,     # 7 Ex (top-3)
            '',          # 8 Synonym (empty — not in JSONL)
            '',          # 9 WordFamily (empty)
            auk,         # 10 AudioUK
            aus,         # 11 AudioUS
            src,         # 12 Source
            cols[13] if len(cols) > 13 else '',  # 13 (extra)
            group_cefr,  # 14 CEFR (per card)
            new_tags,    # 15 Tags
        ]
        out_rows.append(new_row)
        new_card_count += 1

    if first_card:
        # No group generated (shouldn't happen since n_groups > 0)
        out_rows.append(cols[:16])
    stats['split'] += 1

# Write output
with open(OUT, 'w', encoding='utf-8', newline='') as f:
    for hl in header_lines:
        f.write(hl + '\n')
    for row in out_rows:
        # Replace newlines and tabs in fields
        clean = [str(c).replace('\r', '').replace('\n', '<br>').replace('\t', ' ') for c in row]
        f.write('\t'.join(clean) + '\n')

print(f'\nWrote {OUT}')
print(f'Total rows: {len(out_rows)} (was {len(data_lines)})')
print(f'  +{new_card_count - len(data_lines) + stats["kept_unchanged"] + stats["no_jsonl"] + stats["no_defs"] + stats["all_unclassified"]} net new cards')
print(f'\nStats:')
for k, v in stats.items():
    print(f'  {k:25} {v}')
