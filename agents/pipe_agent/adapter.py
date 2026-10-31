"""Adapter: simulated pipe record -> the team's scoring.py input schema -> score_pipe().

The pipe agent's ratings (PoF, CoF, risk index, risk class) come from agents/pipe_agent/scoring.py (rubric v2.0).
Fields the simulator does not have are derived and documented here:
  - condition_grade: proxy from age and break count (real inspections would replace it)
  - observation_years: fixed 20-year break record
"""
from functools import lru_cache

from agents.pipe_agent import scoring
from sim import costs

MATERIAL_MAP = {"cast_iron": "cast iron", "ductile_iron": "ductile iron", "pvc": "pvc", "steel": "steel",
                "protected_ductile_iron": "protected ductile iron"}
OBS_YEARS = 20


def soil_label(x):
    return ("very low", "low", "moderate", "high", "very high")[min(4, int(x * 5))]


def condition_grade(age, nbreaks):
    return min(5, 1 + min(3, int(max(0, age) // 25)) + (1 if nbreaks >= 2 else 0))


def _effective(rec, year, treat, cfg):
    p = rec["pipe"]
    inst, mat, nb = p["install_year"], p["material"], len(p["breaks"])
    if treat == "replace":
        inst, mat, nb = year, "protected_ductile_iron", 0
    elif treat == "reline":
        inst = int(round(year - (1 - cfg["rho"]) * (year - inst)))
        nb = nb // 2
    return inst, mat, nb


def _args(rec, year, t, treat, cfg):
    p = rec["pipe"]
    inst, mat, nb = _effective(rec, year, treat, cfg)
    assess = year + t
    return (inst, MATERIAL_MAP[mat], nb, round(rec["length_ft"] / 3.28084, 3), soil_label(p["soil"]),
            condition_grade(assess - inst, nb), int(rec["customers"]), "hospital" if rec["critical"] else "none",
            int(round(p["diameter_in"] * 25.4)), rec["exposure"], int(rec["aadt"]),
            int(costs.emergency_cost(cfg, rec["length_ft"])), assess)


@lru_cache(maxsize=None)
def _score(args):
    (inst, mat, nb, length_m, soil, grade, cust, fac, diam, expo, aadt, ecost, assess) = args
    row = dict(installation_year=inst, material=mat, break_count=nb, length_m=length_m, observation_years=OBS_YEARS,
               soil_corrosivity=soil, condition_grade=grade, customers_affected=cust, critical_facility=fac,
               diameter_mm=diam, property_exposure=expo, aadt=aadt, emergency_cost_usd=ecost)
    return scoring.score_pipe(row, assess)


def score(rec, year, t=0, treat=None, cfg=None):
    return _score(_args(rec, year, t, treat, cfg))


def pof(rec, year, t, treat, cfg):
    v = score(rec, year, t, treat, cfg)["pof_index"]
    if v is None:
        raise ValueError(f"incomplete pipe data for {rec['segment_id']}: {score(rec, year, t, treat, cfg)['validation_warnings']}")
    return v


def cof_prime(rec, year, cfg):
    """Consequence index without the traffic and cost components, renormalised (return_formula.md 2.2)."""
    r = score(rec, year, 0, None, cfg)
    return (0.35 * r["cof_customers_score"] + 0.30 * r["cof_facilities_score"] + 0.15 * r["cof_flood_score"]) / 0.80


def rating(rec, year, cfg):
    r = score(rec, year, 0, None, cfg)
    return dict(risk_class=r["risk_class"], risk_index=r["risk_index"], recommended_action=r["recommended_action"],
                pof_index=r["pof_index"], cof_index=r["cof_index"])
