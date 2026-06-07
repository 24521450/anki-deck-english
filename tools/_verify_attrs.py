"""Check all 5 word pages for opal* / ox* attributes on h1 and elsewhere."""
import re
from bs4 import BeautifulSoup

for w in ['rigorous', 'yield', 'aggregate', 'sick', 'paradigm']:
    with open(fr'C:\Users\admin\Downloads\ielts-deck\data\.cache_html\oxford_{w}.html', 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f.read(), 'lxml')
    print(f"=== {w} ===")
    # h1 attrs
    h1 = soup.find('h1', class_='headword')
    if h1:
        print(f"  h1 attrs: {dict(h1.attrs)}")
    # Any element with opal* or ox* attribute (not ox5000 class)
    for el in soup.find_all(True):
        for attr_name in el.attrs:
            if attr_name in ('opal_written', 'opal_spoken', 'ox3000', 'ox5000', 'awl', 'oxford3000', 'oxford5000'):
                print(f"  {el.name} ({' '.join(el.get('class', []))}).{attr_name}={el.attrs[attr_name]} text={el.get_text(strip=True)[:60]!r}")
    # Also look for class containing ox5000 etc
    for el in soup.find_all(class_=True):
        cls = ' '.join(el.get('class', []))
        if 'ox5000' in cls.lower() or 'ox3000' in cls.lower() or 'opal_' in cls.lower():
            print(f"  class {el.name}={cls!r} text={el.get_text(strip=True)[:60]!r}")
    print()
