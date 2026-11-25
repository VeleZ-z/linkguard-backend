import pickle, numpy as np, math, collections
from urllib.parse import urlsplit
from publicsuffix2 import get_sld
from feat2 import feats2
data=pickle.load(open('data.pkl','rb')); X0,y,src,doms=pickle.load(open('X.pkl','rb'))
top=[l.strip() for l in open('top1m.txt')]
rank={}
for i,d in enumerate(top):
    s=get_sld(d) or d
    if s==d: rank.setdefault(s,i+1)          # solo dominios registrables (excluye sufijos/plataformas)
art=__import__('json').load(open('model_proto.json')); W={int(k):v for k,v in art['weights'].items()}; b=art['bias']
th=pickle.load(open('th.pkl','rb'))[0]
def p_of(u): 
    f=feats2(u,False); return 1/(1+math.exp(-(b+sum(W.get(k,0)*v for k,v in f.items()))))
def reg(u):
    h=(urlsplit(u if '://' in u else 'http://'+u).hostname or '').lower(); return get_sld(h) or h
# 1) cuántos positivos viven en dominios "rankeados" (costo de la allowlist)
for name in ('jpcert','phishdb'):
    idx=[i for i in range(len(data)) if src[i]==name]
    r=[rank.get(reg(data[i][0]),10**9) for i in idx]
    print(f"{name:8} positivos con dominio registrable en top-1k:{np.mean([x<=1000 for x in r]):.2%}  top-10k:{np.mean([x<=10000 for x in r]):.2%}  top-100k:{np.mean([x<=100000 for x in r]):.2%}  top-1M:{np.mean([x<=10**6 for x in r]):.2%}")
# 2) hard negatives con allowlist por banda
hard=[l.rstrip('\n').split('\t')[2] for l in open('bench.tsv') if l.split('\t')[1]=='hardneg']
for band in (1000,10000,100000,1000000):
    flagged=[u for u in hard if p_of(u)>th[0.03] and rank.get(reg(u),10**9)>band]
    print(f"allowlist top-{band:>7}: hardneg aún marcados {len(flagged)}/48", [reg(u) for u in flagged][:8])
