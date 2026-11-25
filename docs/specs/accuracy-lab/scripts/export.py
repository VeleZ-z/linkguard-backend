import pickle, json, numpy as np, time, math, random
from sklearn.linear_model import LogisticRegression
from feat2 import feats2, N
data=pickle.load(open('data.pkl','rb')); X0,y,src,doms=pickle.load(open('X.pkl','rb')); Xb,Xr=pickle.load(open('X2.pkl','rb'))
rng=np.random.RandomState(0); ud=np.unique(doms); test_d=set(rng.choice(ud,int(len(ud)*0.3),replace=False))
te=np.array([d in test_d for d in doms]); tr=~te
clf=LogisticRegression(C=3,max_iter=3000,class_weight='balanced',solver='liblinear').fit(Xb[tr],y[tr])
w=clf.coef_[0]; b=float(clf.intercept_[0]); nz=np.nonzero(w)[0]
art={'version':'proto-1','n_features':N,'bias':b,'weights':{int(i):round(float(w[i]),4) for i in nz}}
s=json.dumps(art,separators=(',',':')); open('model_proto.json','w').write(s); print('pesos no nulos',len(nz),'JSON KB',len(s)//1024)
# umbrales por FPR sobre test de negativos
p_te=clf.predict_proba(Xb[te])[:,1]; yt=y[te]; neg=np.sort(p_te[yt==0])
th={f:float(neg[int(len(neg)*(1-f))]) for f in (0.003,0.01,0.03,0.05)}; print('umbrales',{k:round(v,3) for k,v in th.items()})
for f,t in th.items(): print(f"FPR {f:.1%}: recall in-dist {(p_te[yt==1]>t).mean():.1%} | JPCERT {(p_te[(yt==1)&(src[te]=='jpcert')]>t).mean():.1%} | PhishDB {(p_te[(yt==1)&(src[te]=='phishdb')]>t).mean():.1%}")
# paridad inferencia pura
W={int(k):v for k,v in art['weights'].items()}
def predict(u):
    f=feats2(u,False); z=b+sum(W.get(k,0.0)*v for k,v in f.items()); return 1/(1+math.exp(-z))
sample=random.sample(range(len(data)),500); diffs=max(abs(predict(data[i][0])-clf.predict_proba(Xb[i])[0,1]) for i in sample); print('máx diferencia sklearn vs puro:',f'{diffs:.2e}')
t0=time.perf_counter(); [predict(data[i][0]) for i in sample]; print('latencia media inferencia (ms/URL):',round((time.perf_counter()-t0)/500*1000,3))
# negativos difíciles (no vistos en entrenamiento)
hard=[l.rstrip('\n').split('\t')[2] for l in open('bench.tsv') if l.split('\t')[1]=='hardneg']
for f in (0.01,0.03): 
    fl=[u for u in hard if predict(u)>th[f]]; print(f"hardneg con umbral FPR{f:.0%}: {len(fl)}/{len(hard)} marcados"); [print('   ',u[:90]) for u in fl]
pickle.dump((th,),open('th.pkl','wb'))
