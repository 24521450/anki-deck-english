"""Investigate the verifier's two specific claims:
1. yield's <h1> has opal_written='y' attribute
2. sick has sense section that restarts numbering (e.g. senses 15-16 use sensenum=1,2)
"""
import re
from bs4 import BeautifulSoup

# 1. Yield: check h1 for opal_written
with open(r'C:\Users\admin\Downloads\ielts-deck\data\.cache_html\oxford_yield.html', 'r', encoding='utf-8') as f:
    soup = BeautifulSoup(f.read(), 'lxml')

print("=== yield: <h1> and headword area ===")
h1 = soup.find('h1', class_='headword')
if h1:
    print('h1 attrs:', dict(h1.attrs))
    # Check the entry/parent
    entry = soup.find(id='entryContent')
    if entry:
        # Look for opal attribute anywhere
        for el in entry.find_all(True):
            for k, v in el.attrs.items():
                sv = str(v)
                if 'opal' in sv.lower() or k in ('opal_written', 'opal_spoken', 'opal', 'fkopalspoken', 'fkopalwritten'):
                    print(f"  {el.name}.{k}={v} (text: {el.get_text(strip=True)[:60]!r})")
                    break
    # Look at the webtop area
    webtop = soup.find('div', class_='webtop')
    if webtop:
        print('webtop attrs:', dict(webtop.attrs))
        print('webtop text:', webtop.get_text(' ', strip=True)[:200])

# Also check headword parent — the OPAL icon might be a sibling
print()
print("=== yield: look for opal_written attribute on any element ===")
for el in soup.find_all(True):
    if 'opal' in el.attrs:
        print(f"  {el.name} class={' '.join(el.get('class', []))} opal attrs: {dict(el.get('opal_written', None))}")

# 2. Sick: examine the structure around sense 15-16
print()
print("=== sick: sense structure ===")
with open(r'C:\Users\admin\Downloads\ielts-deck\data\.cache_html\oxford_sick.html', 'r', encoding='utf-8') as f:
    sick_soup = BeautifulSoup(f.read(), 'lxml')

senses = sick_soup.find_all('li', class_='sense')
print(f'total senses: {len(senses)}')
for i, s in enumerate(senses):
    sid = s.get('id', '')
    sn = s.get('sensenum', '?')
    cefr = s.get('cefr', '')
    fkcefr = s.get('fkcefr', '')
    def_span = s.find('span', class_='def')
    def_txt = def_span.get_text(' ', strip=True)[:50] if def_span else ''
    # Find parent OL or section
    parent = s.find_parent(['ol', 'div'])
    parent_id = parent.get('id', '') if parent else ''
    parent_class = ' '.join(parent.get('class', [])) if parent else ''
    print(f"  {i:2}: id={sid!r:25} sensenum={sn!r:5} cefr={cefr!r:5} fkcefr={fkcefr!r:5} parent_id={parent_id!r:25} parent_class={parent_class!r:25} def={def_txt!r}")
