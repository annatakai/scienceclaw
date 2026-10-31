"""Dig Once road condition rating, heuristic v0.1 (mirrors the style of pipe_agent/scoring.py).

Run: python -m agents.road_agent.scoring data/synthetic_roads.csv outputs/scored_roads.csv --year 2026
Input columns: segment_id, last_paved_year, road_class, aadt, length_ft
All thresholds are ASSUMPTIONS until calibrated to the MassDOT pavement report.
"""
import argparse
from datetime import date
from pathlib import Path

VERSION = "0.1-heuristic"
P_MIN = 40       # ASSUMPTION: at or below this pavement condition rating (PCR) the road is urgent
PCR_OK = 85      # ASSUMPTION: at or above this there is no urgency
BANDS = [(85, "Good", "Routine monitoring"),
         (70, "Fair", "Preservation treatment (cheap, at the right time)"),
         (40, "Poor", "Repave or rehabilitate; coordinate with utility work"),
         (0, "Failed", "Reconstruct")]


def pcr_value(age, adt):
    """Pavement condition 0-100 from pavement age and traffic loading (simplified deterioration curve)."""
    k = 0.6 + 0.4 * adt / 10_000
    return max(0.0, 100.0 - k * max(0.0, age) ** 1.4)


def pcr(road, year, t=0, repaved=False):
    age = t if repaved else (year - road["last_paved"] + t)
    return pcr_value(age, road["adt"])


def rate_condition(p):
    for floor, name, action in BANDS:
        if p >= floor:
            return name, action
    return BANDS[-1][1], BANDS[-1][2]


def urgency_from_pcr(p):
    return 1.0 if p <= P_MIN else max(0.0, (PCR_OK - p) / (PCR_OK - P_MIN))


def score_road(row, assessment_year):
    age = assessment_year - int(row["last_paved_year"])
    p = pcr_value(age, float(row["aadt"]))
    name, action = rate_condition(p)
    return {"pcr": round(p, 2), "wear_index": round(100 - p, 2), "condition_rating": name,
            "street_age": age, "urgency": round(urgency_from_pcr(p), 3), "recommended_action": action,
            "methodology_version": VERSION}


def main():
    import pandas as pd
    ap = argparse.ArgumentParser(description="Dig Once road condition rating")
    ap.add_argument("input_csv", type=Path)
    ap.add_argument("output_csv", type=Path)
    ap.add_argument("--year", type=int, default=date.today().year)
    a = ap.parse_args()
    df = pd.read_csv(a.input_csv)
    res = pd.DataFrame([score_road(r, a.year) for r in df.to_dict("records")])
    out = pd.concat([df.reset_index(drop=True), res], axis=1).sort_values("wear_index", ascending=False)
    a.output_csv.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(a.output_csv, index=False)
    print(f"Rated {len(out)} roads -> {a.output_csv}")


if __name__ == "__main__":
    main()
