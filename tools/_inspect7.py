"""Inspect word page structure for definitions, examples, register tags, subjects, word family."""
import re
from bs4 import BeautifulSoup

with open(r"C:\Users\admin\Downloads\ielts-deck\data\.cache_html\_inspect_rigorous.html", "r", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, "lxml")
entry = soup.find(id="entryContent")
if not entry:
    print("No entryContent")
    raise SystemExit

# Senses — show full structure
print("--- senses (rigorous) ---")
for li in entry.find_all("li", class_="sense"):
    attrs = {k: v for k, v in li.attrs.items() if k in ("sensenum", "cefr", "id")}
    print("SENSE", attrs)
    # definition
    def_span = li.find("span", class_="def")
    if def_span:
        print("  DEF:", def_span.get_text(" ", strip=True))
    # examples
    examples = li.find_all("span", class_="x")
    for ex in examples:
        print("  EX:", ex.get_text(" ", strip=True)[:200])
    # synonyms
    syn = li.find(class_="synonyms")
    if syn:
        print("  SYN:", syn.get_text(" ", strip=True)[:100])
    # labels inside sense
    for span in li.find_all("span", class_="labels"):
        print("  LABELS:", span.get_text(" ", strip=True)[:100])
    # register / topic in definfo
    for span in li.find_all("span", class_="definfo"):
        print("  DEFINFO:", span.get_text(" ", strip=True)[:100])

# Word family
print("--- word family ---")
wf = entry.find(class_="wordfamily")
if wf:
    print(wf.get_text(" ", strip=True)[:300])
# Derivative box
for u in entry.find_all("span", class_=re.compile("derivat|word_fam|wf")):
    print("WF:", u.get_text(" ", strip=True)[:200])

# Other POS sections — each pos in its own entry?
entries = entry.find_all(class_="entry")
print(f"Total entries: {len(entries)}")
for e in entries:
    pos = e.find("span", class_="pos")
    print("ENTRY pos=", pos.get_text(strip=True) if pos else "?", "id=", e.get("id"))
