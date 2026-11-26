import sys, collections
sys.path.insert(0,'/home/claude/linkguard-backend')
from app.normalization import normalize
from app.engine.pipeline import run_rules
from app.scoring.scorer import score_results
rows=[l.rstrip('\n').split('\t') for l in open('bench.tsv')]
stat=collections.defaultdict(collections.Counter); skipped=collections.Counter(); fp=[]
for y,src,u in rows:
    try:
        p=normalize(u); res=run_rules(p); s=score_results(res)
    except Exception as e:
        skipped[src]+=1; continue
    stat[src][s.risk_level.value]+=1
    if y=='0' and s.risk_level.value!='Bajo': fp.append((src,s.score,u,[r.rule_id[:3] for r in res if r.activated]))
print('descartadas por normalizador:',dict(skipped))
for src,c in stat.items():
    n=sum(c.values()); print(f"{src:11} n={n:5} Bajo={c['Bajo']/n:6.1%} Medio={c['Medio']/n:6.1%} Alto={c['Alto']/n:6.1%}")
TP=sum(stat[s]['Medio']+stat[s]['Alto'] for s in ('jpcert','phishdb')); FN=sum(stat[s]['Bajo'] for s in ('jpcert','phishdb'))
FP=sum(stat[s]['Medio']+stat[s]['Alto'] for s in ('top10k','citizenlab','hardneg')); TN=sum(stat[s]['Bajo'] for s in ('top10k','citizenlab','hardneg'))
P=TP/(TP+FP) if TP+FP else 0; R=TP/(TP+FN); print(f"\nTP={TP} FN={FN} FP={FP} TN={TN}  Acc={(TP+TN)/(TP+TN+FP+FN):.3f} Prec={P:.3f} Recall={R:.3f} F1={2*P*R/(P+R) if P+R else 0:.3f}")
print('\nFP (muestra):'); [print(' ',x) for x in fp[:25]]
