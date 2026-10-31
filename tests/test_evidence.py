"""Every config value is tagged (source, status, date); snapshots and the claims ledger cover them. ALL DATA SIMULATED."""
import csv, json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from cip import ledger
from sim import snapshot
from sim.config import CFG
from sim.config_meta import META

STRUCTURAL = {"seed", "start_year", "horizon_years", "neighborhood", "max_segments", "proposal_floor", "proposal_cap", "era_mid",
              "era_new", "neighborhoods_old", "neighborhoods_new", "select", "reserve_mode", "reserve_pilot_seeds",
              "reserve_percentile", "loan_terms"}


class T(unittest.TestCase):
    def test_every_config_value_is_tagged(self):
        missing = [k for k in CFG if k not in META and k not in STRUCTURAL and not k.startswith("llm")]
        self.assertEqual(missing, [])
        for k, (status, source, checked, rng, note) in META.items():
            self.assertIn(status, ("Sourced", "Calibrated", "Simulated assumption"), k)
            self.assertTrue(source and checked and rng and note, k)

    def test_snapshot_written_next_to_results(self):
        with tempfile.TemporaryDirectory() as d:
            p = snapshot.write(os.path.join(d, "results.csv"), CFG, seeds=3)
            self.assertTrue(str(p).endswith("results.csv.config.json"))
            snap = json.load(open(p))
            self.assertEqual(snap["config"]["dig_fixed"]["status"], "Simulated assumption")
            self.assertEqual(snap["config"]["cost_inflation"]["status"], "Sourced")
            self.assertEqual(snap["config"]["loan_terms.srf_loan"]["status"], "Simulated assumption")

    def test_claims_ledger_covers_inputs_and_is_current(self):
        rows = ledger.rows()
        text = " ".join(r[0] for r in rows)
        for k in META:
            self.assertIn(f"Input {k}:", text)
        on_disk = list(csv.reader(open(ledger.OUT)))[1:]
        self.assertEqual(len(on_disk), len(rows), "docs/claims_ledger.csv is stale: run python3 -m cip.ledger")
        self.assertTrue(all(r[2] in ("Sourced", "Calibrated", "Simulated assumption") for r in on_disk))


if __name__ == "__main__":
    unittest.main()
