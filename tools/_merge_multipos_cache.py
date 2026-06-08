"""Multi-POS pass: parse all oxford_*_(POS).html cache files and merge into JSONL.

Existing JSONL has records with mixed-POS defs (e.g. just has adv=A1 + adj=C1 mixed
in one record, with head_cefr = lowest = A1). The multi-POS cache files (e.g.
oxford_just_2_(adj).html) have POS-specific defs with correct per-def def_cefr.

This script:
  1. Finds all cache files matching `oxford_*_(adj).html` etc. (POS-specific pages)
  2. Parses each into a multi-POS record (one record per word+pos)
  3. If a word already exists in JSONL: merge by appending POS-specific defs
     and overwriting the per-POS head_cefr (not the global head_cefr).
  4. If new: add as new record.

Idempotent. Does NOT touch records that have no matching cache file.
"""
import json
import re
import shutil
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timezone

PR = Path(r"C:\Users\admin\Downloads\ielts-deck")
JSONL = PR / "data" / "oxford_full.jsonl"
CACHE = PR / "data" / ".cache_html"

# POS code mapping (filename -> full POS name)
POS_MAP = {
    "noun": "noun", "verb": "verb", "adj": "adjective", "adv": "adverb",
    "prep": "preposition", "pron": "pronoun", "conj": "conjunction",
    "det": "determiner", "modal": "modal verb", "aux": "auxiliary verb",
    "excl": "exclamation", "num": "number", "prefix": "prefix",
    "suffix": "suffix", "comb": "combining form",
    "phrasal verb": "phrasal verb", "idiom": "idiom",
    "phrase": "phrase",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_oxford_page(text: str, word: str, pos_label: str) -> dict | None:
    """Parse a single oxford_*_(POS).html file. pos_label = the POS short code in
    filename (e.g. 'adj', 'noun', 'verb'). Returns dict suitable to merge."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(text, "lxml")
    entry = soup.find(id="entryContent")
    if not entry:
        return None

    h1 = entry.find("h1", class_="headword")
    list_flags = {}
    if h1:
        for attr, targets in {
            "ox3000": ("Oxford 3000",), "ox5000": ("Oxford 5000",),
            "opal_written": ("OPAL written",), "opal_spoken": ("OPAL spoken",),
            "academic": ("AWL",), "awl": ("AWL",),
        }.items():
            if h1.get(attr) == "y":
                for t in targets:
                    list_flags[t] = True

    pos_full = POS_MAP.get(pos_label, pos_label)
    senses = entry.find_all("li", class_="sense")
    cefr_levels = []
    definitions = []
    for n, li in enumerate(senses, start=1):
        sense_cefr = ""
        for attr in ("fkcefr", "cefr"):
            v = (li.get(attr) or "").upper()
            if re.match(r"^[A-C][12]$", v):
                sense_cefr = v
                break
        if sense_cefr and sense_cefr not in cefr_levels:
            cefr_levels.append(sense_cefr)

        is_idiom = False
        cur = li
        for _ in range(8):
            cur = cur.parent
            if not cur:
                break
            if cur.name == "div" and "idioms" in (cur.get("class") or []):
                is_idiom = True
                break

        def_span = li.find("span", class_="def")
        def_text = def_span.get_text(" ", strip=True) if def_span else ""
        examples = [ex.get_text(" ", strip=True) for ex in li.find_all("span", class_="x")
                    if ex.get_text(strip=True)]

        idm_phrase = ""
        if is_idiom:
            idm_head = li.find(class_="idm")
            if idm_head:
                idm_phrase = idm_head.get_text(" ", strip=True)

        definitions.append({
            "n": n,
            "sensenum_local": li.get("sensenum"),
            "is_idiom": is_idiom,
            "idm_phrase": idm_phrase or None,
            "text": def_text,
            "examples": examples,
            "pos": pos_full,
            "def_cefr": sense_cefr,
        })

    cefr_order = {"A1": 1, "A2": 2, "B1": 3, "B2": 4, "C1": 5, "C2": 6}
    head_cefr = min(cefr_levels, key=lambda c: cefr_order.get(c, 99)) if cefr_levels else None

    return {
        "pos": pos_full,
        "head_cefr": head_cefr,
        "definitions": definitions,
        "oxford_lists": [n for n in ("Oxford 3000", "Oxford 5000") if list_flags.get(n)],
    }


def find_pos_in_filename(filename: str) -> tuple[str, str] | None:
    """Parse `oxford_<word>_<n>_(pos).html` or `oxford_<word>_(pos).html` -> (word, pos_short).
    Returns None if filename doesn't match.
    """
    m = re.match(r"^oxford_(.+?)(?:_(\d+))?_\(([^)]+)\)\.html$", filename)
    if not m:
        return None
    word, _n, pos_short = m.groups()
    return word, pos_short


def main():
    import time
    print("Loading JSONL...", flush=True)
    recs: dict[str, dict] = {}
    for line in JSONL.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        recs[r["word"]] = r
    print(f"  {len(recs)} records", flush=True)

    # Find all multi-POS cache files
    pattern = re.compile(r"^oxford_(.+?)(?:_(\d+))?_\(([^)]+)\)\.html$")
    cache_files = []
    for f in CACHE.iterdir():
        m = pattern.match(f.name)
        if m:
            cache_files.append((m.group(1), m.group(3), f))
    print(f"  Found {len(cache_files)} multi-POS cache files", flush=True)

    stats = {
        "files_parsed": 0,
        "files_failed": 0,
        "records_merged": 0,
        "records_created": 0,
        "pos_defs_added": 0,
    }

    # Group by (word, pos_short) to handle duplicate pages (e.g. just has _1_ and _2_)
    by_pos: dict[tuple[str, str], list[Path]] = defaultdict(list)
    for word, pos_short, f in cache_files:
        by_pos[(word, pos_short)].append(f)

    for idx, ((word, pos_short), files) in enumerate(by_pos.items(), 1):
        # For words like "just" with _1_(adv) and _2_(adj), the cache already
        # has POS tag in filename. Just use the file's parse to get per-pos defs.
        # If there are multiple files for same (word, pos), the Oxford 3000 one
        # (without _N_ suffix) usually has more complete data.
        # Prefer the file WITHOUT _N_ suffix.
        primary = None
        for f in files:
            if not re.search(r"_\d+_\(", f.name):
                primary = f
                break
        if primary is None:
            primary = files[0]

        text = primary.read_text(encoding="utf-8", errors="replace")
        pos_record = parse_oxford_page(text, word, pos_short)
        if pos_record is None or not pos_record["definitions"]:
            stats["files_failed"] += 1
            continue
        stats["files_parsed"] += 1

        if word in recs:
            r = recs[word]
            # Merge: append this POS's defs into the existing record,
            # but ONLY defs whose pos matches (don't duplicate cross-POS defs).
            existing_defs = r.get("definitions", [])
            existing_pos_set = {d.get("pos") for d in existing_defs}
            new_defs = [d for d in pos_record["definitions"] if d.get("pos") not in existing_pos_set]
            existing_defs.extend(new_defs)
            stats["pos_defs_added"] += len(new_defs)
            r["definitions"] = existing_defs
            # Update head_cefr to be lowest across all POS (already in this record)
            cefr_order = {"A1": 1, "A2": 2, "B1": 3, "B2": 4, "C1": 5, "C2": 6}
            all_cefrs = [d.get("def_cefr") for d in existing_defs if d.get("def_cefr")]
            if all_cefrs:
                r["cefr"] = min(all_cefrs, key=lambda c: cefr_order.get(c, 99))
            r["pos"] = list(set(r.get("pos", []) + [pos_record["pos"]]))
            r["fetched_at"] = now_iso()
            stats["records_merged"] += 1
        else:
            # New record
            new_rec = {
                "word": word,
                "source": "oxford",
                "source_url": f"https://www.oxfordlearnersdictionaries.com/definition/english/{word}",
                "fetched_at": now_iso(),
                "cefr": pos_record["head_cefr"],
                "pos": [pos_record["pos"]],
                "register_tags": [],
                "subject_labels": [],
                "oxford_lists": pos_record["oxford_lists"],
                "opal": None,
                "awl": None,
                "definitions": pos_record["definitions"],
            }
            recs[word] = new_rec
            stats["records_created"] += 1

        if idx % 100 == 0:
            print(f"  [{idx}/{len(by_pos)}] parsed={stats['files_parsed']} merged={stats['records_merged']}", flush=True)

    # Backup + write
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bak = JSONL.with_suffix(f".{ts}.bak")
    shutil.copy2(JSONL, bak)
    print(f"Backup: {bak}", flush=True)

    with JSONL.open("w", encoding="utf-8") as f:
        for w in sorted(recs.keys()):
            f.write(json.dumps(recs[w], ensure_ascii=False) + "\n")
    print(f"Wrote {len(recs)} records to {JSONL}", flush=True)

    print(f"\n=== Stats ===", flush=True)
    for k, v in stats.items():
        print(f"  {k:25s} = {v}", flush=True)


if __name__ == "__main__":
    main()
