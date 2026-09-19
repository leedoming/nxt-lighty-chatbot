#!/usr/bin/env python3
"""Score saved chatbot responses without calling AWS.
Expected JSONL rows: {id, response}. Gold rows are joined by id.
"""
import argparse,json,re
from pathlib import Path

def norm(s): return re.sub(r'\s+',' ',s or '').strip()
def parse_tags(s):
    out={}
    for tag in ('intro','contents','department'):
        m=re.search(fr'<{tag}>(.*?)</{tag}>',s or '',re.S|re.I)
        out[tag]=norm(m.group(1)) if m else ''
    return out

def fact_recall(resp,groups):
    if not groups:return None
    r=norm(resp).lower(); hits=0
    for aliases in groups:
        if any(norm(a).lower() in r for a in aliases): hits+=1
    return hits/len(groups)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--responses',required=True); ap.add_argument('--gold',default='evaluation/data/golden_seed_v0.jsonl'); ap.add_argument('--out',default='evaluation/results/response_eval.json')
    a=ap.parse_args(); root=Path(__file__).resolve().parents[1]
    gold={x['id']:x for x in (json.loads(l) for l in (root/a.gold).read_text(encoding='utf-8').splitlines() if l.strip())}
    rsp=[json.loads(l) for l in Path(a.responses).read_text(encoding='utf-8').splitlines() if l.strip()]
    rows=[]
    for x in rsp:
        g=gold[x['id']]; p=parse_tags(x.get('response','')); dept=g.get('expected_department')
        rows.append({'id':x['id'],'tag_compliant':bool(p['contents']),
                     'department_exact_match': None if not dept else norm(dept)==norm(p['department']),
                     'required_fact_recall':fact_recall(x.get('response',''),g.get('required_fact_groups',[])),
                     'parsed':p})
    def avg(k):
        vals=[r[k] for r in rows if r[k] is not None]
        return sum(vals)/len(vals) if vals else None
    out={'count':len(rows),'tag_compliance_rate':avg('tag_compliant'),'department_exact_match':avg('department_exact_match'),'required_fact_recall':avg('required_fact_recall'),'rows':rows}
    (root/a.out).write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps({k:v for k,v in out.items() if k!='rows'},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
