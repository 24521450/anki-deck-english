"""Look for verb tabs or alternate forms for yield/aggregate."""
import requests, re
from bs4 import BeautifulSoup

for w in ['yield', 'aggregate']:
    r = requests.get(f'https://www.oxfordlearnersdictionaries.com/definition/english/{w}', headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
    soup = BeautifulSoup(r.text, 'lxml')
    print(f"=== {w} ===")
    # Look for any verb mention
    if 'verb' in r.text.lower():
        for m in re.finditer(r'verb', r.text, re.IGNORECASE):
            s = max(0, m.start() - 80)
            e = min(len(r.text), m.end() + 120)
            print(f"   ...{r.text[s:e]}...")
            break
    # Find all senses
    senses = soup.find_all('li', class_='sense')
    print(f"  senses: {len(senses)}")
    # Look for 'Idioms'
    if 'Idioms' in r.text:
        idx = r.text.find('Idioms')
        print(f"  'Idioms' at {idx}: ...{r.text[idx-50:idx+200]}...")
    # Find 'related entries' section
    if 'relatedentries' in r.text:
        idx = r.text.find('relatedentries')
        print(f"  relatedentries at {idx}: ...{r.text[idx:idx+400]}...")
    print()
