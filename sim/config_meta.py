"""Source, status and date checked for every number the report, demo and claims ledger show (docs/evidence_plan.md section 5).
status: Sourced (a document we can cite) | Calibrated (fit to real data we can name) | Simulated assumption (shown with a tested range).
`range` is the range actually tested; "not yet tested" until experiments/sensitivity.py has run it. Nothing is Calibrated yet.
`checked` is the date the entry was last reviewed; "as recorded in X" means the team's register says so and the original
document was not re-read in this repo. Never put a source here that has not been seen."""
S, C, A = "Sourced", "Calibrated", "Simulated assumption"
ASSUMPTION = "ASSUMPTION"
D = "2026-10-31"
REG = "docs/assumptions_register.md"
NT = "not yet tested"

META = {
    "annual_budget_per_mile": (A, ASSUMPTION, D, NT, "Capital budget per mile of street per year."),
    "breaks_per_mile_year": (A, ASSUMPTION, D, NT, "Expected water-main breaks per mile per year (N_target = this x miles). BWSC reports just over 35 failures a year (docs/budget_agent_reference.md); not yet divided by BWSC miles of main."),
    "proposal_fraction": (A, ASSUMPTION, D, NT, "Share of segments each agent may propose on."),
    "central_proposal_fraction": (A, ASSUMPTION, D, NT, "Share of segments the central planner scans."),
    "reserve_max_fraction": (A, ASSUMPTION, D, "0.10 to 0.25 per docs/interfaces.md", "Cap on the simulated reserve as a share of the budget."),
    "reserve_fraction": (A, ASSUMPTION, D, "0.10 to 0.25 per docs/interfaces.md", "Fixed reserve; used only when reserve_mode is fixed."),
    "urgency_full_prob": (A, ASSUMPTION, D, NT, "Yearly failure probability that scores urgency 1.0."),
    "critical_facility_multiplier": (A, ASSUMPTION, D, NT, "Urgency boost for a critical facility."),
    "urgent_cap_fraction": (A, ASSUMPTION, D, NT, "Tier 1 work may use at most this share of the spendable amount."),
    "urgent_override": (A, ASSUMPTION, D, NT, "Urgency at or above this is Tier 1 and can be funded below the hurdle."),
    "min_return": (A, ASSUMPTION, D, NT, "Return hurdle per dollar."),
    "dig_fixed": (A, ASSUMPTION, D, NT, "Cost to open one street segment, paid once per opening (evidence_plan.md priority 1)."),
    "pipe_per_ft": (A, ASSUMPTION, D, NT, "Pipe work cost per foot."),
    "repave_per_ft": (A, ASSUMPTION, D, NT, "Repaving cost per foot."),
    "reline_frac": (A, ASSUMPTION, D, NT, "Relining cost as a share of replacement."),
    "emergency_multiplier": (A, ASSUMPTION, D, NT, "A failure repair costs this multiple of planned replacement."),
    "discount_rate": (A, ASSUMPTION, D, "0.03 to 0.07 per docs/evidence_plan.md", "Discount rate."),
    "cost_inflation": (S, "MassDOT FY27-31 CIP p.58 (asphalt +40% over five years, about 7% a year)", D + " (as recorded in " + REG + "; original not re-read here)", NT, "Cost inflation per year."),
    "department_split": (A, ASSUMPTION, D, NT, "Fixed pipe/road shares, isolated baseline only."),
    "c_social_max": (A, ASSUMPTION, D, NT, "Dollar cost of a worst-case failure (social cost)."),
    "u0": (A, ASSUMPTION, D, NT, "Road user cost, dollars per vehicle-mile at worst condition."),
    "lam": (A, "Range 0.06 to 0.6 stated by the team from the literature; value is ASSUMPTION", D, "0.06 to 0.6", "Share of pavement life lost per cut."),
    "L": (A, ASSUMPTION, D, NT, "Resurfacing cycle in years."),
    "H_replace": (A, ASSUMPTION, D, NT, "Benefit horizon of a replacement, years."),
    "H_reline": (A, ASSUMPTION, D, NT, "Benefit horizon of a reline, years."),
    "rho": (A, ASSUMPTION, D, NT, "Share of pipe age removed by relining."),
    "H_preserve": (A, ASSUMPTION, D, NT, "Benefit horizon of pavement preservation."),
    "rho_preserve": (A, ASSUMPTION, D, NT, "Share of pavement age removed by preservation."),
    "preserve_frac": (A, ASSUMPTION, D, NT, "Preservation cost as a share of a repave."),
    "reconstruct_mult": (A, ASSUMPTION, D, NT, "Reconstruction cost as a multiple of a repave."),
    "reconstruct_bonus_years": (A, ASSUMPTION, D, NT, "Extra years of like-new condition after reconstruction."),
    "pof_band": (A, ASSUMPTION, D, NT, "PoF bounds: x0.85 and x1.15 + 5 (the rubric has no error bar)."),
    "road_benefit_band": (A, ASSUMPTION, D, NT, "Road benefit bounds, plus or minus this share."),
    "P_min": (A, ASSUMPTION, D, NT, "PCR at or below which a road is Failed."),
    "funding_mix": (S, "BWSC 2024-2026 CIP water program, Table 11 (p.19)", D + " (as recorded in " + REG + ")", "fixed", "Share of each year's spendable amount by source."),
    "loan_terms.interest_free_loan": (S, "BWSC CIP p.18 (MWRA LWSAP, interest-free, 10 years)", D + " (as recorded in " + REG + ")", "fixed", "Interest-free loan terms."),
    "loan_terms.srf_loan": (A, "Term from BWSC CIP p.18 (20 to 30 years, below market); rate 2% and 25 years chosen by the team", D, NT, "State revolving loan terms."),
    "loan_terms.bonds": (A, ASSUMPTION, D, NT, "Bond rate and term."),
    "rate_revenue_eligible_work": (S, "BWSC CIP p.17: renewal and replacement, including main relining (docs/budget_agent_reference.md). Relining added by decision; interfaces.md listed replace_pipe and repave only", D + " (as recorded in the docs)", "fixed", "Work that rate revenue may pay for."),
    "era_old": (A, ASSUMPTION, D, NT, "When pipes were mostly laid, older neighborhoods."),
    "adt_range": (A, ASSUMPTION, D, NT, "Traffic range by road class."),
    "street_network": (S, "Analyze Boston Street Segments (SAM) + MassDOT Road Inventory (data/SOURCES.md)", "2026-10-31 (download date in data/build_info.json)", "fixed", "Street geometry, names, lengths, classes (REAL). Everything on and under the streets is simulated."),
}


def tag(name):
    """(status, source, date, range, note) for a config key; unknown keys are an error so nothing ships untagged."""
    return META[name]
