"""Assign the R&D expenditure band used across all three tools.
Bands (fixed dollar cutoffs, rounded from FY2024 deciles, agreed 2026-09-24):
  Under $2M · $2–3M · $3–5M · $5–7.5M · $7.5–15M · $15–30M · $30–75M · $75–250M · $250–500M · $500M–1B · $1B+
  plus "No reported R&D" for institutions with no HERD report.
Source figure: exact total R&D from NSF HERD via the crosswalk (FY2024, else FY2023).
Campuses inside a combined HERD report use Carnegie's campus figure (FY2023).
Outputs: universe2.json (Award Insights), profile3.json (Portfolio)."""
import json
M = 1e6
EDGES = [(2, 'Under $2M'), (3, '$2–3M'), (5, '$3–5M'), (7.5, '$5–7.5M'), (15, '$7.5–15M'), (30, '$15–30M'),
         (75, '$30–75M'), (250, '$75–250M'), (500, '$250–500M'), (1000, '$500M–1B'), (1e9, '$1B+')]
NONE = 'No reported R&D'
ORDER = [lab for _, lab in EDGES][::-1] + [NONE]
def band(v):
    if not v or v <= 0: return NONE
    for cut, lab in EDGES:
        if v < cut * M: return lab

ent = json.load(open('entities.json'))
rad = {d['u']: d for d in json.load(open('rad3.json'))}
comb = {u: e for e in ent.values() if e['kind'] == 'comb' for u in e['units']}
def figure(u):
    e = ent.get(u)
    if e and e['kind'] == 'u':
        for y in ('2024', '2023'):
            if e['tot'].get(y): return e['tot'][y] * 1000, int(y), 'HERD'
    if u in comb and u in rad and rad[u]['h3']:
        return rad[u]['h3'], 2023, 'Carnegie campus split'
    return 0, None, None

uni = json.load(open('universe.json'))
from collections import Counter
moved = Counter(); cnt = Counter()
for d in uni:
    v, y, src = figure(d['u'])
    old = d['hb']
    d['herd'] = round(v); d['hb'] = band(v); d['hby'] = y; d['hbs'] = src
    cnt[d['hb']] += 1
json.dump(uni, open('universe2.json', 'w'), separators=(',', ':'))

prof = json.load(open('profile2.json'))
for k, r in prof.items():
    if r['k'] == 'u':
        v, y, _ = figure(k)
    else:
        e = ent[k]; y = '2024' if e['tot'].get('2024') else '2023'; v = e['tot'].get(y, 0) * 1000
    r['hb'] = band(v)
json.dump(prof, open('profile3.json', 'w'), separators=(',', ':'))
json.dump(ORDER, open('band_order.json', 'w'), ensure_ascii=False)
print('Award Insights universe:', {b: cnt[b] for b in ORDER})
