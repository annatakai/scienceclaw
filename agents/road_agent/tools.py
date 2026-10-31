"""Read-only tools for the Claude-driven road agent. They read ONLY the road view (self.view), the road ratings
(road scoring.py) and the board. No pipe fields, no budget. Numbers come from existing code."""
from agents.llm import ToolError
from agents.llm_support import RATIONALE, RESPONSE_ITEMS, board_view, spec, validate_proposals, validate_responses

WORKS = {"repave": None}


class RoadTools:
    def __init__(self, agent, year, board, max_n):
        self.a, self.year, self.board, self.max_n, self.cfg = agent, year, board, max_n, agent.cfg
        self.submitted = None
        self.responses = None

    def _priority(self, seg):
        return self.a.ratings[seg]["wear_index"] * self.a.view[seg]["road"]["adt"] ** 0.5

    def _row(self, seg):
        rec, rt = self.a.view[seg], self.a.ratings[seg]
        return dict(segment_id=seg, street=rec["street"], condition_rating=rt["condition_rating"], pcr=rt["pcr"],
                    wear_index=rt["wear_index"], priority_score=round(self._priority(seg), 1))

    def get_top_worn_roads(self, n=10):
        n = max(1, min(25, int(n)))
        ranked = sorted(self.a.view, key=lambda s: -self._priority(s))
        return dict(year=self.year, roads=[self._row(s) for s in ranked[:n]])

    def get_road_detail(self, segment_id):
        if segment_id not in self.a.view:
            raise ToolError(f"unknown segment {segment_id}")
        rec, rt = self.a.view[segment_id], self.a.ratings[segment_id]
        pr = self.a._proposal(self.year, rec)
        return dict(self._row(segment_id), length_ft=round(rec["length_ft"]), road_class=rec["road"]["road_class"],
                    last_paved=rec["road"]["last_paved"], adt=rec["road"]["adt"], street_age=rt["street_age"],
                    urgency=rt["urgency"], recommended_action=rt["recommended_action"],
                    options={"repave": dict(work_cost=round(pr["work_cost"]), pcr_after=round(pr["road"]["pcr_after"][0], 1))})

    def get_board_plans(self):
        return dict(messages=board_view(self.board, self.year))

    def submit_proposals(self, proposals):
        self.submitted = validate_proposals(proposals, self.a.view, WORKS, self.max_n, self.cfg)
        return dict(accepted=len(self.submitted))

    def respond_to_join_requests(self, responses):
        y, b = self.year, self.board
        theirs = {m["segment_id"] for m in b.get(y, 1, "pipe", "post_plan")}
        asked = {m["segment_id"] for m in b.get(y, 2, "pipe", "join_request")}
        mine = self.a._mine()
        # phase 'join': pipe plans (round 1). phase 'accept': pipe join requests (round 2), only on streets already in my plan.
        allowed = ({"join_request": theirs, "decline": theirs} if self.phase == "join"
                   else {"accept": asked & mine, "decline": asked})
        self.responses = validate_responses(responses, allowed, self.cfg)
        return dict(accepted=len(self.responses))

    phase = "propose"

    @property
    def handlers(self):
        return {n: getattr(self, n) for n in ("get_top_worn_roads", "get_road_detail", "get_board_plans",
                                              "submit_proposals", "respond_to_join_requests")}

    def specs(self, phase):
        self.phase = phase
        seg = {"segment_id": {"type": "string"}}
        s = [spec("get_top_worn_roads", "Roads ranked by wear weighted by traffic (highest first), with condition rating and pavement condition (PCR).",
                  {"n": {"type": "integer", "description": "how many, 1-25"}}),
             spec("get_road_detail", "Full record of one road: class, last paved year, traffic, urgency and the repave cost.", seg, ["segment_id"]),
             spec("get_board_plans", "All messages on the shared board this year (plans, join requests, replies).")]
        if phase == "propose":
            item = {"type": "object", "required": ["segment_id", "work", "rationale"],
                    "properties": {"segment_id": {"type": "string"}, "work": {"type": "string", "enum": ["repave"]}, "rationale": RATIONALE}}
            s.append(spec("submit_proposals", f"Submit up to {self.max_n} repave proposals. Call once.",
                          {"proposals": {"type": "array", "items": item}}, ["proposals"]))
        else:
            acts = ["join_request", "decline"] if phase == "join" else ["accept", "decline"]
            s.append(spec("respond_to_join_requests",
                          "Offer to repave in the same opening as a pipe plan (join_request) or decline." if phase == "join"
                          else "Accept or decline the pipe agent's join requests. Call once.",
                          {"responses": RESPONSE_ITEMS(acts)}, ["responses"]))
        return s
