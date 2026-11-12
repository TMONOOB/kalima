"""Write the latest figures into site/index.html, then refresh the offline cache name in site/sw.js.

- ACCURACY: the test scores from train.js (build/model.scores.json)
- PACK_WORDS: the number of words in the data files (build/packs/accuracy.json from tag_and_score.js)
- BOOK_LIST: the books and their details (build/docs_more.json from extract_more.py)

Run it after any change to the site, even with no arguments except the site folder, so visitors'
phones pick up the new version:  python3 update_page.py <site dir> [build dir]
"""
import hashlib, json, os, re, sys

site = sys.argv[1]
build = sys.argv[2] if len(sys.argv) > 2 else None
page_path = os.path.join(site, 'index.html')
page = open(page_path, encoding='utf8').read()


def set_const(src, name, value_js):
    out, n = re.subn(r'const ' + name + r' = [^\n]*;', lambda m: 'const ' + name + ' = ' + value_js + ';', src, count=1)
    if n != 1:
        raise SystemExit(name + ' not found in index.html')
    return out


if build:
    P = ['noun', 'verb', 'adj', 'adv', 'pron', 'prep', 'det', 'conj', 'num', 'other']
    sc_path = os.path.join(build, 'model.scores.json')
    if os.path.exists(sc_path):
        sc = json.load(open(sc_path, encoding='utf8'))
        mix = []
        for c in sc['ewt_test']['confusions'][:6]:
            a, b = c['pair'].split(' -> ')
            mix.append([P.index(a), P.index(b), c['n'], ', '.join(c['examples'][:4])])
        acc = {'date': sc.get('date', ''), 'test': {'n': sc['ewt_test']['n'], 'acc': sc['ewt_test']['acc']},
               'gum': {'n': sc['gum_test']['n'], 'acc': sc['gum_test']['acc']}, 'pud': {'n': sc['pud']['n'], 'acc': sc['pud']['acc']},
               'byType': [sc['ewt_test']['byClass'][k]['recall'] for k in P], 'mix': mix, 'trainWords': sc.get('trainWords', 0)}
        page = set_const(page, 'ACCURACY', json.dumps(acc, ensure_ascii=False))
        print('accuracy on new EWT text:', acc['test']['acc'], '%')
    pk_path = os.path.join(build, 'packs', 'accuracy.json')
    if os.path.exists(pk_path):
        words = sum(json.load(open(pk_path, encoding='utf8'))['kalimaWords'].values())
        page = set_const(page, 'PACK_WORDS', str(words))
        print('words in data files:', words)
    dm_path = os.path.join(build, 'docs_more.json')
    if os.path.exists(dm_path):
        page = set_const(page, 'BOOK_LIST', json.dumps(json.load(open(dm_path, encoding='utf8'))['books'], ensure_ascii=False))
open(page_path, 'w', encoding='utf8').write(page)

# offline cache name = a fingerprint of every site file, so phones fetch the new version
h = hashlib.sha256()
for root, _, files in sorted(os.walk(site)):
    for f in sorted(files):
        if f != 'sw.js':
            h.update(open(os.path.join(root, f), 'rb').read())
sw_path = os.path.join(site, 'sw.js')
sw = open(sw_path, encoding='utf8').read()
sw, n = re.subn(r"const VERSION = '[^']*';", "const VERSION = 'kalima-" + h.hexdigest()[:12] + "';", sw, count=1)
if n != 1:
    raise SystemExit('VERSION not found in sw.js')
open(sw_path, 'w', encoding='utf8').write(sw)
print('offline cache name: kalima-' + h.hexdigest()[:12])
