# `data/` — Oxford vocabulary dataset for ielts-deck

Oxford Learner's Dictionary metadata for all words in `vocab_list/` (Oxford 3000 + 5000 + AWL ≈ 5,000 words). Drives the Anki card content (CEFR, POS, definitions, examples, list membership, register tags, subject labels).

## Files

| File | Format | Purpose |
| --- | --- | --- |
| `oxford_labels.json` | JSON | **Labels taxonomy.** One-shot scrape of `https://www.oxfordlearnersdictionaries.com/about/english/labels`. Contains: `symbols` (14 corpus icons), `register_labels` (12 register tags), `usage_restrictions` (5 usage notes), `subject_labels` (23 academic subject tags). Single source of truth for taxonomy. |
| `oxford_samples.json` | JSON | **Design sample (5 words).** Used for design-system validation only (`rigorous`, `yield`, `aggregate`, `sick`, `paradigm`). Kept for backwards compat with `tools/scrape_oxford.py`. |
| `oxford_full.jsonl` | JSONL | **Full deck scrape (5,002 words, 26,464+ definitions).** One JSON object per line. Produced by `tools/scrape_with_fallback.py`. Source mix: 4,959 Oxford + 43 Cambridge (fallback for Oxford 404s). Each record has `source` field (`oxford` or `cambridge`) and `sensenum_local` per definition (null = idiom/phrasal verb, not a regular sense). Replace whole file to rebuild. |
| `anki_vocab.db` | SQLite | **Queryable mirror of `oxford_full.jsonl`.** Built by `tools/load_oxford_sqlite.py`. Schema: `words` (with `source` field), `definitions`, `pos`, `register_tags`, `subject_labels`. Use for ad-hoc queries. |
| `card_synonyms.json` | JSON | Per-card synonym data (source: in-progress synonym generation). |
| `missing_audio.json` | JSON | List of words missing UK/US TTS audio. Consumed by audio regen. |
| `.synonym_partitions/` | JSON | Intermediate synonym scraper output, partitioned by POS (verb / noun / other). |
| `.cache_html/{word}.html` + `.cache_html/{word}.status` | HTML | Raw cached pages from Oxford (and historically Cambridge) dictionary. `.status` is the 3-digit HTTP code (200 / 404). |

## Regeneration

```bash
# Full re-scrape (Oxford primary + Cambridge fallback, ~6 min, 4 concurrent)
python tools/scrape_with_fallback.py

# Incremental re-scrape (only words not in JSONL)
python tools/scrape_with_fallback.py   # without 'overwrite' arg

# Build SQLite from JSONL
python tools/load_oxford_sqlite.py

# Ad-hoc query
python tools/load_oxford_sqlite.py --query "SELECT cefr, COUNT(*) FROM words GROUP BY cefr"

# Validate JSONL (defs, sources, idiom detection, register tags)
python tools/_validate_jsonl.py
```

The scraper is **incremental by default**: reads `vocab_list/` and only fetches words not already in `oxford_full.jsonl`. Use `scrape_with_fallback.py overwrite` for a clean rebuild from cache. Safe to re-run after partial failures.

## Schema (`oxford_full.jsonl`)

Each line is a JSON object:

```json
{
  "word": "negotiate",
  "source": "oxford",
  "source_url": "https://www.oxfordlearnersdictionaries.com/definition/english/negotiate",
  "fetched_at": "2026-06-07T12:55:48+00:00",
  "cefr": "B2",
  "pos": ["verb"],
  "register_tags": ["formal"],
  "subject_labels": ["War and conflict", "Politics", "Business"],
  "oxford_lists": ["Oxford 5000"],
  "opal": null,
  "awl": null,
  "definitions": [
    {
      "n": 1,
      "sensenum_local": "1",
      "text": "to try to reach an agreement by formal discussion",
      "examples": ["The two sides are still negotiating.", "a negotiating team"]
    },
    {
      "n": 2,
      "sensenum_local": "2",
      "text": "to arrange or agree something by formal discussion",
      "examples": ["to negotiate a deal/contract/treaty"]
    },
    {
      "n": 3,
      "sensenum_local": "3",
      "text": "to successfully get over or past a difficult part on a path or route",
      "examples": ["The horse negotiated the fence."]
    }
  ]
}
```

**Notes on `sensenum_local`**:
- Oxford's `sensenum` attribute is **per-section** (resets per POS group). We use a global counter for `n` and preserve the local `sensenum` as `sensenum_local` for diagnostics.
- `sensenum_local=null` indicates the entry is an idiom or phrasal verb (not a numbered regular sense). 2,597 of 5,002 words have ≥1 idiom.
- For words where `sensenum_local` is `null` AND the definition text is short (e.g., "at sb's discretion"), it's a genuine idiom; for multi-POS words (e.g., "sick" with 16 entries), use `sensenum_local` to detect section boundaries.

**Cambridge records** (43 of 5,002): have `source: "cambridge"`, `register_tags: []`, `subject_labels: []` (Cambridge doesn't expose structured labels in scrapeable HTML). URL: `https://dictionary.cambridge.org/dictionary/english/{word}`.

## SQL example

```sql
-- B2 words with formal register tag
SELECT w.word, w.cefr, w.n_defs
FROM words w
JOIN register_tags r ON r.word = w.word
WHERE w.cefr = 'B2' AND r.tag = 'formal'
ORDER BY w.word
LIMIT 20;

-- Subject distribution
SELECT label, COUNT(*) AS n
FROM subject_labels
GROUP BY label
ORDER BY n DESC;
```

## Coverage

Source `vocab_list/`:
- Oxford 3000: ~2,968 headwords
- Oxford 5000: ~1,996 headwords (subset of 5000 not in 3000)
- AWL: ~570 headwords
- **Total: 5,002 unique words**

Cached in `.cache_html/`: ~6,800 raw HTML pages (Oxford + Cambridge + leftovers from old runs).

Scraped (written to `oxford_full.jsonl`): **5,002 words** (4,959 Oxford + 43 Cambridge fallback).

CEFR distribution:
| CEFR | Count |
| --- | --- |
| A1 | 887 |
| A2 | 784 |
| B1 | 693 |
| B2 | 1,288 |
| C1 | 1,275 |
| C2 | 11 |
| (none) | 64 |

Source mix: 99.1% Oxford / 0.9% Cambridge fallback (43 of 5,002).

## Failure modes

- HTTP 404: word not in Oxford dictionary (e.g., typos, rare forms). Logged as `{"word": X, "error": "HTTP 404", ...}`. Filter via `jq 'select(.error)'` or `jq -c 'select(. | has("error") | not)'`.
- Parse failure: HTML structure changed. Re-runs will overwrite the bad record (incremental re-scrape).

## See also

- `vocab_list/Oxford/Oxford_3000.md`, `vocab_list/Oxford/Oxford_5000.md` — Oxford tier lists in markdown table
- `vocab_list/AWL/AWL.json` — Academic Word List in JSON
- `tools/scrape_oxford.py` — original 5-word design scraper
- `tools/scrape_oxford_full.py` — v1 full incremental scraper (no fallback)
- `tools/scrape_with_fallback.py` — **v2 scraper** (Oxford primary + Cambridge fallback, recommended)
- `tools/load_oxford_sqlite.py` — JSONL → SQLite loader
- `tools/_validate_jsonl.py` — JSONL data quality inspector
