from pathlib import Path
import json, sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'evaluation'))
from alias_metadata_eval_v2 import title_query, section_query
from guarded_rerank_eval import run
from chunking_ab_eval import atomic_chunks, document_texts

def load_q(qid):
    for line in (ROOT/'evaluation/data/golden_seed_v0.jsonl').read_text(encoding='utf-8').splitlines():
        q=json.loads(line)
        if q['id']==qid:return q
    raise KeyError(qid)

def test_alias_is_scoped_to_title_metadata():
    assert '모집단위이동' in title_query('전과 신청은 언제야?')
    assert title_query('국가장학금과 교내장학금을 같이 받을 수 있어?') == '국가장학금과 교내장학금을 같이 받을 수 있어?'

def test_intent_is_scoped_to_section_metadata():
    assert '신청기간' in section_query('재입학 신청은 몇 월에 해?')
    assert '제출서류' in section_query('입대휴학 증빙 서류가 뭐야?')

def test_guarded_rerank_known_failure_cases():
    corpus=ROOT/'evaluation/data/corpus_20250325'
    items=atomic_chunks(corpus,title_boost=2,target=120,max_chars=190,overlap_units=1,augment_html=False)
    docs=document_texts(corpus,title_boost=2)
    qs=[load_q(x) for x in ['q008','q029','q063']]
    r=run(items,docs,qs,'test',.20,.08)
    by={x['id']:x for x in r['rows']}
    assert by['q008']['doc_rank']==1 and by['q008']['section_rank']==1
    assert by['q029']['section_rank']==1 and by['q029']['fact_cov_1']==1.0
    assert by['q063']['doc_rank']==1 and by['q063']['section_rank']==1 and by['q063']['fact_cov_1']==1.0
