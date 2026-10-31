"""Claims ledger: every number that appears in the demo or the capital plan report, with its status, source and date checked
(docs/evidence_plan.md section 5). Regenerate with: python3 -m cip.ledger  ->  docs/claims_ledger.csv
Inputs come from sim/config_meta.py (one row per config value) and OUTPUTS below (one row per kind of output shown).
Nothing here is a claim about real Boston assets: ALL ASSET DATA IS SIMULATED."""
import csv
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from sim.config import CFG  # noqa: E402
from sim.config_meta import META  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parent.parent / "docs" / "claims_ledger.csv"
SIM = "Simulated assumption"
D = "2026-10-31"
# (claim, where shown, status, source / how derived)
OUTPUTS = [
    ("Segments, miles and road class of the street network", "demo header, legend, report tiles", "Sourced", "Analyze Boston SAM + MassDOT Road Inventory; data/SOURCES.md; counts in README"),
    ("Pipe material, install year, breaks, diameter, soil, customers, critical facility", "demo info panel, table", SIM, "sim/city.py seeded generator; ALL ASSET DATA SIMULATED"),
    ("Pavement last-paved year, condition (PCR), traffic", "demo info panel, table, road layer", SIM, "sim/city.py and agents/road_agent/scoring.py"),
    ("Pipe risk class and index", "demo map, legend, table", SIM, "team rubric agents/pipe_agent/scoring.py v2.0 applied to simulated pipes"),
    ("Funded projects, total funded, street openings, shared digs", "report tiles, Decision list", SIM, "sim/runner.py through cip/report.py; one seed"),
    ("Dig savings", "report tiles, demo Compare, Decision list comparison", SIM, "shared trench cost and avoided penalty (sim/costs.py bundle); driven by dig_fixed and lam"),
    ("Return per dollar, urgency tier, return range", "report, Decision list", SIM, "sim/costs.py implementing docs/return_formula.md"),
    ("Funding by year and source", "report funding table", SIM, "dollars simulated; source shares are Sourced (BWSC CIP Table 11) and enforced in agents/budget_agent/agent.py"),
    ("Debt service and net cost after financing", "report funding table, tiles", SIM, "loan repayments from loan_terms (cip/report.py annual_payment); financing factors in sim/costs.py"),
    ("Program pace (miles per year)", "report pace table", SIM, "funded lengths from the simulation; network miles Sourced"),
    ("Emergency reserve balance by year and its share of the budget", "report reserve table", SIM, "sim/reserve.py: 95th percentile of simulated yearly emergency cost over pilot seeds, capped; sizing record in outputs/reserve_cache.json"),
    ("Capital, emergency repair and road user cost totals; failures", "demo KPIs, Compare, README", SIM, "sim/runner.py; compare results in outputs/results/*.json with config snapshot"),
    ("Mean differences and 95% confidence intervals between strategies", "README, compare output", SIM, "experiments/compare.py, paired by seed"),
    ("BWSC funding mix 29.3 / 30.3 / 21.1 / 19.3 percent", "report methodology", "Sourced", "BWSC 2024-2026 CIP Table 11 (p.19), as recorded in docs/assumptions_register.md section 3; original not re-read here"),
    ("About 35 BWSC water pipe failures per year", "docs only (not yet used in the model)", "Sourced", "BWSC CIP as quoted in docs/budget_agent_reference.md; model break rate is a separate ASSUMPTION until calibrated"),
    ("Net cost factors 0.811 / 0.800 / 1.0", "report methodology", "Sourced", "computed from the loan terms at the 4% discount rate (docs/return_formula.md section 5); tested in tests/test_costs.py"),
]


def rows():
    out = []
    for name, (status, source, checked, rng, note) in META.items():
        v = "(real street data)" if name == "street_network" else (CFG["loan_terms"][name.split(".")[1]] if name.startswith("loan_terms.") else CFG.get(name))
        out.append((f"Input {name}: {note}", "report methodology page, config snapshot", status, source, checked.split(" ")[0], f"value {v}; range tested: {rng}"))
    for claim, where, status, src in OUTPUTS:
        out.append((claim, where, status, src, D, "model output; see source"))
    return out


def main():
    with OUT.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["claim", "where_shown", "status", "source", "date_checked", "notes"])
        w.writerows(rows())
    print(f"wrote {OUT} ({len(rows())} rows)")


if __name__ == "__main__":
    main()
