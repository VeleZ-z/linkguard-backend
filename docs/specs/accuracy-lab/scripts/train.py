import pickle, random, numpy as np, scipy.sparse as sp, collections, time
from urllib.parse import urlsplit
from publicsuffix2 import get_sld
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from feat import feats, N
random.seed(3)
data=pickle.load(open('data.pkl','rb'))
t=time.time()
def reg(u):
    h=(urlsplit(u if '://' in u else 'http://'+u).hostname or '').lower(); return get_sld(h) or h
rows=[];cols=[];vals=[]
for i,(u,y,s) in enumerate(data):
    for k,v in feats(u).items(): rows.append(i);cols.append(k);vals.append(v)
X=sp.csr_matrix((vals,(rows,cols)),shape=(len(data),N)); y=np.array([d[1] for d in data]); src=np.array([d[2] for d in data])
doms=np.array([reg(d[0]) for d in data])
print('featurizado',X.shape,f'{time.time()-t:.0f}s')
pickle.dump((X,y,src,doms),open('X.pkl','wb'))
def metrics(clf,Xt,yt,name):
    p=clf.predict_proba(Xt)[:,1]; auc=roc_auc_score(yt,p)
    neg=np.sort(p[yt==0])
    out=[]
    for fpr in (0.01,0.03,0.05):
        th=neg[int(len(neg)*(1-fpr))]; rec=(p[yt==1]>th).mean(); out.append(f"FPR{fpr:.0%}->Recall {rec:.1%}")
    print(f"{name:34} AUC={auc:.4f}  "+'  '.join(out))
    return p
# A) split aleatorio agrupado por dominio
ud=np.unique(doms); random.shuffle(list(ud)); rng=np.random.RandomState(0); test_d=set(rng.choice(ud,int(len(ud)*0.3),replace=False))
te=np.array([d in test_d for d in doms]); tr=~te
for C in (0.3,1,3):
    clf=LogisticRegression(C=C,max_iter=2000,class_weight='balanced',solver='liblinear').fit(X[tr],y[tr])
    metrics(clf,X[te],y[te],f'A grupo-dominio C={C}')
# B) cross-source: entrenar con phishdb+legit(70%), probar JPCERT + legit(30%)
neg_te=te&(y==0); 
trB=tr&(src!='jpcert'); teB=(te&(y==0))|(src=='jpcert')&te
clf=LogisticRegression(C=1,max_iter=2000,class_weight='balanced',solver='liblinear').fit(X[trB],y[trB])
metrics(clf,X[teB],y[teB],'B train PhishDB -> test JPCERT')
trC=tr&(src!='phishdb'); teC=(te&(y==0))|((src=='phishdb')&te)
clf2=LogisticRegression(C=1,max_iter=2000,class_weight='balanced',solver='liblinear').fit(X[trC],y[trC])
metrics(clf2,X[teC],y[teC],'C train JPCERT -> test PhishDB')
