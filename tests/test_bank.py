from app.knowledge.bank import load_bank, validate_bank, by_skill
from app.knowledge.skills import SKILLS
from app.knowledge import numeric


def test_bank_validates():
    bank = load_bank()
    assert len(bank) >= 250
    assert validate_bank(bank) == []


def test_every_area_has_questions_and_followups():
    bank = load_bank()
    topics = {q.topic for q in bank.values()}
    for t in ("accounting", "valuation", "dcf", "ma", "lbo", "fig", "healthcare", "energy", "commercial", "behavioral"):
        assert t in topics
    with_fu = sum(1 for q in bank.values() if q.followups)
    assert with_fu / len(bank) > 0.9
    authored = sum(1 for q in bank.values() if any(not f.text.startswith('You left something out') and f.text != "That's not right. Take it from the top, one step at a time." for f in q.followups))
    assert authored / len(bank) > 0.45


def test_difficulty_ladder_exists_for_depreciation():
    bank = load_bank()
    chain = ["acc_dep10", "acc_dep_zero_tax", "acc_dep_nol", "acc_nol_acquisition"]
    diffs = [bank[c].difficulty for c in chain]
    assert diffs == sorted(diffs)
    for a, b in zip(chain, chain[1:]):
        assert any(f.next_id == b for f in bank[a].followups)


def test_skills_referenced_exist():
    bank = load_bank()
    for q in bank.values():
        assert q.skill in SKILLS


def test_numeric_generators_self_check():
    numeric.self_test()
    for name in numeric.GENERATORS:
        g = numeric.generate(name, 42)
        g2 = numeric.generate(name, 42)
        assert g["text"] == g2["text"] and g["answer"] == g2["answer"], "generator must be deterministic by seed"
        ok, err = numeric.check(g["answer"], g)
        assert ok
