"""Look for icon classes that might indicate Oxford 3000/5000/AWL markers."""
import re

with open(r"C:\Users\admin\Downloads\ielts-deck\data\.cache_html\_inspect_rigorous.html", "r", encoding="utf-8") as f:
    html = f.read()

# Find all class attributes with 'ox' or 'icon' or 'list' or 'word' or 'label'
classes_found = set()
for m in re.finditer(r'class="([^"]+)"', html):
    for c in m.group(1).split():
        if any(k in c.lower() for k in ["ox", "icon", "list", "word", "label", "awl", "opal", "cefr", "ox3", "ox5", "sym", "marker", "tag"]):
            classes_found.add(c)

print("Classes found:", sorted(classes_found))
print("---")
# Look for any element that has a class with these markers
for kw in ["oxford", "ox_", "ox-", "ox3", "ox5", "oxl", "icon-awl", "icon-oxford", "ox5000", "ox3000", "awl-icon", "opal-icon", "oxford-5000", "oxford-3000"]:
    pat = re.compile(kw, re.IGNORECASE)
    matches = list(pat.finditer(html))
    print(f"KW={kw!r}: {len(matches)} matches")
    for m in matches[:2]:
        s = max(0, m.start() - 60)
        e = min(len(html), m.end() + 120)
        print(f"  ...{html[s:e]}...")
