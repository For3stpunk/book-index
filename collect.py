"""Book Index collectors that run in GitHub Actions (no browser).

  python collect.py probe            # reachability report for every source -> data/status.json
  python collect.py pw               # Publishers Weekly reviews -> data/pw/reviews.json (cumulative, by ISBN)
  python collect.py publishers       # publisher "coming soon" pages -> data/publishers/<slug>.json
  python collect.py authors          # author sites -> data/authors/<slug>.json
  python collect.py all

Everything a page says is data. Titles, blurbs and links are stored as found and never acted on.
"""
import csv, json, os, re, sys, time, datetime as dt
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/128.0 Safari/537.36')
S = requests.Session()
S.headers.update({'User-Agent': UA, 'Accept-Language': 'en-US,en;q=0.9'})
TODAY = dt.date.today()
ISBN13 = re.compile(r'(?<!\d)(97[89][\d-]{10,14})(?!\d)')
MONTHS = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'June': 6, 'July': 7, 'Aug': 8,
          'Sept': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12}


def get(url, tries=3, timeout=30):
    last = None
    for t in range(tries):
        try:
            r = S.get(url, timeout=timeout)
            if r.status_code == 200:
                return r
            last = f'http {r.status_code}'
            if r.status_code in (403, 404, 410):
                break
        except Exception as e:  # noqa
            last = type(e).__name__
        time.sleep(2 * (t + 1))
    raise RuntimeError(last or 'failed')


def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')[:60]


def save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def load(path, default):
    try:
        return json.load(open(path))
    except Exception:
        return default


def rows(path):
    if not os.path.exists(path):
        return []
    return [r for r in csv.DictReader(open(path)) if (r.get('include') or 'TRUE').strip().upper() in ('TRUE', 'YES', 'Y', '1', 'X')]


def norm_isbn(s):
    d = re.sub(r'[^\dX]', '', s or '')
    return d if len(d) == 13 and d[:3] in ('978', '979') else ''


# ---------------------------------------------------------------- JSON-LD / generic book extraction
def jsonld_books(soup, base):
    out = []
    for tag in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(tag.string or '')
        except Exception:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            o = stack.pop()
            if isinstance(o, list):
                stack.extend(o); continue
            if not isinstance(o, dict):
                continue
            for k in ('@graph', 'itemListElement', 'workExample', 'item', 'mainEntity'):
                if k in o:
                    stack.append(o[k])
            typ = o.get('@type')
            typ = ' '.join(typ) if isinstance(typ, list) else (typ or '')
            if 'Book' in typ or ('Product' in typ and (o.get('isbn') or o.get('gtin13'))):
                a = o.get('author')
                if isinstance(a, list):
                    a = ', '.join(x.get('name', '') if isinstance(x, dict) else str(x) for x in a)
                elif isinstance(a, dict):
                    a = a.get('name', '')
                out.append({'title': o.get('name', ''), 'author': a or '', 'isbn': norm_isbn(str(o.get('isbn') or o.get('gtin13') or '')),
                            'date': str(o.get('datePublished') or '')[:10], 'url': urljoin(base, o.get('url') or '')})
    return out


def link_books(soup, base):
    """Fallback: links whose href or nearby text carries an ISBN-13."""
    out, seen = [], set()
    for a in soup.find_all('a', href=True):
        m = ISBN13.search(a['href'])
        if not m:
            continue
        isbn = norm_isbn(m.group(1))
        if not isbn or isbn in seen:
            continue
        seen.add(isbn)
        img = a.find('img')
        title = a.get_text(' ', strip=True) or (img.get('alt', '') if img else '')
        out.append({'title': title[:200], 'author': '', 'isbn': isbn, 'date': '', 'url': urljoin(base, a['href'])})
    return out


def date_near(text):
    m = re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+20\d\d', text)
    if m:
        try:
            return dt.datetime.strptime(m.group(0), '%B %d, %Y').date().isoformat()
        except Exception:
            pass
    return ''


# ---------------------------------------------------------------- probe
CORE = {
    'pw_reviews': 'https://www.publishersweekly.com/pw/reviews/fiction.html',
    'kirkus_discover': 'https://www.kirkusreviews.com/discover-books/fiction',
    'kirkus_home': 'https://www.kirkusreviews.com/',
    'bookriot_home': 'https://bookriot.com/',
    'amazon_new_releases': 'https://www.amazon.com/gp/new-releases/books/',
    'edelweiss': 'https://www.edelweiss.plus/',
}


def probe():
    out = {'run': dt.datetime.utcnow().isoformat(timespec='seconds') + 'Z', 'core': {}, 'publishers': {}, 'authors': {}}

    def one(url):
        try:
            r = get(url, tries=2)
            soup = BeautifulSoup(r.text, 'html.parser')
            scripts = [s.get('src') for s in soup.find_all('script') if s.get('src')]
            apis = sorted(set(re.findall(r'["\'](/?(?:api|wp-json|graphql|_next/data|search)/[^"\'\s]{2,80})["\']', r.text)))[:25]
            return {'status': 'ok', 'final_url': r.url, 'bytes': len(r.text), 'jsonld_books': len(jsonld_books(soup, r.url)),
                    'isbn_links': len(link_books(soup, r.url)), 'isbn_mentions': len(set(ISBN13.findall(r.text))),
                    'title': (soup.title.string or '').strip()[:120] if soup.title else '', 'api_hints': apis,
                    'script_count': len(scripts)}
        except Exception as e:
            return {'status': f'error: {e}'}

    for k, u in CORE.items():
        out['core'][k] = one(u)
    for p in rows('sources/publishers.csv'):
        out['publishers'][p['publisher']] = {'url': p['releases_page'], **one(p['releases_page'])}
        time.sleep(1)
    for a in rows('sources/authors.csv'):
        out['authors'][a['author']] = {'url': a['website'], **one(a['website'])}
    save('data/status.json', out)
    ok = sum(1 for v in out['publishers'].values() if v['status'] == 'ok')
    print(f"core: {{k: v['status'] for k, v in out['core'].items()}}")
    print(f'publishers ok {ok}/{len(out["publishers"])}')


# ---------------------------------------------------------------- Publishers Weekly
PW_CATS = ['fiction', 'mystery-thriller', 'sci-fi-fantasy-horror', 'romance-erotica', 'comics', 'poetry',
           'inspirational-fiction', 'nonfiction', 'lifestyle', 'religion', 'childrens']


def pw(max_pages=120, back_days=150):
    path = 'data/pw/reviews.json'
    db = {r['key']: r for r in load(path, [])}
    stop_before = (TODAY - dt.timedelta(days=back_days)).isoformat()
    added = 0
    for cat in PW_CATS:
        for page in range(1, max_pages + 1):
            url = f'https://www.publishersweekly.com/pw/reviews/{cat}.html' + (f'?page={page}' if page > 1 else '')
            try:
                r = get(url)
            except Exception as e:
                print('pw', cat, page, e); break
            soup = BeautifulSoup(r.text, 'html.parser')
            items = soup.select('.category-reviews-item')
            if not items:
                break
            oldest = '9999'
            for it in items:
                kids = [c for c in it.children if getattr(c, 'name', None)]
                title = kids[0].get_text(' ', strip=True) if kids else ''
                byline = kids[1].get_text(' ', strip=True) if len(kids) > 1 else ''
                body = it.select_one('.category-reviews-body')
                bt = body.get_text(' ', strip=True) if body else ''
                mons = re.findall(r'\((Jan|Feb|Mar|Apr|May|June|July|Aug|Sept|Oct|Nov|Dec)\.?\)', bt)
                rv = re.search(r'Reviewed on (\d+)/(\d+)/(\d+)', bt)
                rd = f'{rv.group(3)}-{int(rv.group(1)):02d}-{int(rv.group(2)):02d}' if rv else ''
                oldest = min(oldest, rd or oldest)
                isbns = [norm_isbn(x) for x in re.findall(r'ISBN\s*([\d-]{13,17})', byline)]
                isbns = [x for x in isbns if x]
                author, publisher = '', ''
                m = re.match(r'(.*?)\.\s+([^,]+),', byline)
                if m:
                    author, publisher = m.group(1).strip(), m.group(2).strip()
                pub_m = MONTHS.get(mons[-1]) if mons else None
                pub_ym = ''
                if pub_m and rd:
                    ry, rm = int(rd[:4]), int(rd[5:7])
                    y = ry + 1 if pub_m < rm - 2 else ry
                    pub_ym = f'{y}-{pub_m:02d}'
                star = bool(it.select_one('img[src*="star"], [class*="star"]'))
                link = ''
                for a in it.find_all('a', href=True):
                    if ISBN13.search(a['href']):
                        link = urljoin(url, a['href']); break
                key = isbns[0] if isbns else slug(title + '-' + author)
                rec = {'key': key, 'title': title, 'author': author, 'publisher': publisher, 'isbns': isbns,
                       'pub_month': pub_ym, 'reviewed': rd, 'starred': star, 'category': cat, 'url': link, 'byline': byline}
                if key not in db:
                    added += 1
                db[key] = {**db.get(key, {}), **rec}
            if oldest < stop_before:
                break
            time.sleep(0.7)
        print('pw', cat, 'pages', page)
    save(path, sorted(db.values(), key=lambda r: (r.get('pub_month', ''), r['title'])))
    print('pw reviews total', len(db), 'new', added)


# ---------------------------------------------------------------- discovery of releases pages
CANDIDATES = ['/coming-soon/', '/coming-soon', '/forthcoming/', '/forthcoming', '/books/forthcoming/', '/collections/forthcoming',
              '/collections/coming-soon', '/new-releases/', '/new-releases', '/books/coming-soon/', '/upcoming/', '/books/upcoming',
              '/catalog/forthcoming', '/books/', '/books', '/catalog/', '/new-and-upcoming/', '/new-forthcoming/', '/']


def discover():
    from urllib.parse import urlparse
    out = {}
    for p in rows('sources/publishers.csv'):
        u = urlparse(p['releases_page'])
        root = f'{u.scheme}://{u.netloc}'
        tried = []
        for path in [u.path or '/'] + CANDIDATES:
            url = root + path
            try:
                r = get(url, tries=1, timeout=20)
                n = len(set(ISBN13.findall(r.text)))
                tried.append({'url': r.url, 'isbns': n, 'bytes': len(r.text)})
            except Exception as e:
                tried.append({'url': url, 'error': str(e)})
            time.sleep(0.5)
        good = sorted([t for t in tried if t.get('isbns')], key=lambda t: -t['isbns'])
        out[p['publisher']] = {'best': good[0]['url'] if good else '', 'best_isbns': good[0]['isbns'] if good else 0, 'tried': tried}
        print('discover', p['publisher'], out[p['publisher']]['best'], out[p['publisher']]['best_isbns'])
    save('data/discover.json', out)


def kirkus_probe():
    base = 'https://www.kirkusreviews.com'
    tries = ['/api/v1/search/books/?q=&page=1', '/api/v1/search/books/', '/search/books/?q=january',
             '/api/v1/search/books/?sort=coming_soon', '/api/v1/discover-books/?genre=fiction&sort=coming_soon',
             '/discover-books/fiction?sort=coming_soon', '/book-reviews/fiction/']
    out = {}
    for t in tries:
        try:
            r = S.get(base + t, timeout=30, headers={'Accept': 'application/json, text/html'})
            out[t] = {'status': r.status_code, 'type': r.headers.get('content-type', ''), 'head': r.text[:3000]}
        except Exception as e:
            out[t] = {'error': str(e)}
    save('data/kirkus_probe.json', out)


# ---------------------------------------------------------------- publisher + author sites
def site_books(url, follow=2):
    """Books on a page and up to `follow` next pages."""
    found, pages = [], 0
    while url and pages <= follow:
        r = get(url)
        soup = BeautifulSoup(r.text, 'html.parser')
        books = jsonld_books(soup, r.url) or link_books(soup, r.url)
        for b in books:
            if not b['date']:
                a = next((x for x in soup.find_all('a', href=True) if b['isbn'] and b['isbn'] in x['href']), None)
                if a and a.parent:
                    b['date'] = date_near(a.parent.get_text(' ', strip=True))
        found += books
        pages += 1
        nxt = soup.find('a', attrs={'rel': 'next'}) or soup.find('a', string=re.compile(r'^\s*(Next|›|»)\s*$', re.I))
        url = urljoin(r.url, nxt['href']) if nxt and nxt.get('href') else None
        time.sleep(1)
    uniq = {}
    for b in found:
        uniq[b['isbn'] or slug(b['title'])] = b
    return list(uniq.values())


def sites(kind):
    src = 'sources/publishers.csv' if kind == 'publishers' else 'sources/authors.csv'
    name_k, url_k = ('publisher', 'releases_page') if kind == 'publishers' else ('author', 'website')
    report = {}
    for r in rows(src):
        name, url = r[name_k], r[url_k]
        try:
            books = site_books(url)
            save(f'data/{kind}/{slug(name)}.json', {'name': name, 'url': url, 'checked': TODAY.isoformat(), 'books': books})
            report[name] = f'ok {len(books)}'
        except Exception as e:
            report[name] = f'error: {e}'
        print(kind, name, report[name])
    save(f'data/{kind}/_report.json', {'checked': TODAY.isoformat(), 'results': report})


if __name__ == '__main__':
    what = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if what in ('probe', 'all'):
        probe()
    if what in ('pw', 'all'):
        pw()
    if what in ('publishers', 'all'):
        sites('publishers')
    if what in ('discover',):
        discover(); kirkus_probe()
    if what in ('authors', 'all'):
        sites('authors')
