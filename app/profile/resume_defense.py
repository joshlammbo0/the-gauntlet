"""Resume Defense: turns each resume bullet into claims, concepts, credibility challenges and
question trees, with the supporting documents and the gaps the candidate must fill. Everything here is
derived from app/profile/facts.py; nothing is invented."""
from typing import Dict, List

from app.profile import facts

# Per-bullet analysis. Questions marked 'advanced' assume the basics were answered.
ANALYSIS: Dict[str, Dict] = {
    "hobo_b1": {
        "claims": ["Built 10+ DCF models", "Valued Marcellus Shale mineral and royalty interests", "Forecast production declines", "Forecast commodity prices", "Modeled asset-level cash flows", "Presented findings and recommendations to principals"],
        "concepts": ["energy.decline_curves", "energy.pricing", "energy.interests", "energy.nav", "energy.reserves"],
        "challenges": ["'10+' models in ten weeks: were these templated variants or distinct builds?", "Did he build the decline curves or receive them?", "Did he actually present, or sit in while a principal presented?", "No discount rate, price deck or recommendation is documented anywhere."],
        "questions": ["Walk me through the structure of one of your royalty DCFs, tab by tab.", "How did you forecast production volumes for a producing well?", "What assumptions drove your decline curves, and where did they come from?", "How did you determine the discount rate?", "What was your price deck?", "How did basis differentials change the realized gas price?", "How did you compute net revenue interest for a tract?", "What did you present to the principals, and what did they push back on?"],
        "advanced": ["Why hyperbolic rather than exponential decline, and what b-factor?", "How did you treat undeveloped locations whose timing the operator controls?", "What was the most questionable assumption in your models?", "If Henry Hub fell 20%, what happened to your valuations and why isn't it a straight 20%?", "How is a mineral-interest DCF different from a corporate DCF?", "How would you defend one valuation to an investment committee?"],
        "evidence": ["RESUME", "CL_EVR", "CL_LAZ", "TMAY", "CALLS (business description from the candidate's own calls)"],
    },
    "hobo_b2": {
        "claims": ["Analyzed Utica expansion", "Evaluated prospective acquisition opportunities", "Benchmarked Appalachian Basin operators"],
        "concepts": ["energy.reserves", "energy.pricing"],
        "challenges": ["What does 'benchmarking operators' mean concretely: which metrics, which operators?", "No conclusion is documented."],
        "questions": ["What is different about the Utica versus the Marcellus?", "Which operators did you benchmark and on what metrics?", "What did you conclude about Utica expansion?"],
        "advanced": ["Why would a mineral owner care which operator holds the lease above its acreage?", "How did you weigh a smaller operator set and shorter production history?"],
        "evidence": ["RESUME"],
    },
    "hobo_b3": {
        "claims": ["Commodity price sensitivity analyses", "Downside scenario analyses", "Evaluated acquisition bid pricing"],
        "concepts": ["energy.pricing", "dcf.sensitivities", "commercial.downside"],
        "challenges": ["Which sensitivity mattered most? Were bids actually made?"],
        "questions": ["Which sensitivity moved value most: price, decline, timing or discount rate?", "How did the sensitivities change the bid you recommended?", "Describe your downside case."],
        "advanced": ["How did you handle a fixed-dollar basis differential in a price-down case?", "Did you sensitize the b-factor or the terminal decline?"],
        "evidence": ["RESUME", "CL_LAZ"],
    },
    "gpva_b1": {
        "claims": ["Analyzed 5 years of revenue and procedure data", "Benchmarked physician performance", "Venous and arterial service lines"],
        "concepts": ["healthcare.services"],
        "challenges": ["Data access and tooling: Excel? how many rows?", "Did he define the benchmarks or were they given?"],
        "questions": ["What data did you have and how was it structured?", "How did you define 'performance' for a physician?", "What did you find?"],
        "advanced": ["How did you separate volume, mix and reimbursement rate effects?", "What was the payer mix and how did it matter?"],
        "evidence": ["RESUME", "STORIES", "TMAY"],
    },
    "gpva_b2": {
        "claims": ["Identified drivers of physician performance gaps", "Presented recommendations to management"],
        "concepts": ["healthcare.services", "commercial.positioning"],
        "challenges": ["Correlation vs causation on referrals vs tenure", "Did management act?"],
        "questions": ["What were the drivers of the gaps?", "What did you recommend and why?", "How did management react?"],
        "advanced": ["How do you know referral patterns caused the mix difference rather than tenure or specialty?", "How would a healthcare-services banker use your finding in a sell-side CIM?"],
        "evidence": ["RESUME", "STORIES"],
    },
    "gpva_b3": {
        "claims": ["Russian-English interpretation during patient consultations"],
        "concepts": ["behavioral.story_structure"],
        "challenges": ["Soft bullet; interviewers may test the language claim or ask a communication story."],
        "questions": ["Tell me about interpreting a difficult diagnosis conversation.", "How did that experience shape how you communicate complex information?"],
        "advanced": [],
        "evidence": ["RESUME", "STORIES"],
    },
    "map_b1": {"claims": ["Selected for MAP fellowship backed by Guggenheim and Wells Fargo"], "concepts": ["behavioral.fit"],
               "challenges": ["What is MAP, how selective, what does it involve?"], "questions": ["What is the MAP fellowship and what have you done in it?"], "advanced": ["What did you learn from the mock Superdays about your own weaknesses?"], "evidence": ["RESUME"]},
    "map_b2": {"claims": ["Advanced to technical playoffs via HireVues, mock Superdays, technical assessments"], "concepts": ["behavioral.fit"],
               "challenges": ["Vague on what the playoffs test."], "questions": ["What were the technical assessments like, and what tripped you up?"], "advanced": [], "evidence": ["RESUME"]},
    "map_b3": {"claims": ["Wells Fargo sports IB case competition", "Weekly technical assignments: three-statement modeling, franchise valuation, investment strategy", "Final pitch to Wells Fargo professionals"],
               "concepts": ["deal.thesis", "valuation.football_field", "dcf.terminal_value"],
               "challenges": ["Team work: which parts were his?", "Franchise valuation is unconventional; can he defend a 50x exit multiple or an EV/Revenue approach?"],
               "questions": ["How do you value an NFL franchise?", "Walk me through the Seahawks model: revenue streams and the cost side.", "Which valuation method did you weight most and why?"],
               "advanced": ["Why would a DCF understate what buyers pay for a franchise?", "How did you treat the salary cap and revenue sharing in the forecast?", "What did your range look like against the Forbes/Sportico figures?"],
               "evidence": ["RESUME", "SEA (Seattle_Seahawks_Valuation_Model.xlsx)"]},
    "ten_b1": {"claims": ["20+ hours weekly to D1 training, competition and travel", "Balanced with McDonough schedule"], "concepts": ["behavioral.pressure"],
               "challenges": ["What was sacrificed? How does this translate to unpredictable banking hours?"], "questions": ["How do you manage 20+ hours of tennis with a full course load?", "What did you give up?"], "advanced": ["Tennis has an off-season; banking doesn't. What's your plan for month nine?"], "evidence": ["RESUME"]},
    "ten_b2": {"claims": ["Starting lineup as a freshman", "No. 3 singles and No. 2 doubles", "20+ dual matches"], "concepts": ["behavioral.pressure"],
               "challenges": ["Pressure stories should be specific matches, not generalities."], "questions": ["Tell me about a match where you were under real pressure."], "advanced": [], "evidence": ["RESUME"]},
    "ten_b3": {"claims": ["Led Georgetown in singles wins", "Second-most doubles wins 2025–26"], "concepts": ["behavioral.leadership"], "challenges": ["Leadership by results vs leadership of people."], "questions": ["Does leading the team in wins make you a leader? What leadership have you shown off the court?"], "advanced": [], "evidence": ["RESUME"]},
    "ten_b4": {"claims": ["Five-Star Recruit", "No. 8 national ranking Boys' 18s", "No. 2 in PA", "300+ career singles wins", "ITA Scholar-Athlete", "BIG EAST Doubles Team of the Week"], "concepts": ["behavioral.pressure"],
               "challenges": ["The back injury comeback (verified in story bank) underlies the ranking arc."], "questions": ["Walk me through your junior tennis career, including the injury."], "advanced": ["What specifically did you change in rehab and training to get back to the top 10?"], "evidence": ["RESUME", "STORIES"]},
    "gadif_b1": {"claims": ["SELL pitch on Viasat", "5-year projections, DCF, comps, SOTP", "$41 price target", "33% downside", "Starlink competition, capex, refinancing risk"],
                 "concepts": ["deal.thesis", "dcf.terminal_value", "valuation.football_field", "dcf.wacc"],
                 "challenges": ["Perpetuity DCF gave $26 vs exit-multiple $51: why the gap?", "TV is 78% of value.", "What's happened since Oct 23?"],
                 "questions": ["Walk me through your Viasat thesis.", "How did you build the SOTP and what did you do with the spectrum?", "Why 8x exit and 2% growth?"],
                 "advanced": ["Your reverse DCF said the market implies 6.65% revenue growth vs your 4.3%. Why is the market wrong?", "What would make you cover the short?", "How did Starlink show up in your numbers rather than just your narrative?"],
                 "evidence": ["RESUME", "VSAT (VSAT_DCF_Sell_Thesis.xlsx)"]},
    "gadif_b2": {"claims": ["StandardAero BUY thesis", "DCF, bottom-up WACC, comps", "48% upside", "90% fund approval"],
                 "concepts": ["deal.thesis", "dcf.cost_of_equity", "dcf.wacc", "valuation.comps"],
                 "challenges": ["Upside figure conflicts: resume 48%, model 46%, the candidate's notes 23%.", "Variant perception missing (networking-call feedback).", "Bottom-up beta set includes FTAI (premium multiple, lessor)."],
                 "questions": ["Walk me through your StandardAero thesis.", "How did you build the WACC? Which peers for beta and why?", "What's the variant perception?"],
                 "advanced": ["Resume says 48% upside; your own notes say 23%. Which is it and from which method?", "Explain the pass-through revenue mechanism and why it expands margins.", "What happens to the thesis if the aerospace cycle turns?"],
                 "evidence": ["RESUME", "SARO (SARO_DCF_final.xlsx)", "STORIES", "CALLS (bank associate, 5 Nov)"]},
    "gadif_b3": {"claims": ["Weekly recommendations on aerospace holdings"], "concepts": ["deal.thesis"], "challenges": ["Which holdings? What was one recommendation?"], "questions": ["What's one weekly recommendation you made and what happened?"], "advanced": [], "evidence": ["RESUME"]},
    "gci_b1": {"claims": ["BUY pitch on United Therapeutics", "Projections, DCF, comps, pipeline analysis", "$670 price target", "23% upside"],
               "concepts": ["deal.thesis", "healthcare.biotech", "healthcare.pharma"],
               "challenges": ["Team pitch with five other named presenters: what was the candidate's part?", "rNPV inputs undocumented."],
               "questions": ["Walk me through your UTHR thesis.", "What part of the pitch did you build?", "What's the strongest argument against the thesis?"],
               "advanced": ["Why hasn't the market priced in the September 30 patent ruling?", "What probability of approval did the rNPV assume for IPF, and why?", "Ninety percent of revenue is one molecule. How does that affect your multiple?"],
               "evidence": ["RESUME", "UTHR (GCI Fall 2026 - United Therapeutics Corp.pptx)"]},
    "gci_b2": {"claims": ["BUY on Insulet", "$172 price target", "29% implied upside", "Comps and DCF"],
               "concepts": ["deal.thesis", "healthcare.medtech", "dcf.terminal_value"],
               "challenges": ["29% vs which price/date? The Oct DCF compares to $141.10 (29% → ~$182; $172 → 22%).", "Variant perception not stated."],
               "questions": ["Walk me through your Insulet valuation.", "Why did you select a 2.5% terminal growth rate?", "How would your valuation change if WACC rose 100bps?"],
               "advanced": ["Explain the competitive dynamics of insulin pumps and how you modeled them.", "You left SBC in EBIT; most sell-side models add it back. Defend that.", "What does GLP-1 adoption do to your T2D assumptions?"],
               "evidence": ["RESUME", "PODD_PPT", "PODD_DCF (insulet_dcf.html)"]},
}


def bullets() -> List[Dict]:
    out = []
    for b in facts.all_bullets():
        a = ANALYSIS.get(b["id"], {})
        exp = facts.experience(b["experience_id"]) or {}
        out.append({
            "id": b["id"], "experience_id": b["experience_id"], "org": b["org"], "text": b["text"], "status": b["status"], "source": b["source"],
            "claims": a.get("claims", []), "concepts": a.get("concepts", []), "challenges": a.get("challenges", []),
            "questions": a.get("questions", []), "advanced": a.get("advanced", []), "evidence": a.get("evidence", [b["source"]]),
            "unknowns": [u for u in exp.get("unknowns", [])], "discrepancies": exp.get("discrepancies", []),
        })
    return out


def question_pool(exp_id: str = None) -> List[Dict]:
    """Flat list of resume-defense questions usable by the selector."""
    pool = []
    for b in bullets():
        if exp_id and b["experience_id"] != exp_id:
            continue
        for i, qtext in enumerate(b["questions"]):
            pool.append({"id": "rd_%s_%d" % (b["id"], i), "bullet_id": b["id"], "experience_id": b["experience_id"], "text": qtext, "level": "basic", "skill": "resume." + b["experience_id"], "difficulty": 3})
        for i, qtext in enumerate(b["advanced"]):
            pool.append({"id": "rd_%s_a%d" % (b["id"], i), "bullet_id": b["id"], "experience_id": b["experience_id"], "text": qtext, "level": "advanced", "skill": "resume." + b["experience_id"], "difficulty": 5})
    return pool
