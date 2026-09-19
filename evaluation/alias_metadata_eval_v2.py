#!/usr/bin/env python3
import argparse, csv, json, re, sys
from pathlib import Path
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from chunking_ab_eval import atomic_chunks, document_texts, rank_indices, fact_coverage, evaluate

DOMAIN_ALIASES=[
    (re.compile(r"전과"), "모집단위이동 전공이동"),
    (re.compile(r"졸업\s*유예"), "학사학위취득의 유예 졸업유예"),
    (re.compile(r"복수\s*전공|부전공"), "주전공 부전공 복수전공"),
    (re.compile(r"개명|이름\s*(?:변경|수정)|성명\s*(?:변경|수정)"), "개인정보변경 학적정보 성명변경"),
    (re.compile(r"모바일\s*학생증|카드형\s*학생증"), "학생증발급 학생증"),
    (re.compile(r"졸업증명|성적증명|재학증명|증명서"), "증명발급 증명서"),
    (re.compile(r"수강\s*신청"), "수강정보 수강신청"),
    (re.compile(r"전자\s*출결"), "헤이영캠퍼스 전자출결"),
    (re.compile(r"병결|질병.*결석|공결"), "출석 공결 병결"),
]
INTENT_RULES=[
    (re.compile(r"(언제|몇\s*월|신청\s*기간|신청.*시기|기간.*언제)"), "신청기간 신청시기 일정"),
    (re.compile(r"(서류|증빙|구비|제출.*뭐|무엇.*제출)"), "제출서류 구비서류 증빙서류"),
    (re.compile(r"(절차|신청.*방법|어떻게.*신청|어떻게.*해야)"), "신청절차 신청방법"),
    (re.compile(r"(어디.*문의|문의.*어디|연락처|전화번호)"), "사용문의 문의처 담당부서 연락처"),
]

def title_query(q):
    e=[]
    for p,a in DOMAIN_ALIASES:
        if p.search(q): e.append(a)
    return q + (" "+" ".join(e) if e else "")

def section_query(q):
    e=[]
    for p,a in INTENT_RULES:
        if p.search(q): e.append(a)
    return q + (" "+" ".join(e) if e else "")

def vf(texts):
    v=TfidfVectorizer(analyzer='char_wb',ngram_range=(2,5),min_df=1,sublinear_tf=True)
    return v,v.fit_transform(texts)

def sc(v,m,q): return (m@v.transform([q]).T).toarray().ravel()

def custom(items,docs,qs,name,weights,alias=True,intent=True):
    wc,wd,wt,ws=weights
    cv,cm=vf([x['raw_text'] for x in items])
    dv,dm=vf([x['raw_text'] for x in docs])
    tv,tm=vf([x.get('title','') for x in items])
    sv,sm=vf([x.get('section_title','') or '' for x in items])
    dpos={d['mn']:i for i,d in enumerate(docs)}
    rows=[]
    for q in qs:
        uq=q['query']; tq=title_query(uq) if alias else uq; sq=section_query(uq) if intent else uq
        c=sc(cv,cm,uq); d=sc(dv,dm,uq); t=sc(tv,tm,tq); s=sc(sv,sm,sq)
        scores=np.array([wc*c[i]+wd*d[dpos[it['mn']]]+wt*t[i]+ws*s[i] for i,it in enumerate(items)])
        order=rank_indices(scores); top=[items[i] for i in order[:5]]
        gm=str(q['gold_mn']); gi=q.get('gold_section_index')
        dr=next((r for r,i in enumerate(order,1) if items[i]['mn']==gm),None)
        sr=None if gi is None else next((r for r,i in enumerate(order,1) if items[i]['mn']==gm and items[i].get('section_index')==gi),None)
        fc={k:fact_coverage(top[:k],q.get('required_fact_groups') or []) for k in (1,3,5)}
        rows.append({'id':q['id'],'query':uq,'title_query':tq,'section_query':sq,'category':q.get('category'),'difficulty':q.get('difficulty'),
                     'gold_title':q.get('gold_title'),'gold_mn':gm,'gold_section_index':gi,'doc_rank':dr,'section_rank':sr,
                     'fact_cov_1':fc[1],'fact_cov_3':fc[3],'fact_cov_5':fc[5],
                     'top1_title':top[0]['title'],'top1_section':top[0].get('section_title'),'top1_source':top[0].get('source')})
    def rm(key, filt=lambda r:True):
        vals=[r[key] for r in rows if filt(r)]; n=len(vals)
        return {'n':n,'r1':sum(x and x<=1 for x in vals)/n,'r3':sum(x and x<=3 for x in vals)/n,'r5':sum(x and x<=5 for x in vals)/n,
                'mrr':sum(1/x if x else 0 for x in vals)/n}
    def fm(filt=lambda r:True):
        vals=[r for r in rows if filt(r) and r['fact_cov_1'] is not None]; n=len(vals)
        return {'n':n,'@1':sum(r['fact_cov_1'] for r in vals)/n,'@3':sum(r['fact_cov_3'] for r in vals)/n,'@5':sum(r['fact_cov_5'] for r in vals)/n}
    return {'name':name,'weights':weights,'document':rm('doc_rank'),'section':rm('section_rank',lambda r:r['gold_section_index'] is not None),
            'fact':fm(),'hard_fact':fm(lambda r:r['difficulty']=='hard'),'rows':rows}

def summarize(r):
    name=r.get('name',r.get('title'))
    fact=r.get('fact',r.get('fact_coverage'))
    hard=r.get('hard_fact',r.get('hard_fact_coverage'))
    return {'run':name,'dev_score':.3*r['document']['r1']+.25*r['section']['r1']+.25*fact['@1']+.2*fact['@5'],
            'doc_r1':r['document']['r1'],'doc_r3':r['document']['r3'],'doc_r5':r['document']['r5'],'doc_mrr':r['document']['mrr'],
            'section_r1':r['section']['r1'],'section_r3':r['section']['r3'],'section_r5':r['section']['r5'],'section_mrr':r['section']['mrr'],
            'fact_cov_1':fact['@1'],'fact_cov_3':fact['@3'],'fact_cov_5':fact['@5'],
            'hard_fact_cov_1':hard['@1'],'hard_fact_cov_5':hard['@5'],'weights':json.dumps(r.get('weights'),ensure_ascii=False)}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--corpus',default=str(HERE/'data/corpus_20250325'));ap.add_argument('--gold',default=str(HERE/'data/golden_seed_v0.jsonl'));ap.add_argument('--out',default=str(HERE/'results')); a=ap.parse_args()
    qs=[json.loads(x) for x in Path(a.gold).read_text(encoding='utf-8').splitlines() if x.strip()]
    # Exact previous best configuration for fair reference.
    ref_items=atomic_chunks(a.corpus,title_boost=2,target=120,max_chars=190,overlap_units=1,augment_html=False)
    ref_docs=document_texts(a.corpus,title_boost=2)
    ref=evaluate(ref_items,qs,'hier_char','REF_previous_best_C_hier_atomic_t120_m190_o1',docs=ref_docs,doc_weight=.35)
    # Custom models use explicit metadata and no hidden title repetition.
    items=atomic_chunks(a.corpus,title_boost=0,target=120,max_chars=190,overlap_units=1,augment_html=False)
    docs=document_texts(a.corpus,title_boost=0)
    runs=[ref]
    for name,w,al,it in [
        ('M1_metadata_raw_query',(.55,.25,.12,.08),False,False),
        ('M2_metadata_intent',(.55,.25,.10,.10),False,True),
        ('M3_alias_metadata_light',(.55,.25,.12,.08),True,True),
        ('M4_alias_title_focus',(.52,.23,.18,.07),True,True),
        ('M5_alias_heading_balanced',(.50,.22,.16,.12),True,True),
        ('M6_low_metadata',(.60,.28,.08,.04),True,True),
        ('M7_heading_focus',(.50,.22,.10,.18),True,True),
    ]:
        runs.append(custom(items,docs,qs,name,w,al,it))
    sums=[summarize(r) for r in runs]; best=max(runs,key=lambda r:summarize(r)['dev_score'])
    out=Path(a.out);out.mkdir(exist_ok=True,parents=True)
    with (out/'alias_metadata_v2_summary.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(sums[0].keys()));w.writeheader();w.writerows(sums)
    # Normalize ref row field names for detailed comparison
    def rmap(r): return {x['id']:x for x in r['rows']}
    A=rmap(ref);B=rmap(best); changes=[]
    for q in qs:
        x=A[q['id']];y=B[q['id']]
        changes.append({'id':q['id'],'query':q['query'],'category':q.get('category'),'difficulty':q.get('difficulty'),'gold_title':q.get('gold_title'),
                        'ref_doc_rank':x['doc_rank'],'new_doc_rank':y['doc_rank'],'ref_section_rank':x['section_rank'],'new_section_rank':y['section_rank'],
                        'ref_fact_cov_1':x['fact_cov_1'],'new_fact_cov_1':y['fact_cov_1'],
                        'ref_top1':f"{x['top1_title']} / {x['top1_section']}", 'new_top1':f"{y['top1_title']} / {y['top1_section']}",
                        'title_query':y.get('title_query',q['query']),'section_query':y.get('section_query',q['query'])})
    with (out/'alias_metadata_v2_query_changes.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(changes[0].keys()));w.writeheader();w.writerows(changes)
    (out/'alias_metadata_v2_results.json').write_text(json.dumps({'status':'developmental_seed_v0_not_final','best_run':best.get('name',best.get('title')),'summary':sums,'runs':runs},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'best':best.get('name',best.get('title')),'summary':sums},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
