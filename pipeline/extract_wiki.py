"""Turn Wikimedia dumps (Wikinews, Wikivoyage, Simple English Wikipedia) into Kalima documents.

usage: python3 extract_wiki.py <dumps dir> <out json> [words per project, e.g. news=400000,voyage=250000,simple=350000]

The dumps dir holds enwikinews.xml.bz2, enwikivoyage.xml.bz2 and simplewiki.xml.bz2, downloaded from
https://dumps.wikimedia.org/<project>/latest/<project>-latest-pages-articles.xml.bz2

Only running prose is kept: tables, lists, infoboxes, references, image captions and "See also" style
sections are dropped, and so is any paragraph that still looks like markup or is too short to be a
sentence. Texts about Saudi Arabia, the Gulf, Egypt and the Levant are taken first; the rest is a fixed
random sample, so a rebuild gives the same texts.
"""
import bz2, json, os, random, re, sys, urllib.parse
import xml.etree.ElementTree as ET
from collections import Counter

DUMPS, OUT = sys.argv[1:3]
TARGET = {'news': 400000, 'voyage': 250000, 'simple': 350000}
if len(sys.argv) > 3:
    for kv in sys.argv[3].split(','):
        k, v = kv.split('=')
        TARGET[k] = int(v)

PROJECTS = {
    'news': dict(file='enwikinews.xml.bz2', site='https://en.wikinews.org/wiki/', type='news', name='Wikinews',
                 lic='CC BY 2.5', licUrl='https://creativecommons.org/licenses/by/2.5/', min_words=120, max_words=2500),
    'voyage': dict(file='enwikivoyage.xml.bz2', site='https://en.wikivoyage.org/wiki/', type='web', name='Wikivoyage',
                   lic='CC BY-SA 4.0', licUrl='https://creativecommons.org/licenses/by-sa/4.0/', min_words=200, max_words=2500),
    'simple': dict(file='simplewiki.xml.bz2', site='https://simple.wikipedia.org/wiki/', type='academic', name='Simple English Wikipedia',
                   lic='CC BY-SA 4.0', licUrl='https://creativecommons.org/licenses/by-sa/4.0/', min_words=500, max_words=2500),
}

# Places that decide a text's region. Matched against Wikinews/Wikipedia categories and Wikivoyage's IsPartOf chain.
REGION_PLACES = {
    'saudi': ['Saudi Arabia', 'Riyadh', 'Jeddah', 'Mecca', 'Makkah', 'Medina', 'Dammam', 'Saudi'],
    'gulf': ['United Arab Emirates', 'Dubai', 'Abu Dhabi', 'Qatar', 'Doha', 'Bahrain', 'Kuwait', 'Oman', 'Muscat', 'Sharjah'],
    'egypt': ['Egypt', 'Cairo', 'Alexandria', 'Luxor', 'Aswan', 'Giza', 'Sinai'],
    'levant': ['Jordan', 'Amman', 'Lebanon', 'Beirut', 'Syria', 'Damascus', 'Palestinian territories', 'Palestine', 'Gaza', 'West Bank'],
    'uk': ['United Kingdom', 'England', 'Scotland', 'Wales', 'Northern Ireland', 'London'],
}
PLACE_REGION = {p.lower(): r for r, ps in REGION_PLACES.items() for p in ps}
REGION_RANK = {'saudi': 0, 'gulf': 1, 'egypt': 2, 'levant': 3}

DROP_SECTIONS = re.compile(r'^(references?|notes?|sources?|external links?|see also|related( news| articles)?|further reading|'
                           r'bibliography|footnotes|citations|gallery|other websites|related pages|interviews?|sister links)$', re.I)
VOYAGE_DROP = re.compile(r'^(go next|stay safe|stay healthy|connect|cope|respect|get around|buy|eat|drink|sleep|learn|work|'
                         r'by (plane|train|bus|car|boat|ship|ferry|road|air|taxi|bike|bicycle|foot)|on foot)$', re.I)
# Wikivoyage's practical sections are mostly listings (names, prices, phone numbers), so only its descriptive
# sections are kept: the opening, Understand, See, Do, Get in, Talk and the like.

DROP_TAGS = r'ref|gallery|math|chem|code|syntaxhighlight|source|pre|timeline|score|hiero|imagemap|graph|mapframe|maplink|templatedata|poem|references|div|table|noinclude|includeonly'
# Kalima is used in classrooms: leave out texts with swearing, slurs or sexual content.
UNSUITABLE = re.compile(r"\b(fuck\w*|shit|shits|shitty|shitshow|bullshit|cunt\w*|bitch\w*|nigger\w*|motherf\w*|porn\w*|"
                        r"sex|sexy|sexual\w*|sexually|erotic\w*|prostitut\w*|nude|nudity|naked|rape\w*|raping|masturbat\w*|orgasm\w*)\b", re.I)
WORD = re.compile(r"[^\W_]+(?:['’][^\W_]+)?")


def words(s):
    return len(WORD.findall(s))


def strip_balanced(s, open_, close, keep=None):
    """Remove every outermost open_...close span (nesting aware). keep(inner) may return replacement text."""
    out, i, n = [], 0, len(s)
    lo, lc = len(open_), len(close)
    while i < n:
        j = s.find(open_, i)
        if j < 0:
            out.append(s[i:]); break
        out.append(s[i:j])
        depth, k = 1, j + lo
        while k < n and depth:
            if s.startswith(open_, k): depth += 1; k += lo
            elif s.startswith(close, k): depth -= 1; k += lc
            else: k += 1
        if keep:
            out.append(keep(s[j + lo:k - lc]))
        i = k
    return ''.join(out)


KEEP_TEMPLATES = {'w', 'wp', 'wikipedia', 'wikt', 'wiktionary', 'nowrap', 'nobr', 'small', 'smaller', 'big', 'lang', 'transl',
                  'ill', 'interlanguage link', 'iast', 'nowiki', 'sic', 'abbr', 'em', 'strong', 'vanchor', 'anchor', 'linktext'}


def template_text(inner):
    """The words a reader sees for the templates that wrap ordinary text ({{w|Riyadh}}, {{convert|5|km}}); nothing for the rest."""
    inner = strip_balanced(inner, '{{', '}}', template_text)
    parts = [x.strip() for x in inner.split('|')]
    name = parts[0].lower().replace('_', ' ').strip()
    args = [x for x in parts[1:] if not re.match(r'^[\w -]+=', x)]
    if name in ('convert', 'cvt') and len(args) >= 2:
        return args[0] + ' ' + args[1]
    if name in ('lang', 'transl') and len(args) >= 2:
        return args[-1]
    if name in ('ill', 'interlanguage link') and args:
        return args[0]
    if name in KEEP_TEMPLATES and args:
        return args[-1] if name in ('w', 'wp', 'wikipedia', 'wikt', 'wiktionary') else args[0]
    return ''


def link_text(inner):
    t = inner.split('|')
    target = t[0].strip()
    m = re.match(r'\s*:?\s*([a-z-]+)\s*:(.*)$', target, re.I)
    if m:
        prefix = m.group(1).lower()
        if prefix in ('file', 'image', 'media', 'category', 'commons'):
            return ''
        if len(t) == 1 and re.fullmatch(r'[a-z]{2,3}(-[a-z]+)?', prefix) and not target.startswith(':'):
            return ''                                        # interlanguage link at the foot of a page
        target = m.group(2) if prefix in ('w', 'wikipedia', 'wikt', 'wiktionary', 'n', 'wikinews', 'voy', 's', 'q', 'b', 'simple', 'en') or re.fullmatch(r'[a-z]{2,3}', prefix) else target
    label = (t[-1] if len(t) > 1 else target).strip()
    return re.sub(r'#.*$', '', label) if len(t) == 1 else label


def clean_wikitext(src):
    s = src
    s = re.sub(r'<!--.*?-->', '', s, flags=re.S)
    s = re.sub(r'<(' + DROP_TAGS + r')\b[^>]*/>', '', s, flags=re.I)
    s = re.sub(r'<(' + DROP_TAGS + r')\b[^>]*>.*?</\1\s*>', '', s, flags=re.I | re.S)
    s = strip_balanced(s, '{|', '|}')
    s = strip_balanced(s, '[[', ']]', link_text)
    s = strip_balanced(s, '{{', '}}', template_text)
    s = re.sub(r'\[(?:https?:)?//[^\s\]]+\s+([^\]]*)\]', r'\1', s)
    s = re.sub(r'\[(?:https?:)?//[^\]]*\]', '', s)
    s = re.sub(r'https?://\S+', '', s)
    s = re.sub(r"'{2,}", '', s)
    s = re.sub(r'</?[a-zA-Z][^>]*>', '', s)
    s = s.replace('&nbsp;', ' ').replace('&ndash;', '–').replace('&mdash;', '—').replace('&amp;', '&')
    s = re.sub(r'&[a-z]+;|&#\d+;', ' ', s)
    return s


GOOD_END = re.compile(r'[.!?]["”’)]?$')
BAD = re.compile(r'[{}\[\]|=<>_^~\\@#*]|\s[:;]\s*$|\b(px|thumb|upright)\b')


def paragraphs(src, voyage=False):
    """Prose paragraphs from wikitext, with the section heading they are under."""
    text = clean_wikitext(src)
    out, section, dropping = [], '', False
    for block in re.split(r'\n\s*\n|\n(?==)', text):
        lines = [l for l in block.split('\n')]
        keep = []
        for l in lines:
            m = re.match(r'^(={2,6})\s*(.*?)\s*\1\s*$', l.strip())
            if m:
                section = m.group(2).strip()
                dropping = bool(DROP_SECTIONS.match(section) or (voyage and VOYAGE_DROP.match(section)))
                continue
            if dropping:
                continue
            l = l.strip()
            if not l or l[0] in '*#:;|!{}=' or l.startswith('----'):
                if keep:
                    out.append(' '.join(keep)); keep = []
                continue
            keep.append(l)
        if keep and not dropping:
            out.append(' '.join(keep))
    good = []
    for p in out:
        p = re.sub(r'\s+', ' ', p).strip()
        p = re.sub(r'\(\s*[,;]?\s*\)', '', p)            # "( )" left by removed templates
        p = re.sub(r'\s+([,.;:!?])', r'\1', p)
        p = re.sub(r'([,;:])(?:\s*[,;:])+', r'\1', p)            # ",;" left where a template stood
        p = re.sub(r'\(\s*[,;:]\s*', '(', p)
        p = re.sub(r'\s{2,}', ' ', p).strip()
        w = words(p)
        if w < 12 or not GOOD_END.search(p) or BAD.search(p):
            continue
        if sum(c.isdigit() for c in p) > len(p) * 0.08:
            continue
        if re.search(r'[^\x00-ɏ‐-› °€£$]', p):       # non-Latin scripts (place names in Arabic etc.)
            p2 = re.sub(r'\s*\([^()]*[^\x00-ɏ‐-›][^()]*\)', '', p)
            if re.search(r'[^\x00-ɏ‐-› °€£$]', p2):
                continue
            p = p2
        good.append(p)
    return good


def pages(path):
    ns = ''
    with bz2.open(path, 'rb') as f:
        for ev, el in ET.iterparse(f, events=('end',)):
            tag = el.tag.rsplit('}', 1)[-1]
            if tag != 'page':
                continue
            if not ns:
                ns = el.tag[:el.tag.index('}') + 1] if el.tag.startswith('{') else ''
            title = el.findtext(ns + 'title')
            pns = el.findtext(ns + 'ns')
            redirect = el.find(ns + 'redirect') is not None
            text = el.findtext(ns + 'revision/' + ns + 'text') or ''
            ts = el.findtext(ns + 'revision/' + ns + 'timestamp') or ''
            el.clear()
            if pns == '0' and not redirect:
                yield title, text, ts


def region_from(names):
    """The region named most often in names (categories, or a Wikivoyage IsPartOf chain); a tie goes to the first."""
    found = [PLACE_REGION[n.strip().lower()] for n in names if n.strip().lower() in PLACE_REGION]
    if not found:
        return None
    c = Counter(found)
    return max(found, key=lambda r: (c[r], -found.index(r)))


def cap(paras, max_words):
    out, w = [], 0
    for p in paras:
        pw = words(p)
        if out and w + pw > max_words:
            break
        out.append(p); w += pw
    return out, w


def collect(key):
    P = PROJECTS[key]
    path = os.path.join(DUMPS, P['file'])
    items, parent, seen = [], {}, 0
    for title, text, ts in pages(path):
        seen += 1
        low = text.lower()
        if re.match(r'\s*#redirect', low) or '{{disambig' in low or '{{disambiguation' in low:
            continue
        cats = re.findall(r'\[\[\s*category\s*:\s*([^\]|]+)', text, re.I)
        info = {'title': title, 'ts': ts}
        if key == 'news':
            if '{{publish' not in low and '{{archive' not in low:      # only published articles
                continue
            m = re.search(r'\{\{\s*date\s*\|\s*([^}|]+)', text, re.I)
            info['date'] = m.group(1).strip() if m else ts[:10]
            info['region'] = region_from(cats)
        elif key == 'voyage':
            m = re.search(r'\{\{\s*ispartof\s*\|\s*([^}|]+)', text, re.I)
            if m:
                parent[title] = m.group(1).strip()
            st = re.search(r'\{\{\s*(star|guide|usable|outline|stub)(city|country|region|district|park|airport|itinerary|topic|travel ?topic|diveguide|ruralarea|event|phrasebook)?\b', text, re.I)
            info['status'] = st.group(1).lower() if st else ''
            if info['status'] in ('outline', 'stub') or re.search(r'\{\{\s*(phrasebook|ttcf|vfd|disamb)', text, re.I):
                continue
        else:
            if title.lower().startswith(('list of', 'lists of')) or re.match(r'^\d{1,4}( BC)?$', title):
                continue
            info['region'] = PLACE_REGION.get(title.lower()) or region_from(cats)
            info['good'] = bool(re.search(r'\{\{\s*(good|very good) article', text, re.I))
        paras = paragraphs(text, key == 'voyage')
        if any(UNSUITABLE.search(p) for p in paras) or UNSUITABLE.search(title):
            continue
        paras, w = cap(paras, P['max_words'])
        if w < P['min_words']:
            continue
        info['paras'] = paras; info['words'] = w
        items.append(info)
    if key == 'voyage':
        for it in items:
            chain, t = [it['title']], it['title']
            for _ in range(12):
                t = parent.get(t)
                if not t or t in chain: break
                chain.append(t)
            it['region'] = region_from(chain)
    print(f'{P["name"]}: {seen:,} pages, {len(items):,} usable, {sum(i["words"] for i in items):,} words', file=sys.stderr)
    return items


def choose(key, items):
    rnd = random.Random('kalima-' + key)
    rnd.shuffle(items)
    regional = sorted([i for i in items if i.get('region') in REGION_RANK], key=lambda i: REGION_RANK[i['region']])
    rest = [i for i in items if i.get('region') not in REGION_RANK]
    if key == 'simple':
        rest.sort(key=lambda i: not i.get('good'))                 # good articles first, then the random rest
    if key == 'voyage':
        rank = {'star': 0, 'guide': 1, 'usable': 2, '': 3}
        rest.sort(key=lambda i: rank.get(i.get('status', ''), 3))
    budget = TARGET[key]
    # regional texts may fill at most 40% of a project's share, so each project still covers the world
    picked, w = [], 0
    for i in regional:
        if w >= budget * 0.4: break
        picked.append(i); w += i['words']
    for i in rest:
        if w >= budget: break
        picked.append(i); w += i['words']
    return picked


MONTHS = {m: i for i, m in enumerate(['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august',
                                         'september', 'october', 'november', 'december'], 1)}


def news_date(s):
    """(year, month, day) from a Wikinews {{date}} value such as 'February 10, 2009', or None."""
    m = re.search(r'([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})', s or '') or re.search(r'(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})', s or '')
    if not m:
        return None
    a, b, y = m.groups()
    mon, day = (a, b) if a.isalpha() else (b, a)
    mo = MONTHS.get(mon.lower())
    return (int(y), mo, int(day)) if mo else None


def news_licence(date):
    # Wikinews:Copyright — before 25 Sept 2005 public domain; to 15 Dec 2024 CC BY 2.5; from 16 Dec 2024 CC BY 4.0
    if date and date < (2005, 9, 25):
        return 'Public domain', ''
    if date and date >= (2024, 12, 16):
        return 'CC BY 4.0', 'https://creativecommons.org/licenses/by/4.0/'
    return 'CC BY 2.5', 'https://creativecommons.org/licenses/by/2.5/'


docs, stats = [], Counter()
for key in ('news', 'voyage', 'simple'):
    P = PROJECTS[key]
    for n, it in enumerate(choose(key, collect(key)), 1):
        region = it.get('region') or 'intl'
        title = it['title']
        lic, lic_url, year = P['lic'], P['licUrl'], ''
        if key == 'news':
            dt = news_date(it.get('date'))
            lic, lic_url = news_licence(dt)
            year = str(dt[0]) if dt else ''
        src = P['name'] + (' · ' + year if year else '') + ' · ' + lic
        docs.append({
            'col': 'wiki', 'id': f'{key}-{n:05d}', 'genre': key,
            'title': title[:160], 'type': P['type'], 'region': region,
            'source': src, 'author': P['name'] + ' contributors', 'lic': lic, 'licUrl': lic_url,
            'url': P['site'] + urllib.parse.quote(title.replace(' ', '_'), safe="/:(),'!*"),
            'text': '\n\n'.join(it['paras']), 'gold': [],
        })
        stats[(key, region)] += it['words']
json.dump({'docs': docs}, open(OUT, 'w', encoding='utf8'), ensure_ascii=False)
for key in ('news', 'voyage', 'simple'):
    rows = {r: w for (k, r), w in stats.items() if k == key}
    print(key, sum(rows.values()), dict(sorted(rows.items(), key=lambda x: -x[1])), file=sys.stderr)
print('texts', len(docs), 'words', sum(stats.values()), file=sys.stderr)
