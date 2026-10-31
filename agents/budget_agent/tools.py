"""Tools for the Claude-driven budget agent. It sees the proposals it was shown (with their priced blocks from
sim/costs.py) and its own spendable amount. It cannot fund anything it was not shown or exceed the spendable amount:
the tool refuses. Pipe and road agents never get these tools."""
from agents.budget_agent.scoring import score_candidate
from agents.llm import ToolError
from agents.llm_support import RATIONALE, check_rationale, spec

ITEMS = {"type": "array", "items": {"type": "object", "required": ["id", "reason"],
                                    "properties": {"id": {"type": "string", "description": "candidate id from list_candidates"},
                                                   "reason": RATIONALE}}}


class BudgetTools:
    def __init__(self, agent, props, spendable):
        self.a, self.cfg, self.spendable = agent, agent.cfg, spendable
        self.cands = {}
        for c in (c for c in agent._cands(props, True) if not c.get("wait")):
            c["id"] = c["members"][0]["proposal_id"] if not c["bundle"] else f"{c['bundle']}:{c['members'][0]['proposal_id']}"
            c["eligible"] = agent._passes(c)
            self.cands[c["id"]] = c
        self.funded, self.rejected = {}, {}   # id -> reason
        self.remaining, self.urgent_spent = spendable, 0.0
        self.errors = 0

    def _urgent(self, c):
        return c["urg"] >= self.cfg["urgent_override"]

    def _row(self, c):
        sc = score_candidate(c["ret"], c["urg"], self.cfg["min_return"])
        return dict(id=c["id"], segment_id=c["seg"], works=[m["work"] for m in c["members"]], is_bundle=bool(c["bundle"]),
                    cost=round(c["cost"]), benefit=round(c["B"]), return_per_dollar=round(c["ret"], 2),
                    return_rating=sc["return_rating"], urgency_tier=sc["urgency_tier"], urgency_name=sc["urgency_name"],
                    dig_saving=round(c["saving"]), eligible=c["eligible"])

    def list_candidates(self):
        rows = sorted(self.cands.values(), key=lambda c: -c["ret"])
        return dict(spendable=round(self.spendable), remaining=round(self.remaining), hurdle=self.cfg["min_return"],
                    n_candidates=len(rows), note="Only one candidate per segment can be funded; only eligible ones.",
                    candidates=[self._row(c) for c in rows[:40]])

    def get_candidate_detail(self, id):
        if id not in self.cands:
            raise ToolError(f"unknown candidate {id}")
        c = self.cands[id]
        return dict(self._row(c), net_value=round(c["npv"]),
                    same_segment=[k for k, o in self.cands.items() if o["seg"] == c["seg"] and k != id],
                    members=[dict(proposal_id=m["proposal_id"], agent=m["agent"], work=m["work"], proposer_rationale=m["rationale"],
                                  cost_alone=round(m["priced"]["cost_alone"]), cost_if_combined=round(m["priced"]["cost_if_combined"]),
                                  repaving_penalty=round(m["priced"]["penalty"]),
                                  benefit_low=round(m["priced"]["benefit_usd_lo"]), benefit_high=round(m["priced"]["benefit_usd_hi"]))
                             for m in c["members"]],
                    funded=id in self.funded, rejected=id in self.rejected)

    def _items(self, items):
        if not isinstance(items, list) or not items:
            raise ToolError("items must be a non-empty list")
        return items

    def fund(self, items):
        """Fund candidates in order. Each item is checked on its own; refusals do not stop the others."""
        out = []
        for it in self._items(items):
            try:
                cid, why = it.get("id"), check_rationale(it.get("reason"), self.cfg)
                c = self.cands.get(cid)
                if c is None:
                    raise ToolError(f"unknown candidate {cid}")
                if cid in self.funded:
                    raise ToolError("already funded")
                if not c["eligible"]:
                    raise ToolError(f"not eligible: return {c['ret']:.2f} is below the {self.cfg['min_return']} hurdle and it is not urgent")
                if any(self.cands[k]["seg"] == c["seg"] for k in self.funded):
                    raise ToolError(f"segment {c['seg']} already has a funded candidate")
                if c["cost"] > self.remaining:
                    raise ToolError(f"cost {c['cost']:,.0f} exceeds remaining budget {self.remaining:,.0f}")
                cap = self.cfg["urgent_cap_fraction"] * self.spendable
                if self._urgent(c) and self.urgent_spent + c["cost"] > cap:
                    raise ToolError("urgent-work cap reached")
            except (ToolError, AttributeError) as e:
                self.errors += 1
                out.append(dict(id=(it.get("id") if isinstance(it, dict) else None), ok=False, error=str(e)))
                continue
            self.funded[cid] = why
            self.remaining -= c["cost"]
            self.urgent_spent += c["cost"] if self._urgent(c) else 0.0
            out.append(dict(id=cid, ok=True, remaining=round(self.remaining)))
        return dict(results=out)

    def reject(self, items):
        out = []
        for it in self._items(items):
            try:
                cid, why = it.get("id"), check_rationale(it.get("reason"), self.cfg)
                if cid not in self.cands:
                    raise ToolError(f"unknown candidate {cid}")
                if cid in self.funded:
                    raise ToolError("already funded")
            except (ToolError, AttributeError) as e:
                self.errors += 1
                out.append(dict(id=(it.get("id") if isinstance(it, dict) else None), ok=False, error=str(e)))
                continue
            self.rejected[cid] = why
            out.append(dict(id=cid, ok=True))
        return dict(results=out)

    @property
    def handlers(self):
        return {n: getattr(self, n) for n in ("list_candidates", "get_candidate_detail", "fund", "reject")}

    def specs(self):
        return [spec("list_candidates", "Fundable options (single proposals and shared-dig bundles) with cost, benefit, return, urgency, eligibility and the money left. All numbers are computed for you."),
                spec("get_candidate_detail", "Detail of one candidate: members, proposer rationales, repaving penalty, benefit range, competing candidates on the same segment.",
                     {"id": {"type": "string"}}, ["id"]),
                spec("fund", "Fund candidates, in the order given. Refused if not eligible, the segment is already funded, or it exceeds the money left.",
                     {"items": ITEMS}, ["items"]),
                spec("reject", "Reject candidates with a reason (optional; unlisted candidates are simply not funded).", {"items": ITEMS}, ["items"])]
