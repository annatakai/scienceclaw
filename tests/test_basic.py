"""Sanity tests. Run: python3 -m unittest discover -s tests -v   (ALL DATA SIMULATED)"""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from agents.pipe_agent import scoring
from agents.road_agent import scoring as road_scoring
from agents.budget_agent import scoring as budget_scoring
from sim import reserve
from sim.city import City
from sim.config import CFG

SMALL = dict(CFG, max_segments=800)   # compact 800-segment area: fast; the full network has its own loader test
from sim.runner import simulate


class T(unittest.TestCase):
    def test_deterministic(self):
        a, b = simulate("coordinated", seed=7, cfg=SMALL), simulate("coordinated", seed=7, cfg=SMALL)
        self.assertEqual((a["total_cost"], a["fail"]), (b["total_cost"], b["fail"]))

    def test_decentralised_views(self):
        city = City(dict(SMALL, seed=1))
        self.assertNotIn("road", city.view_for("pipe")[0])
        self.assertNotIn("pipe", city.view_for("road")[0])

    def test_calibration_hits_target(self):
        city = City(dict(SMALL, seed=3))
        self.assertAlmostEqual(sum(city.p_fail(s, CFG["start_year"]) for s in city.segs), city.cfg["n_target"], places=6)

    def test_team_rubric_complete_for_every_pipe(self):
        city = City(dict(SMALL, seed=4))
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
        # the mechanism, under a stress break rate (0.30 per mile): at the calibrated rate (35 / 1,018) bundling saves nothing on this area
        stress = dict(SMALL, breaks_per_mile_year=0.30)
        self.assertGreater(simulate("coordinated", seed=42, cfg=stress)["dig_savings"], 0)
        self.assertEqual(simulate("isolated", seed=42, cfg=SMALL)["dig_savings"], 0)

    def test_budget_respected(self):
        r = simulate("coordinated", seed=5, cfg=SMALL, record=True)
        cap = reserve.spendable(r["cfg"]) * CFG["horizon_years"]
        self.assertLessEqual(r["spend"], cap + 1)

    def test_real_street_loader(self):
        city = City(dict(CFG, seed=1))
        self.assertGreater(len(city.segs), 10_000)
        self.assertTrue(700 < city.total_miles < 1000, city.total_miles)
        self.assertTrue(all(s["road"]["road_class"] in ("arterial", "collector", "local") for s in city.segs))
        self.assertTrue(all(s["length_ft"] > 0 and len(s["coords"]) >= 2 for s in city.segs))
        self.assertEqual(len(city.by_id), len(city.segs))     # segment ids are unique
        self.assertAlmostEqual(city.cfg["annual_capital_budget"], CFG["annual_budget_per_mile"] * city.total_miles, delta=1)

    def test_subset_options_and_stable_attributes(self):
        se = City(dict(CFG, seed=1, neighborhood="South End"))
        self.assertTrue(0 < len(se.segs) < 1000 and all(s["neighborhood"] == "South End" for s in se.segs))
        full = City(dict(CFG, seed=1, max_segments=300))
        self.assertEqual(len(full.segs), 300)
        again = City(dict(CFG, seed=1, neighborhood="South End"))   # a segment looks the same however it is loaded
        self.assertEqual(se.segs[0]["pipe"], again.segs[0]["pipe"])

    def test_older_pipes_in_older_neighborhoods(self):
        city = City(dict(CFG, seed=1))
        def mean_year(nbs):
            v = [s["pipe"]["install_year"] for s in city.segs if s["neighborhood"] in nbs]
            return sum(v) / len(v)
        self.assertLess(mean_year(CFG["neighborhoods_old"]), mean_year(CFG["neighborhoods_new"]))

    def test_all_strategies_run(self):
        for s in ("isolated", "pooled", "coordinated", "central"):
            self.assertIn("total_cost", simulate(s, seed=2, cfg=SMALL))


if __name__ == "__main__":
    unittest.main()
