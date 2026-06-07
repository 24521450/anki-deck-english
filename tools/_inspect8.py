"""Look deeper at yield and aggregate."""
import requests
from bs4 import BeautifulSoup

for w in ['yield', 'aggregate']:
    r = requests.get(f'https://www.oxfordlearnersdictionaries.com/definition/english/{w}', headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
    soup = BeautifulSoup(r.text, 'lxml')
    entry = soup.find(id='entryContent')
    print(f"=== {w} ===")
    # All POS elements
    poss = [el.get_text(strip=True) for el in entry.find_all('span', class_='pos')]
    print(f"POS: {poss}")
    # Look for 'verb' or 'adjective' pos anywhere
    for cls in ['pos', 'verb', 'adjective']:
        cnt = len(entry.find_all(class_=cls))
        print(f"  class={cls}: {cnt} elements")
    # Look for multiple h1 headwords
    h1s = entry.find_all('h1', class_='headword')
    print(f"  H1 headwords: {len(h1s)} -> {[h.get_text(strip=True) for h in h1s]}")
    # Look for id containing _2, _3
    all_ids = set()
    for el in entry.find_all(id=True):
        iid = el.get('id', '')
        if '_' in iid:
            prefix = iid.rsplit('_', 1)[0]
            all_ids.add(prefix)
    print(f"  unique id prefixes: {sorted(all_ids)[:10]}")
    # Look for posg / pos block
    for el in entry.find_all(class_='posg'):
        print("  posg:", el.get_text(' ', strip=True)[:100])
    # Check entry groups
    entries = entry.find_all('div', class_='entry', attrs={'id': True})
    print(f"  div.entry: {len(entries)}")
    for e in entries:
        print(f"    entry id={e.get('id')}")
    print()
