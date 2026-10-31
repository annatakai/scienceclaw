"""Sanity tests. Run: python3 -m unittest discover -s tests -v   (ALL DATA SIMULATED)"""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sim import CFG, City
from run import simulate


class T(unittest.TestCase):
    def test_deterministic(self):
        a, b = simulate("coordinated", seed=7), simulate("coordinated", seed=7)
        self.assertEqual(a["total_cost"], b["total_cost"])
        self.assertEqual(a["fail"], b["fail"])

    def test_decentralised_views(self):
        city = City(dict(CFG, seed=1))
        self.assertNotIn("road", city.view_for("pipe")[0])
        self.assertNotIn("pipe", city.view_for("road")[0])

    def test_calibration_hits_target(self):
        city = City(dict(CFG, seed=3))
        total = sum(city.p_fail(s, CFG["start_year"]) for s in city.segs)
        self.assertAlmostEqual(total, CFG["n_target"], places=6)

    def test_bundle_cheaper_than_separate(self):
        r = simulate("coordinated", seed=42)
        self.assertGreater(r["dig_savings"], 0)
        self.assertEqual(simulate("isolated", seed=42)["dig_savings"], 0)

    def test_budget_respected(self):
        r = simulate("coordinated", seed=5)
        cap = CFG["annual_capital_budget"] * (1 - CFG["reserve_fraction"]) * CFG["horizon_years"]
        self.assertLessEqual(r["spend"], cap + 1)

    def test_all_strategies_run(self):
        for s in ("isolated", "pooled", "coordinated", "central"):
            self.assertIn("total_cost", simulate(s, seed=2))


if __name__ == "__main__":
    unittest.main()
