# independent recompute of current annual funding and its scheduled-end buckets for one institution
import csv,gzip,glob,json,os,re,sys,collections
csv.field_size_limit(10**9)
D=os.environ.get('FAI_INPUTS','/home/claude/data'); SITE=os.environ.get('FAI_SITE','site'); uid=sys.argv[1]
cw=json.load(open(f'{D}/ai-1-core/crosswalk/crosswalk_uei_v2.json')); ff=json.load(open(f'{D}/ai-1-core/crosswalk/ffrdc_exclusions.json'))
PX = json.load(open(f'{D}/ai-1-core/program_exclusions.json')); OPS = set(PX['operations']); FAC = set(PX['facilities'])
ueis={u for u,v in cw.items() if v.get('id')==uid and v['type']=='campus'}
a=json.load(open(f'{SITE}/data/agg.json')); t0,asof=a['meta']['t12']; e12,e24=a['meta']['end12'],a['meta']['end24']
t12=collections.Counter(); end={}
for f in glob.glob(f'{D}/trimmed/*.csv.gz'):
    con='Contract' in f
    for r in csv.DictReader(gzip.open(f,'rt')):
        if r['recipient_uei'] not in ueis: continue
        if not con and (r['assistance_type_code'] not in ('04','05') or r['cfda_number'] in ('84.425','93.342','93.364','93.264') or r['cfda_number'] in OPS or r['cfda_number'] in FAC or re.match(r'P031[BEKDP]',r['award_id_fain'] or '')): continue
        if con and (r['award_id_piid'] in ff['piids'] or r.get('parent_award_id_piid') in ff['piids']): continue
        k=r['contract_award_unique_key'] if con else r['assistance_award_unique_key']; ad=r['action_date'][:10]
        if ad>=t0: t12[k]+=float(r['federal_action_obligation'] or 0)
        pe=(r['period_of_performance_current_end_date'] or '')[:10]
        if pe and (k not in end or ad>=end[k][1]): end[k]=(pe,ad)
B=[0.0]*5
for k,v in t12.items():
    if v<=0: continue
    e=end.get(k,('',''))[0]; b=4 if not e else 0 if e<asof else 1 if e<=e12 else 2 if e<=e24 else 3; B[b]+=v
site=[0.0]*5
for k_,b,v,n in a['cliff'].get(uid,[]): site[b]+=v
print(uid,'raw',[round(x/1e6,1) for x in B],'site',[round(x/1e6,1) for x in site])
ok=all(abs(x-y)<=len(a['cliff'].get(uid,[]))+5 for x,y in zip(B,site))
print('OK' if ok else 'MISMATCH'); sys.exit(0 if ok else 1)
