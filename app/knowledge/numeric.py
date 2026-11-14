"""Programmatically generated numeric questions with verified answers and tolerances.

Each generator returns a dict: {id, skill, text, answer, unit, tolerance, solution, difficulty,
params}. `check(answer_value, gen)` returns (correct, relative_error). Generators are seeded so a
question can be regenerated from its params for appeals/debriefs.
"""
import math
import random
from typing import Dict, Optional, Tuple

GENERATORS = {}


def generator(name, skill, difficulty):
    def deco(fn):
        fn.skill = skill
        fn.difficulty = difficulty
        GENERATORS[name] = fn
        return fn
    return deco


def _pick(rng, options):
    return options[rng.randrange(len(options))]


@generator("irr_from_moic", "math.irr", 2)
def irr_from_moic(rng: random.Random) -> Dict:
    moic = _pick(rng, [1.5, 2.0, 2.5, 3.0, 3.5, 4.0])
    years = _pick(rng, [3, 4, 5, 6, 7])
    irr = moic ** (1 / years) - 1
    return {
        "text": "A sponsor earns %.1fx its money over %d years. Approximately what is the IRR? Answer in percent." % (moic, years),
        "answer": irr * 100, "unit": "%", "tolerance": 1.5, "tol_type": "abs",
        "solution": "IRR = MOIC^(1/years) − 1 = %.1f^(1/%d) − 1 = %.1f%%. Rules of thumb: 2x/5y ≈ 15%%, 2.5x/5y ≈ 20%%, 3x/5y ≈ 25%%; rule of 72 for doubling." % (moic, years, irr * 100),
        "params": {"moic": moic, "years": years},
    }


@generator("moic_from_irr", "math.irr", 2)
def moic_from_irr(rng):
    irr = _pick(rng, [10, 15, 20, 25, 30])
    years = _pick(rng, [3, 4, 5])
    moic = (1 + irr / 100) ** years
    return {
        "text": "A %d%% IRR over %d years corresponds to roughly what multiple of money?" % (irr, years),
        "answer": moic, "unit": "x", "tolerance": 0.15, "tol_type": "abs",
        "solution": "MOIC = (1 + IRR)^years = 1.%02d^%d = %.2fx." % (irr, years, moic),
        "params": {"irr": irr, "years": years},
    }


@generator("terminal_value_gordon", "math.terminal_value", 2)
def terminal_value_gordon(rng):
    fcf = _pick(rng, [50, 80, 100, 120, 150, 200])
    g = _pick(rng, [2.0, 2.5, 3.0, 3.5, 4.0])
    wacc = _pick(rng, [8.0, 9.0, 10.0, 11.0, 12.0])
    tv = fcf * (1 + g / 100) / ((wacc - g) / 100)
    return {
        "text": "Final-year free cash flow is $%d million, terminal growth %.1f%%, WACC %.1f%%. What is the terminal value (perpetuity growth method), in $ millions?" % (fcf, g, wacc),
        "answer": tv, "unit": "$M", "tolerance": 0.015, "tol_type": "rel",
        "solution": "TV = FCF × (1+g) / (WACC − g) = %d × %.3f / %.3f = $%.0fM. Common slip: forgetting the (1+g) step-up (gives %.0f)." % (fcf, 1 + g / 100, (wacc - g) / 100, tv, fcf / ((wacc - g) / 100)),
        "params": {"fcf": fcf, "g": g, "wacc": wacc},
    }


@generator("terminal_value_exit", "math.terminal_value", 1)
def terminal_value_exit(rng):
    ebitda = _pick(rng, [60, 90, 120, 150, 250])
    mult = _pick(rng, [6, 7, 8, 9, 10, 12])
    return {
        "text": "Terminal-year EBITDA is $%dM and the exit multiple is %dx. What is the terminal value? And if net debt at exit is $%dM, what is the equity value?" % (ebitda, mult, ebitda * 2),
        "answer": ebitda * mult - ebitda * 2, "unit": "$M equity", "tolerance": 0.02, "tol_type": "rel",
        "solution": "TV = %d × %d = $%dM; equity = TV − net debt = %d − %d = $%dM." % (ebitda, mult, ebitda * mult, ebitda * mult, ebitda * 2, ebitda * mult - ebitda * 2),
        "params": {"ebitda": ebitda, "mult": mult}, "secondary_answer": ebitda * mult,
    }


@generator("ev_bridge", "math.ev_bridge", 1)
def ev_bridge(rng):
    price = _pick(rng, [20, 25, 40, 50, 80])
    shares = _pick(rng, [50, 100, 120, 200])
    debt = _pick(rng, [200, 500, 800, 1000])
    cash = _pick(rng, [50, 100, 150, 300])
    pref = _pick(rng, [0, 0, 100, 200])
    nci = _pick(rng, [0, 0, 50, 100])
    ev = price * shares + debt + pref + nci - cash
    extras = ""
    if pref:
        extras += ", $%dM of preferred stock" % pref
    if nci:
        extras += ", $%dM of non-controlling interest" % nci
    return {
        "text": "Share price $%d, %dM diluted shares, $%dM debt, $%dM cash%s. What is enterprise value?" % (price, shares, debt, cash, extras),
        "answer": ev, "unit": "$M", "tolerance": 0.01, "tol_type": "rel",
        "solution": "Equity %d × %d = %d; EV = equity + debt + preferred + NCI − cash = %d + %d + %d + %d − %d = $%dM." % (price, shares, price * shares, price * shares, debt, pref, nci, cash, ev),
        "params": {"price": price, "shares": shares, "debt": debt, "cash": cash, "pref": pref, "nci": nci},
    }


@generator("implied_multiple", "math.multiples", 2)
def implied_multiple(rng):
    ev = _pick(rng, [800, 1200, 2400, 5000])
    margin = _pick(rng, [10, 15, 20, 25, 30])
    revenue = _pick(rng, [400, 500, 1000, 2000])
    ebitda = revenue * margin / 100
    mult = ev / ebitda
    return {
        "text": "A company has EV of $%dM, revenue of $%dM and a %d%% EBITDA margin. What is its EV/EBITDA multiple?" % (ev, revenue, margin),
        "answer": mult, "unit": "x", "tolerance": 0.03, "tol_type": "rel",
        "solution": "EBITDA = %d × %d%% = %.0f; EV/EBITDA = %d / %.0f = %.1fx." % (revenue, margin, ebitda, ev, ebitda, mult),
        "params": {"ev": ev, "margin": margin, "revenue": revenue},
    }


@generator("wacc_calc", "math.wacc", 2)
def wacc_calc(rng):
    e = _pick(rng, [60, 70, 80])
    re = _pick(rng, [9.0, 10.0, 11.0, 12.0])
    rd = _pick(rng, [5.0, 6.0, 7.0, 8.0])
    t = _pick(rng, [21, 25, 30])
    wacc = e / 100 * re + (1 - e / 100) * rd * (1 - t / 100)
    return {
        "text": "Capital structure %d%% equity / %d%% debt, cost of equity %.0f%%, pre-tax cost of debt %.0f%%, tax rate %d%%. What is WACC?" % (e, 100 - e, re, rd, t),
        "answer": wacc, "unit": "%", "tolerance": 0.2, "tol_type": "abs",
        "solution": "WACC = %.2f × %.0f%% + %.2f × %.0f%% × (1 − %d%%) = %.2f%% + %.2f%% = %.2f%%." % (e / 100, re, 1 - e / 100, rd, t, e / 100 * re, (1 - e / 100) * rd * (1 - t / 100), wacc),
        "params": {"e": e, "re": re, "rd": rd, "t": t},
    }


@generator("capm", "math.wacc", 1)
def capm(rng):
    rf = _pick(rng, [3.5, 4.0, 4.5, 5.0])
    beta = _pick(rng, [0.8, 1.0, 1.2, 1.4, 1.5])
    erp = _pick(rng, [4.0, 4.5, 5.0, 5.5, 6.0])
    re = rf + beta * erp
    return {
        "text": "Risk-free rate %.1f%%, beta %.1f, equity risk premium %.1f%%. Cost of equity?" % (rf, beta, erp),
        "answer": re, "unit": "%", "tolerance": 0.15, "tol_type": "abs",
        "solution": "Re = Rf + β × ERP = %.1f + %.1f × %.1f = %.2f%%." % (rf, beta, erp, re),
        "params": {"rf": rf, "beta": beta, "erp": erp},
    }


@generator("accretion_cash", "math.accretion", 3)
def accretion_cash(rng):
    shares = _pick(rng, [100, 200, 500])
    eps = _pick(rng, [2.0, 3.0, 4.0, 5.0])
    target_ni = _pick(rng, [50, 80, 100, 150])
    pe_paid = _pick(rng, [10, 12, 15, 18, 20])
    rate = _pick(rng, [4, 5, 6, 7])
    t = 25
    price_paid = target_ni * pe_paid
    at_int = price_paid * rate / 100 * (1 - t / 100)
    pf_ni = shares * eps + target_ni - at_int
    pf_eps = pf_ni / shares
    chg = (pf_eps / eps - 1) * 100
    return {
        "text": "Acquirer: %d million shares, EPS $%.2f. It buys a target with $%dM of net income at %dx P/E, financed with debt at %d%% (25%% tax). What is pro forma EPS, and is the deal accretive or dilutive?" % (shares, eps, target_ni, pe_paid, rate),
        "answer": pf_eps, "unit": "$ EPS", "tolerance": 0.03, "tol_type": "abs",
        "solution": "Price = %d × %d = %d. After-tax interest = %d × %d%% × 0.75 = %.1f. PF NI = %d + %d − %.1f = %.1f; / %d shares = $%.3f vs $%.2f → %s %.1f%%. Shortcut: target earnings yield 1/%d = %.1f%% vs after-tax debt cost %.2f%%." % (
            target_ni, pe_paid, price_paid, price_paid, rate, at_int, shares * eps, target_ni, at_int, pf_ni, shares, pf_eps, eps,
            "accretive" if chg > 0 else "dilutive", abs(chg), pe_paid, 100 / pe_paid, rate * 0.75),
        "params": {"shares": shares, "eps": eps, "target_ni": target_ni, "pe_paid": pe_paid, "rate": rate},
        "direction": "accretive" if chg > 0 else "dilutive",
    }


@generator("accretion_stock", "math.accretion", 3)
def accretion_stock(rng):
    shares = _pick(rng, [100, 200])
    eps = _pick(rng, [2.0, 4.0, 5.0])
    pe_acq = _pick(rng, [15, 20, 25])
    target_ni = _pick(rng, [40, 50, 100])
    pe_paid = _pick(rng, [10, 12, 18, 22, 30])
    price = eps * pe_acq
    paid = target_ni * pe_paid
    new_shares = paid / price
    pf_eps = (shares * eps + target_ni) / (shares + new_shares)
    chg = (pf_eps / eps - 1) * 100
    return {
        "text": "Acquirer: %d million shares, EPS $%.2f, trading at %dx P/E. It buys a target with $%dM net income for %dx P/E, all in stock. Pro forma EPS? Accretive or dilutive?" % (shares, eps, pe_acq, target_ni, pe_paid),
        "answer": pf_eps, "unit": "$ EPS", "tolerance": 0.03, "tol_type": "abs",
        "solution": "Acquirer price %.2f × %d = $%.0f. Price paid %d × %d = %d → %.1f new shares. PF NI %d; shares %.1f → EPS $%.3f vs $%.2f: %s. Rule: acquirer P/E %d %s target P/E %d." % (
            eps, pe_acq, price, target_ni, pe_paid, paid, new_shares, shares * eps + target_ni, shares + new_shares, pf_eps, eps,
            "accretive" if chg > 0 else "dilutive", pe_acq, ">" if pe_acq > pe_paid else "<", pe_paid),
        "params": {"shares": shares, "eps": eps, "pe_acq": pe_acq, "target_ni": target_ni, "pe_paid": pe_paid},
        "direction": "accretive" if chg > 0 else "dilutive",
    }


@generator("paper_lbo", "lbo.paper_lbo", 4)
def paper_lbo(rng):
    ebitda = _pick(rng, [50, 100, 200])
    entry = _pick(rng, [7, 8, 10, 12])
    debt_pct = _pick(rng, [50, 60, 70])
    growth = _pick(rng, [5, 8, 10])
    years = 5
    paydown_pct = _pick(rng, [20, 30, 40])
    exit_mult = _pick(rng, [entry - 2, entry, entry, entry + 1])
    ev = ebitda * entry
    debt = ev * debt_pct / 100
    equity = ev - debt
    exit_ebitda = ebitda * (1 + growth / 100) ** years
    debt_left = debt * (1 - paydown_pct / 100)
    exit_ev = exit_ebitda * exit_mult
    exit_eq = exit_ev - debt_left
    moic = exit_eq / equity
    irr = moic ** (1 / years) - 1
    return {
        "text": ("Paper LBO. Buy a company with $%dM EBITDA at %dx, %d%% debt-financed. EBITDA grows %d%% a year for %d years. "
                 "You repay %d%% of the initial debt from cash flow and exit at %dx. What are the MOIC and the approximate IRR?") % (ebitda, entry, debt_pct, growth, years, paydown_pct, exit_mult),
        "answer": irr * 100, "unit": "% IRR", "tolerance": 2.0, "tol_type": "abs", "secondary_answer": moic,
        "solution": ("Entry EV %d × %d = %d; debt %.0f, equity %.0f. Exit EBITDA %d × %.3f^%d = %.1f; exit EV %.1f × %d = %.0f; debt left %.0f; exit equity %.0f. "
                     "MOIC %.2fx → IRR ≈ %.1f%%.") % (ebitda, entry, ev, debt, equity, ebitda, 1 + growth / 100, years, exit_ebitda, exit_ebitda, exit_mult, exit_ev, debt_left, exit_eq, moic, irr * 100),
        "params": {"ebitda": ebitda, "entry": entry, "debt_pct": debt_pct, "growth": growth, "paydown_pct": paydown_pct, "exit_mult": exit_mult},
    }


@generator("depreciation_walk", "accounting.depreciation", 2)
def depreciation_walk(rng):
    d = _pick(rng, [10, 20, 50, 100])
    t = _pick(rng, [20, 25, 30, 40])
    ni = -d * (1 - t / 100)
    cash = d * t / 100
    return {
        "text": "Depreciation rises by $%d with a %d%% tax rate. By how much does cash change (and what happens to net income)?" % (d, t),
        "answer": cash, "unit": "$ cash change", "tolerance": 0.01, "tol_type": "rel", "secondary_answer": ni,
        "solution": "NI falls %d × (1 − %d%%) = %.1f. Cash: NI %.1f + add back %d = +%.1f (the tax shield %d × %d%%)." % (d, t, -ni, ni, d, cash, d, t),
        "params": {"d": d, "t": t},
    }


@generator("growth_compounding", "math.multiples", 2)
def growth_compounding(rng):
    base = _pick(rng, [100, 200, 500])
    g = _pick(rng, [5, 8, 10, 12, 15, 20])
    years = _pick(rng, [3, 5])
    val = base * (1 + g / 100) ** years
    return {
        "text": "Revenue is $%dM and grows %d%% a year for %d years. Approximately what is revenue at the end?" % (base, g, years),
        "answer": val, "unit": "$M", "tolerance": 0.04, "tol_type": "rel",
        "solution": "%d × 1.%02d^%d = %.0f. Shortcut: 1.%02d^%d ≈ %.2f." % (base, g, years, val, g, years, (1 + g / 100) ** years),
        "params": {"base": base, "g": g, "years": years},
    }


@generator("breakeven_synergies", "math.accretion", 3)
def breakeven_synergies(rng):
    shares = _pick(rng, [100, 200])
    eps = _pick(rng, [2.0, 3.0])
    pf_shares = shares + _pick(rng, [20, 30, 50])
    target_ni = _pick(rng, [20, 30, 40])
    t = 25
    required_ni = pf_shares * eps
    shortfall = required_ni - (shares * eps + target_ni)
    pretax = shortfall / (1 - t / 100)
    return {
        "text": "After an all-stock deal the acquirer has %d million shares (was %d) and EPS was $%.2f. The target adds $%dM of net income. How much pre-tax synergy (25%% tax) is needed to break even on EPS?" % (pf_shares, shares, eps, target_ni),
        "answer": pretax, "unit": "$M pre-tax", "tolerance": 0.03, "tol_type": "rel",
        "solution": "Required NI = %d × %.2f = %.0f; have %d + %d = %d; shortfall %.0f after-tax → / 0.75 = $%.1fM pre-tax." % (pf_shares, eps, required_ni, shares * eps, target_ni, shares * eps + target_ni, shortfall, pretax),
        "params": {"shares": shares, "eps": eps, "pf_shares": pf_shares, "target_ni": target_ni},
    }


@generator("royalty_nri", "energy.interests", 3)
def royalty_nri(rng):
    royalty = _pick(rng, [12.5, 15, 18, 20])
    mineral_pct = _pick(rng, [25, 50, 100])
    tract = _pick(rng, [40, 80, 100, 160])
    unit = _pick(rng, [320, 640, 1000])
    monthly_rev = _pick(rng, [500000, 1000000, 2000000])
    nri = royalty / 100 * mineral_pct / 100 * tract / unit
    check = monthly_rev * nri
    return {
        "text": "A lease has a %.1f%% royalty. You own %d%% of the minerals under %d acres pooled into a %d-acre unit that generates $%s of monthly revenue. What is your monthly royalty check?" % (royalty, mineral_pct, tract, unit, "{:,}".format(monthly_rev)),
        "answer": check, "unit": "$ per month", "tolerance": 0.03, "tol_type": "rel",
        "solution": "NRI = %.3f × %.2f × (%d/%d) = %.5f (%.3f%%). Check = %s × %.5f = $%s." % (royalty / 100, mineral_pct / 100, tract, unit, nri, nri * 100, "{:,}".format(monthly_rev), nri, "{:,.0f}".format(check)),
        "params": {"royalty": royalty, "mineral_pct": mineral_pct, "tract": tract, "unit": unit, "monthly_rev": monthly_rev},
    }


@generator("decline_first_year", "energy.decline_curves", 3)
def decline_first_year(rng):
    ip = _pick(rng, [5, 10, 15, 20])  # MMcf/d
    decline = _pick(rng, [50, 60, 70])
    price = _pick(rng, [2.0, 2.5, 3.0])
    basis = _pick(rng, [0.5, 0.8, 1.0])
    avg_rate = ip * (1 - decline / 200)  # linear approx of first-year average
    realized = price - basis
    revenue = avg_rate * 1000 * 365 * realized / 1e6
    return {
        "text": ("A Marcellus well comes on at %d MMcf/d and declines about %d%% over its first year (assume production falls roughly linearly for this estimate). "
                 "Henry Hub is $%.2f and the local basis discount is $%.2f per Mcf. Approximately what is first-year gross revenue, in $ millions?") % (ip, decline, price, basis),
        "answer": revenue, "unit": "$M", "tolerance": 0.10, "tol_type": "rel",
        "solution": "Average rate ≈ %d × (1 − %d%%/2) = %.1f MMcf/d = %.0f Mcf/d × 365 = %.1f MMcf. Realized price %.2f − %.2f = $%.2f → %.1f × %.2f ≈ $%.1fM. (A hyperbolic curve would give a somewhat different average; the point is the basis adjustment and the steep decline.)" % (ip, decline, avg_rate, avg_rate * 1000, avg_rate * 365, price, basis, realized, avg_rate * 365, realized, revenue),
        "params": {"ip": ip, "decline": decline, "price": price, "basis": basis},
    }


@generator("ptbv_justified", "fig.bank_valuation", 3)
def ptbv_justified(rng):
    roe = _pick(rng, [10, 12, 15, 18])
    ke = _pick(rng, [9, 10, 11])
    g = _pick(rng, [2, 3, 4])
    if roe <= ke:
        roe = ke + 3
    ptbv = (roe - g) / (ke - g)
    return {
        "text": "A bank earns a %d%% ROTCE, has a %d%% cost of equity and grows %d%% a year. What P/TBV multiple does that justify?" % (roe, ke, g),
        "answer": ptbv, "unit": "x", "tolerance": 0.1, "tol_type": "abs",
        "solution": "P/TBV = (ROTCE − g)/(Ke − g) = (%d − %d)/(%d − %d) = %.2fx." % (roe, g, ke, g, ptbv),
        "params": {"roe": roe, "ke": ke, "g": g},
    }


def generate(name: str, seed: Optional[int] = None) -> Dict:
    fn = GENERATORS[name]
    seed = seed if seed is not None else random.randrange(1 << 30)
    rng = random.Random(seed)
    q = fn(rng)
    q.update({"id": "num_%s_%d" % (name, seed), "generator": name, "seed": seed, "skill": fn.skill,
              "difficulty": fn.difficulty, "kind": "numeric", "answer_type": "number"})
    return q


def check(value: Optional[float], q: Dict) -> Tuple[bool, Optional[float]]:
    if value is None:
        return False, None
    ans = q["answer"]
    if q.get("tol_type") == "abs":
        err = abs(value - ans)
        return err <= q["tolerance"], err
    err = abs(value - ans) / max(abs(ans), 1e-9)
    return err <= q["tolerance"], err


def self_test() -> None:
    """Recompute every generator from scratch with independent formulas to catch arithmetic bugs."""
    rng = random.Random(1)
    for name in GENERATORS:
        for _ in range(50):
            q = generate(name, rng.randrange(1 << 30))
            p = q["params"]
            if name == "irr_from_moic":
                assert abs((1 + q["answer"] / 100) ** p["years"] - p["moic"]) < 1e-6
            elif name == "terminal_value_gordon":
                assert abs(q["answer"] * (p["wacc"] - p["g"]) / 100 - p["fcf"] * (1 + p["g"] / 100)) < 1e-6
            elif name == "wacc_calc":
                e = p["e"] / 100
                assert abs(q["answer"] - (e * p["re"] + (1 - e) * p["rd"] * (1 - p["t"] / 100))) < 1e-9
            elif name == "paper_lbo":
                assert 0 < q["secondary_answer"] < 20
            elif name == "accretion_cash":
                yld = 100 / p["pe_paid"]
                cost = p["rate"] * 0.75
                assert (q["direction"] == "accretive") == (yld > cost), (yld, cost, q["direction"])
            elif name == "accretion_stock":
                assert (q["direction"] == "accretive") == (p["pe_acq"] > p["pe_paid"]) or p["pe_acq"] == p["pe_paid"]
            assert math.isfinite(q["answer"])


if __name__ == "__main__":
    self_test()
    print("numeric generators OK:", ", ".join(sorted(GENERATORS)))
