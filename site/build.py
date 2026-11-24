import json, re, unicodedata, html, sys
from datetime import date

RAW = json.load(open('raw.json'))
FEED = json.load(open('feed_items.json')) if os.path.exists('feed_items.json') else []
PREV = set(json.load(open('prev_eans.json'))) if len(sys.argv) > 1 else None
import os
TODAY = os.environ.get('TODAY') or date.today().isoformat()
START = os.environ.get('START') or TODAY
END = os.environ.get('END') or '9999-12-31'
SCOPE = os.environ.get('SCOPE', 'all')  # all | trade (drop non-English and non-book items)

NONBOOK = re.compile(r'puzzle|cards|toy|game|kit|calendar|audio|cd|dvd|poster|stationery|journal \(blank\)|merchandise|plush|other', re.I)
BAD_STATUS = {'Cancelled', 'No longer our product', 'Postponed indefinitely', 'Out of print'}


def genre(cats, aud):
    c = ' | '.join(cats)
    f = cats[0] if cats else ''
    top = f.split(' / ')[0]
    if top.startswith('Juvenile') or re.search(r'Ages [0-9]( |,)', aud or ''):
        if re.search(r'Board|Picture|Concepts|Bedtime|Readers|Ages [0-5] ', c + ' ' + (aud or '')):
            return "Picture Books & Early Readers", 'Kids'
        return "Middle Grade & Kids", 'Kids'
    if top.startswith('Young Adult'):
        return 'Young Adult', 'YA'
    rules = [
        (r'Fiction / Romance / Fantasy|Fiction / Fantasy / Romant|Romantasy', 'Romantasy'),
        (r'^Fiction / Romance', 'Romance'),
        (r'^Fiction / (Fantasy)', 'Fantasy'),
        (r'^Fiction / Science Fiction|Dystopian', 'Science Fiction'),
        (r'^Fiction / (Horror|Ghost)|Fiction / Thrillers / Supernatural', 'Horror'),
        (r'^Fiction / (Mystery|Thrillers|Crime|Suspense)', 'Mystery & Thriller'),
        (r'^Fiction / Historical', 'Historical Fiction'),
        (r'^Fiction / Short Stories', 'Short Stories'),
        (r'^Fiction', 'Literary & General Fiction'),
        (r'^Comics & Graphic Novels / (Manga|East Asian|Light Novel)', 'Manga & Light Novels'),
        (r'^Comics', 'Comics & Graphic Novels'),
        (r'^Poetry', 'Poetry'),
        (r'^Biography|^True Crime', 'Memoir, Biography & True Crime'),
        (r'^History', 'History'),
        (r'^(Political Science|Social Science|Law|Education)', 'Politics & Society'),
        (r'^(Science|Nature|Mathematics|Medical)', 'Science & Nature'),
        (r'^(Literary Criticism|Language|Philosophy|Literary Collections|Reference)', 'Ideas, Essays & Criticism'),
        (r'^(Art|Photography|Design|Architecture|Antiques)', 'Art, Photography & Design'),
        (r'^(Music|Performing Arts)', 'Music, Film & Performing Arts'),
        (r'^Cooking', 'Food & Drink'),
        (r'^(Self-Help|Health|Psychology|Family|Body, Mind|Mind, Body)', 'Self-Help, Health & Psychology'),
        (r'^(Religion|Bibles)', 'Religion & Spirituality'),
        (r'^(Business|Computers|Technology)', 'Business & Tech'),
        (r'^Travel', 'Travel'),
        (r'^Humor', 'Humor'),
        (r'^(Sports|Crafts|Games|House|Gardening|Pets|Transportation)', 'Hobbies, Home & Sports'),
    ]
    for pat, g in rules:
        if re.search(pat, f):
            return g, 'Adult'
    return 'Other', 'Adult'


def norm(s):
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode().lower()
    s = s.replace('&', ' and ')
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()


def name_fmt(a):
    # Edelweiss author can be "Last, First"; contributorsWithType is "First Last, First Last"
    return a.strip()


feedn = [(norm(html.unescape(f['title'])), f) for f in FEED]
STOP = {'the', 'a', 'an', 'of', 'and', 'in', 'on', 'to', 'for', 'book', 'books', 'new', 'love', 'christmas', 'home', 'the end'}

out = []
for b in RAW:
    if not b.get('d') or b['d'] < START or b['d'] > END:
        continue
    if b.get('status') in BAD_STATUS:
        continue
    if SCOPE == 'trade' and b.get('lang') and b['lang'] != 'English':
        continue
    if SCOPE == 'trade' and NONBOOK.search(b.get('fmt') or '') and not re.search(r'book', b.get('fmt') or '', re.I):
        continue
    g, aud = genre(b.get('cats') or [], b.get('aud') or '')
    cats = ' | '.join(b.get('cats') or [])
    lgbt = bool(re.search(r'LGBTQ|Gay|Lesbian|Transgender|Bisexual|Queer', cats))
    t = b['t'].strip()
    tn = norm(re.split(r'[:(]', t)[0])
    authors = re.sub(r'\s*\((?:[^()]|\([^()]*\))*\)', '', b.get('a') or '').strip()
    lasts = [norm(x).split()[-1] for x in re.split(r',| and ', authors) if norm(x)]
    news = []
    if tn and tn not in STOP:
        long_title = len(tn) >= 20 and len(tn.split()) >= 4
        for fn, f in feedn:
            if f' {tn} ' in f' {fn} ':
                if long_title or any(l and len(l) > 2 and f' {l} ' in f' {fn} ' for l in lasts):
                    news.append({'title': html.unescape(f['title']), 'link': f['link'], 'source': f['source'], 'date': f['date'], 'beat': f['beat']})
    desc = (b.get('desc') or '').strip()
    paras = ''.join(f'<p>{html.escape(p.strip())}</p>' for p in desc.split('\n') if p.strip())
    img = b.get('img') or ''
    if img:
        img = img.split('?')[0] + '?width=240'
    out.append({
        'sku': b['sku'], 'ean': b.get('ean') or b['sku'], 't': t, 'st': b.get('st') or '', 'a': authors,
        'pub': b.get('pub') or '', 'd': b['d'], 'fmt': b.get('fmt') or '', 'pages': b.get('pages') if (b.get('pages') or '0') not in ('0', 'N/A') else '',
        'g': g, 'aud': aud, 'bisac': (b.get('cats') or [''])[0], 'lgbt': lgbt, 'img': img, 'desc': paras,
        'news': news[:5], 'isNew': (PREV is not None and (b.get('ean') or b['sku']) not in PREV),
        'pr': b.get('cat', 1),
    })

# Collapse editions: same title+author, keep earliest date / hardcover first
key = {}
for r in out:
    k = (norm(r['t']), norm(r['a']))
    o = key.get(k)
    if not o or (r['img'] and not o['img']) or (r['fmt'].startswith('Hard') and not o['fmt'].startswith('Hard') and bool(r['img']) == bool(o['img'])):
        key[k] = r
out = sorted(key.values(), key=lambda r: (r['d'], 0 if r['img'] else 1, r['t']))
import os
os.makedirs('desc', exist_ok=True)
NS = 24
shards = [dict() for _ in range(NS)]
for i, r in enumerate(out):
    s = i % NS
    if r['desc']:
        shards[s][r['ean']] = r['desc']
    r['ds'] = s
    del r['desc']
    for k in ('st', 'fmt', 'pages', 'bisac'):
        if not r[k]: del r[k]
    if not r['news']: del r['news']
    if not r['lgbt']: del r['lgbt']
    if not r['isNew']: del r['isNew']
    if r['sku'] == r['ean'] or r['ean'].endswith(r['sku'][:-1]): del r['sku']
    del r['pr']
    r['img'] = r['img'].replace('https://images-azf.edelweiss.plus/ea/', '~').replace('/images/jacket_covers/original/', '|').replace('?width=240', '')
for s in range(NS):
    json.dump(shards[s], open(f'desc/{s:02d}.json', 'w'), ensure_ascii=False)
json.dump(out, open('books.json', 'w'), ensure_ascii=False, separators=(',', ':'))
from collections import Counter
print(len(out), Counter(r['aud'] for r in out), sum(1 for r in out if r.get('news')))
print(Counter(r['g'] for r in out).most_common())
for r in [r for r in out if r.get('news')][:40]:
    print(r['t'], '|', r['a'], '|', r['news'][0]['title'][:90])
