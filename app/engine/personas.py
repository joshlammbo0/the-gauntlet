"""Interviewer personas: what they emphasize, how they phrase, how hard they push.

These are simulation profiles, not claims about how real bankers behave."""
from typing import Dict, List

PERSONAS: Dict[str, Dict] = {
    "analyst": {
        "name": "Friendly analyst", "title": "Analyst", "seniority": 1,
        "emphasis": {"technical": 0.5, "resume": 0.3, "behavioral": 0.2},
        "topic_weights": {"accounting": 1.3, "valuation": 1.2, "dcf": 1.2, "lbo": 1.0, "ma": 1.0, "resume": 1.3, "behavioral": 0.6, "commercial": 0.5},
        "challenge_threshold": 0.55, "max_followup_depth": 2, "tolerance_for_vague": 0.6,
        "style": "warm, curious, precise about mechanics; recently did these interviews themself",
        "openers": ["Thanks for making time. Let's just dive in.", "Good to meet you. I'll keep this conversational."],
        "ack_good": ["Okay, good.", "Right.", "Makes sense.", "Yep."],
        "ack_neutral": ["Okay.", "Got it.", "Sure."],
        "probe_templates": ["Can you walk me through the mechanics there?", "What's the formula you're using?", "Where does that number come from?"],
        "pivot_templates": ["Let's switch to something else.", "Okay, moving on.", "Let me ask about your resume."],
        "closers": ["That's all I've got. Thanks for your time; the team will be in touch.", "I think we're at time. Appreciate it."],
    },
    "associate": {
        "name": "Detail-oriented associate", "title": "Associate", "seniority": 2,
        "emphasis": {"technical": 0.45, "resume": 0.3, "behavioral": 0.25},
        "topic_weights": {"accounting": 1.2, "valuation": 1.2, "dcf": 1.1, "ma": 1.2, "lbo": 1.0, "resume": 1.2, "behavioral": 0.9, "commercial": 0.7},
        "challenge_threshold": 0.65, "max_followup_depth": 3, "tolerance_for_vague": 0.4,
        "style": "exacting, checks numbers, cares about execution and reliability",
        "openers": ["Let's get started. I'll ask some technicals and then go through your resume.", "Right, let's begin."],
        "ack_good": ["Fine.", "Correct.", "Okay."],
        "ack_neutral": ["Okay.", "Hm.", "Noted."],
        "probe_templates": ["Be precise: what exactly happens to the number?", "You skipped a step.", "Check that math for me.", "That's not quite what I asked."],
        "pivot_templates": ["Different topic.", "Let's go to your resume.", "Next."],
        "closers": ["We're at time. Thanks.", "Okay, that's it from me. Thanks for coming in."],
    },
    "vp": {
        "name": "Skeptical vice president", "title": "Vice President", "seniority": 3,
        "emphasis": {"technical": 0.4, "resume": 0.3, "behavioral": 0.3},
        "topic_weights": {"dcf": 1.3, "valuation": 1.2, "commercial": 1.3, "ma": 1.1, "resume": 1.2, "behavioral": 1.0, "accounting": 0.8, "lbo": 0.9, "deal": 1.3},
        "challenge_threshold": 0.7, "max_followup_depth": 3, "tolerance_for_vague": 0.3,
        "style": "wants the why behind every number; tests whether you understand or memorized",
        "openers": ["I've read your resume. Let's see how much of it you can defend.", "Let's start."],
        "ack_good": ["Okay.", "Fine.", "Right."],
        "ack_neutral": ["Hm.", "Okay.", "Noted."],
        "probe_templates": ["Why?", "You're describing the assumption, not defending it.", "What economically justifies that?", "Can you quantify that?", "How would you know if you were wrong?"],
        "pivot_templates": ["Let's switch gears.", "I understand the thesis. What's the valuation support?", "Let's talk about why you're here."],
        "closers": ["Okay. That's what I needed. Thanks.", "We'll stop there. Thank you."],
    },
    "md": {
        "name": "Direct managing director", "title": "Managing Director", "seniority": 4,
        "emphasis": {"technical": 0.2, "resume": 0.3, "behavioral": 0.5},
        "topic_weights": {"behavioral": 1.5, "commercial": 1.5, "deal": 1.4, "resume": 1.2, "dcf": 0.7, "valuation": 0.8, "accounting": 0.4, "ma": 0.9, "lbo": 0.5},
        "challenge_threshold": 0.7, "max_followup_depth": 2, "tolerance_for_vague": 0.25,
        "style": "short questions, long silences; cares about motivation, judgment and whether you'd be put in front of a client",
        "openers": ["So. Why are you here?", "Tell me about yourself. Short version."],
        "ack_good": ["Okay.", "Good."],
        "ack_neutral": ["Hm.", "Okay."],
        "probe_templates": ["So what?", "Why does that matter?", "Give me a specific example.", "Your answer is getting long. What's the single most important point?", "Would a client believe that?"],
        "pivot_templates": ["Let's talk about something else.", "Tell me about a deal you've followed.", "Last question."],
        "closers": ["Good. That's all. Thank you.", "Okay. Thanks for coming in."],
    },
    "hot_seat": {
        "name": "The Hot Seat", "title": "Interviewer", "seniority": 3,
        "emphasis": {"technical": 0.4, "resume": 0.35, "behavioral": 0.25},
        "topic_weights": {"resume": 1.5, "dcf": 1.3, "deal": 1.4, "behavioral": 1.1, "commercial": 1.2, "valuation": 1.1, "ma": 1.0, "accounting": 0.9, "lbo": 1.0},
        "challenge_threshold": 0.8, "max_followup_depth": 4, "tolerance_for_vague": 0.15,
        "style": "skeptical, direct, persistent; difficulty from rigor, never rudeness",
        "openers": ["I'm going to push on everything you say. Let's start.", "I've seen a lot of resumes like this. Convince me."],
        "ack_good": ["Fine.", "Okay. That holds."],
        "ack_neutral": ["Hm.", "Okay."],
        "probe_templates": ["That's a generic answer. Give me a specific example.", "How do I know you actually built this?", "Your interpretation is incorrect. Walk through it again.", "You've used that term three times. What does it actually mean?", "What's the strongest argument against what you just said?"],
        "pivot_templates": ["Different angle.", "Let's test that claim.", "Back to your resume."],
        "closers": ["Okay. We're done. You'll get a full breakdown.", "That's time."],
    },
}

DEFAULT_PERSONA = "vp"


def persona(key: str) -> Dict:
    return PERSONAS.get(key, PERSONAS[DEFAULT_PERSONA])


def list_personas() -> List[Dict]:
    return [{"key": k, "name": v["name"], "title": v["title"], "style": v["style"]} for k, v in PERSONAS.items()]
