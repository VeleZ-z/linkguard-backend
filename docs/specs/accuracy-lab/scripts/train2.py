import pickle, numpy as np, scipy.sparse as sp, random
from feat2 import feats2, N
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
data=pickle.load(open('data.pkl','rb')); X0,y,src,doms=pickle.load(open('X.pkl','rb'))
def build(rules):
    r=[];c=[];v=[]
    for i,(u,_,_) in enumerate(data):
        for k,val in feats2(u,rules).items(): r.append(i);c.append(k);v.append(val)
    return sp.csr_matrix((v,(r,c)),shape=(len(data),N))
Xb=build(False); Xr=build(True)
pickle.dump((Xb,Xr),open('X2.pkl','wb'))
rng=np.random.RandomState(0); ud=np.unique(doms); test_d=set(rng.choice(ud,int(len(ud)*0.3),replace=False))
te=np.array([d in test_d for d in doms]); tr=~te
def ev(X,name,trm,tem):
    clf=LogisticRegression(C=3,max_iter=3000,class_weight='balanced',solver='liblinear').fit(X[trm],y[trm])
    p=clf.predict_proba(X[tem])[:,1]; yt=y[tem]; neg=np.sort(p[yt==0])
    s=[f"FPR{f:.1%}->R {(p[yt==1]>neg[int(len(neg)*(1-f))]).mean():.1%}" for f in (0.005,0.01,0.03)]
    print(f"{name:42} AUC={roc_auc_score(yt,p):.4f} "+' '.join(s)); return clf
ev(X0,'A base',tr,te); ev(Xb,'A + marca-en-lugar-equivocado',tr,te); ev(Xr,'A + marca + flags F01-F11',tr,te)
trB=tr&(src!='jpcert'); teB=te&((y==0)|(src=='jpcert')); trC=tr&(src!='phishdb'); teC=te&((y==0)|(src=='phishdb'))
for nm,X in (('base',X0),('+marca',Xb),('+marca+reglas',Xr)):
    ev(X,f'B PhishDB->JPCERT {nm}',trB,teB); ev(X,f'C JPCERT->PhishDB {nm}',trC,teC)
