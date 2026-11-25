import csv, glob, random, collections, numpy as np, scipy.sparse as sp, pickle
from urllib.parse import urlsplit
from publicsuffix2 import get_sld
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from feat2 import feats2, N
random.seed(9)
def reg(u):
    h=(urlsplit(u if '://' in u else 'http://'+u).hostname or '').lower(); return get_sld(h) or h
by=collections.defaultdict(list)
for f in glob.glob('/home/claude/phishurl-list/20*/*.csv'):
    y=int(f.split('/')[-2])
    for r in csv.DictReader(open(f,encoding='utf-8',errors='ignore')):
        if r.get('URL','').startswith('http'): by[y].append(r['URL'].strip())
def cap(urls,k):
    urls=list(set(urls)); random.shuffle(urls); c=collections.Counter(); out=[]
    for u in urls:
        r=reg(u)
        if c[r]<3: c[r]+=1; out.append(u)
        if len(out)>=k: break
    return out
old=cap(sum((by[y] for y in range(2019,2024)),[]),15000); new=cap(by[2025]+by[2026],8000)
data=pickle.load(open('data.pkl','rb')); legit=[u for u,y,s in data if y==0]; random.shuffle(legit)
neg_tr,neg_te=legit[:26000],legit[26000:]
def M(urls): 
    r=[];c=[];v=[]
    for i,u in enumerate(urls):
        for k,val in feats2(u,False).items(): r.append(i);c.append(k);v.append(val)
    return sp.csr_matrix((v,(r,c)),shape=(len(urls),N))
Xtr=M(old+neg_tr); ytr=np.array([1]*len(old)+[0]*len(neg_tr)); Xte=M(new+neg_te); yte=np.array([1]*len(new)+[0]*len(neg_te))
clf=LogisticRegression(C=3,max_iter=3000,class_weight='balanced',solver='liblinear').fit(Xtr,ytr)
p=clf.predict_proba(Xte)[:,1]; neg=np.sort(p[yte==0])
print('TEMPORAL: train JPCERT 2019-2023 -> test JPCERT 2025-26  AUC=%.4f'%roc_auc_score(yte,p))
for f in (0.003,0.01,0.03,0.05): print(f"  FPR {f:.1%}: recall {(p[yte==1]>neg[int(len(neg)*(1-f))]).mean():.1%}")
