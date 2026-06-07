"""Look for additional senses for yield/aggregate — maybe loaded via JS or in unbox."""
import requests
from bs4 import BeautifulSoup

for w in ['yield', 'aggregate']:
    r = requests.get(f'https://www.oxfordlearnersdictionaries.com/definition/english/{w}', headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
    soup = BeautifulSoup(r.text, 'lxml')
    entry = soup.find(id='entryContent')
    print(f"=== {w} === entry children:")
    for child in entry.find_all(recursive=False):
        cid = child.get('id', '')[:40]
        cls = ' '.join(child.get('class', []))[:60]
        # text length
        txt = child.get_text(' ', strip=True)[:80]
        print(f"  <{child.name}> id={cid!r} class={cls!r} text={txt!r}")
    print()
