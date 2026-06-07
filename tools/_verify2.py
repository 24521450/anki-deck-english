"""Verify sample extraction."""
import json
with open(r'C:\Users\admin\Downloads\ielts-deck\data\oxford_samples.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
for s in data['samples']:
    print('---', s['word'], '---')
    print(f"  cefr: {s['cefr']}")
    print(f"  pos: {s['pos']}")
    print(f"  register_tags: {s['register_tags']}")
    print(f"  subject_labels: {s['subject_labels']}")
    print(f"  oxford_lists: {s['oxford_lists']}")
    print(f"  opal: {s['opal']}")
    print(f"  awl: {s['awl']}")
    print(f"  definitions: {len(s['definitions'])}")
    print(f"  word_family: {s['word_family']}")
    print()
