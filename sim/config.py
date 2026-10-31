"""All simulation numbers live here. Every value is sourced or tagged ASSUMPTION. ALL DATA IS SIMULATED."""

CFG = dict(
    seed=42, start_year=2026, horizon_years=10,
    # --- network scale (all-Boston): per-mile assumptions; sim/city.py turns them into totals for the loaded network ---
    # The original 260-segment demo (about 25 miles) used $1.2M/yr and 8 breaks/yr; these are the same rates per mile.
    annual_budget_per_mile=48_000,    # ASSUMPTION: capital budget per mile of street per year (about $40M/yr for 839 miles)
    breaks_per_mile_year=0.30,        # ASSUMPTION: expected water-main breaks per mile per year at the start (n_target = this x miles)
    proposal_fraction=0.03,           # ASSUMPTION: each agent proposes work on at most this share of segments per year
    proposal_floor=15, proposal_cap=600,  # ASSUMPTION: bounds on the menu size (floor for small subsets, cap for run time)
    central_proposal_fraction=0.20,   # ASSUMPTION: the central planner scans this share of segments (full data, but bounded for run time)
    neighborhood=None, max_segments=None,  # subset options: a neighborhood name (or list) and a cap on segments
    # ASSUMPTION: when pipes were mostly laid, by neighborhood group: (earliest, latest, most likely install year)
    era_old=(1850, 1975, 1905), era_mid=(1880, 2000, 1935), era_new=(1900, 2012, 1970),
    neighborhoods_old=("Beacon Hill", "North End", "West End", "Downtown", "Chinatown", "Leather District", "Bay Village",
                       "South End", "Back Bay", "Charlestown", "Fenway", "Mission Hill", "Roxbury", "South Boston",
                       "South Boston Waterfront"),
    neighborhoods_new=("West Roxbury", "Hyde Park", "Roslindale", "Mattapan", "Harbor Islands", "Longwood"),
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
    department_split={"pipe": 0.6, "road": 0.4},  # ASSUMPTION (isolated baseline only)
    select="npv",                     # per-segment choice rule: "npv" (return_formula.md section 6) or "ratio"
    c_social_max=500_000,             # ASSUMPTION
    u0=0.30,                          # ASSUMPTION: road user cost, $ per vehicle-mile at worst condition
    lam=0.3, L=15,                    # ASSUMPTION: pavement life lost per cut, resurfacing cycle (years)
    H_replace=10, H_reline=7, rho=0.6,  # ASSUMPTION
    rate_revenue_share=0.5,           # ASSUMPTION (BWSC water program: about 30% rate revenue)
    # Claude-driven agents (strategy "coordinated_llm"). Prices are USD per million tokens (input, output).
    llm_model="claude-haiku-5-5", llm_effort="low", llm_max_tokens=1500,
    llm_max_tool_calls=8,             # per agent per year
    llm_rationale_max=280,            # characters
    llm_prices={"claude-haiku-5-5": (0.10, 0.50), "claude-sonnet-5-5": (2.00, 10.00), "claude-opus-5-5": (4.00, 20.00)},
    # traffic (vehicles/day) range by road class, ASSUMPTION
    adt_range={"arterial": (10_000, 16_000), "collector": (4_000, 8_000), "local": (300, 1_500)},
)


def infl(cfg, year):
    return (1 + cfg["cost_inflation"]) ** (year - cfg["start_year"])


def resolve(cfg, total_miles, n_segments):
    """Fill the network-size totals from the per-mile assumptions unless the caller set them explicitly."""
    c = dict(cfg)
    c.setdefault("annual_capital_budget", round(c["annual_budget_per_mile"] * total_miles))
    c.setdefault("n_target", c["breaks_per_mile_year"] * total_miles)
    c.setdefault("max_proposals", int(min(c["proposal_cap"], max(c["proposal_floor"], c["proposal_fraction"] * n_segments))))
    c.setdefault("max_proposals_central", int(max(c["max_proposals"], c["central_proposal_fraction"] * n_segments)))
    return c
