"""End-to-end- real Docling on the sample PDFs vs the answer key. Slow, so opt in:  pytest -m docling"""

import json

import pytest

from extract import SAMPLES, extract

TRUTH = json.loads((SAMPLES / "expected.json").read_text(encoding="utf-8"))


@pytest.mark.docling
@pytest.mark.parametrize("name", sorted(TRUTH))
def test_sample_bill_matches_answer_key(name):
    from parse import parse_pdf
    bill, exp = extract(parse_pdf(SAMPLES / name)), TRUTH[name]
    assert bill.plan == exp["plan"]
    assert (bill.period_start, bill.period_end) == (exp["period_start"], exp["period_end"])
    assert bill.total_due == exp["total_due"]
    assert [(p.kind, p.kwh, p.rate, p.amount) for p in bill.periods] == \
           [(q["kind"], q["kwh"], q["rate"], q["amount"]) for q in exp["periods"]]
    assert bill.warnings == []