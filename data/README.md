# `data/` — Oxford vocabulary dataset for ielts-deck

Oxford Learner's Dictionary metadata for all words in `vocab_list/` (Oxford 3000 + 5000 + AWL ≈ 5,000 words). Drives the Anki card content (CEFR, POS, definitions, examples, list membership, register tags, subject labels).

## Files

| File | Format | Purpose |
| --- | --- | --- |
| `oxford_labels.json` | JSON | **Labels taxonomy.** One-shot scrape of `https://www.oxfordlearnersdictionaries.com/about/english/labels`. Contains: `symbols` (14 corpus icons), `register_labels` (12 register tags), `usage_restrictions` (5 usage notes), `subject_labels` (23 academic subject tags). Single source of truth for taxonomy. |
| `oxford_samples.json` | JSON | **Design sample (5 words).** Used for design-system validation only (`rigorous`, `yield`, `aggregate`, `sick`, `paradigm`). Kept for backwards compat with `tools/scrape_oxford.py`. |
| `oxford_full.jsonl` | JSONL | **Full deck scrape (2,841+ words, 19,416+ definitions).** One JSON object per line. Produced by `tools/scrape_oxford_full.py`. Append-only. Replace whole file to rebuild. |
| `anki_vocab.db` | SQLite | **Queryable mirror of `oxford_full.jsonl`.** Built by `tools/load_oxford_sqlite.py`. Schema: `words`, `definitions`, `pos`, `register_tags`, `subject_labels`. Use for ad-hoc queries. |
| `card_synonyms.json` | JSON | Per-card synonym data (source: in-progress synonym generation). |
| `missing_audio.json` | JSON | List of words missing UK/US TTS audio. Consumed by audio regen. |
| `.synonym_partitions/` | JSON | Intermediate synonym scraper output, partitioned by POS (verb / noun / other). |
| `.cache_html/{word}.html` + `.cache_html/{word}.status` | HTML | Raw cached pages from Oxford (and historically Cambridge) dictionary. `.status` is the 3-digit HTTP code (200 / 404). |

## Regeneration

```bash
# Full Oxford scrape (~10 min, 1 req/sec throttled to 4 concurrent)
python tools/scrape_oxford_full.py

# Build SQLite from JSONL
python tools/load_oxford_sqlite.py

# Ad-hoc query
python tools/load_oxford_sqlite.py --query "SELECT cefr, COUNT(*) FROM words GROUP BY cefr"
```

The scraper is **incremental**: it reads `vocab_list/` and only fetches words not already in `.cache_html/`. Safe to re-run after partial failures.

## Schema (`oxford_full.jsonl`)

Each line is a JSON object:

```json
{
  "word": "negotiate",
  "source_url": "https://www.oxfordlearnersdictionaries.com/definition/english/negotiate",
  "fetched_at": "2026-06-07T09:57:50+00:00",
  "cefr": "B2",
  "pos": ["verb"],
  "register_tags": ["formal"],
  "subject_labels": ["Politics"],
  "oxford_lists": ["Oxford 5000"],
  "opal": null,
  "awl": null,
  "definitions": [
    {
      "n": 1,
      "text": "to try to reach an agreement by formal discussion",
      "examples": ["The two sides are still negotiating.", "a negotiating team"]
    }
  ]
}
```

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

Cached in `.cache_html/` (after rename): ~3,971 unique words (Oxford + Cambridge dictionary runs).

Scraped (written to `oxford_full.jsonl`): 2,841+5 words (out of 2,875 missing — 29 HTTP 404s for words not in Oxford).

## Failure modes

- HTTP 404: word not in Oxford dictionary (e.g., typos, rare forms). Logged as `{"word": X, "error": "HTTP 404", ...}`. Filter via `jq 'select(.error)'` or `jq -c 'select(. | has("error") | not)'`.
- Parse failure: HTML structure changed. Re-runs will overwrite the bad record (incremental re-scrape).

## See also

- `vocab_list/Oxford/Oxford_3000.md`, `vocab_list/Oxford/Oxford_5000.md` — Oxford tier lists in markdown table
- `vocab_list/AWL/AWL.json` — Academic Word List in JSON
- `tools/scrape_oxford.py` — original 5-word design scraper
- `tools/scrape_oxford_full.py` — full incremental scraper
- `tools/load_oxford_sqlite.py` — JSONL → SQLite loader
