"""Merge _rescrape_results.jsonl + _rescraped_cambridge.jsonl into oxford_full.jsonl.

Logic per word:
  - 3 scrape failures (deprive/derive/devote): update existing JSONL record's
    definitions from Oxford re-scrape; KEEP existing cambridge_cefr (newer scrape may differ).
  - 319 truly missing words:
    - If Oxford re-scrape got defs: create new record from Oxford
    - If Oxford re-scrape failed AND Cambridge got defs+CEFR: create new record from Cambridge
    - If both failed: create stub record with source="unclassified", cefr=null,
      definitions=[], and tag so split_study_cards handles gracefully.

Idempotency: re-running is safe. If a word already in JSONL, update defs only.
"""
import json
import shutil
from pathlib import Path
from datetime import datetime, timezone

PR = Path(r"C:\Users\admin\Downloads\ielts-deck")
JSONL = PR / "data" / "oxford_full.jsonl"
RESCRAPE = PR / "data" / "_rescrape_results.jsonl"
CAMBRIDGE = PR / "data" / "_rescraped_cambridge.jsonl"

SCRAPE_FAILURES = {"deprive", "derive", "devote"}


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def merge():
    print("Loading data...")
    existing: dict[str, dict] = {}
    for r in load_jsonl(JSONL):
        existing[r["word"]] = r
    print(f"  oxford_full.jsonl: {len(existing)} records")

    rescrape: dict[str, dict] = {}
    for r in load_jsonl(RESCRAPE):
        rescrape[r["word"]] = r
    print(f"  rescrape results: {len(rescrape)} records")

    cambridge: dict[str, dict] = {}
    for r in load_jsonl(CAMBRIDGE):
        # de-dup by word (some words appear twice with paren)
        if r["word"] not in cambridge:
            cambridge[r["word"]] = r
    print(f"  cambridge results: {len(cambridge)} records (de-duped)")

    stats = {
        "scrape_failures_updated": 0,
        "oxford_new": 0,
        "cambridge_fallback": 0,
        "unclassified": 0,
        "unchanged": 0,
    }

    # 1. Update 3 scrape failures
    for w in SCRAPE_FAILURES:
        old = existing.get(w)
        new = rescrape.get(w)
        if not new or not new.get("definitions"):
            print(f"  WARN: {w} re-scrape still has no defs")
            continue
        if old:
            old["definitions"] = new["definitions"]
            old["cefr"] = new.get("cefr") or old.get("cefr")
            old["pos"] = new.get("pos") or old.get("pos")
            old["register_tags"] = new.get("register_tags", old.get("register_tags", []))
            old["subject_labels"] = new.get("subject_labels", old.get("subject_labels", []))
            old["oxford_lists"] = new.get("oxford_lists", old.get("oxford_lists", []))
            old["opal"] = new.get("opal", old.get("opal"))
            old["awl"] = new.get("awl", old.get("awl"))
            old["fetched_at"] = now_iso()
            stats["scrape_failures_updated"] += 1
            print(f"  UPDATED {w}: {len(new['definitions'])} defs, cefr={old.get('cefr')}, cam={old.get('cambridge_cefr')}")

    # 2. Process all rescrape results (319 + 3 failures)
    for word, new in rescrape.items():
        # Determine if this is a "new" word or a scrape failure update
        is_failure = word in SCRAPE_FAILURES and word in existing
        is_existing = word in existing

        if is_existing and not is_failure:
            stats["unchanged"] += 1
            continue

        if is_failure:
            # Update existing record: prefer Oxford defs, fallback Cambridge
            old = existing[word]
            if new.get("definitions"):
                # Oxford now has defs
                old["definitions"] = new["definitions"]
                old["cefr"] = new.get("cefr") or old.get("cefr")
                old["pos"] = new.get("pos") or old.get("pos")
                old["register_tags"] = new.get("register_tags", old.get("register_tags", []))
                old["subject_labels"] = new.get("subject_labels", old.get("subject_labels", []))
                old["oxford_lists"] = new.get("oxford_lists", old.get("oxford_lists", []))
                old["opal"] = new.get("opal", old.get("opal"))
                old["awl"] = new.get("awl", old.get("awl"))
                old["fetched_at"] = now_iso()
                stats["scrape_failures_updated"] += 1
                print(f"  UPDATED {word} (Oxford): {len(new['definitions'])} defs, cefr={old.get('cefr')}")
            else:
                # Oxford still no defs -> Cambridge
                cam = cambridge.get(word)
                if cam and cam.get("definitions"):
                    old["definitions"] = cam["definitions"]
                    old["cambridge_cefr"] = cam.get("cambridge_cefr")
                    old["cambridge_all_cefrs"] = cam.get("cambridge_all_cefrs", [])
                    old["cefr"] = old.get("cefr")  # keep null
                    old["pos"] = cam.get("pos") or old.get("pos")
                    old["fetched_at"] = now_iso()
                    stats["scrape_failures_updated"] += 1
                    print(f"  UPDATED {word} (Cambridge): {len(cam['definitions'])} defs, cam_cefr={cam.get('cambridge_cefr')}")
            continue

        # New word: create record
        if new.get("definitions") and not new.get("error"):
            # Oxford ok
            new_rec = {
                "word": word,
                "source": "oxford",
                "source_url": new.get("source_url"),
                "fetched_at": new.get("fetched_at", now_iso()),
                "cefr": new.get("cefr"),
                "pos": new.get("pos", []),
                "register_tags": new.get("register_tags", []),
                "subject_labels": new.get("subject_labels", []),
                "oxford_lists": new.get("oxford_lists", []),
                "opal": new.get("opal"),
                "awl": new.get("awl"),
                "definitions": new["definitions"],
            }
            existing[word] = new_rec
            stats["oxford_new"] += 1
        else:
            # Oxford failed -> Cambridge fallback
            cam = cambridge.get(word)
            if cam and cam.get("definitions") and cam.get("cambridge_cefr"):
                # Cambridge has defs and CEFR
                new_rec = {
                    "word": word,
                    "source": "cambridge",
                    "source_url": cam.get("source_url"),
                    "fetched_at": cam.get("fetched_at", now_iso()),
                    "cefr": cam.get("cefr"),
                    "pos": cam.get("pos", []),
                    "register_tags": [],
                    "subject_labels": [],
                    "oxford_lists": [],
                    "opal": None,
                    "awl": None,
                    "definitions": cam["definitions"],
                    "cambridge_cefr": cam.get("cambridge_cefr"),
                    "cambridge_all_cefrs": cam.get("cambridge_all_cefrs", []),
                }
                existing[word] = new_rec
                stats["cambridge_fallback"] += 1
            else:
                # Both failed -> UNCLASSIFIED stub
                new_rec = {
                    "word": word,
                    "source": "unclassified",
                    "source_url": None,
                    "fetched_at": now_iso(),
                    "cefr": None,
                    "pos": [],
                    "register_tags": [],
                    "subject_labels": [],
                    "oxford_lists": [],
                    "opal": None,
                    "awl": None,
                    "definitions": [],
                    "unclassified": True,
                }
                existing[word] = new_rec
                stats["unclassified"] += 1

    # 3. Sanity: any words in study_split still not in existing?
    study_words = set()
    with (PR / "data" / "study_split.tsv").open("r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("#"):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 4:
                study_words.add(parts[3])

    still_missing = study_words - set(existing.keys())
    if still_missing:
        # Edge case: words in study_split but not targeted by re-scrape
        # (e.g. came from a different source). Create UNCLASSIFIED stub.
        print(f"\n  Edge case: {len(still_missing)} study words not in rescrape -> UNCLASSIFIED")
        for w in still_missing:
            existing[w] = {
                "word": w, "source": "unclassified", "fetched_at": now_iso(),
                "cefr": None, "pos": [], "definitions": [], "unclassified": True,
            }
            stats["unclassified"] += 1

    # 4. Backup + write
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bak = JSONL.with_suffix(f".{ts}.bak")
    shutil.copy2(JSONL, bak)
    print(f"\nBackup: {bak}")

    with JSONL.open("w", encoding="utf-8") as f:
        for w in sorted(existing.keys()):
            f.write(json.dumps(existing[w], ensure_ascii=False) + "\n")
    print(f"Wrote {len(existing)} records to {JSONL}")

    print(f"\n=== Stats ===")
    for k, v in stats.items():
        print(f"  {k:30s} = {v}")


if __name__ == "__main__":
    merge()
