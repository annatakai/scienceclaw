"""Tests for the Claude-driven agents with a mocked model client (no network). ALL DATA SIMULATED."""
import json, os, sys, tempfile, unittest
from types import SimpleNamespace as NS
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from agents.board import Board
from agents.budget_agent.agent import BudgetAgent
from agents.budget_agent.tools import BudgetTools
from agents.llm import LLM, LLMUnavailable, ToolError
from agents.pipe_agent.agent import PipeAgent
from agents.pipe_agent.llm_agent import LLMPipeAgent
from agents.pipe_agent.tools import PipeTools
from agents.road_agent.agent import RoadAgent
from agents.road_agent.tools import RoadTools
from sim.city import City
from sim.config import CFG
from sim.runner import simulate

CFG3 = dict(CFG, sim_years=2, max_segments=300)  # a compact 300-segment area keeps the mock-model tests fast
ROAD_KEYS = {"last_paved", "road_class", "pcr", "condition_rating", "wear_index", "street_age", "urgency", "pcr_after", "priority_score"}
PIPE_KEYS = {"material", "install_year", "prior_breaks", "soil", "customers", "critical_facility", "exposure", "risk_class",
             "risk_index", "pof_now", "pof_after", "cof_prime", "diameter_in"}
BUDGET_KEYS = {"spendable", "remaining", "hurdle", "budget"}


def keys(x, acc=None):
    acc = set() if acc is None else acc
    if isinstance(x, dict):
        for k, v in x.items():
            acc.add(k)
            keys(v, acc)
    elif isinstance(x, list):
        for v in x:
            keys(v, acc)
    return acc


def resp(*blocks, i=100, o=50):
    return NS(content=list(blocks), usage=NS(input_tokens=i, output_tokens=o))


def call(name, **inp):
    return NS(type="tool_use", id=f"tu_{name}_{len(json.dumps(inp))}", name=name, input=inp)


def text(t):
    return NS(type="text", text=t)


def last_result(messages):
    m = messages[-1]
    if m["role"] == "user" and isinstance(m["content"], list):
        return json.loads(m["content"][0]["content"])
    return None


class Policy:
    """A deterministic stand-in for Claude: it only uses what the tools return."""
    def create(self, **kw):
        names = {t["name"] for t in kw["tools"]}
        msgs = kw["messages"]
        r = last_result(msgs)
        if "list_candidates" in names:
            if r is None:
                return resp(call("list_candidates"))
            if "candidates" in r:
                best = {}
                for c in r["candidates"]:
                    if c["eligible"] and (c["segment_id"] not in best):
                        best[c["segment_id"]] = c
                items = [dict(id=c["id"], reason=f"Return {c['return_per_dollar']} ({c['return_rating']}).") for c in best.values()]
                return resp(call("fund", items=items))
            return resp(text("done"))
        if "submit_proposals" in names:
            if r is None:
                return resp(call("get_top_risk_pipes" if "get_top_risk_pipes" in names else "get_top_worn_roads", n=4))
            rows = r.get("pipes") or r.get("roads")
            if rows:
                work = "replace_pipe" if "get_top_risk_pipes" in names else "repave"
                return resp(call("submit_proposals", proposals=[dict(segment_id=x["segment_id"], work=work, rationale=f"Top ranked on {x['street']}.") for x in rows]))
            return resp(text("done"))
        # respond / join / accept phases
        if r is None:
            return resp(call("get_board_plans"))
        if "messages" in r:
            msgs_ = r["messages"]
            if "pipe" == [t for t in names if t == "get_pipe_detail"] and False:
                pass
            if "get_pipe_detail" in names:
                asks = [m["segment_id"] for m in msgs_ if m["frm"] == "road" and m["type"] == "join_request"]
                return resp(call("respond_to_join_requests", responses=[dict(segment_id=s, action="accept", rationale="Same dig.") for s in asks] or
                                 [dict(segment_id=m["segment_id"], action="join_request", rationale="Worn main.") for m in msgs_ if m["frm"] == "road" and m["type"] == "post_plan"][:1]))
            spec_ = next(t for t in kw["tools"] if t["name"] == "respond_to_join_requests")
            acts = spec_["input_schema"]["properties"]["responses"]["items"]["properties"]["action"]["enum"]
            if "join_request" in acts:
                return resp(call("respond_to_join_requests", responses=[dict(segment_id=m["segment_id"], action="join_request", rationale="Resurface in one dig.")
                                                                         for m in msgs_ if m["frm"] == "pipe" and m["type"] == "post_plan"][:2]))
            return resp(call("respond_to_join_requests", responses=[dict(segment_id=m["segment_id"], action="accept", rationale="Shared opening.")
                                                                     for m in msgs_ if m["frm"] == "pipe" and m["type"] == "join_request"] or
                             [dict(segment_id="x", action="decline", rationale="n/a")]))
        return resp(text("done"))


class Client:
    def __init__(self, fn):
        self.messages = NS(create=fn)


def setup(seed=3):
    cfg = dict(CFG3, seed=seed)
    city = City(cfg)
    return city.cfg, city


def agents_with_tools(cfg, city, year=2026):
    board = Board()
    pipe, road = PipeAgent(cfg), RoadAgent(cfg)
    pipe.propose(year, city.view_for("pipe"), board, 6)
    road.propose(year, city.view_for("road"), board, 6)
    pipe.post_plans(year, board)
    road.post_plans(year, board)
    return board, pipe, road


class TestLLM(unittest.TestCase):
    def test_end_to_end_with_mock_model(self):
        with tempfile.TemporaryDirectory() as d:
            llm = LLM(CFG3, client=Client(Policy().create))
            r = simulate("coordinated_llm", seed=2, cfg=CFG3, llm=llm, record=True, trace_dir=d)
            self.assertEqual(r["llm"]["fallbacks"], [], r["llm"]["violations"])
            self.assertGreater(r["total_cost"], 0)
            self.assertGreater(r["llm"]["tool_calls"], 0)
            spendable = r["cfg"]["annual_capital_budget"] * (1 - CFG3["reserve_fraction"])
            for fr in r["years"]:
                self.assertLessEqual(sum(x["amount"] for x in fr["decisions"]), spendable + 1)
                for x in fr["decisions"]:
                    self.assertLessEqual(len(x["reason"]), 280 + 60)  # model reason plus nothing else for funded bundles
            with open(os.path.join(d, "coordinated_llm_seed2.jsonl")) as f:
                lines = [json.loads(l) for l in f]
            self.assertTrue({"t", "year", "agent", "kind", "name", "input", "output"} <= set(lines[0]))
            kinds = {l["kind"] for l in lines}
            self.assertTrue({"tool_call", "board"} <= kinds)

    def test_proposal_schema_validation(self):
        cfg, city = setup()
        board = Board()
        pipe = PipeAgent(cfg)
        pipe.propose(2026, city.view_for("pipe"), board, 4)
        t = PipeTools(pipe, 2026, board, 4)
        seg = city.segs[0]["segment_id"]
        bad = [[dict(segment_id="nope", work="replace_pipe", rationale="x")],
               [dict(segment_id=seg, work="repave", rationale="x")],
               [dict(segment_id=seg, work="replace_pipe", rationale="x" * 281)],
               [dict(segment_id=seg, work="replace_pipe", rationale="")],
               [dict(segment_id=seg, work="replace_pipe", rationale="a"), dict(segment_id=seg, work="replace_pipe", rationale="b")],
               [dict(segment_id=seg, work="replace_pipe", rationale="a")] * 1 + [dict(segment_id=s["segment_id"], work="reline_pipe", rationale="a") for s in city.segs[1:6]],
               []]
        for b in bad:
            with self.assertRaises(ToolError):
                t.submit_proposals(b)
            self.assertIsNone(t.submitted)
        t.submit_proposals([dict(segment_id=seg, work="reline_pipe", rationale="ok")])
        self.assertEqual(t.submitted[0]["work"], "reline_pipe")

    def test_join_response_validation(self):
        cfg, city = setup()
        board, pipe, road = agents_with_tools(cfg, city)
        t = PipeTools(pipe, 2026, board, 0)
        with self.assertRaises(ToolError):   # accept with no join request on that segment
            t.respond_to_join_requests([dict(segment_id=city.segs[0]["segment_id"], action="accept", rationale="x")])
        with self.assertRaises(ToolError):
            t.respond_to_join_requests([dict(segment_id="nope", action="join_request", rationale="x")])

    def test_fallback_after_two_failures(self):
        cfg, city = setup()
        prompts = []

        def bad(**kw):
            prompts.append(kw["messages"][0]["content"])
            r = last_result(kw["messages"])
            if r is None:
                return resp(call("submit_proposals", proposals=[dict(segment_id="nope", work="replace_pipe", rationale="x")]))
            return resp(text("I give up"))
        llm = LLM(cfg, client=Client(bad))
        agent = LLMPipeAgent(cfg, llm)
        board = Board()
        got = agent.propose(2026, city.view_for("pipe"), board, 6)
        ref = PipeAgent(cfg).propose(2026, city.view_for("pipe"), Board(), 6)
        self.assertEqual([p["proposal_id"] for p in got], [p["proposal_id"] for p in ref])
        self.assertEqual(len(llm.fallbacks), 1)
        self.assertEqual(len(llm.violations), 2)
        self.assertIn("rejected", prompts[-1])           # second attempt was told why the first failed
        self.assertNotIn("rejected", prompts[0])

    def test_retry_once_then_success(self):
        cfg, city = setup()
        state = {"n": 0}
        ok = Policy().create

        def flaky(**kw):
            if "submit_proposals" in {t["name"] for t in kw["tools"]} and "rejected" not in kw["messages"][0]["content"]:
                return resp(text("no tools used"))
            return ok(**kw)
        llm = LLM(cfg, client=Client(flaky))
        props = LLMPipeAgent(cfg, llm).propose(2026, city.view_for("pipe"), Board(), 6)
        self.assertEqual(llm.fallbacks, [])
        self.assertEqual(len(llm.violations), 1)
        self.assertTrue(all(p["rationale_source"] == "llm" for p in props))

    def test_tool_call_cap(self):
        cfg, city = setup()
        seen = []

        def loop(**kw):
            r = last_result(kw["messages"])
            if r is not None:
                seen.append(r)
            return resp(call("get_top_risk_pipes", n=len(seen) + 1))
        llm = LLM(cfg, client=Client(loop))
        LLMPipeAgent(cfg, llm).propose(2026, city.view_for("pipe"), Board(), 6)
        self.assertEqual(llm.usage["tool_calls"], 2 * cfg["llm_max_tool_calls"])   # 8 per attempt, 2 attempts, then fallback
        self.assertEqual(len(llm.fallbacks), 1)

    def test_decentralisation_of_tools(self):
        cfg, city = setup()
        board, pipe, road = agents_with_tools(cfg, city)
        seg = city.segs[0]["segment_id"]
        pt, rt = PipeTools(pipe, 2026, board, 6), RoadTools(road, 2026, board, 6)
        outs = [pt.get_top_risk_pipes(25), pt.get_pipe_detail(seg)]
        self.assertFalse(keys(outs) & (ROAD_KEYS | BUDGET_KEYS), keys(outs) & (ROAD_KEYS | BUDGET_KEYS))
        outs = [rt.get_top_worn_roads(25), rt.get_road_detail(seg)]
        self.assertFalse(keys(outs) & (PIPE_KEYS | BUDGET_KEYS), keys(outs) & (PIPE_KEYS | BUDGET_KEYS))
        for tools, phases in ((pt, ("propose", "respond")), (rt, ("propose", "join", "accept"))):
            for ph in phases:
                names = {s["name"] for s in tools.specs(ph)}
                self.assertFalse(names & {"fund", "reject", "list_candidates", "get_candidate_detail"})
        self.assertFalse(any(hasattr(pt, a) for a in ("road", "city", "budget")))

    def test_budget_cap_and_visibility(self):
        cfg, city = setup()
        board, pipe, road = agents_with_tools(cfg, city)
        props = pipe.props + road.props
        for p in props:
            p["priced"] = city.price(p, 2026)
        spendable = 150_000.0   # tiny on purpose
        bt = BudgetTools(BudgetAgent(cfg), props, spendable)
        elig = sorted((c for c in bt.cands.values() if c["eligible"]), key=lambda c: -c["ret"])
        self.assertTrue(elig)
        res = bt.fund([dict(id=c["id"], reason="test") for c in bt.cands.values()] + [dict(id="ghost", reason="x")])["results"]
        self.assertFalse(res[-1]["ok"])
        funded = [bt.cands[i] for i in bt.funded]
        self.assertLessEqual(sum(c["cost"] for c in funded), spendable)
        self.assertEqual(len({c["seg"] for c in funded}), len(funded))          # one funded candidate per segment
        self.assertTrue(all(c["eligible"] for c in funded))
        refused = [r for r in res if not r["ok"]]
        self.assertTrue(any("exceeds remaining" in r["error"] for r in refused) or len(bt.funded) == len(elig))
        # a candidate that was never shown cannot be funded
        self.assertFalse(bt.fund([dict(id="pipe-2026-NOPE", reason="x")])["results"][0]["ok"])
        # rationale limit applies to funding too
        self.assertFalse(bt.fund([dict(id=elig[0]["id"], reason="y" * 300)])["results"][0]["ok"])

    def test_backoff_and_cost_counter(self):
        cfg, _ = setup()
        sleeps, n = [], {"n": 0}

        class Overloaded(Exception):
            status_code = 529

        def create(**kw):
            n["n"] += 1
            if n["n"] <= 2:
                raise Overloaded("overloaded")
            return resp(text("hi"), i=1000, o=500)
        llm = LLM(cfg, client=Client(create), sleep=sleeps.append)
        llm.run("pipe", 2026, "s", "u", [], {})
        self.assertEqual(sleeps, [1.0, 2.0])
        self.assertEqual(llm.usage["input_tokens"], 1000)
        pin, pout = cfg["llm_prices"][cfg["llm_model"]]
        self.assertAlmostEqual(llm.usage["usd"], (1000 * pin + 500 * pout) / 1e6)

    def test_dollar_cap_stops_run(self):
        from agents.llm import BudgetExceeded
        cfg, _ = setup()
        llm = LLM(cfg, client=Client(lambda **kw: resp(text("x"), i=10_000_000, o=0)), max_usd=0.5)
        llm.run("pipe", 2026, "s", "u", [], {})
        with self.assertRaises(BudgetExceeded):
            llm.run("pipe", 2026, "s", "u", [], {})

    def test_no_key_is_reported(self):
        old = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            with self.assertRaises(LLMUnavailable):
                LLM(CFG3).client
        finally:
            if old:
                os.environ["ANTHROPIC_API_KEY"] = old


if __name__ == "__main__":
    unittest.main()
