"""Curated evaluator benchmark (Part 12.1). Each case: question id, answer, expected verdict set and a
score band. Runs deterministic-only by default; `--llm` also runs the model-refined path and reports
agreement. Exit code 1 if any deterministic case falls outside its band."""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.knowledge.bank import load_bank  # noqa: E402
from app.engine.evaluator import evaluate_technical, evaluate_numeric  # noqa: E402
from app.knowledge import numeric  # noqa: E402

B = load_bank()

CASES = [
    ("acc_dep10", "Pre-tax income down 10, net income down 6 at 40%. CFS: start at -6, add back 10 non-cash, cash up 4. BS: cash +4, PP&E -10, assets -6, retained earnings -6, balances. Cash rises because the depreciation tax shield cuts taxes paid by 4.", {"correct"}, (0.85, 1.0), "fully correct"),
    ("acc_dep10", "Net income falls by 6. Cash goes up by 4 because of the add-back. PP&E down 10.", {"partial", "correct"}, (0.45, 0.85), "partially correct (no BS tie-out, no tax shield)"),
    ("acc_dep10", "Depreciation is an expense so net income falls by 10 and cash falls by 10; the balance sheet shrinks by 10 on both sides.", {"incorrect"}, (0.0, 0.3), "confident but wrong"),
    ("acc_dep10", "Bottom line drops six bucks after the 40 percent tax. Cash flow statement starts at minus six, you throw the ten of non-cash D and A back on, so you end up four richer. Balance sheet: cash up four, fixed assets down ten, equity down six through retained earnings. Taxes paid fell by four.", {"correct", "partial"}, (0.7, 1.0), "unconventional wording"),
    ("dcf_walkthrough", "You project unlevered free cash flows for five years and discount them at WACC to get enterprise value.", {"partial"}, (0.3, 0.65), "missing terminal value and bridge"),
    ("dcf_ufcf", "UFCF is EBIT times one minus tax, plus D&A, minus capex, minus the increase in working capital, minus interest expense.", {"partial", "incorrect"}, (0.0, 0.5), "contains misconception (subtracting interest)"),
    ("val_tsm", "Ten options at a ten dollar strike are in the money. They'd pay 100 in proceeds, which buys back five shares at 20, so five net new shares and 105 diluted shares.", {"correct"}, (0.85, 1.0), "math right"),
    ("val_tsm", "You add all ten options so diluted shares are 110.", {"incorrect", "partial"}, (0.0, 0.45), "numerically wrong (no buyback)"),
    ("dcf_tv_next_year", "The formula uses the following year's cash flow because the perpetuity starts one period after the terminal year; the growth rate is long-run nominal growth of the economy, so it can't exceed GDP forever or the company becomes the economy.", {"correct"}, (0.75, 1.0), "reasonable assumptions stated"),
    ("ma_pe_rule", "It depends on whether the acquirer's P/E is higher or lower than the target's. If higher, accretive. If lower, dilutive. Either way could be right depending on synergies.", {"correct", "partial"}, (0.5, 1.0), "requires clarification but substantively right"),
    ("acc_dep10", "Net income is down six, cash is up for. On the balance sheet cash up for, PPNE down ten, retained earnings down six, so it balances; the tax shield is why.", {"correct", "partial"}, (0.6, 1.0), "speech-recognition noise (four->for, PP&E->PPNE)"),
    ("dcf_wacc_up_100", "Value falls. The discount rate goes up so value goes down.", {"partial", "incorrect"}, (0.0, 0.5), "answer without mechanism"),
    ("acc_goodwill", "Goodwill is the premium over book value and it is amortized over 40 years.", {"incorrect", "partial"}, (0.0, 0.45), "outdated/incorrect (amortization)"),
    ("lbo_irr_approx", "2.5x over five years is about a 20% IRR; 2x is 15%, 3x is 25%.", {"correct"}, (0.8, 1.0), "rules of thumb"),
    ("lbo_irr_approx", "2.5x over five years means 150% total, divided by 5 is 30% a year.", {"incorrect", "partial"}, (0.0, 0.45), "linear IRR misconception"),
]

NUMERIC_CASES = [
    ("wacc_calc", 11, lambda g: "%.2f percent" % g["answer"], {"correct"}),
    ("wacc_calc", 11, lambda g: "%.2f percent" % (g["answer"] + 2), {"incorrect", "partial"}),
    ("terminal_value_gordon", 5, lambda g: "about %.0f million" % g["answer"], {"correct"}),
    ("terminal_value_gordon", 5, lambda g: "%.0f" % (g["params"]["fcf"] / ((g["params"]["wacc"] - g["params"]["g"]) / 100)), {"incorrect", "partial"}),
    ("accretion_cash", 3, lambda g: "pro forma EPS is $%.2f so it's %s" % (g["answer"], g["direction"]), {"correct"}),
    ("ev_bridge", 9, lambda g: "%d" % g["answer"], {"correct"}),
]


def run(use_llm: bool = False):
    fails = []
    rows = []
    for qid, ans, verdicts, band, label in CASES:
        r = evaluate_technical(B[qid], ans, "auto", use_llm)
        ok = r["verdict"] in verdicts and band[0] <= r["score"] <= band[1]
        rows.append((qid, label, r["verdict"], r["score"], ok, r.get("provider")))
        if not ok and not use_llm:
            fails.append((qid, label, r["verdict"], r["score"], verdicts, band))
    for name, seed, mk, verdicts in NUMERIC_CASES:
        g = numeric.generate(name, seed)
        r = evaluate_numeric(g, mk(g))
        ok = r["verdict"] in verdicts
        rows.append((g["id"], mk(g)[:40], r["verdict"], r["score"], ok, "deterministic"))
        if not ok:
            fails.append((g["id"], mk(g), r["verdict"], r["score"], verdicts, None))
    return rows, fails


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true")
    a = ap.parse_args()
    rows, fails = run(a.llm)
    print("%-26s %-48s %-10s %5s %s" % ("question", "case", "verdict", "score", "ok"))
    for r in rows:
        print("%-26s %-48s %-10s %5.2f %s %s" % (r[0][:26], r[1][:48], r[2], r[3], "ok" if r[4] else "XX", r[5] or ""))
    print("\n%d/%d within expected band" % (sum(1 for r in rows if r[4]), len(rows)))
    for f in fails:
        print("FAIL:", f)
    sys.exit(1 if fails and not a.llm else 0)
