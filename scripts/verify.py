# independent recompute of FY22-26 totals and each year's dollars straight from the CSVs. A pullback comes off the
# year the money was given (latest first), so no year and no award goes below zero; returns of money obligated before
# FY2022 are not counted.
import csv,gzip,glob,json,collections,re
csv.field_size_limit(10**9)
import os
D=os.environ.get('FAI_INPUTS','/home/claude/data')   # folder holding ai-1-core/ and trimmed/
cw=json.load(open(f'{D}/ai-1-core/crosswalk/crosswalk_uei_v2.json'))
ff=json.load(open(f'{D}/ai-1-core/crosswalk/ffrdc_exclusions.json'))
targets={'214777','131520','199102','187985'}   # Penn State, Howard, NC A&T, New Mexico (largest floored award)
ueis={u:v['id'] for u,v in cw.items() if v.get('id') in targets and v['type']=='campus'}
T=collections.defaultdict(float); TY=collections.defaultdict(lambda:[0.0]*5); AWD=collections.defaultdict(lambda: collections.defaultdict(float))
for f in glob.glob(f'{D}/trimmed/*.csv.gz'):
    c='Contract' in f
    for r in csv.DictReader(gzip.open(f,'rt')):
        u=r['recipient_uei']
        if u not in ueis: continue
        fy=int(r['action_date_fiscal_year'] or 0)
        if not 2022<=fy<=2026: continue
        if not c and r['assistance_type_code'] not in ('04','05'): continue
        if not c and (r['cfda_number'] in ('84.425','93.342','93.364','93.264') or re.match(r'P031[BEKDP]',r['award_id_fain'] or '')): continue
        if c and (r['award_id_piid'] in ff['piids'] or r.get('parent_award_id_piid') in ff['piids']): continue
        k=r['contract_award_unique_key'] if c else r['assistance_award_unique_key']
        AWD[(ueis[u],k)][fy]+=float(r['federal_action_obligation'] or 0)
for (e,k),fys in AWD.items():
    kept={}
    for fy in sorted(fys):
        kept[fy]=max(fys[fy],0.0); need=-fys[fy]
        for p in sorted(kept,reverse=True):
            if need<=0: break
            if p!=fy: t=min(kept[p],need); kept[p]-=t; need-=t
    for fy,v in kept.items(): T[e]+=v; TY[e][fy-2022]+=v
a=json.load(open(os.environ.get('FAI_SITE','site')+'/data/agg.json'))
fail=False
for t in targets:
    rt=T[t]; st=sum(sum(r[4:9]) for r in a['rows'][t] if r[2]!=2 or True)
    tol=len(a['rows'][t])+5   # rounding: up to $1 per stored row
    sy=[sum(r[4+i] for r in a['rows'][t]) for i in range(5)]
    oky=all(abs(x-y)<=tol for x,y in zip(TY[t],sy)) and min(sy)>=0
    ok=abs(rt-st)<=tol and oky; fail|=not ok
    print(f"{t}: raw {rt/1e6:,.2f}M  site {st/1e6:,.2f}M  by year {'same, none below zero' if oky else 'DIFFERENT '+str([round(x/1e6,2) for x in TY[t]])+' vs '+str([round(x/1e6,2) for x in sy])}  {'OK' if ok else 'MISMATCH'}")
import sys; sys.exit(1 if fail else 0)
