"""Claude-driven pipe agent: same interface as PipeAgent. The model chooses segments and work and writes the reason;
every number (risk, PoF, cost) comes from the tools. Invalid output -> retry once -> rule-based fallback."""
from agents.llm_support import StepFailed, attempt_then_fallback, retry_note
from agents.pipe_agent.agent import PipeAgent
from agents.pipe_agent.tools import PipeTools

SYSTEM = ("You are the pipe-asset agent of a city water utility. You see only pipe data and the shared board. "
          "Choose which water mains to repair so streets are opened once. Never calculate; use the numbers the tools return. "
          "Every proposal and reply needs a rationale of at most 280 characters. Be brief and use few tool calls.")


class LLMPipeAgent(PipeAgent):
    def __init__(self, cfg, llm):
        super().__init__(cfg)
        self.llm = llm

    def propose(self, year, view, board, max_n):
        self.view = {r["segment_id"]: r for r in view}
        self.rate_all(year, view)

        def attempt(err):
            t = PipeTools(self, year, board, max_n)
            self.llm.run("pipe", year, SYSTEM,
                         f"Year {year}. Pick up to {max_n} proposals (replace_pipe and/or reline_pipe) for the pipes most worth "
                         f"repairing, then call submit_proposals once." + retry_note(err),
                         t.specs("propose"), t.handlers, stop_when=lambda: t.submitted is not None)
            if t.submitted is None:
                raise StepFailed("submit_proposals was never accepted")
            props = []
            for it in t.submitted:
                p = self._proposal(year, self.view[it["segment_id"]], "replace" if it["work"] == "replace_pipe" else "reline")
                p["rationale"], p["rationale_source"] = it["rationale"], "llm"
                props.append(p)
            return props

        self.props = attempt_then_fallback(self.llm, "pipe", year, "propose", attempt,
                                           lambda: PipeAgent.propose(self, year, view, board, max_n))
        return self.props

    def respond(self, year, board):
        if not (board.get(year, 2, "road", "join_request") or board.get(year, 1, "road", "post_plan")):
            return

        def attempt(err):
            t = PipeTools(self, year, board, 0)
            self.llm.run("pipe", year, SYSTEM,
                         f"Year {year}, round 2. Read the board. Accept or decline the road agent's join requests, and ask to join "
                         f"road plans where replacing the main in the same opening makes sense. Call respond_to_join_requests once." + retry_note(err),
                         t.specs("respond"), t.handlers, stop_when=lambda: t.responses is not None)
            if t.responses is None:
                raise StepFailed("respond_to_join_requests was never accepted")
            return t.responses

        def fallback():
            PipeAgent.respond(self, year, board)
            return None

        resp = attempt_then_fallback(self.llm, "pipe", year, "respond", attempt, fallback)
        for r in resp or []:
            seg, why = r["segment_id"], r["rationale"]
            if r["action"] == "decline":
                board.add(year, 2, "pipe", "decline", seg, f"Decline on {seg}: {why}")
                continue
            if seg not in self._mine():
                self._add(year, seg)
            self._tag(year, seg)
            typ = "accept" if r["action"] == "accept" else "join_request"
            board.add(year, 2, "pipe", typ, seg, ("Accept" if typ == "accept" else "Join request") + f" on {seg}: {why}")
