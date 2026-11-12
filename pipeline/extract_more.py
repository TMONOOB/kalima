"""Extract public-domain books (GITenberg mirrors) and UD English PUD into Kalima documents.

usage: python3 extract_more.py <books dir> <pud conllu> <out json>
"""
import json, os, re, sys

# Re-use the EWT/GUM parsing functions from extract.py without running its main code.
_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'extract.py'), encoding='utf8').read()
exec(_src[_src.index('def read_conllu'):_src.index('\ndocs = []')])

BOOKS_DIR, PUD_FILE, OUT = sys.argv[1:4]

# folder -> (title, author, first published, author died, region)
BOOKS = {
    'Pride-and-Prejudice_1342': ('Pride and Prejudice', 'Jane Austen', 1813, 1817, 'uk'),
    'The-Adventures-of-Sherlock-Holmes_1661': ('The Adventures of Sherlock Holmes', 'Arthur Conan Doyle', 1892, 1930, 'uk'),
    'Anne-of-Green-Gables_45': ('Anne of Green Gables', 'L. M. Montgomery', 1908, 1942, 'intl'),
    'The-Secret-Garden_113': ('The Secret Garden', 'Frances Hodgson Burnett', 1911, 1924, 'uk'),
    'The-Adventures-of-Tom-Sawyer_74': ('The Adventures of Tom Sawyer', 'Mark Twain', 1876, 1910, 'intl'),
    'Treasure-Island_120': ('Treasure Island', 'Robert Louis Stevenson', 1883, 1894, 'uk'),
    'Black-Beauty_271': ('Black Beauty', 'Anna Sewell', 1877, 1878, 'uk'),
    'The-Jungle-Book_236': ('The Jungle Book', 'Rudyard Kipling', 1894, 1936, 'uk'),
    'The-Wonderful-Wizard-of-Oz_55': ('The Wonderful Wizard of Oz', 'L. Frank Baum', 1900, 1919, 'intl'),
    'The-Time-Machine_35': ('The Time Machine', 'H. G. Wells', 1895, 1946, 'uk'),
    'The-Call-of-the-Wild_215': ('The Call of the Wild', 'Jack London', 1903, 1916, 'intl'),
    'Alice-s-Adventures-in-Wonderland_11': ('Alice’s Adventures in Wonderland', 'Lewis Carroll', 1865, 1898, 'uk'),
}
PART_WORDS = 6000
HEADING = re.compile(r"^(chapter|adventure|book|part|stave)\b|^[IVXLC]+\.?(\s|$)", re.I)


def words(s):
    return len(re.findall(r"[^\W_]+(?:['’][^\W_]+)?", s))


def book_paragraphs(path):
    raw = open(path, encoding='utf-8', errors='replace').read().replace('\r\n', '\n').replace('\r', '\n')
    lines = raw.split('\n')
    start = next(i for i, l in enumerate(lines) if re.match(r'\*\*\* ?START OF', l))
    end = next(i for i, l in enumerate(lines) if i > start and (re.match(r'\*\*\* ?END OF', l) or re.match(r'End of (the )?Project Gutenberg', l, re.I)))
    body = '\n'.join(lines[start + 1:end])
    paras = []
    for block in re.split(r'\n\s*\n', body):
        p = ' '.join(x.strip() for x in block.split('\n') if x.strip())
        if not p:
            continue
        if re.match(r'(produced by|e-text prepared by|transcriber|\[illustration)', p, re.I):
            continue
        p = re.sub(r'\[Illustration[^\]]*\]', '', p)
        p = re.sub(r'(?<![\w])_([^_]+)_(?![\w])', r'\1', p)   # _italics_ markers
        p = p.replace('_', '')
        p = re.sub(r'\s+', ' ', p).strip()
        if p and re.search(r'[A-Za-z]', p):
            paras.append(p)
    return paras


docs = []
for folder, (title, author, year, died, region) in BOOKS.items():
    d = os.path.join(BOOKS_DIR, folder)
    txt = sorted(f for f in os.listdir(d) if re.fullmatch(r'\d+(-0)?\.txt', f))[0]
    paras = book_paragraphs(os.path.join(d, txt))
    parts, cur, cw = [], [], 0
    for p in paras:
        w = words(p)
        is_head = len(p) < 80 and w <= 12 and HEADING.search(p) is not None
        if cur and ((is_head and cw >= PART_WORDS * 0.6) or cw + w > PART_WORDS * 1.5):
            parts.append(cur); cur, cw = [], 0
        cur.append(p); cw += w
    if cur:
        if parts and cw < PART_WORDS * 0.3:
            parts[-1].extend(cur)
        else:
            parts.append(cur)
    book_id = folder.rsplit('_', 1)[1]
    for i, part in enumerate(parts, 1):
        docs.append({
            'col': 'books', 'id': f'pg{book_id}-{i:02d}', 'genre': f'pg{book_id}',
            'title': f'{title} · part {i} of {len(parts)}',
            'type': 'fiction', 'region': region,
            'source': f'{author}, {title} ({year}) · public domain',
            'author': author, 'lic': 'Public domain', 'licUrl': '',
            'text': '\n\n'.join(part), 'gold': [],
        })
    print(f'{title}: {len(parts)} parts, {sum(words(p) for p in paras):,} words')

pud_docs = 0
for d in read_conllu(PUD_FILE):
    text, gold, unf = assemble(d)
    if not text.strip():
        continue
    kind = 'news' if d['id'].startswith('n') else 'web'
    docs.append({
        'col': 'pud', 'id': d['id'], 'genre': kind,
        'title': first_sentence_title(text), 'type': kind, 'region': 'intl',
        'source': 'UD English PUD · ' + ('News' if kind == 'news' else 'Wikipedia') + ' · CC BY-SA 3.0',
        'lic': 'CC BY-SA 3.0', 'licUrl': 'https://creativecommons.org/licenses/by-sa/3.0/',
        'text': text, 'gold': gold,
    })
    pud_docs += 1
print('PUD docs', pud_docs, 'words', sum(words(x['text']) for x in docs if x['col'] == 'pud'))
json.dump({'docs': docs, 'books': {k.rsplit('_', 1)[1]: v for k, v in BOOKS.items()}}, open(OUT, 'w', encoding='utf8'), ensure_ascii=False)
print('total new docs', len(docs), 'words', sum(words(x['text']) for x in docs))
