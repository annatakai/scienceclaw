"""Multi-seed comparison, parallel over (strategy, seed). ALL DATA SIMULATED.
Usage: python3 -m experiments.compare [n_seeds] [--neighborhood NAME] [--max-segments N] [--workers N] [--years N] [--budget USD]
Default is 8 seeds on the full network (about 15 s per strategy-year-set per seed, parallelised); use 30 on a subset."""
import argparse
import multiprocessing as mp
import statistics as st
import time

import json
import pathlib

from sim import reserve, snapshot
from sim.config import CFG
from sim.runner import STRATEGIES, simulate

COLS = [("exp_fail", "exp. failures"), ("fail", "failures"), ("spend", "capital $M"), ("emerg", "emergency $M"),
        ("user_cost", "road user $M"), ("total_cost", "total $M"), ("dig_savings", "dig savings $M"),
        ("openings", "openings"), ("avg_pcr_end", "avg PCR end")]
MONEY = ("spend", "emerg", "user_cost", "total_cost", "dig_savings")


def _run(job):
    strategy, seed, cfg = job
    r = simulate(strategy, seed=seed, cfg=cfg)
    return strategy, seed, r


def run_all(n_seeds, cfg, workers=None):
    jobs = [(s, i, cfg) for i in range(n_seeds) for s in STRATEGIES]
    with mp.Pool(workers or mp.cpu_count()) as pool:
        res = pool.map(_run, jobs, chunksize=1)
    runs = {s: [None] * n_seeds for s in STRATEGIES}
    for s, i, r in res:
        runs[s][i] = r
    return runs


def ci(v):
    return 1.96 * st.stdev(v) / len(v) ** 0.5 if len(v) > 1 else float("nan")


def report(runs, n, cfg):
    print(f"{n} seeds, mean (95% CI half-width)")
    print(f"{'strategy':<12}" + "".join(f"{lab:>20}" for _, lab in COLS))
    for s in STRATEGIES:
        row = f"{s:<12}"
        for k, _ in COLS:
            v = [r[k] for r in runs[s]]
            sc = 1e6 if k in MONEY else 1
            row += f"{st.mean(v) / sc:>11.2f} ±{ci(v) / sc:<6.2f}  "
        print(row)
    # paired difference vs isolated on total cost (same seeds => same city and same failure luck)
    for s in ("pooled", "coordinated", "central"):
        d = [a["total_cost"] - b["total_cost"] for a, b in zip(runs[s], runs["isolated"])]
        print(f"paired total-cost difference {s} - isolated: {st.mean(d) / 1e6:+.2f}M ± {ci(d) / 1e6:.2f}M")
    d = [a["total_cost"] - b["total_cost"] for a, b in zip(runs["coordinated"], runs["pooled"])]
    print(f"paired total-cost difference coordinated - pooled (value of the board alone): {st.mean(d) / 1e6:+.2f}M ± {ci(d) / 1e6:.2f}M")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("n_seeds", nargs="?", type=int, default=8)
    ap.add_argument("--neighborhood")
    ap.add_argument("--max-segments", type=int)
    ap.add_argument("--workers", type=int)
    ap.add_argument("--years", type=int)
    ap.add_argument("--budget", type=int, help="annual capital budget in USD (default: per-mile assumption x miles)")
    a = ap.parse_args()
    cfg = dict(CFG, neighborhood=a.neighborhood, max_segments=a.max_segments)
    if a.years:
        cfg["sim_years"] = a.years
    if a.budget:
        cfg["annual_capital_budget"] = a.budget
    cfg = reserve.ensure(cfg)
    t = time.time()
    runs = run_all(a.n_seeds, cfg, a.workers)
    scope = a.neighborhood or ("first %d segments" % a.max_segments if a.max_segments else "full network")
    print(f"scope: {scope}; wall time {time.time() - t:.0f}s on {a.workers or mp.cpu_count()} workers")
    report(runs, a.n_seeds, cfg)
    # raw per-seed results plus the config snapshot, so the printed table can be reproduced and audited
    name = (a.neighborhood or ("max%d" % a.max_segments if a.max_segments else "full")).replace(" ", "_")
    path = pathlib.Path("outputs/results") / f"compare_{name}_{a.n_seeds}seeds.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({s: [{k: v for k, v in r.items() if not isinstance(v, (list, dict))} for r in rs] for s, rs in runs.items()}))
    print("results:", path, "| config snapshot:", snapshot.write(path, cfg, seeds=a.n_seeds, scope=scope))


if __name__ == "__main__":
    main()
