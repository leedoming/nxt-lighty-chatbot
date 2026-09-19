#!/usr/bin/env python3
import argparse, json, math, re, csv
from pathlib import Path
from collections import Counter, defaultdict
import numpy as np
from bs4 import BeautifulSoup
from sklearn.feature_extraction.text import TfidfVectorizer

TOKEN_RE = re.compile(r"[가-힣A-Za-z0-9]+")

def tok(s): return [x.lower() for x in TOKEN_RE.findall(s or "")]
def norm(s): return re.sub(r"\s+", "", (s or "").lower())
def strip_html(h): return " ".join(BeautifulSoup(h or "", "html.parser").stripped_strings)

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

def rank_indices(scores): return list(np.argsort(-np.asarray(scores),kind='stable'))

def load_jsons(root):
    out=[]
    for p in sorted(Path(root).glob('*.json')):
        try: o=json.loads(p.read_text(encoding='utf-8-sig'))
        except Exception: continue
        out.append((p,o))
    return out

def baseline_sections(root, title_boost=2):
    items=[]
    for p,o in load_jsons(root):
        mn=str(o.get('mn','')); title=str(o.get('title','')); dep=o.get('dep')
        for i,s in enumerate(o.get('sections') or []):
            st=str(s.get('title','')); c=str(s.get('content',''))
            prefix=((title+' '+st+' ')*title_boost).strip()
            items.append({'mn':mn,'title':title,'section_index':i,'section_title':st,'sub_index':0,
                          'department':dep,'raw_text':c,'text':(prefix+' '+c).strip(),'source':'section'})
    return items

def split_units(text):
    # Keep line-level facts when the source uses lists/tables; otherwise split long prose sentences.
    lines=[x.strip(' \t-•·') for x in re.split(r'\n+', text or '') if x.strip()]
    units=[]
    for line in lines:
        if len(line) <= 180:
            units.append(line); continue
        # Korean prose often has sentence-final punctuation. Split cautiously.
        parts=[p.strip() for p in re.split(r'(?<=[.!?])\s+', line) if p.strip()]
        if len(parts)==1:
            # Fallback: semicolon / parenthesized clauses can still form large units.
            parts=[p.strip() for p in re.split(r'(?<=다\.)\s+|(?<=함\.)\s+|(?<=됨\.)\s+', line) if p.strip()]
        units.extend(parts or [line])
    return units

def group_units(units, target=150, max_chars=230, overlap_units=1):
    if not units: return []
    chunks=[]; cur=[]; cur_len=0
    for u in units:
        # A single short line is often an atomic rule; group until target, but don't merge beyond max.
        add=len(u)+(1 if cur else 0)
        if cur and cur_len >= target and cur_len+add > max_chars:
            chunks.append('\n'.join(cur))
            cur=cur[-overlap_units:] if overlap_units else []
            cur_len=sum(len(x) for x in cur)+max(0,len(cur)-1)
        cur.append(u); cur_len += add
        if cur_len >= max_chars:
            chunks.append('\n'.join(cur))
            cur=cur[-overlap_units:] if overlap_units else []
            cur_len=sum(len(x) for x in cur)+max(0,len(cur)-1)
    if cur:
        c='\n'.join(cur)
        if not chunks or c != chunks[-1]: chunks.append(c)
    return chunks

def parse_html_to_blocks(html):
    if not html: return []
    soup=BeautifulSoup(html,'html.parser')
    blocks=[]
    # Tables: each row becomes an atomic retrieval unit with cell boundaries preserved.
    for table in soup.find_all('table'):
        headers=[]
        first=table.find('tr')
        if first:
            headers=[x.get_text(' ',strip=True) for x in first.find_all(['th','td'])]
        for ri,tr in enumerate(table.find_all('tr')):
            cells=[x.get_text(' ',strip=True) for x in tr.find_all(['th','td'])]
            if not cells or (ri==0 and headers and cells==headers): continue
            if headers and len(headers)==len(cells):
                txt=' | '.join(f'{h}: {v}' for h,v in zip(headers,cells) if v)
            else:
                txt=' | '.join(cells)
            if txt.strip(): blocks.append(txt)
        table.decompose()
    # Remaining prose/list content.
    for tag in soup.find_all(['p','li','h2','h3','h4']):
        t=tag.get_text(' ',strip=True)
        if t and len(t)>=8: blocks.append(t)
    # De-duplicate while preserving order.
    seen=set(); out=[]
    for b in blocks:
        k=norm(b)
        if k and k not in seen:
            seen.add(k); out.append(b)
    return out

def atomic_chunks(root, title_boost=2, target=150, max_chars=230, overlap_units=1, augment_html=True):
    items=[]
    for p,o in load_jsons(root):
        mn=str(o.get('mn','')); title=str(o.get('title','')); dep=o.get('dep'); sections=o.get('sections') or []
        section_norms=[]
        for i,s in enumerate(sections):
            st=str(s.get('title','')); c=str(s.get('content','')); section_norms.append(norm(c))
            chunks=group_units(split_units(c),target,max_chars,overlap_units) or ([c] if c else [])
            for j,ch in enumerate(chunks):
                prefix=((title+' '+st+' ')*title_boost).strip()
                items.append({'mn':mn,'title':title,'section_index':i,'section_title':st,'sub_index':j,
                              'department':dep,'raw_text':ch,'text':(prefix+' '+ch).strip(),'source':'section_atomic'})
        section_total=sum(len(str(s.get('content',''))) for s in sections)
        html_text_len=len(strip_html(o.get('html_content','')))
        use_html = bool(augment_html and o.get('html_content'))
        if augment_html == 'sparse':
            use_html = bool(o.get('html_content')) and (section_total == 0 or (section_total < 300 and html_text_len > max(500, section_total*2)))
        if use_html:
            html_blocks=parse_html_to_blocks(o.get('html_content',''))
            # Add only HTML blocks that are not substantially duplicates of section text.
            for j,b in enumerate(html_blocks):
                nb=norm(b)
                if not nb: continue
                if any((nb in s or s in nb) and min(len(nb),len(s))>20 for s in section_norms if s):
                    continue
                prefix=((title+' html ')*title_boost).strip()
                items.append({'mn':mn,'title':title,'section_index':None,'section_title':'__html_extra__','sub_index':j,
                              'department':dep,'raw_text':b,'text':(prefix+' '+b).strip(),'source':'html_extra'})
    return items

def document_texts(root,title_boost=2):
    docs=[]
    for p,o in load_jsons(root):
        mn=str(o.get('mn','')); title=str(o.get('title','')); dep=o.get('dep')
        sec=' '.join(str(s.get('title',''))+' '+str(s.get('content','')) for s in (o.get('sections') or []))
        h=strip_html(o.get('html_content',''))
        raw=(sec+' '+h).strip()
        docs.append({'mn':mn,'title':title,'department':dep,'raw_text':raw,'text':(((title+' ')*title_boost)+raw).strip()})
    return docs

def fact_coverage(top_items, fact_groups):
    if not fact_groups: return None
    hay=norm('\n'.join(x.get('raw_text','') for x in top_items))
    got=0
    for group in fact_groups:
        aliases=group if isinstance(group,list) else [group]
        if any(norm(a) in hay for a in aliases if a): got += 1
    return got/len(fact_groups) if fact_groups else None

def evaluate(items, queries, mode='char', title='run', docs=None, doc_weight=None):
    texts=[x['text'] for x in items]
    bm=BM25(texts)
    vec=TfidfVectorizer(analyzer='char_wb',ngram_range=(2,5),min_df=1,sublinear_tf=True)
    mat=vec.fit_transform(texts)
    if docs is not None:
        dv=TfidfVectorizer(analyzer='char_wb',ngram_range=(2,5),min_df=1,sublinear_tf=True)
        dm=dv.fit_transform([x['text'] for x in docs]); doc_pos={d['mn']:i for i,d in enumerate(docs)}
    rows=[]
    for q in queries:
        qs=vec.transform([q['query']]); cs=(mat@qs.T).toarray().ravel()
        if mode=='bm25': scores=bm.scores(q['query'])
        elif mode=='char': scores=cs
        elif mode=='hier_char':
            dq=dv.transform([q['query']]); ds=(dm@dq.T).toarray().ravel()
            scores=np.array([doc_weight*ds[doc_pos[it['mn']]]+(1-doc_weight)*cs[i] for i,it in enumerate(items)])
        else: raise ValueError(mode)
        order=rank_indices(scores)
        top=[items[i] for i in order[:5]]
        gold_mn=str(q['gold_mn']); gold_idx=q.get('gold_section_index')
        doc_rank=next((r for r,i in enumerate(order,1) if items[i]['mn']==gold_mn),None)
        sec_rank=None
        if gold_idx is not None:
            sec_rank=next((r for r,i in enumerate(order,1) if items[i]['mn']==gold_mn and items[i].get('section_index')==gold_idx),None)
        fc={k:fact_coverage(top[:k],q.get('required_fact_groups') or []) for k in (1,3,5)}
        rows.append({'id':q['id'],'query':q['query'],'gold_title':q['gold_title'],'gold_mn':gold_mn,'gold_section_index':gold_idx,
                     'difficulty':q.get('difficulty'),'category':q.get('category'),'doc_rank':doc_rank,'section_rank':sec_rank,
                     'fact_cov_1':fc[1],'fact_cov_3':fc[3],'fact_cov_5':fc[5],
                     'top1_title':top[0]['title'] if top else None,'top1_section':top[0].get('section_title') if top else None,
                     'top1_source':top[0].get('source') if top else None})
    def agg_rank(key, eligible=None):
        rr=[r[key] for r in rows if (eligible(r) if eligible else True)]; n=len(rr)
        return {'n':n,'r1':sum(x is not None and x<=1 for x in rr)/n,'r3':sum(x is not None and x<=3 for x in rr)/n,
                'r5':sum(x is not None and x<=5 for x in rr)/n,'mrr':sum((1/x if x else 0) for x in rr)/n} if n else {}
    def avg(key, subset=None):
        vals=[r[key] for r in rows if r[key] is not None and (subset(r) if subset else True)]
        return sum(vals)/len(vals) if vals else None
    doc=agg_rank('doc_rank'); sec=agg_rank('section_rank',lambda r:r['gold_section_index'] is not None)
    hard=lambda r:r.get('difficulty')=='hard'
    return {'title':title,'item_count':len(items),'document':doc,'section':sec,
            'fact_coverage':{'@1':avg('fact_cov_1'),'@3':avg('fact_cov_3'),'@5':avg('fact_cov_5')},
            'hard_fact_coverage':{'@1':avg('fact_cov_1',hard),'@3':avg('fact_cov_3',hard),'@5':avg('fact_cov_5',hard)},
            'rows':rows}

def category_summary(rows):
    d=defaultdict(list)
    for r in rows: d[r.get('category') or 'unknown'].append(r)
    out=[]
    for cat,rs in sorted(d.items()):
        out.append({'category':cat,'n':len(rs),
                    'doc_r1':sum((x['doc_rank'] or 999)<=1 for x in rs)/len(rs),
                    'section_r1':sum((x['section_rank'] or 999)<=1 for x in rs)/len(rs),
                    'fact_cov_1':sum(x['fact_cov_1'] or 0 for x in rs)/len(rs),
                    'fact_cov_5':sum(x['fact_cov_5'] or 0 for x in rs)/len(rs)})
    return out

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--corpus',default='evaluation/data/corpus_20250325'); ap.add_argument('--gold',default='evaluation/data/golden_seed_v0.jsonl'); ap.add_argument('--out',default='evaluation/results')
    args=ap.parse_args(); root=Path(__file__).resolve().parents[1]
    corpus=root/args.corpus; qs=[json.loads(x) for x in (root/args.gold).read_text(encoding='utf-8').splitlines() if x.strip()]; out=root/args.out; out.mkdir(exist_ok=True)
    docs=document_texts(corpus,title_boost=2)
    variants=[]
    base=baseline_sections(corpus,title_boost=2)
    variants.append(evaluate(base,qs,'char','A_baseline_section_char',docs=docs))
    # Grid of fact-aware chunk sizes; all developmental, selected on seed benchmark only.
    for target,maxc,ov in [(90,150,0),(120,190,0),(120,190,1),(150,230,0),(150,230,1),(180,280,1)]:
        items=atomic_chunks(corpus,title_boost=2,target=target,max_chars=maxc,overlap_units=ov,augment_html=False)
        variants.append(evaluate(items,qs,'char',f'B_atomic_t{target}_m{maxc}_o{ov}',docs=docs))
        variants.append(evaluate(items,qs,'hier_char',f'C_hier_atomic_t{target}_m{maxc}_o{ov}',docs=docs,doc_weight=.35))
    # Ingestion completeness variant: include non-duplicate HTML-only facts.
    items=atomic_chunks(corpus,title_boost=2,target=120,max_chars=190,overlap_units=1,augment_html=True)
    variants.append(evaluate(items,qs,'hier_char','D_hier_atomic_plus_all_html',docs=docs,doc_weight=.35))
    items=atomic_chunks(corpus,title_boost=2,target=120,max_chars=190,overlap_units=1,augment_html='sparse')
    variants.append(evaluate(items,qs,'hier_char','E_hier_atomic_plus_sparse_html',docs=docs,doc_weight=.35))
    def score(v):
        # balanced developmental score: source identification + evidence coverage, avoid optimizing only one metric
        return .3*v['document']['r1']+.25*v['section']['r1']+.25*v['fact_coverage']['@1']+.2*v['fact_coverage']['@5']
    best=max(variants,key=score)
    summary=[]
    for v in variants:
        summary.append({'run':v['title'],'items':v['item_count'],'dev_score':score(v),
                        'doc_r1':v['document']['r1'],'doc_r3':v['document']['r3'],'doc_r5':v['document']['r5'],'doc_mrr':v['document']['mrr'],
                        'section_r1':v['section']['r1'],'section_r3':v['section']['r3'],'section_r5':v['section']['r5'],'section_mrr':v['section']['mrr'],
                        'fact_cov_1':v['fact_coverage']['@1'],'fact_cov_3':v['fact_coverage']['@3'],'fact_cov_5':v['fact_coverage']['@5'],
                        'hard_fact_cov_1':v['hard_fact_coverage']['@1'],'hard_fact_cov_5':v['hard_fact_coverage']['@5']})
    with (out/'chunking_ab_summary.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(summary[0].keys())); w.writeheader(); w.writerows(summary)
    (out/'chunking_ab_results.json').write_text(json.dumps({'status':'developmental_seed_v0_not_final','best_run':best['title'],'summary':summary,'runs':variants},ensure_ascii=False,indent=2),encoding='utf-8')
    # Per-query changes vs baseline for the selected run.
    br={r['id']:r for r in variants[0]['rows']}; rr={r['id']:r for r in best['rows']}
    changes=[]
    for q in qs:
        a=br[q['id']]; b=rr[q['id']]
        changes.append({'id':q['id'],'query':q['query'],'category':q.get('category'),'difficulty':q.get('difficulty'),
                        'gold_title':q['gold_title'],'baseline_doc_rank':a['doc_rank'],'best_doc_rank':b['doc_rank'],
                        'baseline_section_rank':a['section_rank'],'best_section_rank':b['section_rank'],
                        'baseline_fact_cov_1':a['fact_cov_1'],'best_fact_cov_1':b['fact_cov_1'],
                        'baseline_top1':f"{a['top1_title']} / {a['top1_section']}", 'best_top1':f"{b['top1_title']} / {b['top1_section']}"})
    with (out/'chunking_ab_query_changes.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(changes[0].keys())); w.writeheader(); w.writerows(changes)
    cats=category_summary(best['rows'])
    with (out/'chunking_ab_best_category.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(cats[0].keys())); w.writeheader(); w.writerows(cats)
    print(json.dumps({'best':best['title'],'best_metrics':next(x for x in summary if x['run']==best['title']),'baseline':summary[0]},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
