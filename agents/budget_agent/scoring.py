"""Dig Once budget ratings, heuristic v0.1: rates a priced proposal or bundle so decisions are explainable.

Return = present value of expected dollar loss removed / gross cost (see docs in README and sim/costs.py).
All thresholds are ASSUMPTIONS.
"""
VERSION = "0.1-heuristic"
TIERS = [(0.9, 1, "Urgent", "Fund first"), (0.6, 2, "Soon", "Fix within 1-3 years; bundle with other work"),
         (0.3, 3, "Plan", "Schedule with paving or other planned work"), (0.0, 4, "Monitor", "No action; keep watching")]


def urgency_tier(u):
    for floor, n, name, action in TIERS:
        if u >= floor:
            return n, name, action
    return TIERS[-1][1:]


def return_rating(ret, hurdle=1.0):
    if ret >= 2 * hurdle:
        return "Strong"
    if ret >= hurdle:
        return "Acceptable"
    return "Below hurdle"


def score_candidate(ret, urgency, hurdle=1.0):
    n, name, action = urgency_tier(urgency)
    return {"return_rating": return_rating(ret, hurdle), "urgency_tier": n, "urgency_name": name,
            "tier_action": action, "methodology_version": VERSION}
