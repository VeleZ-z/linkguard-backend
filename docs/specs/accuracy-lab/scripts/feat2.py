import re, sys
sys.path.insert(0,'/home/claude/linkguard-backend')
from feat import feats as base_feats, h, split, N
from publicsuffix2 import get_sld, get_tld
from urllib.parse import unquote
top=[l.strip() for l in open('/home/claude/bench/top1m.txt')][:600]
BR=set()
for d in top:
    s=get_sld(d) or d; t=get_tld(d) or ''
    lab=s[:-(len(t)+1)] if t and s.endswith('.'+t) else s
    if len(lab)>=5 and lab.isalpha(): BR.add(lab)
BR|={'paypal','amazon','apple','netflix','microsoft','google','facebook','instagram','whatsapp','binance','coinbase','metamask','rakuten','mercari','docomo','softbank','smbc','mufg','aeon','epos','orico','jcb','yamato','sagawa','usps','dhl','fedex','bancolombia','davivienda','nequi','itau','bradesco','santander','bbva','outlook','office365','onedrive','dropbox','docusign','adobe','steam','roblox'}
MIN_BR=5
def brand_feats(url):
    host,p=split(url)
    sld=get_sld(host) or host; tld=get_tld(host) or ''
    reg=sld[:-(len(tld)+1)] if tld and sld.endswith('.'+tld) else sld
    sub=host[:-(len(sld)+1)] if host.endswith('.'+sld) else ''
    path=unquote((p.path or '')+' '+(p.query or '')).lower()
    toks_sub=set(re.split(r'[^a-z0-9]+',sub)); 
    f={}
    hit_reg=[b for b in BR if b in reg and b!=reg]      # marca embebida en dominio registrable distinto (combosquatting)
    hit_sub=[b for b in BR if (b in sub) and b!=reg]    # marca en subdominio con dominio registrable ajeno
    hit_path=[b for b in BR if (b in path) and b not in reg] # marca en path con dominio ajeno
    if hit_reg: f[h('b_reg')]=1.0
    if hit_sub: f[h('b_sub')]=1.0
    if hit_path: f[h('b_path')]=1.0
    return f
def feats2(url, rules=True):
    f=dict(base_feats(url)); 
    for k,v in brand_feats(url).items(): f[k]=f.get(k,0)+v
    if rules:
        from app.normalization import normalize
        from app.engine.pipeline import run_rules
        try:
            for r in run_rules(normalize(url)):
                if r.activated: f[h('rule:'+r.rule_id)]=1.0
        except Exception: pass
    return f
