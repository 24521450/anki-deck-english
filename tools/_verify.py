"""Verify label examples."""
import json
with open(r'C:\Users\admin\Downloads\ielts-deck\data\oxford_labels.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
print("REGISTER LABELS:")
for r in data['register_labels']:
    print(f"  {r['name']:15} | {r['examples_given']}")
print()
print("USAGE RESTRICTIONS:")
for r in data['usage_restrictions']:
    print(f"  {r['name']:15} | {r['examples_given']}")
