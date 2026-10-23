import csv,gzip,glob,json,sys
csv.field_size_limit(10**9)
import os
D=os.environ.get('FAI_INPUTS','/home/claude/data'); uid=sys.argv[1]; kw=sys.argv[2]
cw=json.load(open(f'{D}/ai-1-core/crosswalk/crosswalk_uei_v2.json'))
PX = json.load(open(f'{D}/ai-1-core/program_exclusions.json')); OPS = set(PX['operations']); FAC = set(PX['facilities'])
ueis={u for u,v in cw.items() if v.get('id')==uid and v['type']=='campus'}
import collections
AWD=collections.defaultdict(lambda: collections.defaultdict(float))
for f in glob.glob(f'{D}/trimmed/*_075_*.csv.gz'):
    for r in csv.DictReader(gzip.open(f,'rt')):
        if r['recipient_uei'] in ueis and r['awarding_sub_agency_name']=='National Institutes of Health' and any(k.lower() in r['awarding_office_name'].lower() for k in kw.split('|')):
            if 'Assistance' in f and (r['assistance_type_code'] not in ('04','05') or r['cfda_number'] in OPS or r['cfda_number'] in FAC): continue
            AWD[r.get('assistance_award_unique_key') or r.get('contract_award_unique_key')][r['action_date_fiscal_year']]+=float(r['federal_action_obligation'] or 0)
raw=0.0
for fys in AWD.values():   # each award floored at zero, as in the build
    bal=0.0
    for fy in sorted(fys): bal=max(bal+fys[fy],0.0)
    raw+=bal
a=json.load(open(os.environ.get('FAI_SITE','site')+'/data/agg.json'))
site=sum(sum(x[4:9]) for x in a['rows'][uid] if any(k.lower() in a['sub'][x[0]][1].lower() for k in kw.split('|')) and x[2]<2)
print(uid,kw,'raw',round(raw/1e6,2),'M  site',round(site/1e6,2),'M')
ok=abs(raw-site)<=len(a['rows'][uid])+5
print('OK' if ok else 'MISMATCH'); sys.exit(0 if ok else 1)
