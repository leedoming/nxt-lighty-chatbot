#!/usr/bin/env python3
import json,csv,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from chunking_ab_eval import baseline_sections, atomic_chunks, document_texts, evaluate

here=Path(__file__).resolve().parent
corpus=here/'data/corpus_20250325'
qs=[json.loads(x) for x in (here/'data/coverage_probe_seed.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
docs=document_texts(corpus,title_boost=2)
variants=[
    evaluate(baseline_sections(corpus,title_boost=2),qs,'char','section_only',docs=docs),
    evaluate(atomic_chunks(corpus,title_boost=2,target=120,max_chars=190,overlap_units=1,augment_html=False),qs,'hier_char','atomic_no_html',docs=docs,doc_weight=.35),
    evaluate(atomic_chunks(corpus,title_boost=2,target=120,max_chars=190,overlap_units=1,augment_html='sparse'),qs,'hier_char','atomic_sparse_html',docs=docs,doc_weight=.35),
]
rows=[]
for v in variants:
    rows.append({'run':v['title'],'doc_r1':v['document']['r1'],'doc_r5':v['document']['r5'],
                 'fact_cov_1':v['fact_coverage']['@1'],'fact_cov_3':v['fact_coverage']['@3'],'fact_cov_5':v['fact_coverage']['@5']})
out=here/'results/coverage_probe_summary.csv'
with out.open('w',newline='',encoding='utf-8-sig') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0].keys()));w.writeheader();w.writerows(rows)
(here/'results/coverage_probe_results.json').write_text(json.dumps({'status':'coverage_probe_seed_not_final','summary':rows,'runs':variants},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(rows,ensure_ascii=False,indent=2))
