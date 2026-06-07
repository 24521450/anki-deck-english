"""Inspect the rigorous word page HTML to find selectors."""
import re
from bs4 import BeautifulSoup

with open(r"C:\Users\admin\Downloads\ielts-deck\data\.cache_html\_inspect_rigorous.html", "r", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, "lxml")

# Find the entry container
entry = soup.find(id="entryContent")
print("entryContent found:", entry is not None)
if entry:
    # Find headword area
    head = entry.find(class_="head")
    if head:
        print("--- head ---")
        print(head.get_text(" ", strip=True))
    # POS spans
    for el in entry.find_all("span", class_="pos"):
        print("POS:", el.get_text(strip=True))
    # CEFR / list markers — look for <a> or <span> with class containing 'oxford-3000' or similar
    for el in entry.find_all(True, attrs={"class": True}):
        cls = " ".join(el.get("class", []))
        if any(k in cls for k in ["oxford-3000", "oxford-5000", "ox3", "ox5", "awl", "opal", "cefr", "symbols", "list"]):
            print("LIST-MARKER class=", cls, "| tag=", el.name, "| text=", el.get_text(strip=True)[:80])

    # Look for any element that has a class indicating list membership
    for el in entry.find_all(True, attrs={"href": True}):
        href = el.get("href", "")
        if any(k in href for k in ["oxford-3000", "oxford-5000", "awl", "opal", "cefr"]):
            print("LINK href=", href, "| text=", el.get_text(strip=True)[:80])
    # Phonet
    for el in entry.find_all("span", class_=re.compile(r"phon")):
        print("PHON class=", " ".join(el.get("class", [])), "| text=", el.get_text(strip=True))

    # senses
    print("--- senses ---")
    for li in entry.find_all("li", class_="sense"):
        attrs = dict(li.attrs)
        text = li.get_text(" ", strip=True)[:160]
        print("sense attrs=", {k: v for k, v in attrs.items() if k in ("sensenum", "cefr", "id", "htag", "hclass")}, "| text=", text)
