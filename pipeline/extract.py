"""Extract UD English EWT and the openly licensed GUM genres into Kalima documents.

Output: one JSON file with, per document, its text (paragraphs separated by blank
lines), metadata for credits, and the hand-made gold labels with character offsets
so Kalima's own tagging can be scored against them.
"""
import glob, json, os, re, sys

EWT_DIR, GUM_DIR, OUT = sys.argv[1], sys.argv[2], sys.argv[3]

# GUM genres whose underlying texts carry a documented licence that allows
# redistribution, adaptation and commercial use (GUM LICENSE.md).
GUM_OPEN = {
    'academic':  ('academic', 'CC BY 4.0', 'https://creativecommons.org/licenses/by/4.0/'),
    'court':     ('conversation', 'CC BY 4.0', 'https://creativecommons.org/licenses/by/4.0/'),
    'news':      ('news', 'CC BY 2.5', 'https://creativecommons.org/licenses/by/2.5/'),
    'interview': ('conversation', 'CC BY 2.5', 'https://creativecommons.org/licenses/by/2.5/'),
    'bio':       ('web', 'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0/'),
    'voyage':    ('web', 'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0/'),
}
GUM_GENRE_NAME = {'academic': 'Academic paper', 'court': 'Court transcript', 'news': 'Wikinews',
                  'interview': 'Wikinews interview', 'bio': 'Wikipedia biography', 'voyage': 'Wikivoyage guide'}
EWT_TYPE = {'weblog': 'web', 'newsgroup': 'web', 'reviews': 'web', 'answers': 'web', 'email': 'work'}
EWT_GENRE_NAME = {'weblog': 'Blog', 'newsgroup': 'Newsgroup', 'reviews': 'Review', 'answers': 'Q&A answer', 'email': 'Email'}


def read_conllu(path):
    """Yield documents: dict(meta, paras=[[sent,...],...]); sent = dict(text, toks)."""
    doc = None
    cur_para = None
    sent = None
    with open(path, encoding='utf8') as fh:
        for line in fh:
            line = line.rstrip('\n')
            if line.startswith('# newdoc'):
                if doc: yield doc
                doc = {'id': line.split('=', 1)[1].strip(), 'meta': {}, 'paras': []}
                cur_para = None
                continue
            if line.startswith('# meta::') and doc is not None:
                k, v = line[8:].split(' = ', 1) if ' = ' in line else (line[8:], '')
                doc['meta'][k.strip()] = v.strip()
                continue
            if re.match(r'# newpar(\b| |$)', line) and not line.startswith('# newpar_block'):
                cur_para = []
                doc['paras'].append(cur_para)
                continue
            if line.startswith('# text = '):
                sent = {'text': line[9:], 'toks': []}
                if cur_para is None:
                    cur_para = []
                    doc['paras'].append(cur_para)
                cur_para.append(sent)
                continue
            if not line:
                sent = None
                continue
            if line.startswith('#') or sent is None:
                continue
            cols = line.split('\t')
            if len(cols) != 10 or not cols[0].isdigit():
                continue  # multiword ranges and empty nodes
            sent['toks'].append((cols[1], cols[3], cols[4], cols[5], cols[2]))
    if doc: yield doc


def assemble(doc):
    """Build text and gold offsets. Returns (text, gold, words, unfound)."""
    parts, gold, off, unfound = [], [], 0, 0
    sn = -1
    paras = [p for p in doc['paras'] if p]
    for pi, para in enumerate(paras):
        if pi:
            parts.append('\n\n'); off += 2
        for si, s in enumerate(para):
            if si:
                parts.append(' '); off += 1
            text = s['text'].replace('\t', ' ')
            sn += 1
            cur = 0
            for form, upos, xpos, feats, lemma in s['toks']:
                k = text.find(form, cur)
                if k < 0 or k - cur > 40:
                    unfound += 1
                    gold.append([-1, -1, upos, xpos, feats, lemma, sn])
                    continue
                gold.append([off + k, off + k + len(form), upos, xpos, feats, lemma, sn])
                cur = k + len(form)
            parts.append(text); off += len(text)
    return ''.join(parts), gold, unfound


def first_sentence_title(text, limit=72):
    s = re.split(r'(?<=[.!?])\s', text.strip(), maxsplit=1)[0].replace('\n', ' ')
    s = re.sub(r'\s+', ' ', s).strip()
    if len(s) <= limit:
        return s
    cut = s[:limit].rsplit(' ', 1)[0]
    return cut.rstrip(',;:-') + '…'


docs = []
stats = {'ewt_unfound': 0, 'gum_unfound': 0}

for split in ('train', 'dev', 'test'):
    for d in read_conllu(os.path.join(EWT_DIR, f'en_ewt-ud-{split}.conllu')):
        genre = d['id'].split('-', 1)[0]
        text, gold, unf = assemble(d)
        stats['ewt_unfound'] += unf
        if not text.strip():
            continue
        docs.append({
            'col': 'ewt', 'id': d['id'], 'genre': genre, 'split': split,
            'title': first_sentence_title(text),
            'type': EWT_TYPE.get(genre, 'web'), 'region': 'intl',
            'source': f"UD English EWT · {EWT_GENRE_NAME.get(genre, genre)} · CC BY-SA 4.0",
            'lic': 'CC BY-SA 4.0', 'licUrl': 'https://creativecommons.org/licenses/by-sa/4.0/',
            'text': text, 'gold': gold,
        })

skipped = {}
for path in sorted(glob.glob(os.path.join(GUM_DIR, 'GUM_*.conllu'))):
    genre = os.path.basename(path).split('_')[1]
    if genre not in GUM_OPEN:
        skipped[genre] = skipped.get(genre, 0) + 1
        continue
    for d in read_conllu(path):
        typ, lic, licurl = GUM_OPEN[genre]
        text, gold, unf = assemble(d)
        stats['gum_unfound'] += unf
        m = d['meta']
        if 'santa-barbara' in m.get('sourceURL', ''):
            # Santa Barbara Corpus material: GUM's licence file gives no licence for it
            skipped['court (Santa Barbara Corpus)'] = skipped.get('court (Santa Barbara Corpus)', 0) + 1
            continue
        author = m.get('author', '').strip()
        docs.append({
            'col': 'gum', 'id': d['id'], 'genre': genre,
            'title': m.get('title') or first_sentence_title(text),
            'type': typ, 'region': 'intl',
            'source': ' · '.join(x for x in [author, GUM_GENRE_NAME[genre], lic, 'via GUM'] if x),
            'author': author, 'url': m.get('sourceURL', ''),
            'lic': lic, 'licUrl': licurl,
            'text': text, 'gold': gold,
        })

json.dump({'docs': docs, 'stats': stats, 'gumSkipped': skipped}, open(OUT, 'w', encoding='utf8'), ensure_ascii=False)
by = {}
for d in docs:
    k = (d['col'], d['genre'])
    by.setdefault(k, [0, 0]); by[k][0] += 1; by[k][1] += sum(1 for g in d['gold'] if g[2] != 'PUNCT')
for k in sorted(by): print(k, 'docs', by[k][0], 'non-punct tokens', by[k][1])
print('totals docs', len(docs), 'non-punct', sum(v[1] for v in by.values()))
print('stats', stats, 'gum skipped genres', skipped)
