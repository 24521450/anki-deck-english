"""Final schema validation of both output JSONs."""
import json
import re
from collections import Counter

# 1. labels.json schema
with open(r'C:\Users\admin\Downloads\ielts-deck\data\oxford_labels.json', 'r', encoding='utf-8') as f:
    labels = json.load(f)

print("=== labels.json ===")
assert "source_url" in labels and "fetched_at" in labels
assert isinstance(labels["symbols"], list) and len(labels["symbols"]) == 14
assert isinstance(labels["register_labels"], list) and len(labels["register_labels"]) == 12
assert isinstance(labels["usage_restrictions"], list) and len(labels["usage_restrictions"]) == 5
assert isinstance(labels["subject_labels"], list) and len(labels["subject_labels"]) == 23
# All symbols have name + description
for s in labels["symbols"]:
    assert "name" in s and "description" in s
# All register labels have name + description + examples_given
for r in labels["register_labels"]:
    assert "name" in r and "description" in r and isinstance(r["examples_given"], list)
# All usage restrictions have name + description + examples_given
for u in labels["usage_restrictions"]:
    assert "name" in u and "description" in u and isinstance(u["examples_given"], list)
print(f"  ✓ 14 symbols, 12 register, 5 usage, 23 subjects — schema OK")

# 2. samples.json schema
with open(r'C:\Users\admin\Downloads\ielts-deck\data\oxford_samples.json', 'r', encoding='utf-8') as f:
    samples = json.load(f)

print()
print("=== samples.json ===")
assert "fetched_at" in samples
assert isinstance(samples["samples"], list) and len(samples["samples"]) == 5
print(f"  ✓ 5 samples")

expected_words = ["rigorous", "yield", "aggregate", "sick", "paradigm"]
got_words = [s["word"] for s in samples["samples"]]
assert got_words == expected_words, f"word order mismatch: {got_words}"
print(f"  ✓ word order: {got_words}")

# Per-sample checks
for s in samples["samples"]:
    for k in ("word", "source_url", "cefr", "pos", "register_tags",
              "subject_labels", "oxford_lists", "opal", "awl",
              "definitions", "word_family"):
        assert k in s, f"missing key '{k}' in {s['word']}"
    assert isinstance(s["pos"], list) and len(s["pos"]) >= 1
    assert isinstance(s["register_tags"], list)
    assert isinstance(s["subject_labels"], list)
    assert isinstance(s["oxford_lists"], list)
    assert isinstance(s["definitions"], list) and len(s["definitions"]) >= 1
    assert isinstance(s["word_family"], list)
    # definitions schema
    for d in s["definitions"]:
        assert isinstance(d["n"], int)
        assert isinstance(d["text"], str)
        assert isinstance(d["examples"], list)

    # Check no duplicate n values (this was the bug in attempt 1)
    ns = [d["n"] for d in s["definitions"]]
    assert len(ns) == len(set(ns)), f"DUPLICATE n values in {s['word']}: {ns}"

    # CEFR uppercase
    if s["cefr"] is not None:
        assert s["cefr"].isupper(), f"CEFR not uppercase: {s['cefr']}"

    # opal: string or null
    assert s["opal"] is None or isinstance(s["opal"], str)

    # awl: string or null
    assert s["awl"] is None or isinstance(s["awl"], str)

    # oxford_lists entries are strings
    for ol in s["oxford_lists"]:
        assert isinstance(ol, str)

    print(f"  ✓ {s['word']:10} cefr={s['cefr']!r:6} senses={len(s['definitions']):2} "
          f"n_range=[{min(ns):2}..{max(ns):2}] unique_n={len(set(ns))} "
          f"opal={s['opal']!r} awl={s['awl']!r} lists={s['oxford_lists']}")

# 3. Specific check that yield's OPAL is no longer null
yld = next(s for s in samples["samples"] if s["word"] == "yield")
assert yld["opal"] == "OPAL written", f"yield.opal should be 'OPAL written', got {yld['opal']!r}"
print()
print("  ✓ yield.opal = 'OPAL written' (was null in attempt 1)")

# 4. Specific check that sick has 16 unique n values
sick = next(s for s in samples["samples"] if s["word"] == "sick")
ns = [d["n"] for d in sick["definitions"]]
assert ns == list(range(1, 17)), f"sick n sequence wrong: {ns}"
print(f"  ✓ sick n sequence is [1..16] (was [1..14,1,2] in attempt 1)")

# 5. Aggregate has AWL
agg = next(s for s in samples["samples"] if s["word"] == "aggregate")
assert agg["awl"] == "AWL", f"aggregate.awl should be 'AWL', got {agg['awl']!r}"
print(f"  ✓ aggregate.awl = 'AWL'")

# 6. Paradigm has AWL
paradigm = next(s for s in samples["samples"] if s["word"] == "paradigm")
assert paradigm["awl"] == "AWL", f"paradigm.awl should be 'AWL', got {paradigm['awl']!r}"
print(f"  ✓ paradigm.awl = 'AWL'")

# 7. Register tags for sick (the 'informal' tag mentioned in task)
assert "informal" in sick["register_tags"], f"sick should have 'informal' register tag: {sick['register_tags']}"
print(f"  ✓ sick has 'informal' register tag (16 senses include informal senses)")

print()
print("ALL CHECKS PASSED")
