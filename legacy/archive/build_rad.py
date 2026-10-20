"""Attach FY2020-24 R&D series (hy) and a unit-quality flag (uq) to each Carnegie-designated institution.
Inputs: rad3.json (Carnegie RAD + IPEDS doctorates), entities.json (from build_herd.py). Output: rad4.json"""
import json
rad=json.load(open('rad3.json')); ent=json.load(open('entities.json'))
comb={u:(k,e['name']) for k,e in ent.items() if e['kind']=='comb' for u in e['units']}
from collections import Counter; c=Counter(); log=[]
for d in rad:
    u=d['u']; car=[None,d['h1'],d['h2'],d['h3'],None]
    if u in comb:
        d['hy']=car; d['uq']={'t':'comb','name':comb[u][1]}; c['comb']+=1; continue
    e=ent.get(u)
    if not e or e['kind']!='u':
        d['hy']=car; d['uq']={'t':'none'}; c['none']+=1; continue
    H=lambda y: (e['tot'].get(str(y)) or 0)*1000 or None
    ser=[H(y) for y in range(2020,2025)]
    diffs={y:(ser[i]-car[i])/car[i] for i,y in [(1,2021),(2,2022),(3,2023)] if car[i] and ser[i]}
    mx=max((abs(v) for v in diffs.values()),default=0)
    if mx<=0.02:
        d['hy']=[ser[0]]+[car[i] or ser[i] for i in (1,2,3)]+[ser[4]]; d['uq']={'t':'ok'}
    elif abs(diffs.get(2021,1))<=0.02:
        # FY2021 matches, a later year doesn't: NSF revised HERD after Carnegie pulled its figures. Use current HERD.
        yrs=[y for y,v in diffs.items() if abs(v)>0.02]
        d['hy']=ser; d['uq']={'t':'rev','yrs':yrs,'p':[round(diffs[y]*100) for y in yrs]}
    elif mx<=0.10 and all(v>0 for v in diffs.values()) or mx<=0.10 and all(v<0 for v in diffs.values()):
        d['hy']=ser; d['uq']={'t':'minor','p':round(sum(diffs.values())/len(diffs)*100,1)}
    else:
        d['hy']=car; d['uq']={'t':'major','p':round(mx*100)}
    c[d['uq']['t']]+=1
    if d['uq']['t']!='ok': log.append((d['n'],d['uq']))
json.dump(rad,open('rad4.json','w'),separators=(',',':'))
print(dict(c)); [print('  ',x) for x in log]
