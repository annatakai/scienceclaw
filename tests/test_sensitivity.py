"""Sensitivity summary and tornado drawing on a small synthetic result. ALL DATA SIMULATED."""
import os, sys, tempfile, unittest, pathlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from experiments import sensitivity as S


def m(mean, ci=0.1):
    return dict(mean=mean, ci=ci, lower_in=5, n=10)


def point(v, iso, pooled, dig):
    return dict(value=v, dig_savings=dict(mean=dig, ci=0.01), vs_isolated=m(iso), vs_pooled=m(pooled), total={})


class T(unittest.TestCase):
    def setUp(self):
        self.o = dict(n_seeds=10, scope="test", base=dict(dig_savings=dict(mean=0.3, ci=0.01), vs_isolated=m(-5), vs_pooled=m(-1), total={}),
                      one_at_a_time={p: dict(why="", base_value=1, low=point(1, -4, -0.05, 0.2), high=point(2, 2.0, -1, 0.4)) for p in S.PARAMS},
                      top3=dict(params=["u0", "lam", "dig_fixed"], corners=[dict(settings={}, **point(0, -3, -1, 0.3)) for _ in range(8)]))

    def test_summary_reports_sign_flip_and_indistinguishable_cases(self):
        t = S.summarize(self.o)
        self.assertIn("the sign flips in the others", t)          # a setting with a positive difference exists
        self.assertIn("not distinguishable from zero", t)         # low value: -0.05 +- 0.10

    def test_tornado_files(self):
        with tempfile.TemporaryDirectory() as d:
            S.tornado(self.o, pathlib.Path(d))
            html = open(os.path.join(d, "tornado.html")).read()
            self.assertIn("SIMULATED DATA", html)
            self.assertEqual(html.count("<svg"), 2)
            for p in S.PARAMS:
                self.assertIn(p, html)


if __name__ == "__main__":
    unittest.main()
