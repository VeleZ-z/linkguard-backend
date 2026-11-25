import csv, glob, random, collections, sys
random.seed(7)
rows=[]
for f in sorted(glob.glob('/home/claude/phishurl-list/20*/*.csv')):
    with open(f, encoding='utf-8', errors='ignore') as fh:
        for r in csv.DictReader(fh):
            if r.get('URL'): rows.append((f.split('/')[-2], r['URL'].strip(), r.get('description','')))
print(len(rows), collections.Counter(y for y,_,_ in rows))
# estratificado por año, dedup por URL
seen=set(); by=collections.defaultdict(list)
for y,u,d in rows:
    if u in seen: continue
    seen.add(u); by[y].append((y,u,d))
out=[]
for y,l in by.items():
    random.shuffle(l); out+=l[:300]
with open('/home/claude/bench/jpcert_sample.tsv','w') as fh:
    for y,u,d in out: fh.write(f"{y}\t{u}\t{d}\n")
print(len(out))
