import re
from bs4 import BeautifulSoup

path = r"C:\Users\admin\.gemini\antigravity-ide\brain\6bb3f673-6771-4a6b-b482-7c6e15c53395\.system_generated\steps\334\content.md"
with open(path, "r", encoding="utf-8") as f:
    text = f.read()

soup = BeautifulSoup(text, "lxml")

print("=== epp-xref elements ===")
for el in soup.find_all(class_=re.compile(r"epp-xref")):
    print(el, el.get_text(strip=True))

print("=== all spans/divs with any text like A2/C2 ===")
for el in soup.find_all(["span", "div"]):
    t = el.get_text(strip=True)
    if t in {"A1", "A2", "B1", "B2", "C1", "C2"}:
        print(el)
