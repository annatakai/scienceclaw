"""Export the synthetic city as CSVs in the team's pipe-scoring schema (and a road schema).
Run: python -m sim.export_city      Then: python agents/pipe_agent/scoring.py data/synthetic_pipes.csv outputs/scored_pipes.csv --year 2026"""
import csv
import pathlib

from agents.pipe_agent import adapter
from sim.city import City
from sim.config import CFG

root = pathlib.Path(__file__).resolve().parent.parent
city = City(dict(CFG))
year = CFG["start_year"]
with open(root / "data" / "synthetic_pipes.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["pipe_id", "installation_year", "material", "break_count", "length_m", "observation_years",
                "soil_corrosivity", "condition_grade", "customers_affected", "critical_facility", "diameter_mm",
                "property_exposure", "aadt", "emergency_cost_usd"])
    for s in city.segs:
        a = adapter._args(city._pipe_rec(s), year, 0, None, CFG)
        inst, mat, nb, length_m, soil, grade, cust, fac, diam, expo, aadt, ecost, _ = a
        w.writerow([s["segment_id"], inst, mat, nb, length_m, adapter.OBS_YEARS, soil, grade, cust, fac, diam, expo, aadt, ecost])
with open(root / "data" / "synthetic_roads.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["segment_id", "street", "last_paved_year", "road_class", "aadt", "length_ft"])
    for s in city.segs:
        w.writerow([s["segment_id"], s["street"], s["road"]["last_paved"], s["road"]["road_class"], s["road"]["adt"],
                    round(s["length_ft"])])
print("wrote data/synthetic_pipes.csv and data/synthetic_roads.csv")
