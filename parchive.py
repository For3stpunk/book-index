"""Crawl the publishersarchive.com directory (publisher pages /publisher/<id>) into data/publishersarchive/publishers.json.
Resumable: ids already saved are skipped. Polite: about 2 requests a second.
usage: python parchive.py START END [MAX_MINUTES]
"""
import json, os, re, sys, time
import requests
from bs4 import BeautifulSoup

UA = 'Mozilla/5.0 (compatible; book-index directory sync; +https://github.com/For3stpunk/book-index)'
S = requests.Session(); S.headers['User-Agent'] = UA
PATH = 'data/publishersarchive/publishers.json'


def label_link(soup, label):
    el = soup.find(string=re.compile(r'^\s*' + re.escape(label) + r'\s*$'))
    if not el:
        return ''
    a = el.find_next('a', href=True)
    return a['href'] if a else ''


def parse(html, pid):
    soup = BeautifulSoup(html, 'html.parser')
    h1 = soup.find('h1')
    name = h1.get_text(' ', strip=True) if h1 else ''
    if not name:
        return None
    text = soup.get_text('\n', strip=True)
    addr = ''
    m = re.search(r'Address\s*\n(.+?)\n(?:Phone|Online|Web)', text, re.S)
    if m:
        addr = ' '.join(x.strip() for x in m.group(1).split('\n') if x.strip())[:200]
    web = label_link(soup, 'Web:')
    subs = ''
    for a in soup.find_all('a', href=True):
        if 'Submission' in a.get_text():
            subs = a['href']; break
    cats = []
    hdr = soup.find(string=re.compile('is listed in the following categories'))
    if hdr:
        box = hdr.find_parent(['div', 'section']) or hdr.parent
        cats = [a.get_text(' ', strip=True) for a in box.find_all('a') if a.get_text(strip=True)]
    return {'id': pid, 'name': name, 'address': addr, 'web': web if web.startswith('http') and 'publishersarchive' not in web else '',
            'submissions': subs if subs.startswith('http') else '', 'categories': [c for c in cats if c][:20],
            'url': f'https://publishersarchive.com/publisher/{pid}'}


def debug(pid):
    r = S.get(f'https://publishersarchive.com/publisher/{pid}', timeout=30)
    soup = BeautifulSoup(r.text, 'html.parser')
    print('status', r.status_code, 'final', r.url, 'bytes', len(r.text))
    print('title', soup.title.string if soup.title else None)
    print('headings', [(h.name, h.get_text(' ', strip=True)[:60]) for h in soup.find_all(['h1', 'h2', 'h3'])][:15])
    print(r.text[:1500])


def main():
    if sys.argv[1] == 'debug':
        debug(int(sys.argv[2])); return
    start, end = int(sys.argv[1]), int(sys.argv[2])
    budget = float(sys.argv[3]) * 60 if len(sys.argv) > 3 else 1e9
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    db = {r['id']: r for r in json.load(open(PATH))} if os.path.exists(PATH) else {}
    missing = set(json.load(open(PATH + '.missing'))) if os.path.exists(PATH + '.missing') else set()
    t0, n = time.time(), 0
    for pid in range(start, end + 1):
        if pid in db or pid in missing:
            continue
        if time.time() - t0 > budget:
            print('time budget reached at', pid); break
        try:
            r = S.get(f'https://publishersarchive.com/publisher/{pid}', timeout=30)
        except Exception as e:
            print(pid, e); time.sleep(5); continue
        if r.status_code == 404:
            missing.add(pid)
        elif r.status_code == 200:
            rec = parse(r.text, pid)
            if rec:
                db[pid] = rec
            else:
                missing.add(pid)
        elif r.status_code in (429, 503):
            time.sleep(60); continue
        n += 1
        if n % 500 == 0:
            json.dump(sorted(db.values(), key=lambda x: x['id']), open(PATH, 'w'), ensure_ascii=False)
            json.dump(sorted(missing), open(PATH + '.missing', 'w'))
            print('saved', len(db), 'at', pid, flush=True)
        time.sleep(0.45)
    json.dump(sorted(db.values(), key=lambda x: x['id']), open(PATH, 'w'), ensure_ascii=False)
    json.dump(sorted(missing), open(PATH + '.missing', 'w'))
    print('done; publishers', len(db), 'missing ids', len(missing))


if __name__ == '__main__':
    main()
