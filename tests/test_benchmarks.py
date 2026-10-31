"""Benchmarks and baselines: the knapsack is exact, the plan is feasible, the rankings do what they say. ALL DATA SIMULATED."""
import itertools, os, random, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sim import reserve
from sim.benchmarks import solve_mckp
from sim.config import CFG
from sim.runner import BASELINES, simulate

SMALL = reserve.ensure(dict(CFG, max_segments=300))


def brute(groups, W):
    best = 0.0
    for combo in itertools.product(*[range(-1, len(g)) for g in groups]):
        w = sum(groups[i][j][0] for i, j in enumerate(combo) if j >= 0)
        if w <= W:
            best = max(best, sum(groups[i][j][1] for i, j in enumerate(combo) if j >= 0))
    return best


class T(unittest.TestCase):
    def test_knapsack_matches_brute_force(self):
        rng = random.Random(5)
        for _ in range(40):
            groups = [[(rng.randint(0, 9), rng.uniform(-2, 20)) for _ in range(rng.randint(1, 3))] for _ in range(rng.randint(1, 5))]
            W = rng.randint(0, 20)
            picks = solve_mckp(groups, W)
            got = sum(groups[g][j][1] for g, j in enumerate(picks) if j >= 0)
            self.assertLessEqual(sum(groups[g][j][0] for g, j in enumerate(picks) if j >= 0), W)
            self.assertAlmostEqual(got, brute(groups, W), places=9)

    def test_optimal_plan_is_feasible_and_not_worse_than_greedy_on_value(self):
        opt = simulate("central_ilp", seed=3, cfg=SMALL, cip=True)
        gre = simulate("central_greedy", seed=3, cfg=SMALL, cip=True)
        cap = reserve.spendable(opt["cip"]["config"])
        for r in (opt, gre):
            by_year = {}
            for d in r["cip"]["decisions"]:
                if d["funded"]:
                    by_year[d["year"]] = by_year.get(d["year"], 0.0) + d["amount"]
            self.assertTrue(all(v <= cap + 1 for v in by_year.values()))
        self.assertGreaterEqual(opt["funded"], 1)
        self.assertLessEqual(opt["total_cost"], gre["total_cost"] * 1.02)   # same menu, exact optimiser; small slack for the dynamics

    def test_all_baselines_run_and_are_deterministic(self):
        for s in BASELINES:
            a, b = simulate(s, seed=2, cfg=SMALL), simulate(s, seed=2, cfg=SMALL)
            self.assertEqual(a["total_cost"], b["total_cost"], s)
            self.assertGreater(a["total_cost"], 0)

    def test_age_first_funds_the_oldest_pipes_first(self):
        r = simulate("age_first", seed=4, cfg=SMALL, cip=True, record=True)
        first = [d for d in r["cip"]["decisions"] if d["funded"] and d["work"] == "replace_pipe" and d["year"] == 2026]
        self.assertTrue(first)
        idx = {s["id"]: i for i, s in enumerate(r["segs"])}
        inst = r["state0"]["inst"]
        funded_inst = [inst[idx[d["segment_id"]]] for d in first]
        self.assertLessEqual(max(funded_inst), sorted(inst)[len(inst) // 2])   # all from the older half of the pipes


if __name__ == "__main__":
    unittest.main()
