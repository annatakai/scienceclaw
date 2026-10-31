"""Run one strategy end to end. Strategies:
  isolated     separate departments, fixed budget split, no board (no coordination)
  pooled       ablation: one shared budget, but no board (no bundling, no negotiation)
  coordinated  pipe + road + budget agents talk on the board, pooled budget
  central      one planner sees every asset (heuristic benchmark; NOT yet a proven upper bound)
  coordinated_llm  coordinated, but the three agents choose and explain with Claude; numbers still come from the tools
"""
from agents.board import Board
from agents.budget_agent.agent import BudgetAgent
from agents.pipe_agent.agent import PipeAgent
from agents.road_agent.agent import RoadAgent
from agents.road_agent.scoring import pcr
from sim.city import City
from sim import reserve
from sim.config import CFG

STRATEGIES = ["isolated", "pooled", "coordinated", "central"]
LLM_STRATEGIES = ["coordinated_llm"]  # same flow as coordinated, agents driven by Claude (agents/llm.py); needs an API key


def _counts_text(counts, order):
    return ", ".join(f"{counts.get(k, 0)} {k}" for k in order)


CLASS_CODE = {"Low": 0, "Moderate": 1, "High": 2, "Critical": 3}
COND_CODE = {"Good": 0, "Fair": 1, "Poor": 2, "Failed": 3}
MATERIALS = ["cast_iron", "ductile_iron", "pvc", "steel", "protected_ductile_iron"]


def snapshot(city, year):
    """Recording only (demo): the per-segment state a map needs. Reads the city; changes nothing."""
    from agents.road_agent.scoring import rate_condition
    rt = [city.pipe_rating(s, year) for s in city.segs]
    p = [pcr(s["road"], year) for s in city.segs]
    return dict(risk=[round(r["risk_index"]) for r in rt], cls=[CLASS_CODE[r["risk_class"]] for r in rt],
                pcr=[round(x) for x in p], cond=[COND_CODE[rate_condition(x)[0]] for x in p],
                inst=[s["pipe"]["install_year"] for s in city.segs],
                mat=[MATERIALS.index(s["pipe"]["material"]) for s in city.segs],
                brk=[len(s["pipe"]["breaks"]) for s in city.segs], paved=[s["road"]["last_paved"] for s in city.segs])


def simulate(strategy, seed=42, record=False, cfg=None, llm=None, trace_dir=None, cip=False, cip_dir=None):
    """llm: an agents.llm.LLM (for coordinated_llm; built from the environment if omitted).
    cip: also return out["cip"] = all priced proposals, all decisions (year, funding_source, bundle_id), a city dict,
    the reserve balance by year and the config used (input of cip/adapter.py). cip_dir: also write it to
    <cip_dir>/run_<strategy>_seed<seed>.json (implies cip)."""
    cip = cip or bool(cip_dir)
    cfg = reserve.ensure(dict(cfg or CFG, seed=seed))   # reserve share from the pilot (cached); fixed fraction if reserve_mode == "fixed"
    city = City(cfg)
    cfg = city.cfg  # with the network-size totals (budget, break target, menu size) filled in
    board = Board()
    use_llm = strategy in LLM_STRATEGIES
    if use_llm:
        from agents.budget_agent.llm_agent import LLMBudgetAgent
        from agents.llm import LLM
        from agents.pipe_agent.llm_agent import LLMPipeAgent
        from agents.road_agent.llm_agent import LLMRoadAgent
        from agents.trace import Tracer
        tracer = Tracer(strategy, seed, trace_dir)
        board.tracer = tracer
        llm = llm or LLM(cfg)
        llm.tracer = tracer
        pipe, road, budget = LLMPipeAgent(cfg, llm), LLMRoadAgent(cfg, llm), LLMBudgetAgent(cfg, llm)
    else:
        pipe, road, budget = PipeAgent(cfg), RoadAgent(cfg), BudgetAgent(cfg)
    cum = dict(exp_fail=0.0, fail=0, weighted_fail=0.0, openings=0, spend=0.0, emerg=0.0, dig_savings=0.0,
               double_digs=0, user_cost=0.0, interest=0.0, net_spend=0.0, shortfall=0.0, proposals=0, funded=0)
    years, cip_props, cip_decs, reserve_rows = [], [], [], []
    balance = 0.0
    state0 = snapshot(city, cfg["start_year"]) if record else None
    n_years = cfg.get("sim_years") or cfg["horizon_years"]  # sim_years < horizon_years: short run, same pricing
    for year in range(cfg["start_year"], cfg["start_year"] + n_years):
        fr = {"year": year}
        if use_llm:
            tracer.year = year
        if record:
            fr["risk_before"] = [round(city.pipe_rating(s, year)["risk_index"]) for s in city.segs]
            fr["class_before"] = [city.pipe_rating(s, year)["risk_class"] for s in city.segs]
            fr["pcr_before"] = [round(pcr(s["road"], year)) for s in city.segs]
        max_n = cfg["max_proposals_central"] if strategy == "central" else cfg["max_proposals"]
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
        elif strategy in ("coordinated", "coordinated_llm"):
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
        if cip:
            cip_props += [dict(p, length_ft=(p["pipe"] or p["road"])["length_ft"], pipe=None, road=None) for p in props]
            cip_decs += decisions
        cum["proposals"] += len(props)
        cum["funded"] += sum(1 for d in decisions if d["funded"])
        res = city.apply(decisions, year)
        exp = city.expected_failures(year)
        fails = city.simulate_failures(year)
        cum["exp_fail"] += exp
        cum["fail"] += len(fails)
        cum["weighted_fail"] += sum(f["weight"] for f in fails)
        cum["openings"] += res["openings"] + len(fails)
        cum["spend"] += res["spend"]
        emerg_year = sum(f["cost"] for f in fails)
        cum["emerg"] += emerg_year
        cum["interest"] += sum(d["loan_interest"] for d in decisions)
        cum["net_spend"] += sum(d["net_cost"] for d in decisions)
        # reserve: the set-aside covers emergency repairs; any excess is a shortfall (paid from the operating budget)
        setaside = cfg["annual_capital_budget"] * reserve.share(cfg)
        opening = balance
        balance = max(0.0, balance + setaside - emerg_year)
        short = max(0.0, emerg_year - (opening + setaside))
        cum["shortfall"] += short
        reserve_rows.append(dict(year=year, opening=round(opening), set_aside=round(setaside), emergency=round(emerg_year),
                                 shortfall=round(short), closing=round(balance)))
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
            fr["emerg_year"] = emerg_year
            fr["n_proposals"] = len(props)
            fr["n_rejected"] = sum(1 for d in decisions if not d["funded"])
            fr["failures"] = [dict(seg=idx[f["segment_id"]], cost=round(f["cost"])) for f in fails]
            fr["risk_after"] = [round(city.pipe_rating(s, year)["risk_index"]) for s in city.segs]
            fr["class_after"] = [city.pipe_rating(s, year)["risk_class"] for s in city.segs]
            fr["pcr_after"] = [round(pcr(s["road"], year)) for s in city.segs]
            fr["rejected"] = [dict(seg=idx[d["segment_id"]], agent=d["agent"], work=d["work"], reason=d["reason"])
                              for d in decisions if not d["funded"]]
            fr["state"] = snapshot(city, year)
            fr["metrics"] = {k: (round(v, 2) if isinstance(v, float) else v) for k, v in cum.items()}
            years.append(fr)
    out = dict(strategy=strategy, seed=seed, **{k: (round(v, 2) if isinstance(v, float) else v) for k, v in cum.items()})
    out["total_cost"] = round(cum["spend"] + cum["emerg"] + cum["user_cost"])
    out["cost_of_ownership"] = round(out["total_cost"] + cum["interest"])   # total cost plus nominal loan interest
    out["reserve"] = reserve_rows
    out["avg_pcr_end"] = round(city.avg_pcr(cfg["start_year"] + n_years - 1), 1)
    if use_llm:
        out["llm"] = dict(llm.usage, fallbacks=list(llm.fallbacks), violations=list(llm.violations))
    if cip:
        out["cip"] = dict(proposals=cip_props, decisions=cip_decs, reserve=reserve_rows, miles=round(city.total_miles, 1),
                          city={s_["segment_id"]: dict(street=s_["street"], neighborhood=s_["neighborhood"]) for s_ in city.segs},
                          reserve_sizing=cfg.get("reserve_sizing"),
                          config={k: v for k, v in cfg.items() if not k.startswith("llm")})
        if cip_dir:
            import json
            import pathlib
            path = pathlib.Path(cip_dir)
            path.mkdir(parents=True, exist_ok=True)
            summary = {k: v for k, v in out.items() if k != "cip"}
            (path / f"run_{strategy}_seed{seed}.json").write_text(json.dumps(dict(summary=summary, **out["cip"]), default=str))
    if record:
        out["years"] = years
        out["state0"] = state0
        out["segs"] = [dict(id=s["segment_id"], street=s["street"], coords=s["coords"], length_ft=round(s["length_ft"]),
                            critical=s["critical"], road_class=s["road"]["road_class"], customers=s["customers"],
                            neighborhood=s["neighborhood"], adt=s["road"]["adt"]) for s in city.segs]
        out["cfg"] = {k: cfg[k] for k in ("annual_capital_budget", "n_target", "max_proposals", "start_year", "horizon_years", "reserve_mode", "reserve_fraction")}
        out["cfg"]["reserve_share"] = reserve.share(cfg)
        out["miles"] = round(city.total_miles, 1)
    return out


if __name__ == "__main__":
    for st in STRATEGIES:
        r = simulate(st)
        print({k: r[k] for k in ("strategy", "exp_fail", "fail", "openings", "spend", "emerg", "dig_savings",
                                 "user_cost", "avg_pcr_end", "total_cost")})
