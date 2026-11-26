import pickle, numpy as np, collections, random, re
from sklearn.linear_model import LogisticRegression
from urllib.parse import urlsplit
data=pickle.load(open('data.pkl','rb')); X0,y,src,doms=pickle.load(open('X.pkl','rb')); Xb,Xr=pickle.load(open('X2.pkl','rb'))
rng=np.random.RandomState(0); ud=np.unique(doms); test_d=set(rng.choice(ud,int(len(ud)*0.3),replace=False))
te=np.array([d in test_d for d in doms]); tr=~te
trB=tr&(src!='jpcert'); teB=te&((y==0)|(src=='jpcert'))
clf=LogisticRegression(C=3,max_iter=3000,class_weight='balanced',solver='liblinear').fit(Xb[trB],y[trB])
idx=np.where(teB)[0]; p=clf.predict_proba(Xb[idx])[:,1]; yt=y[idx]
th=np.sort(p[yt==0])[int((yt==0).sum()*0.97)]
fn=[idx[i] for i in range(len(idx)) if yt[i]==1 and p[i]<=th]; fp=[idx[i] for i in range(len(idx)) if yt[i]==0 and p[i]>th]
print('umbral(FPR3%)',round(th,3),'FN',len(fn),'FP',len(fp))
random.seed(2)
print('\nFN JPCERT (muestra):'); [print('  ',data[i][0][:110]) for i in random.sample(fn,18)]
print('\nFP legit (muestra):'); [print('  ',data[i][0][:110]) for i in random.sample(fp,14)]
tl=collections.Counter(re.sub(r'.*\.','',urlsplit(data[i][0]).hostname or '') for i in fn); print('\nTLD en FN:',tl.most_common(8))
