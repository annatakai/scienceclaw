"""Adapter: runner output (sim/runner.py simulate(..., cip=True)["cip"]) -> the shapes cip/report.py expects.
Runner output: all priced proposals, all decisions (year, funding_source, bundle_id, ...), a city dict with street and
neighborhood, the reserve balance by year, and the config used. ALL DATA SIMULATED."""
from sim.config_meta import META

FLAT = {"loan_terms": ("interest_free_loan", "srf_loan", "bonds")}


def _value(cfg, name):
    if name == "street_network":
        return "real Boston street segments"
    if "." in name:
        a, b = name.split(".")
        return cfg[a][b]
    return cfg[name]


def methodology(cfg, sizing=None):
    """One row per input the report shows: value, status (Sourced / Calibrated / Simulated assumption), source, range tested."""
    rows = []
    for name, (status, source, checked, rng, note) in META.items():
        try:
            v = _value(cfg, name)
        except KeyError:
            continue
        rows.append(dict(name=name, value=v, status=status, source=source, checked=checked, range=rng, note=note))
    if sizing:
        rows.append(dict(name="reserve_share", value=f"{sizing['share']:.2f} of budget" + (" (cap applied)" if sizing["capped"] else ""),
                         status="Simulated assumption", source=f"Derived: 95th percentile of simulated yearly emergency cost "
                         f"(${sizing['p95_yearly_emergency']:,}) over {sizing['pilot_seeds']} pilot seeds = {sizing['uncapped_share']:.2f} of the "
                         f"budget, capped by reserve_max_fraction", checked="2026-10-31", range="cap 0.10 to 0.25 per docs/interfaces.md",
                         note="Share of the annual capital budget set aside for emergency repairs."))
    return rows


def to_report_inputs(run, baseline_run=None):
    """run: the dict returned by simulate(..., cip=True). baseline_run: the isolated run on the same seed (optional)."""
    c = run["cip"]
    props = [p for p in c["proposals"]]
    config = dict(start_year=c["config"]["start_year"], horizon_years=c["config"]["horizon_years"],
                  loan_terms=c["config"]["loan_terms"], miles=c["miles"], reserve=c["reserve"])
    baseline = None
    if baseline_run:
        funded = [d for d in baseline_run["cip"]["decisions"] if d["funded"]]
        keys = {(d["bundle_id"] or d["proposal_id"]) for d in funded}
        baseline = dict(funded_projects=len(funded), street_openings=len(keys), total_funded=sum(d["amount"] for d in funded))
    return dict(decisions=c["decisions"], proposals=props, city=c["city"], config=config, baseline=baseline,
                meta=methodology(c["config"], c.get("reserve_sizing")))
