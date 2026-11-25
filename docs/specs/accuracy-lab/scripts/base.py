import sys, collections
sys.path.insert(0,'/home/claude/linkguard-backend')
from app.normalization import normalize
from app.engine.pipeline import run_rules
from app.scoring.scorer import score_results
rows=[l.rstrip('\n').split('\t') for l in open('/home/claude/bench/jpcert_sample.tsv')]
lvl=collections.Counter(); byyear=collections.defaultdict(collections.Counter); rules=collections.Counter(); sc=collections.Counter(); err=0
fn=[]
for y,u,d in rows:
    try:
        p=normalize(u); res=run_rules(p); s=score_results(res)
    except Exception as e:
        err+=1; continue
    lvl[s.risk_level.value]+=1; byyear[y][s.risk_level.value]+=1
    sc[s.score]+=1
    for r in res:
        if r.activated: rules[r.rule_id]+=1
    if s.score==0: fn.append(u)
n=sum(lvl.values())
print('n',n,'errores',err)
print({k:f"{v} ({v/n:.1%})" for k,v in lvl.items()})
print('recall si positivo=Medio+Alto:', (lvl['Medio']+lvl['Alto'])/n)
print('recall si positivo=Alto     :', lvl['Alto']/n)
print('score==0:', sc[0], f"{sc[0]/n:.1%}")
for y in sorted(byyear): 
    t=sum(byyear[y].values()); print(y, f"Bajo {byyear[y]['Bajo']/t:.0%}  Medio+ {(t-byyear[y]['Bajo'])/t:.0%}")
print('reglas activadas:', {k:f"{v/n:.1%}" for k,v in rules.most_common()})
import random; random.seed(1)
print('\nejemplos score 0:'); [print('  ',u) for u in random.sample(fn,15)]
