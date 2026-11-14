"""Candidate profile with provenance.

The REAL profile lives in `facts_private.py` (gitignored, local only). When it is absent (public
checkout), a clearly-labelled placeholder profile is used so the app still runs; nothing about the
real candidate is in version control.

Every fact carries `status`: verified | prompt_only | unknown | user (entered through the KB UI).
"""
from typing import Dict, List, Optional

VERIFIED = "verified"
PROMPT_ONLY = "prompt_only"
UNKNOWN = "unknown"

try:  # real profile (local only)
    from app.profile.facts_private import (PROFILE, EXPERIENCES, STORIES, TMAY_SPINE,  # noqa: F401
                                           WHY_BANK_MATERIAL, KNOWN_WEAKNESSES)
    IS_PLACEHOLDER = False
except ImportError:  # public / fresh checkout: placeholder candidate
    IS_PLACEHOLDER = True
    PROFILE = {
        "name": "[Your Name]", "preferred_name": "Candidate", "school": "[University], [Business School]",
        "degree": "B.S. in Finance", "grad": "May 20XX", "year": "sophomore", "recruiting_for": "Investment Banking Summer Analyst",
        "gpa": "[GPA]", "hometown": "[Hometown]", "geography": {"primary": "New York", "also": []}, "languages": ["English"],
        "interests_sectors": ["Healthcare", "Energy", "FIG", "M&A", "Generalist"],
    }
    EXPERIENCES: List[Dict] = [
        {"id": "internship", "org": "[Internship employer]", "title": "[Title]", "location": "[City]", "dates": "[Dates]",
         "bullets": [{"id": "int_b1", "status": PROMPT_ONLY, "source": "PLACEHOLDER", "text": "Built valuation models and presented recommendations [replace with your bullet]."}],
         "facts": [], "discrepancies": [],
         "unknowns": [{"id": "int_assumptions", "ask": "Which assumptions drove your model and how did you justify them?"},
                      {"id": "int_recommendation", "ask": "Name one specific recommendation you made and what happened."}]},
        {"id": "club", "org": "[Investment club]", "title": "Analyst", "location": "", "dates": "[Dates]",
         "bullets": [{"id": "club_b1", "status": PROMPT_ONLY, "source": "PLACEHOLDER", "text": "Pitched a stock with a DCF and comps [replace]."}],
         "facts": [], "discrepancies": [], "unknowns": [{"id": "club_thesis", "ask": "What was the variant perception in your pitch?"}]},
    ]
    STORIES: List[Dict] = [
        {"id": "challenge", "title": "[A challenge you overcame]", "status": PROMPT_ONLY, "source": "PLACEHOLDER", "categories": ["challenge", "pressure"], "tennis": False,
         "summary": "Placeholder story. Add your own in app/profile/facts_private.py or through the knowledge base."},
    ]
    TMAY_SPINE = {"status": PROMPT_ONLY, "source": "PLACEHOLDER", "beats": [("origin", "[Where you are from]"), ("spark", "[What got you into finance]"),
                  ("growth", "[What you did about it]"), ("bridge", "[Why advisory rather than investing]"), ("close", "[Why this role now]")], "known_issues": []}
    WHY_BANK_MATERIAL: Dict[str, Dict] = {}
    KNOWN_WEAKNESSES = {"status": PROMPT_ONLY, "source": "PLACEHOLDER", "items": []}


def all_bullets() -> List[Dict]:
    out = []
    for exp in EXPERIENCES:
        for b in exp["bullets"]:
            out.append({**b, "experience_id": exp["id"], "org": exp["org"]})
    return out


def experience(exp_id: str) -> Optional[Dict]:
    for e in EXPERIENCES:
        if e["id"] == exp_id:
            return e
    return None


def discrepancy_report() -> List[Dict]:
    rows = []
    for e in EXPERIENCES:
        for d in e.get("discrepancies", []):
            rows.append({"experience": e["org"], "issue": d})
    if IS_PLACEHOLDER:
        rows.append({"experience": "Profile", "issue": "Placeholder profile in use: copy app/profile/facts_private.example.py to facts_private.py and fill in your verified facts."})
    else:
        rows.append({"experience": "Build prompt vs documents", "issue": "Prompt lists stories (team-captain feedback, correcting a modeling mistake, teaching a junior student) that exist in no document; they are marked prompt_only."})
        rows.append({"experience": "Build prompt vs documents", "issue": "Prompt calls the GPVA role 'Finance and Operations'; the resume title is 'Finance Intern & Medical Interpreter' (May–June 2026)."})
        rows.append({"experience": "Delta Airlines model", "issue": "The Delta DCF file (6 Nov 2026) has #NUM! in both DCF outputs; only the comps columns compute. Not usable as a defended valuation yet."})
    return rows
