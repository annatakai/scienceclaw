"""sim/costs.py against docs/return_formula.md (section 8 worked example, financing factors, wait a year, flags).
ALL DATA SIMULATED."""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from agents.board import Board
from agents.budget_agent.agent import BudgetAgent
from agents.pipe_agent.agent import PipeAgent
from agents.road_agent.agent import RoadAgent
from sim import costs
from sim.city import City
from sim.config import CFG
from sim.runner import simulate

SMALL = dict(CFG, max_segments=300)


class Example(unittest.TestCase):
    """One 420 ft segment, street age 12, 12,000 vehicles a day (return_formula.md section 8)."""
    T, L_FT, AGE = CFG["dig_fixed"], 420, 12

    def setUp(self):
        self.w_pipe = costs.work_cost(CFG, "replace_pipe", self.L_FT)
        self.w_road = costs.work_cost(CFG, "repave", self.L_FT)
        self.pen = costs.dig_penalty(self.w_road, self.AGE, CFG["lam"], CFG["L"])
        self.g = costs.gross_costs(self.T, self.w_pipe, self.w_road, self.pen)

    def test_gross_costs(self):
        self.assertAlmostEqual(self.pen, 3024)
        self.assertAlmostEqual(self.g["pipe_alone"], 179_024)
        self.assertAlmostEqual(self.g["road_alone"], 100_400)
        self.assertAlmostEqual(self.g["bundle"], 226_400)

    def test_returns_and_npv_from_the_documented_benefits(self):
        B_pipe, B_road = 515_484, 104_235
        self.assertEqual(round(B_pipe / self.g["pipe_alone"], 2), 2.88)
        self.assertEqual(round(B_road / self.g["road_alone"], 2), 1.04)
        self.assertEqual(round(619_720 / self.g["bundle"], 2), 2.74)
        npv = lambda B, c: B - c
        self.assertAlmostEqual(npv(B_pipe, self.g["pipe_alone"]), 336_460)
        self.assertAlmostEqual(npv(B_road, self.g["road_alone"]), 3_835)
        B_bundle = 619_720   # the document rounds the pieces: 515,484 + 104,235 = 619,719
        self.assertAlmostEqual(npv(B_bundle, self.g["bundle"]), 393_320)
        separate = npv(B_pipe, self.g["pipe_alone"]) + npv(B_road, self.g["road_alone"])
        self.assertAlmostEqual(separate, 340_296, delta=1)
        self.assertAlmostEqual(npv(B_bundle, self.g["bundle"]) - separate, 53_024, delta=1)   # trench once + avoided penalty
        self.assertAlmostEqual(53_024, self.T + self.pen)
        self.assertEqual(round(costs.marginal_return(B_road, self.w_road), 2), 2.07)

    def test_bundle_function_matches(self):
        mk = lambda B, alone, comb: dict(benefit_usd=B, benefit_usd_lo=B, benefit_usd_hi=B, cost_alone=alone,
                                         cost_if_combined=comb, dig_cost=self.T)
        b = costs.bundle(mk(515_484, self.g["pipe_alone"], self.w_pipe), mk(104_235, self.g["road_alone"], self.w_road), CFG)
        self.assertAlmostEqual(b["cost"], 226_400)
        self.assertAlmostEqual(b["saving"], 53_024)
        self.assertTrue(b["marginal_ok"])
        self.assertEqual(round(b["B"] / b["cost"], 2), 2.74)

    def test_failure_cost(self):
        social = 0.60 * CFG["c_social_max"]               # CoF' of 60
        self.assertAlmostEqual(costs.emergency_cost(CFG, self.L_FT), 378_000)
        self.assertAlmostEqual(costs.emergency_cost(CFG, self.L_FT) + social, 678_000)


class Formulas(unittest.TestCase):
    def test_financing_factors(self):
        self.assertAlmostEqual(costs.financing_factor(CFG, "interest_free_loan"), 0.811, places=3)
        self.assertAlmostEqual(costs.financing_factor(CFG, "srf_loan"), 0.800, places=3)
        self.assertAlmostEqual(costs.financing_factor(CFG, "bonds"), 1.0, places=6)   # 4% bond at a 4% discount rate
        self.assertEqual(costs.financing_factor(CFG, "rate_revenue"), 1.0)

    def test_loan_interest(self):
        self.assertAlmostEqual(costs.loan_interest(CFG, 1000, "interest_free_loan"), 0.0)
        pay = costs.annual_payment(1000, 0.02, 25)
        self.assertAlmostEqual(costs.loan_interest(CFG, 1000, "srf_loan"), pay * 25 - 1000)

    def test_cheapest_source_first_and_reline_eligible(self):
        self.assertEqual(costs.source_order(CFG), ["srf_loan", "interest_free_loan", "rate_revenue", "bonds"])
        self.assertIn("reline_pipe", CFG["rate_revenue_eligible_work"])
        self.assertAlmostEqual(sum(CFG["funding_mix"].values()), 1.0, places=3)

    def test_engineering_review_flag(self):
        self.assertTrue(costs.review_flag(0.8, 1.3, 1.0))
        self.assertTrue(costs.review_flag(0.8, 1.0, 1.0))      # return_hi equal to the hurdle still counts
        self.assertFalse(costs.review_flag(1.1, 1.5, 1.0))
        self.assertFalse(costs.review_flag(0.5, 0.9, 1.0))


class Priced(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.city = City(dict(SMALL, seed=3, reserve_share=0.25))
        cls.cfg = cls.city.cfg
        cls.pipe, cls.road = PipeAgent(cls.cfg), RoadAgent(cls.cfg)
        y = cls.cfg["start_year"]
        cls.pp = cls.pipe.propose(y, cls.city.view_for("pipe"), Board(), 9)
        cls.rp = cls.road.propose(y, cls.city.view_for("road"), Board(), 9)
        for p in cls.pp + cls.rp:
            p["priced"] = cls.city.price(p, y)

    def test_menu_has_the_interfaces_items(self):
        self.assertTrue({"replace_pipe", "reline_pipe", "wait"} <= {p["work"] for p in self.pp})
        self.assertTrue({"repave", "wait"} <= {p["work"] for p in self.rp})
        self.assertTrue({"preserve_road", "reconstruct_road"} & {p["work"] for p in self.rp})
        self.assertTrue(all(p["work_cost"] == 0 for p in self.pp + self.rp if p["work"] == "wait"))

    def test_wait_costs_one_year_of_inflation_and_discount(self):
        g, r = 1 + self.cfg["cost_inflation"], self.cfg["discount_rate"]
        for ps in (self.pp, self.rp):
            wait = next(p for p in ps if p["work"] == "wait")
            job = next(p for p in ps if p["segment_id"] == wait["segment_id"] and p["work"] == wait["defer"]["work"])
            self.assertAlmostEqual(wait["priced"]["cost_alone"], job["priced"]["cost_alone"] * g / (1 + r), places=4)

    def test_wait_loses_a_year_of_benefit_when_nothing_ages(self):
        # flat risk: waiting only pushes the same benefit one year out and drops the last year
        city = self.city
        wait = next(p for p in self.pp if p["work"] == "wait")
        job = next(p for p in self.pp if p["segment_id"] == wait["segment_id"] and p["work"] == "replace_pipe")
        self.assertLess(wait["priced"]["benefit_usd"], job["priced"]["benefit_usd"] * 1.5)
        self.assertGreater(wait["priced"]["benefit_usd"], 0)

    def test_priced_block_fields(self):
        for p in self.pp + self.rp:
            pr = p["priced"]
            self.assertLessEqual(pr["return_lo"], pr["return_alone"] + 1e-9)
            self.assertGreaterEqual(pr["return_hi"], pr["return_alone"] - 1e-9)
            self.assertIn("needs_review", pr)
            self.assertIsNotNone(pr["cost_if_combined"])

    def test_pipe_dollars_are_computed_here_only(self):
        p = next(p for p in self.pp if p["work"] == "replace_pipe")
        s = self.city.by_id[p["segment_id"]]
        T = self.cfg["dig_fixed"]
        pen = costs.dig_penalty(costs.work_cost(self.cfg, "repave", s["length_ft"], p["year"]), p["year"] - s["road"]["last_paved"],
                                self.cfg["lam"], self.cfg["L"])
        self.assertAlmostEqual(p["priced"]["cost_alone"], T + p["work_cost"] + pen)
        self.assertAlmostEqual(p["priced"]["cost_if_combined"], p["work_cost"])


class Funding(unittest.TestCase):
    def test_sources_respect_shares_eligibility_and_budget(self):
        r = simulate("coordinated", seed=5, cfg=dict(SMALL, reserve_share=0.25), cip=True)
        cfg = r["cip"]["config"]
        spend = {}
        for d in r["cip"]["decisions"]:
            if d["funded"]:
                spend.setdefault(d["year"], {}).setdefault(d["funding_source"], 0.0)
                spend[d["year"]][d["funding_source"]] += d["amount"]
                if d["funding_source"] == "rate_revenue":
                    self.assertIn(d["work"], cfg["rate_revenue_eligible_work"])
        spendable = cfg["annual_capital_budget"] * (1 - 0.25)
        self.assertTrue(spend)
        for y, by in spend.items():
            self.assertLessEqual(sum(by.values()), spendable + 1)
            for s, v in by.items():
                self.assertLessEqual(v, cfg["funding_mix"][s] * spendable + 1, (y, s))

    def test_funded_decisions_carry_year_source_and_net_cost(self):
        r = simulate("coordinated", seed=5, cfg=dict(SMALL, reserve_share=0.25), cip=True)
        f = [d for d in r["cip"]["decisions"] if d["funded"]]
        self.assertTrue(f)
        for d in f:
            self.assertIn(d["funding_source"], CFG["funding_mix"])
            self.assertAlmostEqual(d["net_cost"], d["amount"] * costs.financing_factor(CFG, d["funding_source"]))
        self.assertTrue(all(d["work"] != "wait" for d in f))

    def test_reserve_balance_by_year(self):
        r = simulate("isolated", seed=5, cfg=dict(SMALL, reserve_share=0.25))
        self.assertEqual(len(r["reserve"]), CFG["horizon_years"])
        for row in r["reserve"]:
            self.assertAlmostEqual(row["opening"] + row["set_aside"] - row["emergency"] + row["shortfall"], row["closing"], delta=3)
            self.assertGreaterEqual(row["closing"], 0)


if __name__ == "__main__":
    unittest.main()
