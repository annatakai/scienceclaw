"""Dig Once pipe risk scoring, heuristic rubric v2.0.

Run: python agents/pipe_agent/scoring.py input.csv outputs/scored_pipes.csv
No WNTR dependency; hydraulic results can be merged into input CSV.
"""
import argparse
import json
import math
from datetime import date
from pathlib import Path

import pandas as pd

VERSION = '2.0-heuristic'
POF_WEIGHTS = {'age': .20, 'material': .20, 'breaks': .25, 'soil': .15, 'condition': .20}
COF_WEIGHTS = {'customers': .35, 'facilities': .30, 'flood': .15, 'traffic': .10, 'cost': .10}
RANGES = {'age': (10,100), 'material': (15,85), 'breaks': (5,100), 'soil': (10,100), 'condition': (5,100),
          'customers': (0,100), 'facilities': (0,100), 'flood': (20,100), 'traffic': (10,100), 'cost': (10,100)}
MATERIALS = {'hdpe':15, 'pe':15, 'polyethylene':15, 'pvc':20,
             'protected ductile iron':30, 'ductile iron protected':30,
             'ductile iron':45, 'protected steel':40, 'steel protected':40,
             'steel':55, 'lined cast iron':60, 'cast iron lined':60,
             'cast iron':75, 'unlined cast iron':85, 'cast iron unlined':85,
             'asbestos cement':70}
SOILS = {'very low':10, 'low':25, 'moderate':50, 'high':75, 'very high':100}
FACILITIES = {'none':0, 'commercial':20, 'ordinary commercial':20,
              'school':50, 'community shelter':50, 'nursing home':70,
              'vulnerable care':70, 'hospital':100, 'emergency response':100}
EXPOSURES = {'low':20, 'moderate':50, 'high':80, 'very high':100}
CONDITIONS = {1:5, 2:25, 3:50, 4:80, 5:100}


def missing(x):
    return x is None or (isinstance(x, str) and not x.strip()) or bool(pd.isna(x))


def numeric(x, field, warnings, minimum=0, integer=False):
    if missing(x):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        warnings.append(f'{field}: invalid number {x!r}')
        return None
    if not math.isfinite(v) or v < minimum or (integer and not v.is_integer()):
        warnings.append(f'{field}: out-of-range value {x!r}')
        return None
    return v


def category(x, choices, field, warnings):
    if missing(x):
        return None
    key = str(x).strip().lower().replace('_', ' ').replace('-', ' ')
    key = ' '.join(key.split())
    if key not in choices:
        warnings.append(f'{field}: unrecognized category {x!r}')
        return None
    return choices[key]


def tier(value, edges, scores):
    return next((score for edge, score in zip(edges, scores) if value < edge), scores[-1])


def score_age(age):
    return tier(age, [20,40,60,80,100], [10,25,45,65,85,100])


def score_breaks(count, length_m, years):
    rate = count / (length_m / 1000 * years)
    if rate == 0:
        return 5, rate
    if rate <= .1:
        return 25, rate
    if rate <= .3:
        return 50, rate
    if rate <= .6:
        return 75, rate
    return 100, rate


def score_customers(n):
    return tier(n, [1,50,200,500,1000], [0,20,40,60,80,100])


def score_diameter(d):
    return tier(d, [150,250,400,600], [20,40,60,80,100])


def score_traffic(n):
    return tier(n, [1000,5000,15000,30000], [10,30,50,75,100])


def score_cost(n):
    return tier(n, [25000,100000,250000,500000], [10,30,50,75,100])


def score_pipe(row, assessment_year):
    warnings = []
    pof = {}
    cof = {}

    # ---- Probability of Failure ----

    year = numeric(
        row.get("installation_year"),
        "installation_year",
        warnings,
        minimum=1800,
        integer=True
    )

    if year is not None and year <= assessment_year:
        pof["age"] = score_age(assessment_year - year)
    else:
        pof["age"] = None
        if year is not None:
            warnings.append("Installation year is in the future")

    pof["material"] = category(
        row.get("material"), MATERIALS, "material", warnings
    )

    count = numeric(
        row.get("break_count"), "break_count",
        warnings, integer=True
    )
    length = numeric(
        row.get("length_m"), "length_m",
        warnings, minimum=0.000001
    )
    years = numeric(
        row.get("observation_years"), "observation_years",
        warnings, minimum=0.000001
    )

    break_rate = None

    if count is not None and length is not None and years is not None:
        pof["breaks"], break_rate = score_breaks(
            count, length, years
        )
    else:
        pof["breaks"] = None

    pof["soil"] = category(
        row.get("soil_corrosivity"),
        SOILS, "soil_corrosivity", warnings
    )

    grade = numeric(
        row.get("condition_grade"),
        "condition_grade", warnings,
        minimum=1, integer=True
    )

    pof["condition"] = CONDITIONS.get(
        int(grade) if grade is not None else None
    )

    if grade is not None and pof["condition"] is None:
        warnings.append("Invalid condition grade")

    # ---- Consequence of Failure ----

    customers = numeric(
        row.get("customers_affected"),
        "customers_affected", warnings, integer=True
    )

    cof["customers"] = (
        score_customers(customers)
        if customers is not None else None
    )

    cof["facilities"] = category(
        row.get("critical_facility"),
        FACILITIES, "critical_facility", warnings
    )

    diameter = numeric(
        row.get("diameter_mm"), "diameter_mm",
        warnings, minimum=0.000001
    )

    exposure = category(
        row.get("property_exposure"),
        EXPOSURES, "property_exposure", warnings
    )

    cof["flood"] = (
        (score_diameter(diameter) + exposure) / 2
        if diameter is not None and exposure is not None
        else None
    )

    traffic = numeric(
        row.get("aadt"), "aadt", warnings
    )

    cof["traffic"] = (
        score_traffic(traffic)
        if traffic is not None else None
    )

    cost = numeric(
        row.get("emergency_cost_usd"),
        "emergency_cost_usd", warnings
    )

    cof["cost"] = (
        score_cost(cost)
        if cost is not None else None
    )

    # ---- Weighted scores and uncertainty ----

    def aggregate(scores, weights):
        lower = 0.0
        upper = 0.0
        midpoint = 0.0
        completeness = 0.0

        for factor, weight in weights.items():
            value = scores[factor]
            lo, hi = RANGES[factor]

            if value is None:
                lower += weight * lo
                upper += weight * hi
                midpoint += weight * (lo + hi) / 2
            else:
                lower += weight * value
                upper += weight * value
                midpoint += weight * value
                completeness += weight

        exact = midpoint if abs(completeness - 1.0) < 1e-9 else None

        return exact, midpoint, lower, upper, completeness

    pof_exact, pof_mid, pof_lo, pof_hi, pof_complete = aggregate(
        pof, POF_WEIGHTS
    )

    cof_exact, cof_mid, cof_lo, cof_hi, cof_complete = aggregate(
        cof, COF_WEIGHTS
    )

    risk_exact = (
        pof_exact * cof_exact / 100
        if pof_exact is not None and cof_exact is not None
        else None
    )

    risk_estimate = pof_mid * cof_mid / 100
    risk_lower = pof_lo * cof_lo / 100
    risk_upper = pof_hi * cof_hi / 100

    def classify(value):
        if value >= 75:
            return "Critical"
        if value >= 50:
            return "High"
        if value >= 25:
            return "Moderate"
        return "Low"

    risk_class = (
        classify(risk_exact)
        if risk_exact is not None
        else "Incomplete"
    )

    actions = {
        "Critical": "Urgent engineering review",
        "High": "Prioritize engineering assessment",
        "Moderate": "Monitor and evaluate coordinated renewal",
        "Low": "Routine monitoring",
        "Incomplete": "Collect missing data before final ranking"
    }

    contributions = []

    for factor, weight in POF_WEIGHTS.items():
        if pof[factor] is not None:
            contributions.append(
                (factor, pof[factor] * weight)
            )

    contributions.sort(key=lambda x: x[1], reverse=True)

    drivers = [
        f"{name}: {value:.2f} points"
        for name, value in contributions[:3]
    ]

    result = {
        "pof_index": pof_exact,
        "cof_index": cof_exact,
        "risk_index": risk_exact,
        "provisional_risk_index": round(risk_estimate, 2),
        "risk_lower": round(risk_lower, 2),
        "risk_upper": round(risk_upper, 2),
        "risk_class": risk_class,
        "pof_completeness_pct": round(pof_complete * 100, 2),
        "cof_completeness_pct": round(cof_complete * 100, 2),
        "break_rate_per_km_year": break_rate,
        "recommended_action": actions[risk_class],
        "top_three_pof_drivers": "; ".join(drivers),
        "validation_warnings": "; ".join(warnings),
        "methodology_version": VERSION
    }

    for factor, value in pof.items():
        result[f"pof_{factor}_score"] = value

    for factor, value in cof.items():
        result[f"cof_{factor}_score"] = value

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Dig Once water pipe risk scoring"
    )

    parser.add_argument("input_csv", type=Path)
    parser.add_argument("output_csv", type=Path)
    parser.add_argument(
        "--year", type=int, default=date.today().year
    )

    args = parser.parse_args()

    df = pd.read_csv(args.input_csv)

    if "pipe_id" not in df.columns:
        parser.error("Input CSV must contain pipe_id")

    if df["pipe_id"].isna().any() or df["pipe_id"].duplicated().any():
        parser.error("pipe_id values must be unique and nonmissing")

    results = pd.DataFrame([
        score_pipe(row, args.year)
        for row in df.to_dict("records")
    ])

    scored = pd.concat(
        [df.reset_index(drop=True), results],
        axis=1
    )

    scored = scored.sort_values(
        "risk_index", ascending=False, na_position="last"
    )

    args.output_csv.parent.mkdir(
        parents=True, exist_ok=True
    )

    scored.to_csv(args.output_csv, index=False)

    json_path = args.output_csv.with_suffix(".json")

    json_path.write_text(
        json.dumps(
            scored.astype(object)
            .where(pd.notna(scored), None)
            .to_dict("records"),
            indent=2,
            default=str
        )
    )

    print(f"Scored {len(scored)} pipes")
    print(f"Complete scores: {scored.risk_index.notna().sum()}")
    print(f"CSV: {args.output_csv}")
    print(f"JSON: {json_path}")


if __name__ == "__main__":
    main()