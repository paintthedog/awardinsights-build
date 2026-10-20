import pandas as pd, glob, json, sys, os
xw=json.load(open('crosswalk_v2.json')); keep=set(u for u,d in xw.items() if d['type']!='exclude')
cols=['assistance_award_unique_key','award_id_fain','federal_action_obligation','action_date','action_date_fiscal_year','awarding_agency_code','awarding_agency_name','awarding_sub_agency_code','awarding_sub_agency_name','awarding_office_name','recipient_uei','recipient_name','assistance_type_code','assistance_type_description','action_type_code','cfda_number','cfda_title','prime_award_base_transaction_description','period_of_performance_start_date','period_of_performance_current_end_date','total_obligated_amount','primary_place_of_performance_zip_4','primary_place_of_performance_state_name']
os.makedirs('bundle/assistance',exist_ok=True)
for f in sorted(glob.glob('usas/*.csv')):
    dest='bundle/assistance/'+os.path.basename(f).replace('.csv','_trim.csv.gz')
    if os.path.exists(dest): continue
    out=[]
    for ch in pd.read_csv(f,usecols=lambda c: c in cols,dtype=str,chunksize=250000,low_memory=False):
        out.append(ch[ch.recipient_uei.isin(keep)])
    d=pd.concat(out); d.to_csv(dest,index=False,compression='gzip'); print(dest,len(d),flush=True)
