"""Merge Cambridge gap results into oxford_full.jsonl.

For each record in _cambridge_gap_results.jsonl:
  - If cambridge_cefr is set: add to rec as 'cambridge_cefr' and 'cambridge_all_cefrs'
  - Also: if Cambridge has defs and existing rec has no defs (e.g. unclassified stubs),
    add Cambridge defs to fill the gap.
  - NEVER overwrite existing cefr/cambridge_cefr fields.
"""
import json
import shutil
from pathlib import Path
from datetime import datetime, timezone

PR = Path(r"C:\Users\admin\Downloads\ielts-deck")
JSONL = PR / "data" / "oxford_full.jsonl"
GAP = PR / "data" / "_cambridge_gap_results.jsonl"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def merge():
    print("Loading data...")
    recs = {}
    for line in JSONL.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        recs[r["word"]] = r
    print(f"  oxford_full.jsonl: {len(recs)} records")

    gap = [json.loads(l) for l in GAP.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"  Cambridge gap: {len(gap)} records")

    stats = {
        "cefr_added": 0,
        "defs_added": 0,
        "skipped_has_cefr": 0,
        "skipped_no_data": 0,
    }

    for g in gap:
        word = g["word"]
        r = recs.get(word)
        if not r:
            continue
        # Add cambridge_cefr if not already set
        if not r.get("cambridge_cefr") and g.get("cambridge_cefr"):
            r["cambridge_cefr"] = g["cambridge_cefr"]
            r["cambridge_all_cefrs"] = g.get("cambridge_all_cefrs", [])
            stats["cefr_added"] += 1
        elif r.get("cambridge_cefr"):
            stats["skipped_has_cefr"] += 1
        # Fill defs if Oxford has none and Cambridge has them
        if not r.get("definitions") and g.get("definitions"):
            r["definitions"] = g["definitions"]
            r["pos"] = r.get("pos") or g.get("pos", [])
            r["cefr"] = r.get("cefr") or g.get("cambridge_cefr")
            if r.get("source") == "unclassified" and g.get("definitions"):
                # Upgrade from unclassified stub to cambridge source if Cambridge has defs
                r["source"] = "cambridge"
                r["source_url"] = g.get("source_url")
            r["fetched_at"] = now_iso()
            stats["defs_added"] += 1
        if not g.get("cambridge_cefr") and not g.get("definitions"):
            stats["skipped_no_data"] += 1

    # Backup + write
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bak = JSONL.with_suffix(f".{ts}.bak")
    shutil.copy2(JSONL, bak)
    print(f"Backup: {bak}")

    with JSONL.open("w", encoding="utf-8") as f:
        for w in sorted(recs.keys()):
            f.write(json.dumps(recs[w], ensure_ascii=False) + "\n")
    print(f"Wrote {len(recs)} records to {JSONL}")

    print(f"\n=== Stats ===")
    for k, v in stats.items():
        print(f"  {k:25s} = {v}")


if __name__ == "__main__":
    merge()
