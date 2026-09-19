from pathlib import Path
import csv

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "evaluation" / "results" / "final_answer_eval_v1.csv"

def _rows():
    with CSV.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def test_conversation_mode_schema():
    rows = _rows()
    assert len(rows) == 29
    assert {r["conversation_mode"] for r in rows} == {"thread", "dm"}
    assert sum(r["conversation_mode"] == "thread" for r in rows) == 20
    assert sum(r["conversation_mode"] == "dm" for r in rows) == 9

def test_followups_have_context_labels():
    rows = _rows()
    followups = [r for r in rows if r["turn_index"].isdigit() and int(r["turn_index"]) > 1]
    assert followups
    for row in followups:
        assert row["context_retention"] not in {"", "N/A"}
        assert row["reference_resolution"] not in {"", "N/A"}

def test_dm_classroom_rental_regressions_are_preserved():
    rows = {r["id"]: r for r in _rows()}
    for case_id in ("FA-025", "FA-029"):
        assert rows[case_id]["conversation_mode"] == "dm"
        assert rows[case_id]["context_retention"] == "FAIL"
        assert rows[case_id]["reference_resolution"] == "FAIL"
