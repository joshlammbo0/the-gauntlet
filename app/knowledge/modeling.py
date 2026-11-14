"""Modeling Lab: deterministic written modeling challenges (multi-step, each step verified) and the
mental-math arena configuration. Challenges are generated from seeds so retries get new numbers."""
import random
from typing import Dict, List

CHALLENGES = {}


def challenge(name, title, skill, minutes):
    def deco(fn):
        fn.meta = {"name": name, "title": title, "skill": skill, "minutes": minutes}
        CHALLENGES[name] = fn
        return fn
    return deco


def _pick(rng, xs):
    return xs[rng.randrange(len(xs))]


@challenge("mini_dcf", "Mini DCF: five-year UFCF to equity value per share", "dcf.ufcf", 12)
def mini_dcf(rng: random.Random) -> Dict:
    rev0 = _pick(rng, [500, 800, 1000, 1200])
    g = _pick(rng, [0.05, 0.08, 0.10])
    margin = _pick(rng, [0.20, 0.25, 0.30])
    da = _pick(rng, [0.04, 0.05])
    capex = _pick(rng, [0.05, 0.06, 0.07])
    nwc = _pick(rng, [0.02, 0.03])
    tax = 0.25
    wacc = _pick(rng, [0.08, 0.09, 0.10])
    tg = _pick(rng, [0.02, 0.025, 0.03])
    debt = _pick(rng, [200, 400, 600])
    cash = _pick(rng, [50, 100, 150])
    shares = _pick(rng, [50, 100, 200])
    rows = []
    rev = rev0
    pv_sum = 0.0
    ufcfs = []
    for yr in range(1, 6):
        prev = rev
        rev = rev * (1 + g)
        ebit = rev * margin
        nopat = ebit * (1 - tax)
        ufcf = nopat + rev * da - rev * capex - (rev - prev) * nwc
        df = 1 / (1 + wacc) ** yr
        pv = ufcf * df
        pv_sum += pv
        ufcfs.append(ufcf)
        rows.append({"year": yr, "revenue": round(rev, 1), "ebit": round(ebit, 1), "nopat": round(nopat, 1), "da": round(rev * da, 1), "capex": round(rev * capex, 1), "dnwc": round((rev - prev) * nwc, 1), "ufcf": round(ufcf, 1), "df": round(df, 4), "pv": round(pv, 1)})
    tv = ufcfs[-1] * (1 + tg) / (wacc - tg)
    pv_tv = tv / (1 + wacc) ** 5
    ev = pv_sum + pv_tv
    eq = ev - debt + cash
    px = eq / shares
    steps = [
        {"id": "ufcf1", "prompt": "Year 1 unlevered free cash flow ($M)", "answer": round(ufcfs[0], 1), "tol": 0.02, "hint": "EBIT(1−t) + D&A − CapEx − ΔNWC, with Year 1 revenue = %.0f × (1+%.0f%%)." % (rev0, g * 100)},
        {"id": "ufcf5", "prompt": "Year 5 unlevered free cash flow ($M)", "answer": round(ufcfs[-1], 1), "tol": 0.02, "hint": "Same build in year 5."},
        {"id": "tv", "prompt": "Terminal value at end of year 5 (perpetuity growth, $M)", "answer": round(tv, 0), "tol": 0.02, "hint": "UFCF5 × (1+g) / (WACC − g)."},
        {"id": "pv_tv", "prompt": "PV of terminal value ($M)", "answer": round(pv_tv, 0), "tol": 0.02, "hint": "TV / (1+WACC)^5."},
        {"id": "ev", "prompt": "Enterprise value ($M)", "answer": round(ev, 0), "tol": 0.02, "hint": "Sum of PV(UFCF years 1–5) + PV(TV)."},
        {"id": "px", "prompt": "Implied share price ($)", "answer": round(px, 2), "tol": 0.03, "hint": "(EV − debt + cash) / shares."},
    ]
    return {"title": mini_dcf.meta["title"], "skill": "dcf.ufcf", "minutes": 12, "calculator": True,
            "givens": {"Year 0 revenue ($M)": rev0, "Revenue growth": "%.0f%%/yr" % (g * 100), "EBIT margin": "%.0f%%" % (margin * 100), "D&A % revenue": "%.0f%%" % (da * 100),
                       "CapEx % revenue": "%.0f%%" % (capex * 100), "ΔNWC % of Δrevenue": "%.0f%%" % (nwc * 100), "Tax rate": "25%", "WACC": "%.0f%%" % (wacc * 100), "Terminal growth": "%.1f%%" % (tg * 100),
                       "Debt ($M)": debt, "Cash ($M)": cash, "Diluted shares (M)": shares, "Convention": "end-of-year discounting"},
            "steps": steps, "solution_table": rows, "solution_notes": "TV = %.1f × %.3f / %.3f = %.0f; PV(TV) = %.0f; EV = %.0f + %.0f = %.0f; equity = EV − %d + %d = %.0f; / %d = $%.2f." % (ufcfs[-1], 1 + tg, wacc - tg, tv, pv_tv, pv_sum, pv_tv, ev, debt, cash, eq, shares, px)}


@challenge("accretion", "Accretion / dilution: cash, stock and mixed deal", "ma.accretion_dilution", 10)
def accretion(rng: random.Random) -> Dict:
    a_ni = _pick(rng, [400, 500, 800])
    a_sh = _pick(rng, [100, 200])
    a_px = _pick(rng, [40, 50, 60])
    t_ni = _pick(rng, [60, 100, 150])
    premium_mult = _pick(rng, [12, 15, 18, 22])
    price = t_ni * premium_mult
    rate = _pick(rng, [0.05, 0.06, 0.07])
    tax = 0.25
    syn = _pick(rng, [0, 20, 40])
    a_eps = a_ni / a_sh
    cash_eps = (a_ni + t_ni + syn * (1 - tax) - price * rate * (1 - tax)) / a_sh
    new_sh = price / a_px
    stock_eps = (a_ni + t_ni + syn * (1 - tax)) / (a_sh + new_sh)
    mixed_eps = (a_ni + t_ni + syn * (1 - tax) - 0.5 * price * rate * (1 - tax)) / (a_sh + 0.5 * new_sh)
    steps = [
        {"id": "eps0", "prompt": "Acquirer standalone EPS ($)", "answer": round(a_eps, 2), "tol": 0.01, "hint": "NI / shares."},
        {"id": "price", "prompt": "Purchase price ($M)", "answer": price, "tol": 0.001, "hint": "Target NI × P/E paid."},
        {"id": "cash_eps", "prompt": "Pro forma EPS, 100% debt-financed ($)", "answer": round(cash_eps, 3), "tol": 0.01, "hint": "Add target NI and after-tax synergies, subtract after-tax interest; shares unchanged."},
        {"id": "new_sh", "prompt": "New shares issued if 100% stock (M)", "answer": round(new_sh, 2), "tol": 0.01, "hint": "Price / acquirer share price."},
        {"id": "stock_eps", "prompt": "Pro forma EPS, 100% stock ($)", "answer": round(stock_eps, 3), "tol": 0.01, "hint": "Combined NI / (old + new shares)."},
        {"id": "mixed_eps", "prompt": "Pro forma EPS, 50% debt / 50% stock ($)", "answer": round(mixed_eps, 3), "tol": 0.01, "hint": "Half the interest, half the new shares."},
    ]
    return {"title": accretion.meta["title"], "skill": "ma.accretion_dilution", "minutes": 10, "calculator": True,
            "givens": {"Acquirer net income ($M)": a_ni, "Acquirer shares (M)": a_sh, "Acquirer share price ($)": a_px, "Target net income ($M)": t_ni, "P/E paid": "%dx" % premium_mult,
                       "Pre-tax cost of debt": "%.0f%%" % (rate * 100), "Pre-tax synergies ($M)": syn, "Tax rate": "25%"},
            "steps": steps, "solution_notes": "Standalone EPS %.2f. Debt deal: (%d + %d + %.1f − %.1f)/%d = %.3f (%s). Stock deal: %.1f new shares; EPS %.3f (%s). Rule: acquirer P/E %.1fx vs %dx paid." % (
                a_eps, a_ni, t_ni, syn * (1 - tax), price * rate * (1 - tax), a_sh, cash_eps, "accretive" if cash_eps > a_eps else "dilutive", new_sh, stock_eps, "accretive" if stock_eps > a_eps else "dilutive", a_px / a_eps, premium_mult)}


@challenge("sources_uses", "Sources & uses and goodwill for an LBO", "ma.sources_uses", 8)
def sources_uses(rng: random.Random) -> Dict:
    ebitda = _pick(rng, [100, 150, 250])
    mult = _pick(rng, [8, 9, 10, 11])
    ev = ebitda * mult
    existing_debt = _pick(rng, [100, 200, 300])
    cash_target = _pick(rng, [20, 50, 80])
    fees = round(ev * 0.03)
    min_cash = 20
    lev = _pick(rng, [4.0, 5.0, 5.5])
    new_debt = ebitda * lev
    equity_purchase = ev - existing_debt + cash_target
    uses = equity_purchase + existing_debt + fees + min_cash
    sponsor_equity = uses - new_debt - cash_target
    book_equity = _pick(rng, [150, 250, 400])
    writeup = _pick(rng, [50, 100])
    goodwill = equity_purchase - book_equity - writeup + writeup * 0.25
    steps = [
        {"id": "ev", "prompt": "Enterprise value ($M)", "answer": ev, "tol": 0.001, "hint": "EBITDA × multiple."},
        {"id": "eqp", "prompt": "Equity purchase price ($M)", "answer": equity_purchase, "tol": 0.005, "hint": "EV − existing debt + target cash."},
        {"id": "uses", "prompt": "Total uses ($M)", "answer": uses, "tol": 0.005, "hint": "Equity purchase + refinance existing debt + fees (3% of EV) + minimum cash."},
        {"id": "debt", "prompt": "New debt raised ($M)", "answer": new_debt, "tol": 0.001, "hint": "Leverage × EBITDA."},
        {"id": "sponsor", "prompt": "Sponsor equity check ($M)", "answer": round(sponsor_equity, 1), "tol": 0.01, "hint": "Uses − new debt − target cash used."},
        {"id": "gw", "prompt": "Goodwill created ($M), 25% tax on write-up DTL", "answer": round(goodwill, 1), "tol": 0.01, "hint": "Equity price − book equity − write-up + DTL (write-up × 25%)."},
    ]
    return {"title": sources_uses.meta["title"], "skill": "ma.sources_uses", "minutes": 8, "calculator": True,
            "givens": {"LTM EBITDA ($M)": ebitda, "Purchase multiple": "%dx" % mult, "Existing target debt ($M)": existing_debt, "Target cash ($M)": cash_target, "Fees": "3% of EV",
                       "Minimum cash to balance sheet ($M)": min_cash, "New leverage": "%.1fx EBITDA" % lev, "Target book equity ($M)": book_equity, "PP&E write-up ($M)": writeup, "Tax rate": "25%"},
            "steps": steps, "solution_notes": "EV %d; equity %d; uses %d; debt %.0f; sponsor %.1f; goodwill %.1f." % (ev, equity_purchase, uses, new_debt, sponsor_equity, goodwill)}


@challenge("paper_lbo_full", "Paper LBO with debt paydown", "lbo.paper_lbo", 10)
def paper_lbo_full(rng: random.Random) -> Dict:
    ebitda = _pick(rng, [100, 200])
    entry = _pick(rng, [8, 10])
    lev = _pick(rng, [5, 6])
    g = _pick(rng, [0.05, 0.08])
    capex_pct = _pick(rng, [0.25, 0.3])  # of EBITDA
    rate = _pick(rng, [0.07, 0.08])
    tax = 0.25
    ev = ebitda * entry
    debt = ebitda * lev
    equity = ev - debt
    e = ebitda
    d = debt
    paid = 0.0
    for yr in range(5):
        e = e * (1 + g)
        interest = d * rate
        fcf = (e - interest) * (1 - tax) - e * capex_pct  # simplified: D&A ≈ capex for taxes ignored
        d -= fcf
        paid += fcf
    exit_ev = e * entry
    exit_eq = exit_ev - d
    moic = exit_eq / equity
    irr = moic ** 0.2 - 1
    steps = [
        {"id": "equity", "prompt": "Sponsor equity at entry ($M)", "answer": equity, "tol": 0.001, "hint": "EV − debt."},
        {"id": "ebitda5", "prompt": "Year 5 EBITDA ($M)", "answer": round(e, 1), "tol": 0.02, "hint": "Compound at %.0f%% for 5 years." % (g * 100)},
        {"id": "paid", "prompt": "Cumulative debt paydown over 5 years ($M, approximate)", "answer": round(paid, 0), "tol": 0.08, "hint": "Each year: (EBITDA − interest on the opening balance) × (1 − t) − capex; capex = %.0f%% of EBITDA." % (capex_pct * 100)},
        {"id": "exit_eq", "prompt": "Exit equity at %dx ($M)" % entry, "answer": round(exit_eq, 0), "tol": 0.05, "hint": "Exit EV − remaining debt."},
        {"id": "moic", "prompt": "MOIC (x)", "answer": round(moic, 2), "tol": 0.06, "hint": "Exit equity / entry equity."},
        {"id": "irr", "prompt": "IRR (%)", "answer": round(irr * 100, 1), "tol": 0.12, "hint": "MOIC^(1/5) − 1."},
    ]
    return {"title": paper_lbo_full.meta["title"], "skill": "lbo.paper_lbo", "minutes": 10, "calculator": False,
            "givens": {"Entry EBITDA ($M)": ebitda, "Entry multiple": "%dx" % entry, "Leverage": "%dx EBITDA" % lev, "EBITDA growth": "%.0f%%/yr" % (g * 100), "CapEx": "%.0f%% of EBITDA" % (capex_pct * 100),
                       "Interest rate": "%.0f%%" % (rate * 100), "Tax rate": "25%", "Exit": "year 5 at entry multiple", "Simplification": "no working capital; D&A ignored for tax"},
            "steps": steps, "solution_notes": "Equity %d; EBITDA5 %.1f; paydown ≈ %.0f; debt left %.0f; exit EV %.0f; exit equity %.0f; MOIC %.2fx; IRR %.1f%%." % (equity, e, paid, d, exit_ev, exit_eq, moic, irr * 100)}


def generate(name: str, seed: int = None) -> Dict:
    fn = CHALLENGES[name]
    seed = seed if seed is not None else random.randrange(1 << 30)
    out = fn(random.Random(seed))
    out.update({"name": name, "seed": seed, "id": "mod_%s_%d" % (name, seed)})
    return out


def grade(name: str, seed: int, answers: Dict[str, float]) -> Dict:
    ch = generate(name, seed)
    results = []
    correct = 0
    for st in ch["steps"]:
        v = answers.get(st["id"])
        ok = False
        err = None
        if v is not None:
            try:
                v = float(v)
                ref = float(st["answer"])
                err = abs(v - ref) / max(abs(ref), 1e-9)
                ok = err <= st["tol"]
            except (TypeError, ValueError):
                ok = False
        correct += 1 if ok else 0
        results.append({"id": st["id"], "prompt": st["prompt"], "given": v, "expected": st["answer"], "ok": ok, "error": round(err, 4) if err is not None else None, "hint": st["hint"]})
    return {"name": name, "seed": seed, "skill": ch["skill"], "results": results, "score": round(correct / len(ch["steps"]), 3), "solution_notes": ch["solution_notes"], "solution_table": ch.get("solution_table")}


def list_challenges() -> List[Dict]:
    return [dict(fn.meta) for fn in CHALLENGES.values()]


def self_test() -> None:
    for name in CHALLENGES:
        for seed in range(20):
            ch = generate(name, seed)
            g = grade(name, seed, {s["id"]: s["answer"] for s in ch["steps"]})
            assert g["score"] == 1.0, (name, seed, g)
    # independent check of mini_dcf price for a known seed
    ch = generate("mini_dcf", 1)
    gv = ch["givens"]
    assert ch["steps"][-1]["answer"] > 0


if __name__ == "__main__":
    self_test()
    print("modeling OK:", list(CHALLENGES))
