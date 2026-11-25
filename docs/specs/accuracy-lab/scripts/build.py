import random, csv, re
random.seed(11)
pos_jp=[(l.split('\t')[1],'jpcert') for l in open('jpcert_sample.tsv')]
links=[l.strip() for l in open('phishing-links-ACTIVE.txt',errors='ignore') if l.strip().startswith('http')]
pos_pd=[(u,'phishdb') for u in random.sample(links,2400)]
tops=[l.strip() for l in open('top-10000-domains') if l.strip()]
neg_top=[('https://'+d.split()[-1] if ' ' in d else 'https://'+d,'top10k') for d in random.sample(tops,1500)]
neg_cl=[]
for r in csv.DictReader(open('global.csv',encoding='utf-8',errors='ignore')):
    u=r['url'].strip()
    if u.startswith('http'): neg_cl.append((u,'citizenlab'))
neg_cl=random.sample(neg_cl,min(1500,len(neg_cl)))
hard="""https://accounts.google.com/signin/v2/identifier?service=mail&continue=https%3A%2F%2Fmail.google.com%2Fmail%2F
https://login.microsoftonline.com/common/oauth2/v2.0/authorize?client_id=4765445b-32c6-49b0-83e6-1d93765276ca&response_type=code
https://www.paypal.com/signin
https://www.paypal.com/us/smarthelp/contact-us
https://secure.bankofamerica.com/login/sign-in/signOnV2Screen.go
https://www.amazon.com/ap/signin?openid.pape.max_auth_age=0&openid.return_to=https%3A%2F%2Fwww.amazon.com%2F
https://appleid.apple.com/sign-in
https://login.live.com/login.srf
https://www.facebook.com/login/
https://github.com/login
https://github.com/settings/security
https://www.linkedin.com/login
https://www.netflix.com/login
https://signin.ebay.com/ws/eBayISAPI.dll?SignIn
https://secure.chase.com/web/auth/dashboard
https://www.chase.com/personal/online-banking
https://login.salesforce.com/
https://www.dropbox.com/login
https://id.atlassian.com/login
https://accounts.spotify.com/en/login
https://www.instagram.com/accounts/login/
https://twitter.com/i/flow/login
https://myaccount.google.com/security
https://support.apple.com/en-us/HT201355
https://www.bancolombia.com/personas/ayuda/seguridad
https://transacciones.bancolombia.com/
https://www.dian.gov.co/Paginas/Inicio.aspx
https://www.pse.com.co/
https://www.mercadolibre.com.co/ayuda/seguridad
https://sucursalvirtual.davivienda.com/
https://www.bbva.es/personas/servicios-digitales/seguridad.html
https://www.santander.com.br/seguranca
https://www.rakuten.co.jp/
https://www.amazon.co.jp/ap/signin
https://login.yahoo.co.jp/config/login
https://www.mufg.jp/
https://www.smbc-card.com/mem/index.jsp
https://myaccount.microsoft.com/?ref=MeControl
https://www.office.com/login
https://docs.google.com/forms/d/e/1FAIpQLSd/viewform?usp=sf_link
https://drive.google.com/file/d/1aBcDeFgHiJkLmNoPqRsTuVwXyZ/view?usp=sharing
https://forms.office.com/Pages/ResponsePage.aspx?id=DQSIkWdsW0yxEjajBLZtrQAAAAAAAAAAAAMAAZ
https://bit.ly/3xYzAbc
https://t.co/aBcDeFgH
https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL123&index=2
https://es.wikipedia.org/wiki/Phishing#Técnicas
https://stackoverflow.com/questions/12345678/how-to-verify-a-user-account-in-django
https://learn.microsoft.com/en-us/azure/active-directory/authentication/concept-authentication-passwordless""".split('\n')
neg_hard=[(u,'hardneg') for u in hard]
allrows=[(u,1,s) for u,s in pos_jp+pos_pd]+[(u,0,s) for u,s in neg_top+neg_cl+neg_hard]
with open('bench.tsv','w') as f:
    for u,y,s in allrows: f.write(f"{y}\t{s}\t{u}\n")
import collections
print(collections.Counter((y,s) for u,y,s in allrows))
