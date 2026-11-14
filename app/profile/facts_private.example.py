"""EXAMPLE of app/profile/facts_private.py (gitignored). Copy this file to facts_private.py and replace every
value with facts you can defend. Keep the structure; the app reads PROFILE, EXPERIENCES, STORIES, TMAY_SPINE,
WHY_BANK_MATERIAL and KNOWN_WEAKNESSES."""
from typing import Dict, List

VERIFIED = "verified"
PROMPT_ONLY = "prompt_only"
UNKNOWN = "unknown"

PROFILE = {"name": "Alex Example", "preferred_name": "Alex", "school": "Example University", "degree": "B.S. Finance", "grad": "May 2029", "year": "sophomore",
           "recruiting_for": "2028 IB Summer Analyst", "gpa": "3.9", "hometown": "Chicago, IL", "geography": {"primary": "New York", "also": []}, "languages": ["English"],
           "interests_sectors": ["Healthcare", "M&A"]}

EXPERIENCES: List[Dict] = [
    {"id": "intern", "org": "Example Capital", "title": "Summer Analyst", "location": "Chicago", "dates": "June 2026 - August 2026",
     "bullets": [{"id": "intern_b1", "status": VERIFIED, "source": "RESUME", "text": "Built DCF models for three private company targets and presented to partners"}],
     "facts": [{"status": VERIFIED, "source": "RESUME", "text": "Modeled revenue by segment and ran WACC sensitivities."}],
     "discrepancies": [],
     "unknowns": [{"id": "intern_wacc", "ask": "What WACC did you use and how did you build it?"}]},
]

STORIES: List[Dict] = [
    {"id": "failure", "title": "Missed a deadline on a group project and rebuilt the process", "status": VERIFIED, "source": "NOTES",
     "categories": ["failure", "feedback"], "tennis": False, "summary": "Situation, task, action, result, lesson in two sentences each."},
]

TMAY_SPINE = {"status": VERIFIED, "source": "NOTES", "beats": [("origin", "Grew up in Chicago"), ("spark", "First valuation internship"), ("growth", "Investment club pitches"),
              ("bridge", "Investing evaluates decisions; banking advises on them"), ("close", "Transaction-oriented advisory")], "known_issues": []}

WHY_BANK_MATERIAL: Dict[str, Dict] = {"evercore": {"status": VERIFIED, "source": "NOTES", "points": ["Independent advisory model", "Spoke with an analyst in M&A"]}}

KNOWN_WEAKNESSES = {"status": VERIFIED, "source": "NOTES", "items": [("lbo.paper_lbo", "Froze on IRR arithmetic in a mock interview.")]}
