"""Simulated candidates run full interviews in-process (no server needed).

Candidate archetypes: strong, weak, evasive (never answers the question), contradictory (changes
numbers), one_liner (minimal), and keyword_stuffer (buzzwords without logic). Each gets scripted
behavior per question kind. The goal is to check that the engine differentiates them sensibly,
that follow-ups fire for the right reasons, and that nothing crashes across modes.
"""
import os
import random
import re
import sys
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("GAUNTLET_DATA", os.path.join(os.path.dirname(__file__), "..", "data", "sim"))

from app import db  # noqa: E402
from app.engine import controller  # noqa: E402
from app.knowledge.bank import load_bank  # noqa: E402
from app.knowledge import numeric  # noqa: E402

db.init()
BANK = load_bank()


def strong_answer(q):
    """Use the rubric's own solution text plus component texts: an upper bound on what the deterministic engine can reward."""
    if q["source"] == "numeric":
        gen = numeric.generate(q["generator"], q["seed"])
        return "That comes to about %.1f %s." % (gen["answer"], gen.get("unit", ""))
    if q["source"] == "source":
        from app.knowledge import sources
        rec = sources.get(q["id"])
        return rec["answer"][:600]
    if q["source"] == "resume":
        return ("I built the decline-curve DCFs in Excel: monthly production history from the state filings fit to a hyperbolic decline with a terminal exponential, "
                "a price deck off the NYMEX strip less a Dominion South basis differential, net revenue interest from the lease royalty times our mineral share times tract participation, "
                "severance and ad valorem taxes, then a PV at a risk-adjusted discount rate by reserve category: PDP versus undeveloped. I ran price and timing sensitivities and presented "
                "the recommendation to the principals; the biggest sensitivity was the price deck, with 3 scenarios.")
    bq = BANK[q["id"]]
    if bq.kind == "behavioral":
        return ("Last September in club interviews I got pushed hard on what I actually did at Hobo Ventures, and my memorized answers collapsed on the second follow-up; I didn't get into one club. "
                "My job was to be able to defend the work. So I went back to the owner and spent two evenings on the royalty model, Marcellus versus Utica, and why real estate was a hedge, then rebuilt my story from what was true. "
                "In the next interview I could answer three follow-ups deep and got the GADIF spot. I learned that memorized answers fail and understanding is the only prep that holds. "
                "That's also why I want banking rather than research: on the investing side I evaluate decisions already made, and I want to advise on them in a transaction setting.")
    return bq.solution + " " + " ".join(c.text for c in bq.components)


def weak_answer(q):
    if q["source"] == "numeric":
        return "Maybe around 1000?"
    if q["source"] == "source":
        return "I think it basically goes up, um, I don't really know the mechanics, something about cash."
    if q["source"] == "resume":
        return "I did a lot of different things, built some models and stuff like that, and kind of helped out with various analyses."
    bq = BANK[q["id"]]
    if bq.kind == "behavioral":
        return "I'm a hard-working team player and I'm passionate about finance. We faced a challenge once and we worked through it as a team and learned a lot. It was a steep learning curve."
    # take a misconception if one exists
    if bq.misconceptions:
        kw = bq.misconceptions[0].kw[0]
        phrase = re.sub(r"[\\^$.*+?{}\[\]|()]", " ", kw)
        phrase = re.sub(r"\s+", " ", phrase).strip()
        return "I think basically " + phrase + ", um, I'm not totally sure."
    return "I think it basically goes up, I don't really know the mechanics."


def evasive_answer(q):
    return "That's a great question. I'd say the key thing is that I'm really passionate about finance and I bring a strong work ethic from Division I tennis. I love valuation and I'm excited about the opportunity."


def contradictory_answer(q, turn):
    base = strong_answer(q)
    if turn % 2 == 0:
        return base + " We used a WACC of 8.9% and I built the whole model myself."
    return base + " The discount rate was 11 percent and we built the model together as a team; interest rates are the biggest risk."


def one_liner(q):
    return "Yes." if q["source"] != "numeric" else "20"


def run(mode, archetype, config=None, max_turns=12, seed=1):
    random.seed(seed)
    cfg = dict(config or {})
    if mode not in ("deathmatch",):
        cfg.setdefault("max_questions", 6)
    cfg.setdefault("duration_min", 30)
    db.set_setting("use_llm", False)
    iv = controller.Interview.create(mode, cfg)
    turns = iv.start()
    log = [("I", t["text"], t.get("kind")) for t in turns]
    for i in range(max_turns):
        iv = controller.Interview(iv.id)
        if iv.state["phase"] == "ended":
            break
        q = iv.state["current"]
        if archetype == "strong":
            a = strong_answer(q)
        elif archetype == "weak":
            a = weak_answer(q)
        elif archetype == "evasive":
            a = evasive_answer(q)
        elif archetype == "contradictory":
            a = contradictory_answer(q, i)
        else:
            a = one_liner(q)
        dur = max(5.0, len(a.split()) / 150 * 60)
        out = iv.answer(a, dur)
        log.append(("C", a[:90] + ("…" if len(a) > 90 else ""), (out.get("evaluation") or {}).get("verdict") or iv.state["evals"][-1]["verdict"]))
        for t in out["interviewer_turns"]:
            log.append(("I", t["text"], (t.get("kind") or "") + ("/" + (t.get("meta") or {}).get("reason", "") if (t.get("meta") or {}).get("reason") else "")))
    iv = controller.Interview(iv.id)
    if iv.state["phase"] != "ended":
        iv.end()
    from app.engine import debrief
    d = debrief.build(iv.id)
    return iv, log, d


if __name__ == "__main__":
    verbose = "-v" in sys.argv
    results = []
    for mode, cfg in [("superday", {"persona": "vp", "technical_weight": 0.6}), ("death_match", {}), ("resume_defense", {"experience_id": "hobo"}),
                      ("behavioral", {}), ("rapid_fire", {}), ("hot_seat", {}), ("deal_defense", {}), ("explain", {"skill": "accounting.depreciation"}), ("tmay", {}),
                      ("bank_specific", {"bank": "morgan-stanley", "sector": "healthcare"}),
                      ("career", {"bank": "lazard"}), ("deathmatch", {}), ("daily", {}), ("weakness_lab", {})]:
        for arch in ("strong", "weak", "evasive", "contradictory", "one_liner"):
            iv, log, d = run(mode, arch, cfg, seed=zlib.crc32((mode + arch).encode()) % 1000)
            fu = sum(1 for t in log if t[0] == "I" and t[2] and t[2].startswith("followup"))
            results.append((mode, arch, d["overall"]["score"], d["overall"]["n_scored"], fu, len(d["contradictions"])))
            if verbose:
                print("\n=== %s / %s  → overall %s, %d scored, %d follow-ups, %d contradictions" % (mode, arch, d["overall"]["score"], d["overall"]["n_scored"], fu, len(d["contradictions"])))
                for who, text, kind in log:
                    print("  %s [%s] %s" % (who, kind, text[:140]))
    print("\n%-16s %-14s %7s %4s %4s %4s" % ("mode", "archetype", "score", "n", "fu", "ctr"))
    for r in results:
        print("%-16s %-14s %7s %4d %4d %4d" % (r[0], r[1], ("%.2f" % r[2]) if r[2] is not None else "-", r[3], r[4], r[5]))
    # sanity assertions
    by = {(r[0], r[1]): r for r in results}
    problems = []
    for mode in {r[0] for r in results}:
        s, w, e = by[(mode, "strong")][2], by[(mode, "weak")][2], by[(mode, "evasive")][2]
        if s is None or w is None:
            problems.append("%s: missing scores" % mode)
            continue
        if not s > w + 0.15:
            problems.append("%s: strong (%.2f) not clearly above weak (%.2f)" % (mode, s, w))
        if e is not None and e > 0.5:
            problems.append("%s: evasive scored %.2f (should be low)" % (mode, e))
    if by[("superday", "contradictory")][5] == 0 and by[("hot_seat", "contradictory")][5] == 0:
        problems.append("contradictory candidate never flagged")
    print("\nPROBLEMS:" if problems else "\nAll sanity checks passed.")
    for p in problems:
        print(" -", p)
    sys.exit(1 if problems else 0)
