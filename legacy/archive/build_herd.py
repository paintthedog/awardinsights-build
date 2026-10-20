"""Rebuild HERD-derived data for the Portfolio Trends and Designations tools.

Inputs : herd/{year}/herd{year}.csv (NSF HERD microdata, FY2020-24), crosswalk.json,
         universe.json (IPEDS/Carnegie attributes), profile.json (previous build, for regression check)
Outputs: entities.json  - every reporting entity with agency/source/field series ($ thousands)
         profile2.json  - Portfolio Trends data
"""
import csv, json, sys
from collections import defaultdict

YEARS = [2020, 2021, 2022, 2023, 2024]
FEDQ, NONQ = 'Federal expenditures by field and agency', 'Nonfederal expenditures by field and source'
AGENCIES = ['NSF', 'HHS', 'DOD', 'DOE', 'NASA', 'USDA', 'Other agencies']
SOURCES = ['Institution funds', 'State and local government', 'Business', 'Nonprofit organziations', 'All other sources']
FIELDS = {  # HERD "<field>, all" row -> Portfolio label
    'Life sciences, all': 'Life sciences', 'Engineering, all': 'Engineering', 'Physical sciences, all': 'Physical sciences',
    'Computer and information sciences, all': 'Computer & info sci', 'Mathematics and statistics, all': 'Math & statistics',
    'Psychology, all': 'Psychology', 'Social sciences, all': 'Social sciences', 'Non-S&E, all': 'Non-S&E',
    'Geosciences, atmospheric sciences, and ocean sciences, all': 'Geosciences', 'Other sciences, all': 'Other sciences'}

# ---- 1. read HERD per inst_id ----
ag = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
fld = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
name, unitid = {}, defaultdict(dict)
for y in YEARS:
    with open(f'herd/{y}/herd{y}.csv', encoding='latin-1') as f:
        for r in csv.DictReader(f):
            q = r['question']
            if q not in (FEDQ, NONQ):
                continue
            k = r['inst_id']; name[k] = r['inst_name_long']; unitid[k][y] = r['ipeds_unitid'].strip()
            v = float(r['data'] or 0)
            if r['row'] == 'All' and r['column'] != 'Total':
                ag[k][y][r['column']] += v
            if r['row'] in FIELDS and r['column'] == 'Total':
                fld[k][y][FIELDS[r['row']]] += v

# ---- 2. assign inst_ids to entities ----
xw = json.load(open('crosswalk.json'))
by_unit = defaultdict(set)
for k, ys in unitid.items():
    for y, u in ys.items():
        if u: by_unit[u].add(k)
ent_of = {}          # inst_id -> entity key
meta = {}            # entity key -> dict
claimed = set()
for key, c in xw['combined'].items():
    ks = set()
    for h in c['herd']:
        ks |= by_unit[h[1:]] if h.startswith('@') else {h}
    for k in ks: ent_of[k] = key
    meta[key] = {'kind': 'comb', 'name': c['name'], 'units': c['units'], 'flag': c['flag'], 'why': c.get('why', '')}
    claimed |= set(c['units'])
for key, c in xw['independent'].items():
    for k in c['herd']: ent_of[k] = key
    meta[key] = {'kind': 'ind', 'name': c['name'], 'st': c['st']}
for sect in ('link', 'piece'):
    for k, c in xw[sect].items():
        ent_of[k] = c['u']
drop = set(xw['drop'])
unmapped = []
for k, ys in unitid.items():
    if k in ent_of or k in drop:
        continue
    us = {u for u in ys.values() if u}
    if len(us) == 1:
        u = us.pop()
        ent_of[k] = u
    else:
        unmapped.append((k, name[k], ys))
for k, u in list(ent_of.items()):
    if u in claimed:     # a unit that belongs to a combined entity
        raise SystemExit(f'{k} maps to {u}, which is inside a combined entity; fix crosswalk')

# ---- 3. aggregate ----
E = {}
for k, e in ent_of.items():
    d = E.setdefault(e, {'ag': defaultdict(lambda: defaultdict(float)), 'fld': defaultdict(lambda: defaultdict(float)), 'inst': []})
    d['inst'].append(k)
    for y in YEARS:
        for a, v in ag[k].get(y, {}).items(): d['ag'][y][a] += v
        for a, v in fld[k].get(y, {}).items(): d['fld'][y][a] += v
def total(d, y): return sum(d['ag'].get(y, {}).values())
out = {}
for e, d in E.items():
    tot = {y: total(d, y) for y in YEARS if total(d, y) > 0}
    if not tot:
        continue
    out[e] = {'inst': sorted(d['inst']), 'names': sorted({name[k] for k in d['inst']}),
              'tot': {y: round(v) for y, v in tot.items()},
              'ag': {y: {a: round(v) for a, v in d['ag'][y].items() if round(v)} for y in YEARS if y in tot},
              'fld': {y: {a: round(v) for a, v in d['fld'][y].items() if round(v)} for y in YEARS if y in tot},
              **meta.get(e, {'kind': 'u'})}
json.dump(out, open('entities.json', 'w'))
print('entities:', len(out), '| unmapped inst_ids:', len(unmapped))
for x in unmapped: print('  UNMAPPED', x)

# ---- 4. Portfolio profile ----
uni = {e['u']: e for e in json.load(open('universe.json'))}
old = json.load(open('profile.json'))
ATTR = ['ct', 'reg', 'hbcu', 'hsi', 'msi', 'lg', 'aau', 'aplu', 'ep', 'hb', 'alf', 'sz', 'cce', 'wo']
prof = {}
for e, d in out.items():
    rec = {'ag': {str(y): v for y, v in d['ag'].items()}, 'fld': {str(y): v for y, v in d['fld'].items()}, 'k': d['kind']}
    if d['kind'] == 'u':
        u = uni.get(e)
        if u is None and e in old:          # keep previous attributes if IPEDS universe lacks it
            rec.update({a: old[e][a] for a in ['n', 'st', 'des'] + ATTR if a in old[e]})
        elif u is None:
            rec.update({'n': d['names'][0], 'st': '', 'des': ''})
        else:
            rec.update({'n': old[e]['n'] if e in old else u['n'], 'st': u['s'], 'des': u['t'] if u['t'] in ('R1', 'R2', 'RCU') else ''})
            rec.update({a: u.get(a) for a in ATTR})
    elif d['kind'] == 'comb':
        f = uni[d['flag']]
        rec.update({'n': d['name'], 'st': f['s'], 'des': ' + '.join(uni[x]['t'] if uni[x]['t'] in ('R1', 'R2', 'RCU') else '—' for x in d['units']),
                    'units': d['units'], 'ct': f['ct'], 'reg': f['reg'], 'why': d.get('why', '')})
    else:
        rec.update({'n': d['name'], 'st': d['st'], 'des': ''})
    prof[e] = rec
json.dump(prof, open('profile2.json', 'w'), separators=(',', ':'))

# ---- 5. regression vs previous build ----
same = diff = 0; diffs = []
for e, r in old.items():
    if e not in prof:
        diffs.append(('MISSING NOW', e, r['n'])); continue
    a, b = r['ag'], prof[e]['ag']
    ok = all(abs(sum(a.get(y, {}).values()) - sum(b.get(y, {}).values())) < 2 for y in map(str, YEARS))
    same += ok; diff += (not ok)
    if not ok: diffs.append(('CHANGED', e, r['n']))
print(f'regression: {same} unchanged, {diff} changed, {len(prof) - len(old)} net new')
for x in diffs: print('  ', x)
