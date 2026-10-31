"""All simulation numbers live here. Every value is sourced or tagged ASSUMPTION. ALL DATA IS SIMULATED."""

CFG = dict(
    seed=42, start_year=2026, horizon_years=10,
    # --- network scale (all-Boston): per-mile assumptions; sim/city.py turns them into totals for the loaded network ---
    # The original 260-segment demo (about 25 miles) used $1.2M/yr and 8 breaks/yr; these are the same rates per mile.
    annual_budget_per_mile=48_000,    # ASSUMPTION: capital budget per mile of street per year (about $40M/yr for 839 miles)
    breaks_per_mile_year=round(35 / 1018, 4),  # CALIBRATED: BWSC reports just over 35 water pipe failures a year (BWSC CIP, via docs/budget_agent_reference.md) over about 1,018 linear miles of pipe (bwsc.org water system page, read 2026-10-31); n_target = this x simulated street miles
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
    reserve_mode="simulated",         # "simulated": sized from the 95th percentile of yearly emergency cost (sim/reserve.py); "fixed": reserve_fraction
    reserve_fraction=0.15,            # ASSUMPTION: used only when reserve_mode == "fixed"
    reserve_max_fraction=0.25,        # ASSUMPTION: cap on the simulated reserve as a share of the budget (upper end of the 0.10 to 0.25 range tested in interfaces.md)
    reserve_pilot_seeds=5, reserve_percentile=95,  # pilot seeds are 1000+i, separate from the reported seeds
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
    H_preserve=5, rho_preserve=0.4,   # ASSUMPTION: pavement preservation removes this share of pavement age, lasts H_preserve years
    preserve_frac=0.25,               # ASSUMPTION: preservation costs this share of a repave
    reconstruct_mult=2.0, reconstruct_bonus_years=5,  # ASSUMPTION: reconstruction costs this multiple of a repave and gives extra years of like-new condition
    pof_band=(0.85, 1.15, 5.0),       # ASSUMPTION: the rubric has no error bar; PoF bounds are x0.85 and x1.15 + 5 (return_formula.md section 6.4)
    road_benefit_band=0.15,           # ASSUMPTION: roads have no PoF bounds; road benefit is bounded by plus or minus this share
    P_min=40,                         # ASSUMPTION: PCR at or below this is Failed (road_agent/scoring.py P_MIN); reconstruction is offered here
    # Funding sources: BWSC 2024-2026 CIP water program, Table 11 (p.19). Shares are of the spendable amount each year.
    funding_mix={"bonds": 0.293, "rate_revenue": 0.303, "interest_free_loan": 0.211, "srf_loan": 0.193},
    loan_terms={"bonds": {"rate": 0.04, "years": 20},                # ASSUMPTION
                "interest_free_loan": {"rate": 0.0, "years": 10},    # BWSC CIP p.18 (MWRA LWSAP)
                "srf_loan": {"rate": 0.02, "years": 25}},            # term: BWSC CIP p.18; rate: ASSUMPTION
    # DECISION: interfaces.md lists [replace_pipe, repave], but BWSC CIP p.17 and budget_agent_reference.md put main relining
    # under renewal and replacement too, so reline_pipe is eligible. Preservation and reconstruction of roads are not (ASSUMPTION).
    rate_revenue_eligible_work=("replace_pipe", "reline_pipe", "repave"),
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
