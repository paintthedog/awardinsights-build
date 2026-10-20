import json
S='/tmp/claude-0/-home-claude/58faae40-86c1-5b8b-9350-77761ee4f132/scratchpad/'
u=open(S+'universe3.json').read(); n=f"{len(json.loads(u)):,}"
cov=json.load(open(S+'coverage.json'))
def money(d): return f"${d/1e9:.2f}B" if d>=1e9 else f"${d/1e6:.0f}M"
b=(open(S+'tpl.html').read().replace('__N__',n).replace('__UNIVERSE__',u).replace('__AWARDS__',open(S+'awards4.json').read())
   .replace('__PROGINFO__',open(S+'proginfo.json').read()).replace('__COV__',json.dumps(cov))
   .replace('__NALL__',f"{cov['n_all']:,}").replace('__DALL__',money(cov['d_all'])).replace('__NIN__',f"{cov['n_in']:,}").replace('__DIN__',money(cov['d_in'])).replace('__DPCT__',f"{100*cov['d_in']/cov['d_all']:.0f}%"))
open('/mnt/attach/outputs/nsf_peer_finder.html','w').write(b)
print(len(b))
