"""Synthetic city on real Boston main streets (OSM geometry) and everything that changes it.
ALL ASSET DATA IS SIMULATED."""
import json
import math
import pathlib
import random

from agents.pipe_agent import adapter
from agents.road_agent.scoring import pcr
from sim import costs
from sim.config import CFG


class City:
    def __init__(self, cfg):
        self.cfg = cfg
        rng = random.Random(f"city-{cfg['seed']}")
        # REAL street geometry (OpenStreetMap, cached by sim/fetch_streets.py); everything below is simulated
        streets = json.loads((pathlib.Path(__file__).resolve().parent.parent / "data" / "boston_streets.json").read_text())
        self.segs = []
        for st in streets["segments"]:
            yr = rng.randint(1895, 2008)
            if yr < 1950:
                mat = "cast_iron"
            elif yr < 1985:
                mat = rng.choice(["cast_iron", "ductile_iron", "ductile_iron", "steel"])
            else:
                mat = rng.choice(["ductile_iron", "pvc"])
            age = 2026 - yr
            lam = max(0, (age - 30) / 100) * (1.6 if mat == "cast_iron" else 0.6)
            breaks = sorted(rng.randint(2006, 2025) for _ in range(min(3, _poisson(rng, lam))))
            cls, adt_band = cfg["road_class_map"][st["highway"]]
            adt = {"arterial": rng.randint(10_000, 16_000), "collector": rng.randint(4_000, 8_000),
                   "local": rng.randint(300, 1_500)}[adt_band]
            diam = rng.choice([6, 8, 8, 12, 12, 16]) if adt_band != "local" else rng.choice([6, 8, 8, 12])
            self.segs.append(dict(
                segment_id=st["id"], street=st["street"], length_ft=st["length_ft"], coords=st["coords"],
                highway=st["highway"],
                pipe=dict(install_year=yr, material=mat, diameter_in=diam, breaks=breaks, soil=round(rng.random(), 2)),
                road=dict(last_paved=rng.randint(1998, 2025), road_class=cls, adt=adt),
                critical=rng.random() < 0.06,
                customers=int(diam * rng.uniform(15, 45)),
                exposure=rng.choices(["low", "moderate", "high"], weights=[4, 3, 2])[0],
            ))
        self.by_id = {s["segment_id"]: s for s in self.segs}
        # calibration scale C so expected city-wide breaks at the start equal n_target (return_formula.md 2.1)
        tot = sum(adapter.pof(self._pipe_rec(s), cfg["start_year"], 0, None, cfg) / 100 for s in self.segs)
        self.C = cfg["n_target"] / tot

    @staticmethod
    def _pipe_rec(s):
        return dict(segment_id=s["segment_id"], street=s["street"], length_ft=s["length_ft"], pipe=s["pipe"],
                    customers=s["customers"], critical=s["critical"], exposure=s["exposure"], aadt=s["road"]["adt"])

    # decentralisation: an agent only ever gets its own view (traffic counts are public, so pipe sees aadt)
    def view_for(self, owner):
        if owner == "pipe":
            return [self._pipe_rec(s) for s in self.segs]
        return [dict(segment_id=s["segment_id"], street=s["street"], length_ft=s["length_ft"], road=s["road"])
                for s in self.segs]

    def p_fail(self, s, year, t=0):
        return min(1.0, self.C * adapter.pof(self._pipe_rec(s), year, t, None, self.cfg) / 100)

    def cof(self, s, year=None):
        return adapter.cof_prime(self._pipe_rec(s), year or self.cfg["start_year"], self.cfg)

    def pipe_rating(self, s, year):
        return adapter.rating(self._pipe_rec(s), year, self.cfg)

    def fail_cost(self, s, year):
        return costs.fail_cost(self, s, year)

    def price(self, prop, year):
        return costs.price(self, prop, year)

    def apply(self, decisions, year):
        spend = openings = 0
        saving = 0.0
        seen, per_seg = set(), {}
        for dcs in decisions:
            if not dcs["funded"]:
                continue
            s = self.by_id[dcs["segment_id"]]
            spend += dcs["amount"]
            saving += dcs.get("saving_share", 0.0)
            per_seg.setdefault(dcs["segment_id"], set())
            bid = dcs.get("bundle_id")
            if bid:
                if bid not in seen:
                    seen.add(bid)
                    openings += 1
                    per_seg[dcs["segment_id"]].add(bid)
            else:
                openings += 1
                per_seg[dcs["segment_id"]].add(dcs["proposal_id"])
            if dcs["work"] == "replace_pipe":
                s["pipe"].update(install_year=year, breaks=[], material="protected_ductile_iron")
            elif dcs["work"] == "reline_pipe":
                age0 = year - s["pipe"]["install_year"]
                s["pipe"]["install_year"] = int(round(year - (1 - self.cfg["rho"]) * age0))
                s["pipe"]["breaks"] = s["pipe"]["breaks"][: len(s["pipe"]["breaks"]) // 2]
            elif dcs["work"] == "repave":
                s["road"]["last_paved"] = year
        return dict(spend=spend, openings=openings, saving=saving,
                    double_digs=sum(max(0, len(v) - 1) for v in per_seg.values()))

    def simulate_failures(self, year):
        out = []
        for s in self.segs:
            if random.Random(f"fail-{self.cfg['seed']}-{year}-{s['segment_id']}").random() < self.p_fail(s, year):
                s["pipe"]["breaks"].append(year)
                out.append(dict(segment_id=s["segment_id"], cost=self.fail_cost(s, year), weight=1 + self.cof(s) / 100))
        return out

    def expected_failures(self, year):
        return sum(self.p_fail(s, year) for s in self.segs)

    def user_cost(self, year):
        tot = 0.0
        for s in self.segs:
            vmt = s["road"]["adt"] * 365 * s["length_ft"] / 5280
            tot += vmt * self.cfg["u0"] * ((100 - pcr(s["road"], year)) / 100) ** 2
        return tot

    def avg_pcr(self, year):
        return sum(pcr(s["road"], year) for s in self.segs) / len(self.segs)


def _poisson(rng, lam):
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= L:
            return k
        k += 1
