"""Run one strategy end to end. Strategies:
  isolated     separate departments, fixed budget split, no board (no coordination)
  pooled       ablation: one shared budget, but no board (no bundling, no negotiation)
  coordinated  pipe + road + budget agents talk on the board, pooled budget
  central      one planner sees every asset (heuristic benchmark; NOT yet a proven upper bound)
"""
from agents.board import Board
from agents.budget_agent.agent import BudgetAgent
from agents.pipe_agent.agent import PipeAgent
from agents.road_agent.agent import RoadAgent
from agents.road_agent.scoring import pcr
from sim.city import City
from sim.config import CFG

STRATEGIES = ["isolated", "pooled", "coordinated", "central"]


def _counts_text(counts, order):
    return ", ".join(f"{counts.get(k, 0)} {k}" for k in order)


def simulate(strategy, seed=42, record=False, cfg=None):
    cfg = dict(cfg or CFG, seed=seed)
    city = City(cfg)
    board = Board()
    pipe, road, budget = PipeAgent(cfg), RoadAgent(cfg), BudgetAgent(cfg)
    cum = dict(exp_fail=0.0, fail=0, weighted_fail=0.0, openings=0, spend=0.0, emerg=0.0, dig_savings=0.0,
               double_digs=0, user_cost=0.0)
    years = []
    for year in range(cfg["start_year"], cfg["start_year"] + cfg["horizon_years"]):
        fr = {"year": year}
        if record:
            fr["risk_before"] = [round(city.pipe_rating(s, year)["risk_index"]) for s in city.segs]
            fr["class_before"] = [city.pipe_rating(s, year)["risk_class"] for s in city.segs]
            fr["pcr_before"] = [round(pcr(s["road"], year)) for s in city.segs]
        max_n = 10_000 if strategy == "central" else cfg["max_proposals"]
        pipe.propose(year, city.view_for("pipe"), board, max_n)
        road.propose(year, city.view_for("road"), board, max_n)
        pc = {}
        for r in pipe.ratings.values():
            pc[r["risk_class"]] = pc.get(r["risk_class"], 0) + 1
        rc = {}
        for r in road.ratings.values():
            rc[r["condition_rating"]] = rc.get(r["condition_rating"], 0) + 1
        board.add(year, 1, "pipe", "rating", None,
                  f"Rated my {len(city.segs)} pipes with the team rubric: " + _counts_text(pc, ["Critical", "High", "Moderate", "Low"]) + ".")
        board.add(year, 1, "road", "rating", None,
                  f"Rated my {len(city.segs)} roads by pavement condition: " + _counts_text(rc, ["Failed", "Poor", "Fair", "Good"]) + ".")
        if strategy == "central":
            for seg in {p["segment_id"] for p in pipe.props} & {p["segment_id"] for p in road.props}:
                pipe._tag(year, seg)
                road._tag(year, seg)
            board.add(year, 1, "budget", "post_plan", None,
                      "Central planner: solving all segments jointly with full data (heuristic benchmark).")
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
                          f"({d['funding_source'].replace('_', ' ')}). Rated {d['return_rating']} return "
                          f"{d['return_per_dollar']:.2f}, tier {d['urgency_tier']} ({d['urgency_name']}). {d['reason']}")
        res = city.apply(decisions, year)
        exp = city.expected_failures(year)
        fails = city.simulate_failures(year)
        cum["exp_fail"] += exp
        cum["fail"] += len(fails)
        cum["weighted_fail"] += sum(f["weight"] for f in fails)
        cum["openings"] += res["openings"] + len(fails)
        cum["spend"] += res["spend"]
        cum["emerg"] += sum(f["cost"] for f in fails)
        cum["dig_savings"] += res["saving"]
        cum["double_digs"] += res["double_digs"]
        cum["user_cost"] += city.user_cost(year)
        if record:
            idx = {s["segment_id"]: i for i, s in enumerate(city.segs)}
            fr["messages"] = [dict(round=m["round"], frm=m["from"], type=m["type"], seg=idx.get(m["segment_id"]),
                                   text=m["text"]) for m in board.messages if m["year"] == year]
            fr["decisions"] = [dict(seg=idx[d["segment_id"]], agent=d["agent"], work=d["work"], funded=True,
                                    bundle=bool(d["bundle_id"]), amount=round(d["amount"]),
                                    ret=round(d["return_per_dollar"], 2), reason=d["reason"])
                               for d in decisions if d["funded"]]
            fr["n_proposals"] = len(props)
            fr["n_rejected"] = sum(1 for d in decisions if not d["funded"])
            fr["failures"] = [dict(seg=idx[f["segment_id"]], cost=round(f["cost"])) for f in fails]
            fr["risk_after"] = [round(city.pipe_rating(s, year)["risk_index"]) for s in city.segs]
            fr["class_after"] = [city.pipe_rating(s, year)["risk_class"] for s in city.segs]
            fr["pcr_after"] = [round(pcr(s["road"], year)) for s in city.segs]
            fr["metrics"] = {k: (round(v, 2) if isinstance(v, float) else v) for k, v in cum.items()}
            years.append(fr)
    out = dict(strategy=strategy, seed=seed, **{k: (round(v, 2) if isinstance(v, float) else v) for k, v in cum.items()})
    out["total_cost"] = round(cum["spend"] + cum["emerg"] + cum["user_cost"])
    out["avg_pcr_end"] = round(city.avg_pcr(cfg["start_year"] + cfg["horizon_years"] - 1), 1)
    if record:
        out["years"] = years
        fresh = City(cfg)
        out["segs"] = [dict(id=s["segment_id"], street=s["street"], coords=s["coords"], length_ft=round(s["length_ft"]),
                            critical=s["critical"], road_class=s["road"]["road_class"], customers=s["customers"]) for s in fresh.segs]
    return out


if __name__ == "__main__":
    for st in STRATEGIES:
        r = simulate(st)
        print({k: r[k] for k in ("strategy", "exp_fail", "fail", "openings", "spend", "emerg", "dig_savings",
                                 "user_cost", "avg_pcr_end", "total_cost")})
