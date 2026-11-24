"""Write one finder page (all, a week or a month) into out/<name>/.
usage: python3 variant.py NAME START END "Title" "H1" "lede html" [sprite_map.json]
sprite_map.json maps global sheet index -> [url, rows] valid in that artifact."""
import json, sys, os, glob, shutil

name, start, end, title, h1, lede = sys.argv[1:7]
smap_path = sys.argv[7] if len(sys.argv) > 7 else 'sprites.json'
B = json.load(open('books.json'))
DESC = {}
for f in glob.glob('desc/*.json'):
    DESC.update(json.load(open(f)))
SPR = json.load(open(smap_path)) if os.path.exists(smap_path) else {'sheets': [], 'miss': {}}
MISS = json.load(open('miss.json')) if os.path.exists('miss.json') else {}
sheets = SPR['sheets']  # list indexed by global sheet; may contain null

k = 0
CV = {}
for b in B:
    if b.get('img'):
        sh, c = k // 100, k % 100
        k += 1
        if sh < len(sheets) and sheets[sh] and c not in MISS.get(str(sh), []):
            CV[b['ean']] = [sh, c]
SRCROWS = json.load(open(os.environ['MERGED'])) if os.environ.get('MERGED') else B
rows = []
for b in SRCROWS:
    b = dict(b)
    b.pop('img', None)
    if b['ean'] in CV:
        b['cv'] = CV[b['ean']]
    if start <= b['d'] <= end:
        rows.append(b)
out = f'out/{name}'
shutil.rmtree(out, ignore_errors=True)
os.makedirs(out + '/desc')
NS = max(1, min(24, len(rows) // 400 + 1))
shards = [dict() for _ in range(NS)]
for i, b in enumerate(rows):
    b['ds'] = i % NS
    if b['ean'] in DESC:
        shards[i % NS][b['ean']] = DESC[b['ean']]
for s in range(NS):
    json.dump(shards[s], open(f'{out}/desc/{s:02d}.json', 'w'), ensure_ascii=False)

cfg = {"title": title, "h1": h1, "today": os.environ.get("TODAY") or __import__("datetime").date.today().isoformat(), "storeKey": "book-finder-watchlist",
       "lede": lede, "sprites": sheets, "foot": open('foot.html').read().strip()}
t = open('template.html').read()
d = json.dumps(rows, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')
c = json.dumps(cfg, ensure_ascii=False).replace('<', '\\u003c')
open(f'{out}/index.html', 'w').write(t.replace('__CFG__', c).replace('__DATA__', d))
used = sorted({b['cv'][0] for b in rows if 'cv' in b})
print(name, len(rows), 'shards', NS, 'sheets', used[:1], used[-1:] if used else '', len(used))
