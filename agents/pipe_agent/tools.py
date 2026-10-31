"""Read-only tools for the Claude-driven pipe agent. They read ONLY the pipe view (self.view), the pipe ratings
(adapter -> team scoring.py) and the board. No road fields, no budget. Numbers come from existing code."""
from agents.llm import ToolError
from agents.llm_support import (RATIONALE, RESPONSE_ITEMS, board_view, spec, validate_proposals,
                                validate_responses)
from agents.pipe_agent import adapter

WORKS = {"replace_pipe": "replace", "reline_pipe": "reline"}


class PipeTools:
    def __init__(self, agent, year, board, max_n):
        self.a, self.year, self.board, self.max_n, self.cfg = agent, year, board, max_n, agent.cfg
        self.submitted = None   # validated proposals: [{segment_id, work, rationale}]
        self.responses = None   # validated join responses

    def _row(self, seg):
        rec, rt = self.a.view[seg], self.a.ratings[seg]
        return dict(segment_id=seg, street=rec["street"], risk_class=rt["risk_class"], risk_index=round(rt["risk_index"], 1),
                    pof_now=round(adapter.pof(rec, self.year, 0, None, self.cfg), 1))

    def get_top_risk_pipes(self, n=10):
        n = max(1, min(25, int(n)))
        ranked = sorted(self.a.view, key=lambda s: -(self.a.ratings[s]["risk_index"] or 0))
        return dict(year=self.year, pipes=[self._row(s) for s in ranked[:n]])

    def get_pipe_detail(self, segment_id):
        if segment_id not in self.a.view:
            raise ToolError(f"unknown segment {segment_id}")
        rec, p = self.a.view[segment_id], self.a.view[segment_id]["pipe"]
        rt = self.a.ratings[segment_id]
        opts = {}
        for work, treat in WORKS.items():
            pr = self.a._proposal(self.year, rec, treat)
            opts[work] = dict(work_cost=round(pr["work_cost"]), pof_after=round(pr["pipe"]["pof_after"][0], 1))
        return dict(self._row(segment_id), length_ft=round(rec["length_ft"]), material=p["material"],
                    install_year=p["install_year"], diameter_in=p["diameter_in"], prior_breaks=p["breaks"], soil=p["soil"],
                    customers=rec["customers"], critical_facility=rec["critical"], exposure=rec["exposure"],
                    aadt=rec["aadt"], cof_prime=round(adapter.cof_prime(rec, self.year, self.cfg), 1),
                    recommended_action=rt["recommended_action"], options=opts)

    def get_board_plans(self):
        return dict(messages=board_view(self.board, self.year))

    def submit_proposals(self, proposals):
        self.submitted = validate_proposals(proposals, self.a.view, WORKS, self.max_n, self.cfg)
        return dict(accepted=len(self.submitted))

    def respond_to_join_requests(self, responses):
        y, b = self.year, self.board
        theirs = {m["segment_id"] for m in b.get(y, 1, "road", "post_plan")}
        asked = {m["segment_id"] for m in b.get(y, 2, "road", "join_request")}
        mine = self.a._mine()
        self.responses = validate_responses(responses, {"accept": asked, "decline": asked, "join_request": theirs - mine},
                                            self.cfg)
        return dict(accepted=len(self.responses))

    @property
    def handlers(self):
        return {n: getattr(self, n) for n in ("get_top_risk_pipes", "get_pipe_detail", "get_board_plans",
                                              "submit_proposals", "respond_to_join_requests")}

    def specs(self, phase):
        seg = {"segment_id": {"type": "string"}}
        s = [spec("get_top_risk_pipes", "Pipes ranked by the team's risk index (highest first), with risk class and current probability of failure.",
                  {"n": {"type": "integer", "description": "how many, 1-25"}}),
             spec("get_pipe_detail", "Full record of one pipe: material, age, breaks, customers, and the cost and post-work PoF of each work option.", seg, ["segment_id"]),
             spec("get_board_plans", "All messages on the shared board this year (plans, join requests, replies).")]
        if phase == "propose":
            item = {"type": "object", "required": ["segment_id", "work", "rationale"],
                    "properties": {"segment_id": {"type": "string"}, "work": {"type": "string", "enum": sorted(WORKS)}, "rationale": RATIONALE}}
            s.append(spec("submit_proposals", f"Submit up to {self.max_n} proposals (one segment may have both a replace and a reline option; the budget agent picks one). Call once.",
                          {"proposals": {"type": "array", "items": item}}, ["proposals"]))
        else:
            s.append(spec("respond_to_join_requests", "Answer the road agent's join requests (accept/decline) and/or ask to join a road plan (join_request). Call once.",
                          {"responses": RESPONSE_ITEMS(["accept", "decline", "join_request"])}, ["responses"]))
        return s
