from app.knowledge.bank import load_bank
from app.engine.evaluator import evaluate_technical, evaluate_numeric, extract_numbers, normalize
from app.engine.behavioral import evaluate_behavioral
from app.knowledge import numeric

BANK = load_bank()

GOOD_DEP = ("Depreciation goes up 10 so pre-tax income is down 10, with a 40% tax rate net income is down 6. On the cash flow statement net income is down 6 "
            "but I add back the 10 of non-cash depreciation so cash is up 4. On the balance sheet cash is up 4, PP&E is down 10 so assets are down 6, and retained "
            "earnings are down 6 so it balances. Cash goes up because of the tax shield.")
BAD_DEP = "Depreciation goes up by 10, so net income goes down by 10 and cash goes down by 10 too because it's an expense."


def test_correct_answer_scores_high():
    r = evaluate_technical(BANK["acc_dep10"], GOOD_DEP, use_llm=False)
    assert r["verdict"] == "correct" and r["score"] >= 0.9
    assert not r["misconceptions"]


def test_misconception_detected_and_capped():
    r = evaluate_technical(BANK["acc_dep10"], BAD_DEP, use_llm=False)
    assert r["verdict"] in ("incorrect", "partial")
    assert any(m["id"] in ("cash_down", "ni_down_10") for m in r["misconceptions"])
    assert r["score"] <= 0.45


def test_non_answer_and_off_topic():
    assert evaluate_technical(BANK["dcf_walkthrough"], "I don't know.", use_llm=False)["verdict"] == "non_answer"
    r = evaluate_technical(BANK["dcf_walkthrough"], "My favorite tournament is Wimbledon and I like the Lakers and rap music.", use_llm=False)
    assert r["verdict"] == "off_topic" and r["score"] < 0.2


def test_partial_answer_identifies_missing_component():
    r = evaluate_technical(BANK["dcf_walkthrough"], "You project unlevered free cash flows for five years and discount them at the WACC to get enterprise value.", use_llm=False)
    assert r["verdict"] == "partial"
    assert "tv" in r["missing"]
    assert "terminal" in (r["key_error"] or "").lower()


def test_gave_up_caps_score():
    r = evaluate_technical(BANK["val_ev_definition"], "Equity value is share price times diluted shares and enterprise value adds debt and subtracts cash for all capital providers, honestly I forget the rest.", use_llm=False)
    assert r["gave_up"] and r["score"] <= 0.5


def test_normalize_and_numbers():
    assert "wacc" in normalize("the WACK is 9 percent")
    nums = extract_numbers("about 2.5 billion and 30%")
    assert 2500.0 in nums and 30.0 in nums


def test_numeric_tolerance():
    g = numeric.generate("irr_from_moic", 7)
    assert evaluate_numeric(g, "roughly %.0f%%" % g["answer"])["verdict"] == "correct"
    assert evaluate_numeric(g, "%.0f%%" % (g["answer"] + 10))["verdict"] in ("incorrect", "partial")
    assert evaluate_numeric(g, "no idea")["verdict"] == "non_answer"


def test_paper_lbo_secondary_moic_credit():
    g = numeric.generate("paper_lbo", 3)
    r = evaluate_numeric(g, "MOIC is about %.2fx but I can't get the IRR" % g["secondary_answer"])
    assert r["secondary_ok"] and r["score"] >= 0.4


STORY = ("Last September in club interviews I got pushed hard on what I actually did at Hobo Ventures and my memorized answers collapsed on the second follow-up. "
         "I didn't get into one of the clubs. My job was to be able to defend the work. So I went back to the owner and spent two evenings understanding the royalty model, why Marcellus versus Utica "
         "mattered and why real estate was a hedge, and rebuilt my story from what was true. In the next interview I could answer three follow-ups deep and got the GADIF spot. "
         "I learned that memorized answers fail and understanding is the only prep that holds.")
GENERIC = "I'm a hard-working team player and I'm passionate about finance. We faced a challenge and we worked through it as a team and learned a lot. It was a steep learning curve."


def test_behavioral_differentiates_specific_from_generic():
    good = evaluate_behavioral(BANK["beh_failure"], STORY, 75, use_llm=False)
    bad = evaluate_behavioral(BANK["beh_failure"], GENERIC, 20, use_llm=False)
    assert good["score"] > bad["score"] + 0.3
    assert good["verdict"] == "strong" and bad["verdict"] in ("weak", "off_topic")
    assert bad["delivery"]["generic_phrases"]


def test_behavioral_flags_unsupported_claim():
    r = evaluate_behavioral(BANK["beh_leadership"], "I led the United Therapeutics pitch on my own and built 25 DCF models at Hobo Ventures, which the team approved. " + STORY, 70, use_llm=False)
    assert r["unsupported_claims"]
    assert r["score"] <= 0.6


def test_behavioral_off_topic_story():
    r = evaluate_behavioral(BANK["beh_why_ib"], "I grew up playing tennis and love competing. The Lakers are my favorite team.", 30, use_llm=False)
    assert not r["answered_question"] and r["score"] <= 0.4


def test_tmay_beats_detected():
    tmay = ("I'm originally from Pittsburgh where I grew up playing tennis, which led me to Georgetown to play Division 1. I knew I wanted MSB finance but not where. Over the summer I worked at an energy "
            "and real estate investment firm doing asset-level valuation. Back at Georgetown I joined Georgetown Collegiate Investors and the Aerospace and Defense fund to value businesses, and through "
            "conversations with bankers I realized I want to apply those skills in a transaction-oriented advisory environment.")
    r = evaluate_behavioral(BANK["beh_tmay"], tmay, 65, use_llm=False)
    assert r["tmay_order_ok"] and sum(r["tmay_beats"].values()) >= 5
    assert r["score"] >= 0.7


def test_delivery_metrics_flag_fillers_not_character():
    r = evaluate_behavioral(BANK["beh_failure"], "Um so like basically I think um we kind of failed, you know, and um I guess we learned, honestly. " + STORY, 90, use_llm=False)
    assert r["delivery"]["filler_total"] >= 4
    assert all("confiden" not in n.lower() for n in r["delivery"]["notes"])
