"""Baselines and benchmarks against the agents, paired by seed, with 95% t intervals. ALL DATA SIMULATED.
Usage: python3 -m experiments.baselines [n_seeds=30] [--max-segments 800] [--neighborhood NAME]
central_ilp is exact but prices every option on every segment, so it is only run on compact areas (the full network takes hours)."""
import argparse
import json
import pathlib
import statistics as st

from experiments.compare import MONEY, ci, run_all
from sim import reserve, snapshot
from sim.config import CFG
from sim.runner import BASELINES, STRATEGIES

ALL = ["isolated", "pooled", "coordinated", "single_agent", "age_first", "risk_first", "central", "central_greedy", "central_ilp"]
LABEL = {"central": "central (heuristic, 20% scan)", "central_greedy": "central, full menu, greedy", "central_ilp": "central, full menu, exact knapsack"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("n_seeds", nargs="?", type=int, default=30)
    ap.add_argument("--max-segments", type=int, default=800)
    ap.add_argument("--neighborhood")
    a = ap.parse_args()
    cfg = reserve.ensure(dict(CFG, max_segments=None if a.neighborhood else a.max_segments, neighborhood=a.neighborhood))
    runs = run_all(a.n_seeds, cfg, strategies=ALL)
    scope = a.neighborhood or f"compact {a.max_segments}-segment area"
    print(f"{a.n_seeds} seeds, {scope}, mean (95% CI half-width, t); total = capital + emergency repairs + road user cost, $M\n")
    print(f"{'strategy':<38}{'total':>16}{'capital':>14}{'road user':>16}{'funded':>9}{'dig savings':>14}   coordinated minus this, total")
    for s in ALL:
        row = f"{LABEL.get(s, s):<38}"
        for k, w in (("total_cost", 16), ("spend", 14), ("user_cost", 16)):
            v = [r[k] / 1e6 for r in runs[s]]
            row += f"{st.mean(v):>8.2f} ±{ci(v):<5.2f} ".rjust(w)
        row += f"{st.mean(r['funded'] for r in runs[s]):>9.0f}{st.mean(r['dig_savings'] for r in runs[s]) / 1e6:>14.2f}"
        d = [(x["total_cost"] - y["total_cost"]) / 1e6 for x, y in zip(runs["coordinated"], runs[s])]
        row += f"   {st.mean(d):+8.2f} ±{ci(d):.2f}  ({sum(x < 0 for x in d)}/{len(d)} seeds coordinated lower)" if s != "coordinated" else ""
        print(row)
    path = pathlib.Path("outputs/results") / f"baselines_{a.neighborhood or 'max%d' % a.max_segments}_{a.n_seeds}seeds.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({s: [{k: v for k, v in r.items() if not isinstance(v, (list, dict))} for r in rs] for s, rs in runs.items()}))
    print("\nresults:", path, "| config snapshot:", snapshot.write(path, cfg, seeds=a.n_seeds, scope=scope))


if __name__ == "__main__":
    main()
