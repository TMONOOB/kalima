"""Build Kalima's names list and write it into site/index.html.

Sources: the hand-written lists in names/curated_*.txt (17 most-spoken languages) and the CC0
popular-names-by-country dataset in names/pnbc. Names that are also everyday English words (they appear
written in lowercase at least 3 times in the corpus) are kept separately: the page only treats those
as names in the middle of a sentence.

usage: python3 build_names.py <names dir> <site dir>
"""
import collections, csv, glob, json, os, re, sys, unicodedata

names_dir, site = sys.argv[1:3]
latin = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿĀ-žḀ-ỿ'’-]+$")
names, by_lang = {}, collections.defaultdict(set)
for f in sorted(glob.glob(os.path.join(names_dir, 'curated_*.txt'))):
    lang = None
    for line in open(f, encoding='utf8'):
        if line.startswith('## '):
            lang = line[3:].strip(); continue
        for w in line.split():
            if latin.match(w) and len(w) >= 2:
                names.setdefault(w.lower(), w); by_lang[lang].add(w.lower())
for fn in ['common-forenames-by-country.csv', 'common-surnames-by-country.csv']:
    for r in csv.DictReader(open(os.path.join(names_dir, 'pnbc', fn), encoding='utf-8-sig')):
        for w in re.split(r'\s+', (r.get('Romanized Name') or '').strip()):
            if w and latin.match(w) and len(w) >= 2 and w[0].isupper():
                names.setdefault(w.lower(), w)
for n in list(names):  # accent-free spellings (José -> Jose)
    a = ''.join(c for c in unicodedata.normalize('NFD', n) if unicodedata.category(c) != 'Mn')
    if a != n and latin.match(a):
        names.setdefault(a, a)

low = collections.Counter()
for p in glob.glob(os.path.join(site, 'data', '*.txt')):
    for line in open(p, encoding='utf8'):
        if line[:1] == '#':
            continue
        f = line.rstrip('\n').split('\t')
        if len(f) > 1 and f[1] and f[1][0].islower():
            low[f[1].lower()] += 1
ambig = sorted(n for n in names if low[n] >= 3 or len(n) <= 2)
amb = set(ambig)
safe = sorted(n for n in names if n not in amb)

q = lambda xs: '|'.join(xs).replace('\\', '').replace("'", "\\'")
page_path = os.path.join(site, 'index.html')
page = open(page_path, encoding='utf8').read()
page, n1 = re.subn(r"const NAMES_ONLY = '[^\n]*';", lambda m: "const NAMES_ONLY = '" + q(safe) + "';", page, count=1)
page, n2 = re.subn(r"const NAMES_ALSO_WORDS = '[^\n]*';", lambda m: "const NAMES_ALSO_WORDS = '" + q(ambig) + "';", page, count=1)
if n1 != 1 or n2 != 1:
    raise SystemExit('names lines not found in index.html')
open(page_path, 'w', encoding='utf8').write(page)
print('names:', len(names), '| only names:', len(safe), '| also everyday words:', len(ambig))
print('hand-written per language:', {k: len(v) for k, v in by_lang.items()})
