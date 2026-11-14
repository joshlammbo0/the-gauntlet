"""Skill taxonomy. Dotted ids: area.skill. Mastery is tracked per skill id."""
from typing import Dict, List

AREAS: Dict[str, str] = {
    "accounting": "Accounting",
    "valuation": "Valuation fundamentals",
    "dcf": "DCF",
    "ma": "M&A",
    "lbo": "LBOs",
    "fig": "FIG",
    "healthcare": "Healthcare",
    "energy": "Energy",
    "commercial": "Commercial & strategic judgment",
    "math": "Mental math",
    "behavioral": "Behavioral",
    "resume": "Resume defense",
    "deal": "Deal / pitch defense",
}

SKILLS: Dict[str, str] = {
    # accounting
    "accounting.three_statements": "Three statements and how they link",
    "accounting.depreciation": "Depreciation and D&A walk-throughs",
    "accounting.deferred_taxes": "Deferred taxes and NOLs",
    "accounting.working_capital": "Working capital (AR, inventory, AP, deferred revenue)",
    "accounting.revenue_recognition": "Revenue recognition and deferred revenue",
    "accounting.capex": "CapEx, PP&E and cash flow classification",
    "accounting.sbc": "Stock-based compensation",
    "accounting.goodwill": "Goodwill, intangibles and impairment",
    "accounting.debt": "Debt issuance, interest and repayment",
    "accounting.purchase_accounting": "Purchase accounting",
    "accounting.cash_flow_statement": "Cash flow statement mechanics",
    # valuation
    "valuation.ev_equity": "Enterprise value vs equity value",
    "valuation.diluted_shares": "Diluted shares, TSM, convertibles",
    "valuation.bridge_items": "Bridge items: cash, debt, preferred, NCI, leases",
    "valuation.multiples": "Multiples: which, when, why",
    "valuation.comps": "Trading comparables",
    "valuation.precedents": "Precedent transactions",
    "valuation.precedents_vs_comps": "Precedents vs comps",
    "valuation.ebitda_quality": "EBITDA adjustments and limitations",
    "valuation.football_field": "Valuation ranges and triangulation",
    # dcf
    "dcf.ufcf": "Unlevered free cash flow",
    "dcf.wacc": "WACC and its inputs",
    "dcf.cost_of_equity": "Cost of equity, beta, CAPM",
    "dcf.terminal_value": "Terminal value (Gordon growth and exit multiple)",
    "dcf.discounting": "Discount factors and mid-year convention",
    "dcf.sensitivities": "Sensitivities and what moves value",
    "dcf.pitfalls": "DCF pitfalls and edge cases",
    "dcf.levered_vs_unlevered": "Levered vs unlevered DCF, APV",
    # ma
    "ma.accretion_dilution": "Accretion / dilution",
    "ma.financing": "Cash vs stock vs debt financing",
    "ma.sources_uses": "Sources and uses",
    "ma.synergies": "Synergies and break-even",
    "ma.purchase_accounting": "Goodwill creation and PPA in M&A",
    "ma.rationale": "Strategic rationale and premiums",
    "ma.process": "Deal process and advisory roles",
    # lbo
    "lbo.basics": "LBO mechanics and why leverage boosts returns",
    "lbo.returns": "IRR, MOIC and return drivers",
    "lbo.debt": "Debt tranches, covenants, cash sweep",
    "lbo.candidate": "What makes a good LBO candidate",
    "lbo.paper_lbo": "Paper LBO",
    "lbo.exit": "Exit assumptions and sensitivity",
    # fig
    "fig.bank_valuation": "Bank valuation (P/TBV, P/E, DDM)",
    "fig.bank_drivers": "ROE, NIM, provisions, capital",
    "fig.rates": "Interest rates and bank earnings",
    "fig.other": "Insurance, asset managers, payments, fintech",
    # healthcare
    "healthcare.biotech": "Biotech valuation and rNPV",
    "healthcare.medtech": "MedTech valuation and dynamics",
    "healthcare.services": "Healthcare services and payer mix",
    "healthcare.pharma": "Pharma economics, patents, exclusivity",
    "healthcare.ma": "Healthcare M&A",
    # energy
    "energy.reserves": "Reserve categories, PDP vs PUD",
    "energy.decline_curves": "Decline curves and production forecasting",
    "energy.pricing": "Price decks, Henry Hub, basis differentials",
    "energy.interests": "Royalty vs mineral vs working interests",
    "energy.nav": "NAV and PV-10",
    "energy.renewables": "Renewables, PPAs, contracted vs merchant",
    "energy.project_finance": "Project finance basics",
    # commercial
    "commercial.market_sizing": "Market sizing",
    "commercial.positioning": "Competitive positioning and moats",
    "commercial.capital_allocation": "Capital allocation and financing decisions",
    "commercial.good_business_good_stock": "Good business vs good stock",
    "commercial.downside": "Downside scenario thinking",
    "commercial.restructuring": "Restructuring and distressed situations",
    "commercial.capital_markets": "Capital markets: debt, equity, leveraged finance",
    "commercial.markets": "Markets, macro and investing knowledge",
    "commercial.industry": "Industry-specific valuation (TMT, consumer, industrials, real estate, mining)",
    # math
    "math.irr": "IRR from MOIC",
    "math.terminal_value": "Terminal value arithmetic",
    "math.ev_bridge": "EV bridge arithmetic",
    "math.accretion": "Accretion/dilution arithmetic",
    "math.wacc": "WACC arithmetic",
    "math.multiples": "Multiples and margins arithmetic",
    # behavioral
    "behavioral.tmay": "Tell me about yourself / walk me through your resume",
    "behavioral.why_ib": "Why investment banking",
    "behavioral.why_bank": "Why this bank / group",
    "behavioral.story_structure": "Story structure and specificity",
    "behavioral.failure": "Failure, mistakes, weaknesses",
    "behavioral.conflict": "Conflict and feedback",
    "behavioral.leadership": "Leadership and teamwork",
    "behavioral.pressure": "Pressure, priorities, hours",
    "behavioral.fit": "Fit, motivation, self-awareness",
    # resume
    "resume.hobo": "Hobo Ventures defense",
    "resume.gpva": "Vascular practice defense",
    "resume.gadif": "GADIF pitches defense",
    "resume.gci": "GCI pitches defense",
    "resume.map": "MAP / case competition defense",
    "resume.tennis": "Athletics defense",
    # deal
    "deal.thesis": "Investment thesis defense",
    "deal.transaction": "M&A transaction discussion",
}


def area_of(skill_id: str) -> str:
    return skill_id.split(".")[0]


def skills_in_area(area: str) -> List[str]:
    return [s for s in SKILLS if s.startswith(area + ".")]


# Prerequisite graph: skill -> skills that should be understood first. Used by the selector (don't ask
# advanced questions before foundations), Weakness Lab (diagnose the real gap) and the skill graph UI.
PREREQS: Dict[str, List[str]] = {
    "accounting.depreciation": ["accounting.three_statements"],
    "accounting.deferred_taxes": ["accounting.depreciation"],
    "accounting.working_capital": ["accounting.three_statements"],
    "accounting.revenue_recognition": ["accounting.working_capital"],
    "accounting.capex": ["accounting.depreciation"],
    "accounting.sbc": ["accounting.three_statements"],
    "accounting.goodwill": ["accounting.three_statements"],
    "accounting.debt": ["accounting.three_statements"],
    "accounting.purchase_accounting": ["accounting.goodwill", "accounting.deferred_taxes"],
    "accounting.cash_flow_statement": ["accounting.three_statements"],
    "valuation.ev_equity": ["accounting.three_statements"],
    "valuation.diluted_shares": ["valuation.ev_equity"],
    "valuation.bridge_items": ["valuation.ev_equity"],
    "valuation.multiples": ["valuation.ev_equity"],
    "valuation.comps": ["valuation.multiples"],
    "valuation.precedents": ["valuation.comps"],
    "valuation.precedents_vs_comps": ["valuation.precedents"],
    "valuation.ebitda_quality": ["valuation.multiples", "accounting.cash_flow_statement"],
    "valuation.football_field": ["valuation.comps", "dcf.terminal_value"],
    "dcf.ufcf": ["accounting.cash_flow_statement", "accounting.capex", "accounting.working_capital"],
    "dcf.cost_of_equity": ["valuation.ev_equity"],
    "dcf.wacc": ["dcf.cost_of_equity", "accounting.debt"],
    "dcf.terminal_value": ["dcf.ufcf", "valuation.multiples"],
    "dcf.discounting": ["dcf.wacc"],
    "dcf.sensitivities": ["dcf.terminal_value", "dcf.wacc"],
    "dcf.pitfalls": ["dcf.sensitivities"],
    "dcf.levered_vs_unlevered": ["dcf.ufcf", "dcf.wacc"],
    "ma.accretion_dilution": ["valuation.multiples", "accounting.debt"],
    "ma.financing": ["ma.accretion_dilution"],
    "ma.sources_uses": ["valuation.ev_equity"],
    "ma.synergies": ["ma.accretion_dilution"],
    "ma.purchase_accounting": ["accounting.purchase_accounting", "ma.sources_uses"],
    "ma.rationale": ["valuation.precedents"],
    "ma.process": ["ma.rationale"],
    "lbo.basics": ["valuation.ev_equity", "accounting.debt"],
    "lbo.returns": ["lbo.basics"],
    "lbo.debt": ["lbo.basics"],
    "lbo.candidate": ["lbo.basics", "dcf.ufcf"],
    "lbo.paper_lbo": ["lbo.returns", "math.irr"],
    "lbo.exit": ["lbo.returns"],
    "fig.bank_valuation": ["valuation.multiples", "dcf.levered_vs_unlevered"],
    "fig.bank_drivers": ["fig.bank_valuation"],
    "fig.rates": ["fig.bank_drivers"],
    "fig.other": ["fig.bank_valuation"],
    "healthcare.biotech": ["dcf.ufcf", "dcf.discounting"],
    "healthcare.medtech": ["valuation.multiples"],
    "healthcare.services": ["accounting.three_statements"],
    "healthcare.pharma": ["healthcare.biotech"],
    "healthcare.ma": ["ma.rationale", "healthcare.biotech"],
    "energy.decline_curves": ["energy.reserves"],
    "energy.pricing": ["energy.reserves"],
    "energy.interests": ["energy.reserves"],
    "energy.nav": ["energy.decline_curves", "energy.pricing", "dcf.discounting"],
    "energy.renewables": ["dcf.ufcf"],
    "energy.project_finance": ["energy.renewables", "lbo.debt"],
    "commercial.good_business_good_stock": ["valuation.multiples"],
    "commercial.capital_allocation": ["dcf.wacc"],
    "commercial.downside": ["dcf.sensitivities"],
    "commercial.restructuring": ["lbo.debt", "valuation.ev_equity"],
    "commercial.capital_markets": ["accounting.debt", "valuation.ev_equity"],
    "math.irr": ["lbo.returns"],
    "math.terminal_value": ["dcf.terminal_value"],
    "math.ev_bridge": ["valuation.ev_equity"],
    "math.accretion": ["ma.accretion_dilution"],
    "math.wacc": ["dcf.wacc"],
    "behavioral.why_bank": ["behavioral.why_ib"],
    "behavioral.tmay": ["behavioral.story_structure"],
}


def prereqs_of(skill_id: str) -> List[str]:
    return PREREQS.get(skill_id, [])


def dependents_of(skill_id: str) -> List[str]:
    return [k for k, v in PREREQS.items() if skill_id in v]
