"""Emergency reserve sized from the simulation, replacing the fixed 15% (docs/assumptions_register.md section 7).
reserve share = min(95th percentile of yearly emergency repair cost across pilot seeds / annual budget, reserve_max_fraction).
Emergency repairs are drawn from the reserve each year; the balance by year is reported by the runner. ALL DATA SIMULATED."""
import hashlib
import json
import multiprocessing as mp
import pathlib

CACHE = pathlib.Path(__file__).resolve().parent.parent / "outputs" / "reserve_cache.json"
KEYS = ("neighborhood", "max_segments", "annual_budget_per_mile", "breaks_per_mile_year", "emergency_multiplier", "pipe_per_ft",
        "repave_per_ft", "c_social_max", "cost_inflation", "reserve_pilot_seeds", "reserve_percentile", "reserve_max_fraction",
        "horizon_years", "sim_years", "annual_capital_budget", "n_target", "dig_fixed", "discount_rate")


def share(cfg):
    """Fraction of the annual capital budget held back."""
    if cfg.get("reserve_mode") == "fixed":
        return cfg["reserve_fraction"]
    return cfg["reserve_share"]


def spendable(cfg):
    return cfg["annual_capital_budget"] * (1 - share(cfg))


def _percentile(v, q):
    v = sorted(v)
    k = (len(v) - 1) * q / 100
    lo, hi = int(k), min(int(k) + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


def _pilot_run(job):
    from sim.runner import simulate
    cfg, seed = job
    r = simulate("isolated", seed=seed, cfg=cfg, record=True)
    return [y["emerg_year"] for y in r["years"]], r["cfg"]["annual_capital_budget"]


def size(cfg, workers=None):
    """Run the pilot (isolated strategy, no reserve held back, seeds 1000+i, separate from reported seeds)."""
    n = cfg["reserve_pilot_seeds"]
    pilot = dict(cfg, reserve_mode="fixed", reserve_fraction=0.0, reserve_share=0.0)
    jobs = [(pilot, 1000 + i) for i in range(n)]
    with mp.get_context("spawn").Pool(workers or min(n, mp.cpu_count())) as pool:
        res = pool.map(_pilot_run, jobs, chunksize=1)
    yearly = [x for r, _ in res for x in r]
    budget = res[0][1]
    p = _percentile(yearly, cfg["reserve_percentile"])
    return dict(p95_yearly_emergency=round(p), annual_budget=budget, uncapped_share=round(p / budget, 4),
                share=round(min(p / budget, cfg["reserve_max_fraction"]), 4), capped=p / budget > cfg["reserve_max_fraction"],
                pilot_seeds=n, yearly_values=len(yearly))


def ensure(cfg):
    """Return cfg with reserve_share (and the sizing record) filled in, from the cache or a pilot. Call in the parent
    process before starting workers."""
    if cfg.get("reserve_mode") == "fixed" or "reserve_share" in cfg:
        return cfg
    key = hashlib.sha1(json.dumps({k: cfg.get(k) for k in KEYS}, sort_keys=True, default=str).encode()).hexdigest()[:16]
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    if key not in cache:
        cache[key] = size(cfg)
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(cache, indent=1))
    rec = cache[key]
    return dict(cfg, reserve_share=rec["share"], reserve_sizing=rec)
