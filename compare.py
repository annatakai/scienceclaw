"""Multi-seed comparison. Usage: python compare.py [n_seeds] [budget]. ALL DATA SIMULATED."""
import sys, statistics as st
from run import simulate, STRATEGIES
from sim import CFG

n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
budget = int(sys.argv[2]) if len(sys.argv) > 2 else CFG["annual_capital_budget"]
cfg = dict(CFG, annual_capital_budget=budget)
runs = {s: [simulate(s, seed=i, cfg=cfg) for i in range(n)] for s in STRATEGIES}
cols = [("exp_fail", "exp. failures"), ("fail", "failures"), ("spend", "capital $M"), ("emerg", "emergency $M"),
        ("user_cost", "road user $M"), ("total_cost", "total $M"), ("dig_savings", "dig savings $M"),
        ("openings", "openings"), ("avg_pcr_end", "avg PCR end")]
print(f"{n} seeds, budget ${budget:,}/yr, mean (95% CI half-width)")
print(f"{'strategy':<12}" + "".join(f"{lab:>20}" for _, lab in cols))
for s in STRATEGIES:
    row = f"{s:<12}"
    for k, _ in cols:
        v = [r[k] for r in runs[s]]
        m, h = st.mean(v), 1.96 * st.stdev(v) / len(v) ** 0.5
        sc = 1e6 if k in ("spend", "emerg", "user_cost", "total_cost", "dig_savings") else 1
        row += f"{m / sc:>11.2f} ±{h / sc:<6.2f}  "
    print(row)
# paired difference vs isolated on total cost (same seeds => same city and same failure luck)
for s in ("pooled", "coordinated", "central"):
    d = [a["total_cost"] - b["total_cost"] for a, b in zip(runs[s], runs["isolated"])]
    print(f"paired total-cost difference {s} - isolated: {st.mean(d) / 1e6:+.2f}M ± {1.96 * st.stdev(d) / len(d) ** 0.5 / 1e6:.2f}M")
d = [a["total_cost"] - b["total_cost"] for a, b in zip(runs["coordinated"], runs["pooled"])]
print(f"paired total-cost difference coordinated - pooled (value of the board alone): {st.mean(d) / 1e6:+.2f}M ± {1.96 * st.stdev(d) / len(d) ** 0.5 / 1e6:.2f}M")
