"""Merge the extracted collections into one file and mark which texts are for training and which for testing.

EWT keeps its official train/dev/test split; GUM uses the split in its splits.md; PUD is test-only;
the books have no hand-checked labels and are only tagged, never scored.

usage: python3 merge_docs.py <docs.json> <docs_more.json> <gum splits.md> <out docs_all.json>
"""
import json, re, sys
from collections import Counter

a_path, b_path, splits_path, out = sys.argv[1:5]
a = json.load(open(a_path, encoding='utf8'))
b = json.load(open(b_path, encoding='utf8'))
split, cur = {}, None
for line in open(splits_path, encoding='utf8'):
    m = re.match(r'## (\w+)', line)
    if m:
        cur = m.group(1); continue
    m = re.match(r'\s*\*\s*(GUM_\S+)', line)
    if m:
        split[m.group(1)] = cur
for d in a['docs']:
    if d['col'] == 'gum':
        d['split'] = split.get(d['id'], 'train')
for d in b['docs']:
    if d['col'] == 'pud':
        d['split'] = 'test'
docs = a['docs'] + b['docs']
json.dump({'docs': docs}, open(out, 'w', encoding='utf8'), ensure_ascii=False)
print(len(docs), 'texts:', dict(Counter((d['col'], d.get('split', '-')) for d in docs)))
