"""Look for related entries / word lists / 'more information' section."""
import re
from bs4 import BeautifulSoup

with open(r"C:\Users\admin\Downloads\ielts-deck\data\.cache_html\_inspect_rigorous.html", "r", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, "lxml")
# Find relatedentries
re_div = soup.find(id="relatedentries")
if re_div:
    print("--- relatedentries ---")
    print(re_div.get_text(" | ", strip=True)[:1500])

# Find anything mentioning wordlists
for el in soup.find_all(True):
    txt = el.get_text(strip=True)
    if "Word Lists" in txt and len(txt) < 200:
        print("WL:", el.name, el.get("class"), txt[:150])
        break

# Find anything with 'oxford 3000' or 'oxford 5000' visually
for el in soup.find_all(True, attrs={"aria-label": True}):
    al = el.get("aria-label", "")
    if any(k in al.lower() for k in ["oxford", "awl", "opal", "3000", "5000"]):
        print("ARIA:", al)

# Look for any element with 'data-wordlist' or similar
for el in soup.find_all(True):
    for k, v in el.attrs.items():
        sv = str(v)
        if any(kw in sv.lower() for kw in ["oxford-3000", "oxford-5000", "awl-list", "opal-list"]):
            print(f"  {el.name}.{k}={v}")

# Look for 'More information' or 'Word Lists' headings
for h in soup.find_all(['h2', 'h3', 'h4', 'div', 'span']):
    txt = h.get_text(strip=True)
    if txt in ("More information", "Word Lists", "Word lists"):
        print("SEC:", h.name, h.get("class"), txt)

# Print everything after the entry
body = soup.find("body")
if body:
    children = list(body.descendants)
    print(f"Total descendants: {len(children)}")
