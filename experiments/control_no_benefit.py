"""Zero-benefit control (docs/evidence_plan.md section 3): set the trench cost and the dig penalty to zero. The savings from
sharing a dig come from those two numbers, so with both at zero the dig savings must be exactly zero and the value of the
board (coordinated minus pooled) must shrink to what is left once the mechanism is removed. ALL DATA SIMULATED.
Usage: python3 -m experiments.control_no_benefit [n_seeds=10] [--max-segments 800]"""
import argparse
import statistics as st

from experiments.compare import ci, run_all
from sim import reserve
from sim.config import CFG


def summarize(runs, label):
    d = [a["total_cost"] - b["total_cost"] for a, b in zip(runs["coordinated"], runs["pooled"])]
    ds = [r["dig_savings"] for r in runs["coordinated"]]
    n = {k: st.mean(r["proposals"] for r in runs[k]) for k in ("pooled", "coordinated")}
    f = {k: st.mean(r["funded"] for r in runs[k]) for k in ("pooled", "coordinated")}
    print(f"{label:<28} dig savings ${st.mean(ds) / 1e6:6.3f}M | coordinated - pooled total cost {st.mean(d) / 1e6:+8.3f}M ± {ci(d) / 1e6:.3f}M"
          f" | proposals pooled {n['pooled']:.0f} vs coordinated {n['coordinated']:.0f}; funded {f['pooled']:.0f} vs {f['coordinated']:.0f}")
    return st.mean(ds), st.mean(d), ci(d)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("n_seeds", nargs="?", type=int, default=10)
    ap.add_argument("--max-segments", type=int, default=800)
    a = ap.parse_args()
    base = reserve.ensure(dict(CFG, max_segments=a.max_segments))
    print(f"{a.n_seeds} seeds, {a.max_segments}-segment area; the penalty is zeroed with lam=0, the trench with dig_fixed=0")
    on = summarize(run_all(a.n_seeds, base), "as configured")
    ctrl = reserve.ensure(dict(base, dig_fixed=0, lam=0.0, reserve_share=base["reserve_share"]))
    off = summarize(run_all(a.n_seeds, ctrl), "control: trench = 0, penalty = 0")
    print("\nPASS: dig savings vanish." if abs(off[0]) < 1.0 else "\nFAIL: dig savings did not vanish; look for a bug before going further.")
    gap = abs(off[1]) <= off[2]
    print("The coordinated-pooled gap " + ("is within its confidence interval of zero." if gap else
          f"does NOT vanish ({off[1] / 1e6:+.3f}M, CI ±{off[2] / 1e6:.3f}M). Not a bug by itself: coordination also changes WHICH work is funded "
          "(the board's join requests add proposals, see the counts above, and the budget does not bind, so more work clears the hurdle). "
          "That is a menu-size effect, separate from shared-dig savings: a pooled run with a 3x larger menu does better than coordinated "
          "with the normal menu (checked by hand, see AUDIT.md item 11)."))


if __name__ == "__main__":
    main()
