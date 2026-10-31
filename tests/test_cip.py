"""CIP report: funded list equals the funded decisions, spending within the spendable amount, debt service follows loan terms.
ALL DATA SIMULATED."""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from cip import adapter, report
from sim import costs, reserve
from sim.config import CFG
from sim.runner import simulate

SMALL = dict(CFG, max_segments=300, reserve_share=0.25)


class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.coord = simulate("coordinated", seed=11, cfg=SMALL, cip=True)
        cls.iso = simulate("isolated", seed=11, cfg=SMALL, cip=True)
        cls.rep = report.build_report(**adapter.to_report_inputs(cls.coord, cls.iso))

    def test_funded_list_equals_funded_decisions(self):
        want = {d["proposal_id"] for d in self.coord["cip"]["decisions"] if d["funded"]}
        got = {r["proposal_id"] for r in self.rep["funded"]}
        self.assertEqual(got, want)
        self.assertEqual(self.rep["summary"]["funded_projects"], len(want))
        self.assertAlmostEqual(self.rep["summary"]["total_funded"], sum(d["amount"] for d in self.coord["cip"]["decisions"] if d["funded"]))
        self.assertEqual(report.to_csv(self.rep).count("\n"), len(want) + 1)
        self.assertGreaterEqual(report.to_html(self.rep).count('data-seg="'), len(want))
        self.assertEqual([r["rank"] for r in self.rep["funded"]], list(range(1, len(want) + 1)))

    def test_spending_never_exceeds_spendable(self):
        spendable = reserve.spendable(self.coord["cip"]["config"])
        for y in self.rep["by_year"]:
            self.assertLessEqual(y["total"], spendable + 1)
        self.assertEqual({y["year"] for y in self.rep["by_year"]}, set(range(2026, 2036)))

    def test_no_wait_placeholder_in_lists(self):
        self.assertTrue(all(r["work"] != "wait" for r in self.rep["funded"] + self.rep["not_funded"]))

    def test_debt_service_matches_loan_terms(self):
        cfg = {"start_year": 2027, "horizon_years": 12, "loan_terms": CFG["loan_terms"]}
        props = [dict(proposal_id=f"p{i}", agent="pipe", segment_id="S", year=2027, work="replace_pipe", rationale="", priced={"urgency": .5})
                 for i in range(3)]
        decs = [dict(proposal_id=f"p{i}", bundle_id=None, funded=True, amount=100_000, funding_source=s, return_per_dollar=2.0, reason="")
                for i, s in enumerate(("interest_free_loan", "srf_loan", "rate_revenue"))]
        rep = report.build_report(decs, props, {"S": dict(street="X", neighborhood="Y")}, cfg)
        pay = 100_000 / 10 + costs.annual_payment(100_000, 0.02, 25)       # rate revenue: cash, no debt service
        self.assertEqual(rep["by_year"][0]["debt_service"], 0)             # first payment the year after issue
        self.assertAlmostEqual(rep["by_year"][1]["debt_service"], pay, delta=1)
        self.assertAlmostEqual(rep["by_year"][10]["debt_service"], pay, delta=1)   # the 10-year loan is still being repaid
        self.assertAlmostEqual(report.annual_payment(1000, 0.02, 25), costs.annual_payment(1000, 0.02, 25))

    def test_debt_service_in_run_report(self):
        t = SMALL["loan_terms"]
        for y in self.rep["by_year"]:
            due = 0.0
            for r in self.rep["funded"]:
                lt = t.get(r["funding_source"])
                if lt and r["year"] < y["year"] <= r["year"] + lt["years"]:
                    due += costs.annual_payment(r["amount"], lt["rate"], lt["years"])
            self.assertAlmostEqual(y["debt_service"], due, delta=1)

    def test_methodology_tags_every_input(self):
        self.assertTrue(self.rep["methodology"])
        for m in self.rep["methodology"]:
            self.assertIn(m["status"], {"Sourced", "Calibrated", "Simulated assumption"})
            self.assertTrue(m["source"])

    def test_page_is_self_contained(self):
        page = report.to_page(self.rep)
        self.assertNotIn("http://", page.replace("http://www.w3.org", ""))
        self.assertIn("SIMULATED DATA", page)
        self.assertIn("Methodology", page)
        self.assertIn("cip:select", page)
        self.assertIn("map:year", page)


if __name__ == "__main__":
    unittest.main()
