"""Find Oxford 3000/5000/AWL list markers in word page."""
import re
from bs4 import BeautifulSoup

with open(r"C:\Users\admin\Downloads\ielts-deck\data\.cache_html\_inspect_rigorous.html", "r", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, "lxml")
entry = soup.find(id="entryContent")

# Look for hidden class="oxford-3000" or list-type attributes
for el in entry.find_all(True):
    cls = el.get("class") or []
    if any("oxford" in c.lower() for c in cls) or "ox3000" in str(el.attrs) or "ox5000" in str(el.attrs):
        print("OX class=", cls, "tag=", el.name, "text=", el.get_text(strip=True)[:120])

# Look for img inside the headword area
print("---")
head = entry.find(class_="head")
if head:
    for img in head.find_all("img"):
        print("HEAD IMG alt=", img.get("alt", ""), "src=", img.get("src", "")[-60:])
    for a in head.find_all("a"):
        href = a.get("href", "")
        if href and ("oxford" in href.lower() or "awl" in href.lower() or "opal" in href.lower() or "3000" in href or "5000" in href):
            print("HEAD A href=", href, "text=", a.get_text(strip=True)[:80])

# Look for any class with 'ox' or 'wordlist'
print("--- classes with 'ox' ---")
for el in entry.find_all(True, class_=re.compile(r"\box", re.I)):
    cls = " ".join(el.get("class", []))
    if any(k in cls.lower() for k in ["oxford", "ox_", "ox-", "ox3", "ox5", "oxl", "ox3k", "ox5k", "awl", "opal", "list-"]):
        print(cls, "|", el.name, "|", el.get_text(strip=True)[:100])

# Dump the head section html
print("--- head raw html (first 2000 chars) ---")
if head:
    print(str(head)[:2000])
