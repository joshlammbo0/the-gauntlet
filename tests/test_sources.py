import os

import pytest

from app.knowledge import ingest, sources
from app.knowledge.bank import load_bank


def _available():
    p = ingest.discover_sources()
    return bool(p.get("mi400_2025") and p.get("wsp_redbook"))


pytestmark = pytest.mark.skipif(not _available(), reason="guides not present on this machine")


def test_ingest_is_idempotent_and_stable():
    r1 = ingest.run(write=False)
    r2 = ingest.run(write=False)
    assert r1["counts"]["unique"] == r2["counts"]["unique"]
    assert r1["counts"]["unique"] >= 1200
    assert r1["sources"]["mi400_2025"]["records"] >= 350
    assert r1["sources"]["wsp_redbook"]["records"] >= 600


def test_records_have_citations_and_skills():
    recs = sources.all_records()
    assert len(recs) >= 1000
    for r in recs[:200]:
        assert r["page"] and r["section"] and r["skill"] and r["source"]
        assert 1 <= r["level"] <= 5
        c = sources.citation(r)
        assert c["short"] and c["verification"] in ("verified", "unverified")


def test_derived_rubric_rewards_correct_mechanics():
    recs = [r for r in sources.all_records() if "depreciation" in r["question"].lower() and "10" in r["question"] and "up" in r["question"].lower()]
    assert recs
    q = sources.as_question(recs[0])
    assert q.components and q.solution
    from app.engine.evaluator import evaluate_technical
    good = ("Pre-tax income falls by 10 so net income falls by 7.5 at a 25% tax rate. On the cash flow statement net income is down 7.5 but you add back the 10 of non-cash depreciation, so cash is up 2.5. "
            "On the balance sheet cash is up 2.5 and PP&E is down 10, so assets are down 7.5; equity is down 7.5 through retained earnings. Intuition: the tax shield saves 2.5.")
    bad = "It goes down and the company has less money."
    g = evaluate_technical(q, good, use_llm=False)
    b = evaluate_technical(q, bad, use_llm=False)
    assert g["score"] > b["score"] + 0.3


def test_authored_questions_have_levels():
    bank = load_bank()
    levels = {q.level for q in bank.values()}
    assert levels >= {1, 2, 3, 4}
    assert bank["acc_three_statements"].level == 1
    assert bank["acc_dep_zero_tax"].level >= 4
