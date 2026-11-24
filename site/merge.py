"""Merge cloud-collected sources into the Edelweiss list.
usage: python3 merge.py REPO_DIR  -> books_merged.json (same shape as books.json, plus src / pwStar / pwUrl / tba)
"""
import json, re, sys, glob, os, unicodedata

repo = sys.argv[1]
B = json.load(open('books.json'))


def norm(s):
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode().lower()
    s = re.split(r'[:(]', s)[0]
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()


def last(a):
    a = re.sub(r'\(.*?\)', '', a or '')
    first = re.split(r',| and | & ', a)[0].strip()
    return norm(first).split()[-1] if norm(first) else ''


by_isbn, by_ta = {}, {}
for b in B:
    b.setdefault('src', ['E'])
    by_isbn[b['ean']] = b
    by_ta[(norm(b['t']), last(b['a']))] = b

added = matched = 0
pw = json.load(open(f'{repo}/data/pw/reviews.json')) if os.path.exists(f'{repo}/data/pw/reviews.json') else []
def fix(r):
    m = re.match(r'^(.*)\.\s+([^.,]+?),\s*\$', r.get('byline', ''))
    if m:
        r['author'] = re.split(r',\s*(trans|illus|edited|ed\.)', m.group(1))[0].strip()
        r['publisher'] = m.group(2).strip()
    return r


for r in map(fix, pw):
    hit = next((by_isbn[i] for i in r.get('isbns', []) if i in by_isbn), None) or by_ta.get((norm(r['title']), last(r['author'])))
    if hit:
        matched += 1
        if 'PW' not in hit['src']:
            hit['src'].append('PW')
        hit['pwStar'] = hit.get('pwStar') or bool(r.get('starred'))
        if r.get('url'):
            hit['pwUrl'] = r['url']
        continue
    if not r.get('pub_month'):
        continue
    isbn = (r.get('isbns') or [''])[0]
    rec = {'ean': isbn or 'pw-' + re.sub(r'[^a-z0-9]+', '-', norm(r['title']))[:40], 't': r['title'], 'a': r['author'], 'pub': r['publisher'],
           'd': r['pub_month'] + '-01', 'tba': True, 'g': 'Other', 'aud': 'Kids' if r.get('category') == 'childrens' else 'Adult',
           'src': ['PW'], 'pwStar': bool(r.get('starred'))}
    if r.get('url'):
        rec['pwUrl'] = r['url']
    cat = r.get('category', '')
    rec['g'] = {'fiction': 'Literary & General Fiction', 'mystery-thriller': 'Mystery & Thriller', 'sci-fi-fantasy-horror': 'Fantasy',
                'romance-erotica': 'Romance', 'comics': 'Comics & Graphic Novels', 'poetry': 'Poetry', 'inspirational-fiction': 'Religion & Spirituality',
                'nonfiction': 'Ideas, Essays & Criticism', 'lifestyle': 'Hobbies, Home & Sports', 'religion': 'Religion & Spirituality',
                'childrens': 'Middle Grade & Kids'}.get(cat, 'Other')
    B.append(rec)
    by_isbn[rec['ean']] = rec
    by_ta[(norm(rec['t']), last(rec['a']))] = rec
    added += 1

pub_hits = pub_added = 0
for f in glob.glob(f'{repo}/data/publishers/*.json'):
    if f.endswith('_report.json'):
        continue
    d = json.load(open(f))
    for bk in d.get('books', []):
        hit = by_isbn.get(bk.get('isbn')) or by_ta.get((norm(bk.get('title')), last(bk.get('author'))))
        if hit and 'P' not in hit['src']:
            hit['src'].append('P')
            pub_hits += 1
        elif not hit and bk.get('date') and bk.get('title') and len(bk['title']) > 2:
            rec = {'ean': bk.get('isbn') or 'pub-' + re.sub(r'[^a-z0-9]+', '-', norm(bk['title']))[:40], 't': bk['title'], 'a': bk.get('author', ''),
                   'pub': d.get('name', ''), 'd': bk['date'], 'g': 'Other', 'aud': 'Adult', 'src': ['P'], 'pubUrl': bk.get('url', '')}
            B.append(rec); by_isbn[rec['ean']] = rec; by_ta[(norm(rec['t']), last(rec['a']))] = rec
            pub_added += 1

B.sort(key=lambda r: (r['d'], 1 if r.get('tba') else 0, 0 if r.get('img') else 1, r['t']))
json.dump(B, open('books_merged.json', 'w'), ensure_ascii=False, separators=(',', ':'))
print('pw matched', matched, 'pw added', added, 'publisher hits', pub_hits, 'publisher added', pub_added, 'total', len(B))
