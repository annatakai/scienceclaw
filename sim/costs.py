"""The ONLY place dollars are computed (work cost, benefit, gross cost, urgency, return, NPV, financing).
Implements docs/return_formula.md. Pipe and road agents report indices and call work_cost() for their own work;
the budget agent calls bundle(), share_amount() and net_cost() instead of doing arithmetic itself. ALL DATA IS SIMULATED."""
from agents.road_agent.scoring import urgency_from_pcr
from sim.config import infl

WAIT = "wait"
PIPE_WORKS = ("replace_pipe", "reline_pipe")
ROAD_WORKS = ("repave", "preserve_road", "reconstruct_road")


def d(cfg, t):
    return 1 / (1 + cfg["discount_rate"]) ** t


# ---------------------------------------------------------------- work cost (what an agent reports)
def work_cost(cfg, work, length_ft, year=None):
    """Cost of the work itself: no trench, no penalty (return_formula.md section 5)."""
    f = infl(cfg, year) if year is not None else 1.0
    if work == "replace_pipe":
        return cfg["pipe_per_ft"] * length_ft * f
    if work == "reline_pipe":
        return cfg["pipe_per_ft"] * length_ft * f * cfg["reline_frac"]
    if work == "repave":
        return cfg["repave_per_ft"] * length_ft * f
    if work == "preserve_road":
        return cfg["repave_per_ft"] * length_ft * f * cfg["preserve_frac"]
    if work == "reconstruct_road":
        return cfg["repave_per_ft"] * length_ft * f * cfg["reconstruct_mult"]
    raise ValueError(work)


def emergency_cost(cfg, length_ft):
    """Emergency repair cost of a failure on a main of this length (planned replacement x multiplier); also the
    figure passed to the team's pipe rubric."""
    return cfg["emergency_multiplier"] * cfg["pipe_per_ft"] * length_ft


def fail_cost(city, s, year):
    """F_i = emergency_multiplier * W_pipe + CoF'/100 * C_social_max (return_formula.md 2.2)."""
    cfg = city.cfg
    return emergency_cost(cfg, s["length_ft"]) * infl(cfg, year) + city.cof(s) / 100 * cfg["c_social_max"]


# ---------------------------------------------------------------- pure formulas (section 5 and 6)
def dig_penalty(w_road, street_age, lam, L):
    """Penalty = W_road * lost_years / L, lost_years = max(0, lam * (L - street_age))."""
    return w_road * max(0.0, lam * (L - max(0, street_age))) / L


def gross_costs(T, w_pipe, w_road, penalty):
    return dict(pipe_alone=T + w_pipe + penalty, road_alone=T + w_road, bundle=T + w_pipe + w_road)


def marginal_return(benefit, work):
    return benefit / work if work > 0 else float("inf")


def review_flag(ret_lo, ret_hi, hurdle):
    """Needs engineering review when return_lo < hurdle <= return_hi (section 6.4)."""
    return ret_lo is not None and ret_lo < hurdle <= ret_hi


def annual_payment(principal, rate, years):
    return principal / years if rate == 0 else principal * rate / (1 - (1 + rate) ** -years)


def financing_factor(cfg, source):
    """f_source: present value (at the discount rate) of repayments per dollar borrowed. Cash sources are 1.0."""
    t = cfg["loan_terms"].get(source)
    if source == "rate_revenue" or not t:
        return 1.0
    r = cfg["discount_rate"]
    pay = annual_payment(1.0, t["rate"], t["years"])
    return pay * (1 - (1 + r) ** -t["years"]) / r


def net_cost(cfg, amount, source):
    return amount * financing_factor(cfg, source)


def loan_interest(cfg, amount, source):
    """Nominal interest over the life of the loan: total repayments minus principal."""
    t = cfg["loan_terms"].get(source)
    if source == "rate_revenue" or not t:
        return 0.0
    return annual_payment(amount, t["rate"], t["years"]) * t["years"] - amount


def source_order(cfg):
    """Cheapest first: lowest present value of repayments per dollar; rate revenue before bonds on a tie (cash, no debt)."""
    return sorted(cfg["funding_mix"], key=lambda s: (round(financing_factor(cfg, s), 6), s != "rate_revenue"))


def share_amount(priced, n_members):
    """What one member of a decision is paid: stand-alone = cost_alone; in a bundle = its own work + an equal share of the dig."""
    if n_members == 1:
        return priced["cost_alone"]
    return priced["cost_if_combined"] + priced["dig_cost"] / n_members


def bundle(a, b, cfg):
    """Two priced proposals sharing one dig on the same segment: cost = T once + both works; benefit adds; marginal check
    on each add-on is B / W (return_formula.md 6.2)."""
    cost = a["dig_cost"] + a["cost_if_combined"] + b["cost_if_combined"]
    B, lo, hi = (a["benefit_usd"] + b["benefit_usd"], a["benefit_usd_lo"] + b["benefit_usd_lo"],
                 a["benefit_usd_hi"] + b["benefit_usd_hi"])
    h = cfg["min_return"]
    return dict(cost=cost, B=B, B_lo=lo, B_hi=hi, saving=a["cost_alone"] + b["cost_alone"] - cost,
                marginal=(marginal_return(a["benefit_usd"], a["cost_if_combined"]),
                          marginal_return(b["benefit_usd"], b["cost_if_combined"])),
                marginal_ok=all(marginal_return(x["benefit_usd"], x["cost_if_combined"]) >= h for x in (a, b)),
                ret_lo=lo / cost, ret_hi=hi / cost)


# ---------------------------------------------------------------- pricing a proposal
def _pipe_benefit(cfg, F, before, after, H, shift=0):
    """sum d(t) * (EL_before(t) - EL_after(t)) over the job's life. shift=1 prices the same job done a year later:
    the pipe keeps aging one more year and the first year of benefit is lost (section 3, defer)."""
    return sum(d(cfg, t) * (before[t] - after[t - shift]) * F for t in range(shift, H))


def price(city, prop, year):
    """The `priced` block (interfaces.md section 5). For work == "wait" it prices doing the deferred job one year later:
    benefit_usd is its benefit, cost_alone is its gross cost, both in today's dollars (section 3, defer)."""
    cfg, s = city.cfg, city.by_id[prop["segment_id"]]
    inf = infl(cfg, year)
    g = 1 + cfg["cost_inflation"]
    T = cfg["dig_fixed"] * inf
    wait = prop["work"] == WAIT
    job = prop["defer"]["work"] if wait else prop["work"]
    W = prop["defer"]["work_cost"] if wait else prop["work_cost"]
    sh = 1 if wait else 0
    street_age = year - s["road"]["last_paved"]
    if prop["pipe"]:
        pb = prop["pipe"]
        H = min(cfg["H_replace"] if job == "replace_pipe" else cfg["H_reline"], len(pb["pof_before"]))
        F = fail_cost(city, s, year)
        pr = lambda a: [min(1.0, city.C * x / 100) for x in a]
        before, after, lo, hi = pr(pb["pof_before"]), pr(pb["pof_after"]), pr(pb["pof_lo"]), pr(pb["pof_hi"])
        B, Blo, Bhi = (_pipe_benefit(cfg, F, b, after, H, sh) for b in (before, lo, hi))
        w_road = work_cost(cfg, "repave", s["length_ft"], year)
        pen = dig_penalty(w_road, street_age, cfg["lam"], cfg["L"])
        urgency = min(1.0, before[0] / cfg["urgency_full_prob"]) * (cfg["critical_facility_multiplier"] if s["critical"] else 1.0)
        alone, comb = gross_costs(T, W, 0.0, pen)["pipe_alone"], W
    else:
        rb = prop["road"]
        H = min({"repave": cfg["H_replace"], "preserve_road": cfg["H_preserve"],
                 "reconstruct_road": cfg["H_replace"]}[job], len(rb["pcr_before"]))
        vmt = rb["adt"] * 365 * s["length_ft"] / 5280
        u = lambda p: cfg["u0"] * ((100 - p) / 100) ** 2
        B = sum(d(cfg, t) * vmt * (u(rb["pcr_before"][t]) - u(rb["pcr_after"][t - sh])) for t in range(sh, H))
        band = cfg["road_benefit_band"]
        Blo, Bhi = B * (1 - band), B * (1 + band)
        urgency = urgency_from_pcr(rb["pcr_before"][0])
        pen, alone, comb = 0.0, gross_costs(T, 0.0, W, 0.0)["road_alone"], W
    if wait:   # costs rise by (1+g) and are paid a year from now
        alone, comb, T, pen = (x * g * d(cfg, 1) for x in (alone, comb, T, pen))   # benefits are already discounted to today
    return dict(urgency=min(1.0, urgency), cost_alone=alone, cost_if_combined=comb, dig_cost=T, penalty=pen,
                benefit_usd=B, benefit_usd_lo=Blo, benefit_usd_hi=Bhi,
                return_alone=B / alone, return_lo=Blo / alone, return_hi=Bhi / alone,
                needs_review=review_flag(Blo / alone, Bhi / alone, cfg["min_return"]) and not wait)
