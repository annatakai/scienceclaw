"""Run one strategy end to end. Strategies:
  isolated     separate departments, fixed budget split, no board (no coordination)
  pooled       ablation: one shared budget, but no board (no bundling, no negotiation)
  coordinated  pipe + road + budget agents talk on the board, pooled budget
  central      one planner sees every asset (ideal benchmark, upper bound)
"""
from sim import CFG, City
from agents import Board, PipeAgent, RoadAgent, BudgetAgent, bundle_id

STRATEGIES = ["isolated", "pooled", "coordinated", "central"]


def simulate(strategy, seed=42, record=False, cfg=None):
    cfg = dict(cfg or CFG, seed=seed)
    city = City(cfg)
    board = Board()
    pipe, road, budget = PipeAgent(cfg), RoadAgent(cfg), BudgetAgent(cfg)
    cum = dict(exp_fail=0.0, fail=0, weighted_fail=0.0, openings=0, spend=0.0, emerg=0.0, dig_savings=0.0, double_digs=0, user_cost=0.0)
    years = []
    for year in range(cfg["start_year"], cfg["start_year"] + cfg["horizon_years"]):
        fr = {"year": year}
        if record:
            fr["risk_before"] = [round(_risk(city, s, year)) for s in city.segs]
            fr["pcr_before"] = [round(_pcr(s, year)) for s in city.segs]
        max_n = 10_000 if strategy == "central" else cfg["max_proposals"]
        pipe.propose(year, city.view_for("pipe"), board, max_n)
        road.propose(year, city.view_for("road"), board, max_n)
        n0 = len(board.messages)
        if strategy == "central":
            for seg in {p["segment_id"] for p in pipe.props} & {p["segment_id"] for p in road.props}:
                pipe._tag(year, seg)
                road._tag(year, seg)
            board.add(year, 1, "budget", "post_plan", None,
                      "Central planner: solving all segments jointly with full data (ideal benchmark).")
        elif strategy == "coordinated":
            pipe.post_plans(year, board)
            road.post_plans(year, board)
            board.add(year, 1, "board", "hurdle", None, f"Going return threshold this year: {cfg['min_return']:.2f}.")
            road.join(year, board)
            pipe.respond(year, board)
            road.accept(year, board)
        props = pipe.props + road.props
        for p in props:
            p["priced"] = city.price(p, year)
        decisions = budget.allocate(props, year, "isolated" if strategy == "isolated" else "pooled")
        for d in decisions:
            if d["funded"]:
                board.add(year, 2, "budget", "funding_decision", d["segment_id"],
                          f"Fund {d['work'].replace('_', ' ')} on {d['segment_id']} for ${d['amount']:,.0f} "
                          f"({d['funding_source'].replace('_', ' ')}). {d['reason']}")
        res = city.apply(decisions, year)
        exp = city.expected_failures(year)
        fails = city.simulate_failures(year)
        emerg = sum(f["cost"] for f in fails)
        cum["exp_fail"] += exp
        cum["fail"] += len(fails)
        cum["weighted_fail"] += sum(f["weight"] for f in fails)
        cum["openings"] += res["openings"] + len(fails)
        cum["spend"] += res["spend"]
        cum["emerg"] += emerg
        cum["dig_savings"] += res["saving"]
        cum["double_digs"] += res["double_digs"]
        cum["user_cost"] += city.user_cost(year)
        if record:
            idx = {s["segment_id"]: i for i, s in enumerate(city.segs)}
            fr["messages"] = [dict(round=m["round"], frm=m["from"], type=m["type"], seg=idx.get(m["segment_id"]),
                                   text=m["text"]) for m in board.messages if m["year"] == year]
            fr["decisions"] = [dict(seg=idx[d["segment_id"]], agent=d["agent"], work=d["work"], funded=d["funded"],
                                    bundle=bool(d["bundle_id"]), amount=round(d["amount"]),
                                    ret=round(d["return_per_dollar"], 2), reason=d["reason"])
                               for d in decisions if d["funded"]]
            fr["n_proposals"] = len(props)
            fr["n_rejected"] = sum(1 for d in decisions if not d["funded"])
            fr["failures"] = [dict(seg=idx[f["segment_id"]], cost=round(f["cost"])) for f in fails]
            fr["risk_after"] = [round(_risk(city, s, year)) for s in city.segs]
            fr["pcr_after"] = [round(_pcr(s, year)) for s in city.segs]
            fr["metrics"] = {k: (round(v, 2) if isinstance(v, float) else v) for k, v in cum.items()}
            years.append(fr)
    out = dict(strategy=strategy, seed=seed, **{k: (round(v, 2) if isinstance(v, float) else v) for k, v in cum.items()})
    out["total_cost"] = round(cum["spend"] + cum["emerg"] + cum["user_cost"])
    out["avg_pcr_end"] = round(city.avg_pcr(cfg["start_year"] + cfg["horizon_years"] - 1), 1)
    if record:
        out["years"] = years
        out["segs"] = [dict(id=s["segment_id"], street=s["street"], coords=s["coords"], length_ft=round(s["length_ft"]),
                            critical=s["critical"], customers=s["customers"]) for s in _fresh(cfg).segs]
    return out


def _fresh(cfg):
    return City(cfg)


def _risk(city, s, year):
    from sim import pof_index
    pof = pof_index(s["pipe"], s["length_ft"], year, cfg=city.cfg)
    return pof * (0.4 + 0.6 * city.cof(s) / 100)


def _pcr(s, year):
    from sim import pcr
    return pcr(s["road"], year)


if __name__ == "__main__":
    for st in STRATEGIES:
        r = simulate(st)
        print({k: r[k] for k in ("strategy", "exp_fail", "fail", "openings", "spend", "emerg", "dig_savings", "user_cost", "avg_pcr_end", "total_cost")})
