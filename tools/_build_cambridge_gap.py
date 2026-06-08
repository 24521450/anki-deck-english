"""Build target list of 172 words needing Cambridge fallback:
- in study list 3020
- in oxford_full.jsonl with source=oxford AND cefr=None AND cambridge_cefr=None
- has definitions (defs non-empty)

Output: data/_cambridge_gap.txt (one word per line)
"""
import json
from pathlib import Path

PR = Path(r"C:\Users\admin\Downloads\ielts-deck")
JSONL = PR / "data" / "oxford_full.jsonl"
STUDY = PR / "data" / "English Academic Vocabulary.txt"
OUT = PR / "data" / "_cambridge_gap.txt"

recs = {json.loads(l)['word']: json.loads(l)
        for l in JSONL.read_text(encoding='utf-8').splitlines() if l.strip()}

# Words in study list
study_words = set()
with STUDY.open("r", encoding="utf-8") as f:
    for line in f:
        if line.startswith("#"):
            continue
        parts = line.rstrip("\n").split("\t")
        if len(parts) >= 4:
            study_words.add(parts[3])

# Target: any source (oxford/cambridge/unclassified), cefr=None, cambridge_cefr=None, in study list
# Skip if already has CEFR from any source
targets = []
for w in sorted(study_words):
    r = recs.get(w)
    if not r:
        continue
    if r.get("cefr"):
        continue
    if r.get("cambridge_cefr"):
        continue
    # Even if defs are empty, try Cambridge — Cambridge often has CEFR for these
    targets.append(w)

print(f"Words in study list: {len(study_words)}")
print(f"Targets (Oxford defs OK, no CEFR, no Cambridge yet): {len(targets)}")
print(f"Sample: {targets[:10]}")

OUT.write_text("\n".join(targets) + "\n", encoding="utf-8")
print(f"Wrote {len(targets)} words to {OUT}")
