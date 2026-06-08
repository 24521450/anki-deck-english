import json
from pathlib import Path

DATA = Path(r"C:\Users\admin\Downloads\ielts-deck\data")

for p in sorted(DATA.glob("oxford_full*")):
    try:
        with open(p, "r", encoding="utf-8") as f:
            for n, line in enumerate(f, 1):
                if '"constrain"' in line or '"constrain' in line:
                    rec = json.loads(line)
                    if rec["word"] == "constrain":
                        print(f"{p.name}: L{n} -> cefr={rec.get('cefr')}, cambridge_cefr={rec.get('cambridge_cefr')}, cambridge_all={rec.get('cambridge_all_cefrs')}")
    except Exception as e:
        print(f"Error reading {p.name}: {e}")
