import math, re, zlib, ipaddress
from urllib.parse import urlsplit, unquote
from publicsuffix2 import get_sld, get_tld
N=2**17
VOW=set('aeiou')
def h(s): return zlib.crc32(s.encode())%N
def ent(s):
    if not s: return 0.0
    from collections import Counter
    c=Counter(s); t=len(s); return -sum(v/t*math.log2(v/t) for v in c.values())
def split(url):
    if '://' not in url: url='http://'+url
    p=urlsplit(url.strip()); host=(p.hostname or '').lower().rstrip('.')
    return host,p
def feats(url):
    host,p=split(url)
    f={}
    def add(k,v=1.0): f[h(k)]=f.get(h(k),0)+v
    try: ipaddress.ip_address(host); isip=1
    except: isip=0
    sld=get_sld(host) or host; tld=get_tld(host) or host.rsplit('.',1)[-1]
    reg=sld[:-(len(tld)+1)] if sld.endswith('.'+tld) else sld
    sub=host[:-(len(sld)+1)] if host.endswith('.'+sld) else ''
    labels=[x for x in sub.split('.') if x]
    path=unquote(p.path or ''); q=unquote(p.query or '')
    add('tld='+tld); add('isip',isip)
    # n-gramas del nombre registrable
    r='^'+reg+'$'
    for n in (2,3,4):
        for i in range(len(r)-n+1): add('r%d:'%n+r[i:i+n],1.0)
    # tokens de subdominio
    for l in labels:
        for t in re.split(r'[-_]',l): 
            if t: add('st:'+t[:20])
        add('slen',len(l)/20)
    for t in re.split(r'[^a-z0-9]+',(reg+' '+sub).replace('.',' ')): 
        if t: add('ht:'+t[:20])
    for t in re.split(r'[^a-z0-9]+',(path+' '+q).lower()):
        if t and len(t)<=20: add('pt:'+t)
    ext=re.search(r'\.([a-z0-9]{2,5})$',path.lower()); 
    if ext: add('ext='+ext.group(1))
    # numéricas (todas en [0,~1])
    L=len(reg) or 1
    dig=sum(c.isdigit() for c in reg); hy=reg.count('-')
    vow=sum(c in VOW for c in reg); 
    mr=max((len(m) for m in re.findall(r'[^aeiou0-9\-]+',reg)),default=0)
    add('n_lenreg',min(L,40)/40); add('n_dig',dig/L); add('n_hy',min(hy,5)/5); add('n_vow',vow/L)
    add('n_conrun',min(mr,12)/12); add('n_ent',ent(reg)/5); add('n_nsub',min(len(labels),6)/6)
    add('n_dots',min(host.count('.'),8)/8); add('n_pathlen',min(len(path),100)/100); add('n_qlen',min(len(q),100)/100)
    add('n_depth',min(path.count('/'),8)/8); add('n_https',1.0 if p.scheme=='https' else 0.0)
    add('n_totlen',min(len(url),200)/200); add('n_at','@' in url); add('n_port',1.0 if p.port and p.port not in (80,443) else 0.0)
    add('n_hasq',1.0 if q else 0.0); add('n_emptypath',1.0 if path in ('','/') else 0.0)
    return f
