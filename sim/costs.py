"""The ONLY place dollars are computed (benefit, cost, urgency, return). Follows return_formula.md in simplified form.
Pipe and road agents report indices and their own work cost; this module converts them to dollars."""
from agents.pipe_agent import adapter
from agents.road_agent.scoring import urgency_from_pcr
from sim.config import infl


def fail_cost(city, s, year):
    """Dollar cost of one pipe failure: emergency repair plus social cost scaled by consequence."""
    cfg = city.cfg
    w = cfg["pipe_per_ft"] * s["length_ft"] * infl(cfg, year)
    return cfg["emergency_multiplier"] * w + city.cof(s) / 100 * cfg["c_social_max"]


def price(city, prop, year):
    cfg, s = city.cfg, city.by_id[prop["segment_id"]]
    inf = infl(cfg, year)
    T = cfg["dig_fixed"] * inf
    w_road = cfg["repave_per_ft"] * s["length_ft"] * inf
    d = lambda t: 1 / (1 + cfg["discount_rate"]) ** t
    if prop["pipe"]:
        pb = prop["pipe"]
        H = cfg["H_replace"] if prop["work"] == "replace_pipe" else cfg["H_reline"]
        F = fail_cost(city, s, year)
        pr = lambda a: [min(1.0, city.C * x / 100) for x in a]
        before, after, lo, hi = pr(pb["pof_before"]), pr(pb["pof_after"]), pr(pb["pof_lo"]), pr(pb["pof_hi"])
        ben = lambda b: sum(d(t) * (b[t] - after[t]) * F for t in range(H))
        B, Blo, Bhi = ben(before), ben(lo), ben(hi)
        street_age = year - s["road"]["last_paved"]
        pen = w_road * max(0.0, cfg["lam"] * (cfg["L"] - street_age)) / cfg["L"]
        W = prop["work_cost"]
        urgency = min(1.0, before[0] / cfg["urgency_full_prob"]) * (
            cfg["critical_facility_multiplier"] if s["critical"] else 1.0)
        alone, comb = T + W + pen, W
    else:
        rb = prop["road"]
        H = cfg["H_replace"]
        vmt = rb["adt"] * 365 * s["length_ft"] / 5280
        u = lambda p: cfg["u0"] * ((100 - p) / 100) ** 2
        B = sum(d(t) * vmt * (u(rb["pcr_before"][t]) - u(rb["pcr_after"][t])) for t in range(H))
        Blo, Bhi = B * 0.85, B * 1.15
        W = prop["work_cost"]
        urgency = urgency_from_pcr(rb["pcr_before"][0])
        alone, comb, pen = T + W, W, 0.0
    return dict(urgency=min(1.0, urgency), cost_alone=alone, cost_if_combined=comb, dig_cost=T, penalty=pen,
                benefit_usd=B, benefit_usd_lo=Blo, benefit_usd_hi=Bhi,
                return_alone=B / alone, return_lo=Blo / alone, return_hi=Bhi / alone)
