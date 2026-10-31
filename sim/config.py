"""All simulation numbers live here. Every value is sourced or tagged ASSUMPTION. ALL DATA IS SIMULATED."""

CFG = dict(
    seed=42, start_year=2026, horizon_years=10,
    annual_capital_budget=1_200_000,  # ASSUMPTION (demo value; 600k is too small to move failures)
    reserve_fraction=0.15,            # ASSUMPTION
    urgency_full_prob=0.30,           # ASSUMPTION
    critical_facility_multiplier=1.25,  # ASSUMPTION
    urgent_cap_fraction=0.5,          # ASSUMPTION
    urgent_override=0.9,              # ASSUMPTION
    min_return=1.0,                   # ASSUMPTION (return hurdle)
    dig_fixed=50_000,                 # ASSUMPTION: cost to open one street segment
    pipe_per_ft=300,                  # ASSUMPTION
    repave_per_ft=120,                # ASSUMPTION
    reline_frac=0.5,                  # ASSUMPTION: reline costs this share of replacement
    emergency_multiplier=3.0,         # ASSUMPTION
    discount_rate=0.04,               # ASSUMPTION
    cost_inflation=0.07,              # MassDOT FY27-31 CIP p.58 (asphalt +40% over 5 years)
    max_proposals=15,                 # menu size per agent per year
    department_split={"pipe": 0.6, "road": 0.4},  # ASSUMPTION (isolated baseline only)
    select="npv",                     # per-segment choice rule: "npv" (return_formula.md section 6) or "ratio"
    n_target=8.0,                     # ASSUMPTION: expected breaks per year for the whole city
    c_social_max=500_000,             # ASSUMPTION
    u0=0.30,                          # ASSUMPTION: road user cost, $ per vehicle-mile at worst condition
    lam=0.3, L=15,                    # ASSUMPTION: pavement life lost per cut, resurfacing cycle (years)
    H_replace=10, H_reline=7, rho=0.6,  # ASSUMPTION
    rate_revenue_share=0.5,           # ASSUMPTION (BWSC water program: about 30% rate revenue)
    # OSM highway tag -> (road_class, traffic band). Tertiary is a "local-ish collector": collector class, local traffic.
    road_class_map={"trunk": ("arterial", "arterial"), "primary": ("arterial", "arterial"),
                    "secondary": ("collector", "collector"), "tertiary": ("collector", "local")},  # ASSUMPTION
)


def infl(cfg, year):
    return (1 + cfg["cost_inflation"]) ** (year - cfg["start_year"])
