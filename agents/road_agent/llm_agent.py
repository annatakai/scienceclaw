"""Claude-driven road agent: same interface as RoadAgent (propose, post_plans, join, accept)."""
from agents.llm_support import StepFailed, attempt_then_fallback, retry_note
from agents.road_agent.agent import RoadAgent
from agents.road_agent.tools import RoadTools

SYSTEM = ("You are the road-asset agent of a city. You see only road data and the shared board. "
          "Choose which streets to repave, ideally in the same opening as pipe work. Never calculate; use the numbers the tools return. "
          "Every proposal and reply needs a rationale of at most 280 characters. Be brief and use few tool calls.")


class LLMRoadAgent(RoadAgent):
    def __init__(self, cfg, llm):
        super().__init__(cfg)
        self.llm = llm

    def propose(self, year, view, board, max_n):
        self.view = {r["segment_id"]: r for r in view}
        self.rate_all(year, view)

        def attempt(err):
            t = RoadTools(self, year, board, max_n)
            self.llm.run("road", year, SYSTEM,
                         f"Year {year}. Pick up to {max_n} streets to repave, then call submit_proposals once." + retry_note(err),
                         t.specs("propose"), t.handlers, stop_when=lambda: t.submitted is not None)
            if t.submitted is None:
                raise StepFailed("submit_proposals was never accepted")
            props = []
            for it in t.submitted:
                p = self._proposal(year, self.view[it["segment_id"]])
                p["rationale"], p["rationale_source"] = it["rationale"], "llm"
                props.append(p)
            return props

        self.props = attempt_then_fallback(self.llm, "road", year, "propose", attempt,
                                           lambda: RoadAgent.propose(self, year, view, board, max_n))
        self.complete(year)   # add the wait-a-year (and, for roads, preserve or reconstruct) alternatives
        return self.props

    def _respond(self, year, board, phase, prompt, rule_fn):
        def attempt(err):
            t = RoadTools(self, year, board, 0)
            specs = t.specs(phase)
            self.llm.run("road", year, SYSTEM, prompt + retry_note(err), specs, t.handlers,
                         stop_when=lambda: t.responses is not None)
            if t.responses is None:
                raise StepFailed("respond_to_join_requests was never accepted")
            return t.responses

        def fallback():
            rule_fn(self, year, board)
            return None

        return attempt_then_fallback(self.llm, "road", year, phase, attempt, fallback) or []

    def join(self, year, board):
        if not board.get(year, 1, "pipe", "post_plan"):
            return
        resp = self._respond(year, board, "join",
                             f"Year {year}, round 2. Read the pipe plans on the board. For streets where resurfacing in the same "
                             f"opening makes sense, send a join_request; decline the rest you want to answer. Call respond_to_join_requests once.",
                             RoadAgent.join)
        for r in resp:
            seg, why = r["segment_id"], r["rationale"]
            if r["action"] == "decline":
                board.add(year, 2, "road", "decline", seg, f"Decline on {seg}: {why}")
                continue
            if seg not in self._mine():
                self.props += self._menu(year, self.view[seg])
            self._tag(year, seg)
            board.add(year, 2, "road", "join_request", seg, f"Join request on {seg}: {why}")

    def accept(self, year, board):
        if not board.get(year, 2, "pipe", "join_request"):
            return
        resp = self._respond(year, board, "accept",
                             f"Year {year}. The pipe agent asked to join some of your plans. Accept or decline each. Call respond_to_join_requests once.",
                             RoadAgent.accept)
        for r in resp:
            seg, why = r["segment_id"], r["rationale"]
            if r["action"] == "accept":
                self._tag(year, seg)
                board.add(year, 2, "road", "accept", seg, f"Accept on {seg}: {why}")
            else:
                board.add(year, 2, "road", "decline", seg, f"Decline on {seg}: {why}")
