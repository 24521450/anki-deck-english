"""Look very carefully for Oxford list icons."""
import re

with open(r"C:\Users\admin\Downloads\ielts-deck\data\.cache_html\_inspect_rigorous.html", "r", encoding="utf-8") as f:
    html = f.read()

# Look for any element with these substrings
for kw in ["My Word Lists", "Add to", "oxford-5000", "oxford5000", "ox3k", "ox5k", "icon-star", "star-o", "star-icon", "oxford-list", "list-icon", "wn", "cefr=", "cefr-"]:
    matches = list(re.finditer(kw, html, re.IGNORECASE))
    print(f"KW={kw!r}: {len(matches)}")
    for m in matches[:2]:
        s = max(0, m.start() - 60)
        e = min(len(html), m.end() + 200)
        print(f"   ...{html[s:e]}...")

# Look for any data-* attribute that mentions list
for m in re.finditer(r'data-([\w-]+)="([^"]*)"', html):
    name, val = m.group(1), m.group(2)
    if any(k in val.lower() for k in ["oxford", "awl", "opal", "3000", "5000", "list"]):
        print(f"DATA: {name}={val}")

# Look for any element with class containing 'star', 'icon-' (other than icon-audio, icon-bar)
for m in re.finditer(r'class="([^"]+)"', html):
    for c in m.group(1).split():
        if c.startswith("icon-") and c not in ("icon-audio", "icon-bar"):
            print(f"ICON-CLASS: {c}")

# Look for any href that contains 'wordlists' or 'oxford' or 'awl'
print("--- hrefs ---")
for m in re.finditer(r'href="([^"]+)"', html):
    href = m.group(1)
    if any(k in href.lower() for k in ["wordlist", "awl", "oxford-", "opal", "3000", "5000", "academic"]):
        print(f"HREF: {href}")
