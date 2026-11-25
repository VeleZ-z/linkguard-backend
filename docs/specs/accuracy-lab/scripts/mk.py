import random, csv, glob, collections, pickle
from urllib.parse import urlsplit
from publicsuffix2 import get_sld
random.seed(5)
def reg(u):
    h=(urlsplit(u if '://' in u else 'http://'+u).hostname or '').lower(); return get_sld(h) or h
def cap(urls,k,per=3):
    random.shuffle(urls); c=collections.Counter(); out=[]
    for u in urls:
        r=reg(u)
        if c[r]<per: c[r]+=1; out.append(u)
        if len(out)>=k: break
    return out
jp=[]
for f in glob.glob('/home/claude/phishurl-list/20*/*.csv'):
    for r in csv.DictReader(open(f,encoding='utf-8',errors='ignore')):
        if r.get('URL','').startswith('http'): jp.append(r['URL'].strip())
jp=cap(list(set(jp)),20000)
pdb=cap([l.strip() for l in open('phishing-links-ACTIVE.txt',errors='ignore') if l.startswith('http')],20000)
top=[l.strip() for l in open('top1m.txt') if l.strip()]
bands=[(0,1000,1000),(1000,10000,6000),(10000,100000,14000),(100000,999999,15000)]
negd=[]
for a,b,k in bands: negd+=random.sample(top[a:b],k)
cl=[r['url'].strip() for r in csv.DictReader(open('global.csv',encoding='utf-8',errors='ignore')) if r['url'].startswith('http')]
paths=[urlsplit(u).path+('?'+urlsplit(u).query if urlsplit(u).query else '') for u in cl if urlsplit(u).path not in('','/')]
neg=[]
for d in negd:
    pre=random.choice(['https://','https://www.','http://']) 
    u=pre+d+(random.choice(paths) if random.random()<0.5 else '/')
    neg.append(u)
neg+=cl
data=[(u,1,'jpcert') for u in jp]+[(u,1,'phishdb') for u in pdb]+[(u,0,'legit') for u in neg]
print(collections.Counter((y,s) for u,y,s in data))
pickle.dump(data,open('data.pkl','wb'))
