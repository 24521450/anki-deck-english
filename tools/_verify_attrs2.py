"""Check all sense elements for opal/oxford/awl attributes."""
import re
from bs4 import BeautifulSoup

for w in ['rigorous', 'yield', 'aggregate', 'sick', 'paradigm']:
    with open(fr'C:\Users\admin\Downloads\ielts-deck\data\.cache_html\oxford_{w}.html', 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f.read(), 'lxml')
    print(f"=== {w} ===")
    # Walk entry, find h1 and all senses
    entry = soup.find(id='entryContent')
    h1 = entry.find('h1', class_='headword')
    # Aggregate attributes from h1
    if h1:
        for k, v in h1.attrs.items():
            if k in ('opal_written', 'opal_spoken', 'ox3000', 'ox5000', 'academic', 'awl', 'random'):
                print(f"  h1.{k}={v}")
    # Walk senses
    for sense in entry.find_all('li', class_='sense'):
        sid = sense.get('id', '')
        for k, v in sense.attrs.items():
            if k in ('opal_written', 'opal_spoken', 'ox3000', 'ox5000', 'academic', 'awl', 'random') and v == 'y':
                print(f"  sense({sid}).{k}={v}")
    print()
