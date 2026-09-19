#!/usr/bin/env python3
import argparse,csv,json,re,sys
from pathlib import Path
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
from chunking_ab_eval import atomic_chunks,document_texts,rank_indices,fact_coverage
from alias_metadata_eval_v2 import title_query,section_query

def vf(texts):
    v=TfidfVectorizer(analyzer='char_wb',ngram_range=(2,5),min_df=1,sublinear_tf=True)
    return v,v.fit_transform(texts)
def sc(v,m,q):return (m@v.transform([q]).T).toarray().ravel()

def run(items,docs,qs,name,alpha,beta):
    # Base exactly matches the previous best: title-prefixed chunk cosine + title-prefixed doc cosine.
    cv,cm=vf([x['text'] for x in items]);dv,dm=vf([x['text'] for x in docs]);dpos={d['mn']:i for i,d in enumerate(docs)}
    tv,tm=vf([x['title'] for x in items]);sv,sm=vf([x.get('section_title','') or '' for x in items])
    rows=[]
    for q in qs:
        uq=q['query']; tq=title_query(uq); sq=section_query(uq)
        c=sc(cv,cm,uq); d=sc(dv,dm,uq)
        base=np.array([.65*c[i]+.35*d[dpos[it['mn']]] for i,it in enumerate(items)])
        # Positive-only metadata deltas: adding aliases/intents can boost a candidate only when the expanded
        # query improves its metadata match. It cannot penalize the original lexical ranking.
        title_raw=sc(tv,tm,uq); title_exp=sc(tv,tm,tq)
        sec_raw=sc(sv,sm,uq); sec_exp=sc(sv,sm,sq)
        alias_delta=np.maximum(0,title_exp-title_raw) if tq!=uq else np.zeros_like(base)
        intent_delta=np.maximum(0,sec_exp-sec_raw) if sq!=uq else np.zeros_like(base)
        scores=base+alpha*alias_delta+beta*intent_delta
        order=rank_indices(scores);top=[items[i] for i in order[:5]]
        gm=str(q['gold_mn']);gi=q.get('gold_section_index')
        dr=next((r for r,i in enumerate(order,1) if items[i]['mn']==gm),None)
        sr=None if gi is None else next((r for r,i in enumerate(order,1) if items[i]['mn']==gm and items[i].get('section_index')==gi),None)
        fc={k:fact_coverage(top[:k],q.get('required_fact_groups') or []) for k in (1,3,5)}
        rows.append({'id':q['id'],'query':uq,'title_query':tq,'section_query':sq,'category':q.get('category'),'difficulty':q.get('difficulty'),'gold_title':q.get('gold_title'),'gold_mn':gm,'gold_section_index':gi,
                     'doc_rank':dr,'section_rank':sr,'fact_cov_1':fc[1],'fact_cov_3':fc[3],'fact_cov_5':fc[5],
                     'top1_title':top[0]['title'],'top1_section':top[0].get('section_title'),
                     'alias_triggered':tq!=uq,'intent_triggered':sq!=uq})
    def rm(key,f=lambda r:True):
        v=[r[key] for r in rows if f(r)];n=len(v)
        return {'n':n,'r1':sum(x and x<=1 for x in v)/n,'r3':sum(x and x<=3 for x in v)/n,'r5':sum(x and x<=5 for x in v)/n,'mrr':sum(1/x if x else 0 for x in v)/n}
    def fm(f=lambda r:True):
        v=[r for r in rows if f(r) and r['fact_cov_1'] is not None];n=len(v)
        return {'n':n,'@1':(sum(r['fact_cov_1'] for r in v)/n if n else None),'@3':(sum(r['fact_cov_3'] for r in v)/n if n else None),'@5':(sum(r['fact_cov_5'] for r in v)/n if n else None)}
    return {'name':name,'alpha':alpha,'beta':beta,'document':rm('doc_rank'),'section':rm('section_rank',lambda r:r['gold_section_index'] is not None),'fact':fm(),'hard_fact':fm(lambda r:r['difficulty']=='hard'),'rows':rows}

def summ(r):
    return {'run':r['name'],'alpha':r['alpha'],'beta':r['beta'],'dev_score':.3*r['document']['r1']+.25*r['section']['r1']+.25*r['fact']['@1']+.2*r['fact']['@5'],
            'doc_r1':r['document']['r1'],'doc_r3':r['document']['r3'],'doc_r5':r['document']['r5'],'doc_mrr':r['document']['mrr'],
            'section_r1':r['section']['r1'],'section_r3':r['section']['r3'],'section_r5':r['section']['r5'],'section_mrr':r['section']['mrr'],
            'fact_cov_1':r['fact']['@1'],'fact_cov_3':r['fact']['@3'],'fact_cov_5':r['fact']['@5'],'hard_fact_cov_1':r['hard_fact']['@1'],'hard_fact_cov_5':r['hard_fact']['@5']}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--corpus',default=str(HERE/'data/corpus_20250325'));ap.add_argument('--gold',default=str(HERE/'data/golden_seed_v0.jsonl'));ap.add_argument('--out',default=str(HERE/'results'));a=ap.parse_args()
    qs=[json.loads(x) for x in Path(a.gold).read_text(encoding='utf-8').splitlines() if x.strip()]
    items=atomic_chunks(a.corpus,title_boost=2,target=120,max_chars=190,overlap_units=1,augment_html=False);docs=document_texts(a.corpus,title_boost=2)
    grid=[(0,0)]+[(aa,bb) for aa in (.03,.05,.08,.10,.15,.20) for bb in (.02,.03,.05,.08,.10)]
    runs=[run(items,docs,qs,f'G_guarded_a{aa}_b{bb}',aa,bb) for aa,bb in grid]
    # Selection constraint: never sacrifice previous hard-fact@1 or fact@5; among those maximize developmental score.
    ref=runs[0]; eligible=[r for r in runs if r['hard_fact']['@1']>=ref['hard_fact']['@1'] and r['fact']['@5']>=ref['fact']['@5']]
    best=max(eligible,key=lambda r:summ(r)['dev_score'])
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True);ss=[summ(r) for r in runs]
    with (out/'guarded_rerank_summary.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(ss[0].keys()));w.writeheader();w.writerows(ss)
    A={r['id']:r for r in ref['rows']};B={r['id']:r for r in best['rows']};chg=[]
    for q in qs:
        x=A[q['id']];y=B[q['id']]
        if (x['doc_rank'],x['section_rank'],x['fact_cov_1'],x['top1_title'],x['top1_section']) != (y['doc_rank'],y['section_rank'],y['fact_cov_1'],y['top1_title'],y['top1_section']):
            chg.append({'id':q['id'],'query':q['query'],'category':q.get('category'),'difficulty':q.get('difficulty'),'gold_title':q.get('gold_title'),
                        'alias_triggered':y['alias_triggered'],'intent_triggered':y['intent_triggered'],'title_query':y['title_query'],'section_query':y['section_query'],
                        'ref_doc_rank':x['doc_rank'],'new_doc_rank':y['doc_rank'],'ref_section_rank':x['section_rank'],'new_section_rank':y['section_rank'],
                        'ref_fact_cov_1':x['fact_cov_1'],'new_fact_cov_1':y['fact_cov_1'],'ref_top1':f"{x['top1_title']} / {x['top1_section']}",'new_top1':f"{y['top1_title']} / {y['top1_section']}"})
    with (out/'guarded_rerank_changes.csv').open('w',newline='',encoding='utf-8-sig') as f:
        if chg:
            w=csv.DictWriter(f,fieldnames=list(chg[0].keys()));w.writeheader();w.writerows(chg)
    (out/'guarded_rerank_results.json').write_text(json.dumps({'status':'developmental_seed_v0_not_final','selection_constraint':'hard_fact@1 and fact@5 must not regress vs previous best','best_run':best['name'],'reference':summ(ref),'best':summ(best),'all':ss,'changes':chg},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'reference':summ(ref),'best':summ(best),'changed_queries':len(chg)},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
