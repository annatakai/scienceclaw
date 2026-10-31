"""Sanity tests. Run: python3 -m unittest discover -s tests -v   (ALL DATA SIMULATED)"""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from agents.pipe_agent import scoring
from agents.road_agent import scoring as road_scoring
from agents.budget_agent import scoring as budget_scoring
from sim.city import City
from sim.config import CFG
from sim.runner import simulate


class T(unittest.TestCase):
    def test_deterministic(self):
        a, b = simulate("coordinated", seed=7), simulate("coordinated", seed=7)
        self.assertEqual((a["total_cost"], a["fail"]), (b["total_cost"], b["fail"]))

    def test_decentralised_views(self):
        city = City(dict(CFG, seed=1))
        self.assertNotIn("road", city.view_for("pipe")[0])
        self.assertNotIn("pipe", city.view_for("road")[0])

    def test_calibration_hits_target(self):
        city = City(dict(CFG, seed=3))
        self.assertAlmostEqual(sum(city.p_fail(s, CFG["start_year"]) for s in city.segs), CFG["n_target"], places=6)

    def test_team_rubric_complete_for_every_pipe(self):
        city = City(dict(CFG, seed=4))
        for s in city.segs:
            r = city.pipe_rating(s, CFG["start_year"])
            self.assertIn(r["risk_class"], ("Critical", "High", "Moderate", "Low"))

    def test_team_rubric_known_row(self):
        row = dict(installation_year=1941, material="unlined cast iron", break_count=3, length_m=150, observation_years=10,
                   soil_corrosivity="high", condition_grade=4, customers_affected=450, critical_facility="hospital",
                   diameter_mm=300, property_exposure="high", aadt=18000, emergency_cost_usd=150000)
        r = scoring.score_pipe(row, 2026)   # sample row BOS_001 from the team's data; rubric v2.0 rates it High
        self.assertIsNotNone(r["risk_index"])
        self.assertGreaterEqual(r["risk_index"], 50)
        self.assertEqual(r["methodology_version"], scoring.VERSION)

    def test_road_and_budget_ratings(self):
        self.assertEqual(road_scoring.rate_condition(90)[0], "Good")
        self.assertEqual(road_scoring.rate_condition(30)[0], "Failed")
        self.assertEqual(budget_scoring.return_rating(2.5), "Strong")
        self.assertEqual(budget_scoring.urgency_tier(0.95)[1], "Urgent")

    def test_bundling_saves_digs(self):
        self.assertGreater(simulate("coordinated", seed=42)["dig_savings"], 0)
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
