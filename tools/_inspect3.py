"""Inspect webtop block."""
import re

with open(r"C:\Users\admin\Downloads\ielts-deck\data\.cache_html\_inspect_rigorous.html", "r", encoding="utf-8") as f:
    html = f.read()

# Look for webtop
m = re.search(r'<div class="webtop">.*?</div>\s*</div>', html, re.DOTALL)
if m:
    print("webtop block length:", len(m.group()))
    print(m.group()[:3000])
print("---")
# Look for any 'oxford-3000' or 'oxford_3000' in entire HTML
for kw in ["oxford-3000", "oxford_3000", "oxford-5000", "oxford_5000", "awl", "OPAL", "opal"]:
    for mm in re.finditer(kw, html, re.IGNORECASE):
        start = max(0, mm.start() - 100)
        end = min(len(html), mm.end() + 200)
        print(f"  KW={kw}: ...{html[start:end]}...")
