"""Dig Once: shared simulation pieces. ALL DATA IS SIMULATED (synthetic city on real Boston coordinates).

Contains: config, synthetic city, pipe/road risk methods, pricing (the ONLY place dollars are computed),
failures, and applying funding decisions. Follows interfaces.md v0.2 / return_formula.md in simplified form.
"""
import math
import random

CFG = dict(
    seed=42, start_year=2026, horizon_years=10, grid=9,
    annual_capital_budget=1_200_000,  # ASSUMPTION (demo value; doc default is 600k, which is too small to move failures)
    reserve_fraction=0.15,           # ASSUMPTION
    urgency_full_prob=0.30,          # ASSUMPTION
    critical_facility_multiplier=1.25,  # ASSUMPTION
    urgent_cap_fraction=0.5,         # ASSUMPTION
    urgent_override=0.9,             # ASSUMPTION
    min_return=1.0,                  # ASSUMPTION (hurdle)
    dig_fixed=50_000,                # ASSUMPTION: cost to open one street segment
    pipe_per_ft=300,                 # ASSUMPTION
    repave_per_ft=120,               # ASSUMPTION
    reline_frac=0.5,                 # ASSUMPTION: reline costs this share of replacement
    emergency_multiplier=3.0,        # ASSUMPTION
    discount_rate=0.04,              # ASSUMPTION
    cost_inflation=0.07,             # MassDOT FY27-31 CIP p.58 (asphalt +40% over 5y)
    max_proposals=15,                # menu size per agent per year
    department_split={"pipe": 0.6, "road": 0.4},  # ASSUMPTION (isolated baseline only)
    n_target=8.0,                    # ASSUMPTION: expected breaks/yr for whole city (tuned so worked example ~2.9)
    c_social_max=500_000,            # ASSUMPTION
    u0=0.30,                         # ASSUMPTION: road user cost $/veh-mile at worst condition
    lam=0.3, L=15,                   # ASSUMPTION: pavement life lost per cut, resurfacing cycle
    H_replace=10, H_reline=7, rho=0.6,  # ASSUMPTION
    p_min=40, pcr_ok=85,             # ASSUMPTION: road urgency scale
    rate_revenue_share=0.5,          # ASSUMPTION (BWSC water program is ~30% rate revenue)
    origin_lat=42.3390, origin_lon=-71.0780, dlat=0.0012, dlon=0.0016,  # South End-ish, Boston
)

MAT_SCORE = {"cast_iron": 90, "steel": 60, "ductile_iron": 35, "pvc": 15}


def infl(cfg, year):
    return (1 + cfg["cost_inflation"]) ** (year - cfg["start_year"])


# ----------------------------------------------------------------------------- risk methods
def pof_index(pipe, length_ft, year, t=0, treat=None, cfg=CFG):
    """Heuristic probability-of-failure INDEX 0-100 (not a probability). Weights are the team's own assumption."""
    age0 = year - pipe["install_year"]
    nb = len(pipe["breaks"])
    mat = pipe["material"]
    if treat == "replace":
        age, nb, mat = t, 0, "ductile_iron"
    elif treat == "reline":
        age, nb = (1 - cfg["rho"]) * age0 + t, nb * 0.5
    else:
        age = age0 + t
    age_s = min(100.0, max(0.0, age))
    br_s = min(100.0, (nb / ((length_ft / 3280.84) * 20)) / 0.5 * 100)
    cond_s = min(100.0, age_s + 8 * nb)  # condition unknown -> proxy from age and breaks
    return (0.20 * age_s + 0.20 * MAT_SCORE[mat] + 0.25 * br_s + 0.15 * pipe["soil"] * 100 + 0.20 * cond_s)


def cof_prime(customers, critical, diameter_in):
    """Consequence index without traffic/economic parts, renormalised (return_formula.md 2.2)."""
    cust = min(100.0, customers / 5.0)
    fac = 100.0 if critical else 0.0
    flood = min(100.0, diameter_in * 5.0)
    return (0.35 * cust + 0.30 * fac + 0.15 * flood) / 0.80


def pcr(road, year, t=0, repaved=False):
    age = t if repaved else (year - road["last_paved"] + t)
    k = 0.6 + 0.4 * road["adt"] / 10_000
    return max(0.0, 100.0 - k * max(0.0, age) ** 1.4)


# ----------------------------------------------------------------------------- the city
class City:
    def __init__(self, cfg):
        self.cfg = cfg
        rng = random.Random(f"city-{cfg['seed']}")
        n = cfg["grid"]
        self.segs = []
        mid = n // 2

        def node(i, j):
            return (cfg["origin_lat"] + i * cfg["dlat"], cfg["origin_lon"] + j * cfg["dlon"])

        def add(i1, j1, i2, j2, street, line):
            a, b = node(i1, j1), node(i2, j2)
            dy = (b[0] - a[0]) * 111_320
            dx = (b[1] - a[1]) * 111_320 * math.cos(math.radians(a[0]))
            length_ft = math.hypot(dx, dy) * 3.28084 * rng.uniform(0.95, 1.05)
            yr = rng.randint(1895, 2008)
            if yr < 1950:
                mat = "cast_iron"
            elif yr < 1985:
                mat = rng.choice(["cast_iron", "ductile_iron", "ductile_iron", "steel"])
            else:
                mat = rng.choice(["ductile_iron", "pvc"])
            age = 2026 - yr
            lam = max(0, (age - 30) / 100) * (1.6 if mat == "cast_iron" else 0.6)
            nbreaks = min(3, _poisson(rng, lam))
            breaks = sorted(rng.randint(2006, 2025) for _ in range(nbreaks))
            cls = "arterial" if line in (mid,) else ("collector" if line in (mid - 2, mid + 2) else "local")
            adt = {"arterial": rng.randint(10_000, 16_000), "collector": rng.randint(4_000, 8_000),
                   "local": rng.randint(300, 1_500)}[cls]
            diam = rng.choice([6, 8, 8, 12, 12, 16]) if cls != "local" else rng.choice([6, 8, 8, 12])
            self.segs.append(dict(
                segment_id=f"S{len(self.segs):03d}", street=street, length_ft=length_ft,
                coords=[a, b],
                pipe=dict(install_year=yr, material=mat, diameter_in=diam, breaks=breaks, soil=round(rng.random(), 2)),
                road=dict(last_paved=rng.randint(1998, 2025), road_class=cls, adt=adt),
                critical=rng.random() < 0.06,
                customers=int(diam * rng.uniform(15, 45)),
            ))

        for i in range(n):
            for j in range(n - 1):
                add(i, j, i, j + 1, f"Row {i + 1} St", i)
        for j in range(n):
            for i in range(n - 1):
                add(i, j, i + 1, j, f"Col {j + 1} Ave", j)
        self.by_id = {s["segment_id"]: s for s in self.segs}
        # calibration scale C so expected city-wide breaks at start = n_target (return_formula.md 2.1)
        tot = sum(pof_index(s["pipe"], s["length_ft"], cfg["start_year"], cfg=cfg) / 100 for s in self.segs)
        self.C = cfg["n_target"] / tot

    # decentralisation: an agent only gets its own view
    def view_for(self, owner):
        if owner == "pipe":
            return [dict(segment_id=s["segment_id"], street=s["street"], length_ft=s["length_ft"], pipe=s["pipe"],
                         customers=s["customers"], critical=s["critical"]) for s in self.segs]
        return [dict(segment_id=s["segment_id"], street=s["street"], length_ft=s["length_ft"], road=s["road"])
                for s in self.segs]

    def p_fail(self, s, year, t=0):
        return min(1.0, self.C * pof_index(s["pipe"], s["length_ft"], year, t, cfg=self.cfg) / 100)

    def cof(self, s):
        return cof_prime(s["customers"], s["critical"], s["pipe"]["diameter_in"])

    def fail_cost(self, s, year):
        w = self.cfg["pipe_per_ft"] * s["length_ft"] * infl(self.cfg, year)
        return self.cfg["emergency_multiplier"] * w + self.cof(s) / 100 * self.cfg["c_social_max"]

    # ------------------------------------------------------------------ pricing: the ONLY place dollars are computed
    def price(self, prop, year):
        cfg, s = self.cfg, self.by_id[prop["segment_id"]]
        inf = infl(cfg, year)
        T = cfg["dig_fixed"] * inf
        w_road = cfg["repave_per_ft"] * s["length_ft"] * inf
        r = cfg["discount_rate"]
        d = lambda t: 1 / (1 + r) ** t
        if prop["pipe"]:
            pb = prop["pipe"]
            H = cfg["H_replace"] if prop["work"] == "replace_pipe" else cfg["H_reline"]
            F = self.fail_cost(s, year)
            C = self.C
            pr = lambda a: [min(1.0, C * x / 100) for x in a]
            before, after, lo, hi = pr(pb["pof_before"]), pr(pb["pof_after"]), pr(pb["pof_lo"]), pr(pb["pof_hi"])
            ben = lambda b: sum(d(t) * (b[t] - after[t]) * F for t in range(H))
            B, Blo, Bhi = ben(before), ben(lo), ben(hi)
            street_age = year - s["road"]["last_paved"]
            pen = w_road * max(0.0, cfg["lam"] * (cfg["L"] - street_age)) / cfg["L"]
            W = prop["work_cost"]
            urgency = min(1.0, before[0] / cfg["urgency_full_prob"]) * (
                cfg["critical_facility_multiplier"] if s["critical"] else 1.0)
            alone = T + W + pen
            comb = W
        else:
            rb = prop["road"]
            H = cfg["H_replace"]
            miles = s["length_ft"] / 5280
            vmt = rb["adt"] * 365 * miles
            u = lambda p: cfg["u0"] * ((100 - p) / 100) ** 2
            B = sum(d(t) * vmt * (u(rb["pcr_before"][t]) - u(rb["pcr_after"][t])) for t in range(H))
            Blo, Bhi = B * 0.85, B * 1.15
            W = prop["work_cost"]
            p0 = rb["pcr_before"][0]
            urgency = 1.0 if p0 <= cfg["p_min"] else max(0.0, (cfg["pcr_ok"] - p0) / (cfg["pcr_ok"] - cfg["p_min"]))
            alone = T + W
            comb = W
            pen = 0.0
        urgency = min(1.0, urgency)
        return dict(urgency=urgency, cost_alone=alone, cost_if_combined=comb, dig_cost=T, penalty=pen,
                    benefit_usd=B, benefit_usd_lo=Blo, benefit_usd_hi=Bhi,
                    return_alone=B / alone, return_lo=Blo / alone, return_hi=Bhi / alone)

    # ------------------------------------------------------------------ apply funded decisions
    def apply(self, decisions, year):
        spend = openings = double = 0
        saving = 0.0
        seen_bundles = set()
        per_seg = {}
        for dcs in decisions:
            if not dcs["funded"]:
                continue
            s = self.by_id[dcs["segment_id"]]
            spend += dcs["amount"]
            saving += dcs.get("saving_share", 0.0)
            per_seg.setdefault(dcs["segment_id"], set())
            bid = dcs.get("bundle_id")
            if bid:
                if bid not in seen_bundles:
                    seen_bundles.add(bid)
                    openings += 1
                    per_seg[dcs["segment_id"]].add(bid)
            else:
                openings += 1
                per_seg[dcs["segment_id"]].add(dcs["proposal_id"])
            if dcs["work"] == "replace_pipe":
                s["pipe"].update(install_year=year, breaks=[], material="ductile_iron")
            elif dcs["work"] == "reline_pipe":
                age0 = year - s["pipe"]["install_year"]
                s["pipe"]["install_year"] = int(round(year - (1 - self.cfg["rho"]) * age0))
                s["pipe"]["breaks"] = s["pipe"]["breaks"][: len(s["pipe"]["breaks"]) // 2]
            elif dcs["work"] == "repave":
                s["road"]["last_paved"] = year
        double = sum(max(0, len(v) - 1) for v in per_seg.values())
        return dict(spend=spend, openings=openings, saving=saving, double_digs=double)

    def simulate_failures(self, year):
        out = []
        for s in self.segs:
            p = self.p_fail(s, year)
            if random.Random(f"fail-{self.cfg['seed']}-{year}-{s['segment_id']}").random() < p:
                cost = self.fail_cost(s, year)
                s["pipe"]["breaks"].append(year)
                out.append(dict(segment_id=s["segment_id"], cost=cost, weight=1 + self.cof(s) / 100))
        return out

    def user_cost(self, year):
        """Road user cost $ this year (return_formula.md section 4): VMT * u0 * ((100-PCR)/100)^2."""
        tot = 0.0
        for s in self.segs:
            vmt = s["road"]["adt"] * 365 * s["length_ft"] / 5280
            tot += vmt * self.cfg["u0"] * ((100 - pcr(s["road"], year)) / 100) ** 2
        return tot

    def avg_pcr(self, year):
        return sum(pcr(s["road"], year) for s in self.segs) / len(self.segs)

    def expected_failures(self, year):
        return sum(self.p_fail(s, year) for s in self.segs)


def _poisson(rng, lam):
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= L:
            return k
        k += 1
