"""Look for fkox3000/fkox5000/fkcefr/fkawl/fkopal attributes."""
import re
import requests
from bs4 import BeautifulSoup

for w in ['yield', 'aggregate', 'sick', 'paradigm', 'rigorous']:
    r = requests.get(f'https://www.oxfordlearnersdictionaries.com/definition/english/{w}', headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
    soup = BeautifulSoup(r.text, 'lxml')
    print(f"=== {w} ===")
    # Find all sense elements
    for sense in soup.find_all('li', class_='sense'):
        fk_attrs = {k: v for k, v in sense.attrs.items() if k.startswith('fk')}
        cefr = sense.get('cefr')
        sensenum = sense.get('sensenum')
        def_span = sense.find('span', class_='def')
        def_txt = def_span.get_text(' ', strip=True)[:60] if def_span else ''
        print(f"  sense#{sensenum} cefr={cefr} fk_attrs={fk_attrs} def={def_txt!r}")
    # Also at the entry level
    for entry in soup.find_all('div', class_='entry'):
        fk_attrs = {k: v for k, v in entry.attrs.items() if k.startswith('fk')}
        print(f"  entry#{entry.get('id')} fk_attrs={fk_attrs}")
    print()
