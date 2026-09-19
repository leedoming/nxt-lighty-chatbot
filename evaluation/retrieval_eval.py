#!/usr/bin/env python3
import argparse, json, math, os, re, csv
from pathlib import Path
from collections import Counter, defaultdict
import numpy as np
from bs4 import BeautifulSoup
from sklearn.feature_extraction.text import TfidfVectorizer

TOKEN_RE = re.compile(r"[가-힣A-Za-z0-9]+")

def tok(s): return [x.lower() for x in TOKEN_RE.findall(s or "")]
def strip_html(h): return " ".join(BeautifulSoup(h or "", "html.parser").stripped_strings)

def load_corpus(root, title_boost=1):
    docs=[]; sections=[]
    for p in sorted(Path(root).glob('*.json')):
        o=json.loads(p.read_text(encoding='utf-8-sig'))
        mn=str(o.get('mn','')); title=o.get('title',''); dep=o.get('dep')
        ss=o.get('sections') or []
        parts=[]
        for i,s in enumerate(ss):
            st=str(s.get('title','')); c=str(s.get('content',''))
            parts.append(st+'\n'+c)
            prefix=((title+' '+st+' ')*title_boost).strip()
            sections.append({'mn':mn,'title':title,'section_index':i,'section_title':st,'department':dep,
                             'text':(prefix+' '+c).strip()})
        h=strip_html(o.get('html_content',''))
        if not ss and h:
            sections.append({'mn':mn,'title':title,'section_index':None,'section_title':'__html__','department':dep,
                             'text':(((title+' ')*title_boost)+h).strip()})
        if h: parts.append(h)
        docs.append({'mn':mn,'title':title,'section_index':None,'section_title':'__document__','department':dep,
                     'text':(((title+' ')*title_boost)+' '.join(parts)).strip()})
    return docs, sections

class BM25:
    def __init__(self, texts, k1=1.5, b=.75):
        self.k1=k1; self.b=b; self.toks=[tok(x) for x in texts]; self.N=len(self.toks)
        self.avgdl=sum(map(len,self.toks))/max(self.N,1); self.df=Counter()
        for d in self.toks:
            for t in set(d): self.df[t]+=1
        self.idf={t:math.log(1+(self.N-df+.5)/(df+.5)) for t,df in self.df.items()}
    def scores(self,q):
        qt=tok(q); out=[]
        for d in self.toks:
            tf=Counter(d); dl=len(d); s=0.0
            for t in qt:
                if t not in tf: continue
                f=tf[t]; idf=self.idf.get(t,0)
                den=f+self.k1*(1-self.b+self.b*dl/max(self.avgdl,1e-9))
                s += idf*(f*(self.k1+1)/den)
            out.append(s)
        return np.array(out,dtype=float)

def minmax(x):
    x=np.asarray(x,dtype=float)
    if len(x)==0:return x
    lo,hi=float(x.min()),float(x.max())
    if hi-lo < 1e-12: return np.zeros_like(x)
    return (x-lo)/(hi-lo)

def rank_indices(scores): return list(np.argsort(-np.asarray(scores),kind='stable'))

def evaluate(items, queries, mode='bm25', title='run'):
    texts=[x['text'] for x in items]
    bm=BM25(texts)
    vec=None; mat=None
    if mode in ('char','hybrid'):
        vec=TfidfVectorizer(analyzer='char_wb',ngram_range=(2,5),min_df=1,sublinear_tf=True)
        mat=vec.fit_transform(texts)
    rows=[]
    for q in queries:
        bs=bm.scores(q['query'])
        if mode=='bm25': scores=bs
        else:
            qs=vec.transform([q['query']]); cs=(mat @ qs.T).toarray().ravel()
            scores=cs if mode=='char' else 0.55*minmax(bs)+0.45*minmax(cs)
        order=rank_indices(scores)
        top=[]
        for r,idx in enumerate(order[:5],1):
            it=items[idx]; top.append({k:it.get(k) for k in ('mn','title','section_index','section_title','department')} | {'rank':r,'score':float(scores[idx])})
        gold_mn=q['gold_mn']; gold_idx=q.get('gold_section_index')
        doc_rank=next((r for r,idx in enumerate(order,1) if items[idx]['mn']==gold_mn),None)
        sec_rank=None
        if gold_idx is not None:
            sec_rank=next((r for r,idx in enumerate(order,1) if items[idx]['mn']==gold_mn and items[idx].get('section_index')==gold_idx),None)
        dept=q.get('expected_department')
        topdept=items[order[0]].get('department') if order else None
        rows.append({'id':q['id'],'query':q['query'],'gold_mn':gold_mn,'gold_title':q['gold_title'],
                     'gold_section_index':gold_idx,'difficulty':q.get('difficulty'),'category':q.get('category'),
                     'doc_rank':doc_rank,'section_rank':sec_rank,'expected_department':dept,'top1_department':topdept,
                     'department_metadata_match': (dept is not None and dept==topdept), 'top5':top})
    def agg(rank_key, eligible=None):
        rr=[r[rank_key] for r in rows if (eligible(r) if eligible else True)]
        rr=[x for x in rr if x is not None] if False else rr
        n=len(rr)
        if not n:return None
        return {'n':n,'recall@1':sum(x is not None and x<=1 for x in rr)/n,
                'recall@3':sum(x is not None and x<=3 for x in rr)/n,
                'recall@5':sum(x is not None and x<=5 for x in rr)/n,
                'mrr':sum((1/x if x else 0) for x in rr)/n}
    doc=agg('doc_rank')
    sec=agg('section_rank', lambda r:r['gold_section_index'] is not None)
    dept_rows=[r for r in rows if r['expected_department']]
    deptacc=sum(r['department_metadata_match'] for r in dept_rows)/len(dept_rows) if dept_rows else None
    return {'title':title,'mode':mode,'count':len(rows),'document_metrics':doc,'section_metrics':sec,
            'top1_source_department_match':deptacc,'rows':rows}


def evaluate_hierarchical_char(docs, sections, queries, doc_weight=0.45, title='hierarchical_char'):
    dtexts=[x['text'] for x in docs]; stexts=[x['text'] for x in sections]
    dv=TfidfVectorizer(analyzer='char_wb',ngram_range=(2,5),min_df=1,sublinear_tf=True)
    sv=TfidfVectorizer(analyzer='char_wb',ngram_range=(2,5),min_df=1,sublinear_tf=True)
    dm=dv.fit_transform(dtexts); sm=sv.fit_transform(stexts)
    doc_pos={d['mn']:i for i,d in enumerate(docs)}
    rows=[]
    for q in queries:
        dq=dv.transform([q['query']]); sq=sv.transform([q['query']])
        ds=(dm@dq.T).toarray().ravel(); ss=(sm@sq.T).toarray().ravel()
        scores=np.array([doc_weight*ds[doc_pos[s['mn']]]+(1-doc_weight)*ss[i] for i,s in enumerate(sections)])
        order=rank_indices(scores)
        top=[]
        for rnk,idx in enumerate(order[:5],1):
            it=sections[idx]; top.append({k:it.get(k) for k in ('mn','title','section_index','section_title','department')} | {'rank':rnk,'score':float(scores[idx])})
        gold_mn=q['gold_mn']; gold_idx=q.get('gold_section_index')
        doc_rank=next((rnk for rnk,idx in enumerate(order,1) if sections[idx]['mn']==gold_mn),None)
        sec_rank=next((rnk for rnk,idx in enumerate(order,1) if sections[idx]['mn']==gold_mn and sections[idx].get('section_index')==gold_idx),None) if gold_idx is not None else None
        dept=q.get('expected_department'); topdept=sections[order[0]].get('department') if order else None
        rows.append({'id':q['id'],'query':q['query'],'gold_mn':gold_mn,'gold_title':q['gold_title'],'gold_section_index':gold_idx,
                     'difficulty':q.get('difficulty'),'category':q.get('category'),'doc_rank':doc_rank,'section_rank':sec_rank,
                     'expected_department':dept,'top1_department':topdept,'department_metadata_match':(dept is not None and dept==topdept),'top5':top})
    def agg(rank_key, eligible=None):
        rr=[r[rank_key] for r in rows if (eligible(r) if eligible else True)]; n=len(rr)
        return {'n':n,'recall@1':sum(x is not None and x<=1 for x in rr)/n,'recall@3':sum(x is not None and x<=3 for x in rr)/n,
                'recall@5':sum(x is not None and x<=5 for x in rr)/n,'mrr':sum((1/x if x else 0) for x in rr)/n} if n else None
    dept_rows=[r for r in rows if r['expected_department']]
    return {'title':title,'mode':'hierarchical_char','count':len(rows),'document_metrics':agg('doc_rank'),
            'section_metrics':agg('section_rank',lambda r:r['gold_section_index'] is not None),
            'top1_source_department_match':sum(r['department_metadata_match'] for r in dept_rows)/len(dept_rows) if dept_rows else None,'rows':rows}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--corpus',default='evaluation/data/corpus_20250325'); ap.add_argument('--gold',default='evaluation/data/golden_seed_v0.jsonl'); ap.add_argument('--out',default='evaluation/results')
    args=ap.parse_args(); root=Path(__file__).resolve().parents[1]
    corpus=(root/args.corpus); gold=(root/args.gold); out=(root/args.out); out.mkdir(exist_ok=True)
    qs=[json.loads(x) for x in gold.read_text(encoding='utf-8').splitlines() if x.strip()]
    runs=[]
    docs,secs=load_corpus(corpus,title_boost=1)
    _,secs_boost=load_corpus(corpus,title_boost=3)
    runs.append(evaluate(docs,qs,'bm25','whole_document_bm25'))
    runs.append(evaluate(secs,qs,'bm25','section_bm25'))
    runs.append(evaluate(secs,qs,'char','section_char_tfidf'))
    runs.append(evaluate(secs,qs,'hybrid','section_hybrid'))
    runs.append(evaluate(secs_boost,qs,'hybrid','section_hybrid_titleboost'))
    runs.append(evaluate(secs_boost,qs,'char','section_char_titleboost'))
    docs_boost,_=load_corpus(corpus,title_boost=2)
    _,secs_boost2=load_corpus(corpus,title_boost=2)
    runs.append(evaluate_hierarchical_char(docs_boost,secs_boost2,qs,doc_weight=0.45,title='hierarchical_char_titleboost'))
    summary=[]
    for r in runs:
        summary.append({'run':r['title'],**{f'doc_{k}':v for k,v in r['document_metrics'].items() if k!='n'},
                        **({f'section_{k}':v for k,v in r['section_metrics'].items() if k!='n'} if r['section_metrics'] else {}),
                        'top1_source_department_match':r['top1_source_department_match']})
    (out/'preliminary_results.json').write_text(json.dumps({'benchmark':'seed_v0_needs_human_review','summary':summary,'runs':runs},ensure_ascii=False,indent=2),encoding='utf-8')
    with (out/'preliminary_summary.csv').open('w',newline='',encoding='utf-8-sig') as fh:
        cols=sorted({k for x in summary for k in x.keys()}, key=lambda x:(x!='run',x))
        w=csv.DictWriter(fh,fieldnames=cols); w.writeheader(); w.writerows(summary)
    best=max(runs,key=lambda r:r['section_metrics']['mrr'] if r['section_metrics'] else -1)
    failures=[]
    for row in best['rows']:
        if not row['section_rank'] or row['section_rank']>3:
            failures.append({'id':row['id'],'query':row['query'],'gold_title':row['gold_title'],'gold_section_index':row['gold_section_index'],
                             'section_rank':row['section_rank'],'top1_title':row['top5'][0]['title'],'top1_section':row['top5'][0]['section_title']})
    with (out/'failure_cases_best_run.csv').open('w',newline='',encoding='utf-8-sig') as fh:
        cols=['id','query','gold_title','gold_section_index','section_rank','top1_title','top1_section']; w=csv.DictWriter(fh,fieldnames=cols); w.writeheader(); w.writerows(failures)
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
