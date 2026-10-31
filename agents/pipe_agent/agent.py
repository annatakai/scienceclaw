"""Pipe agent. Ratings come from agents/pipe_agent/scoring.py (via adapter.py). It sees only the pipe view of the
city plus the board, builds a menu of proposals (replace, reline), and negotiates shared digs in round 2."""
from agents.board import bundle_id
from agents.pipe_agent import adapter
from sim.config import infl


class PipeAgent:
    name = owner = "pipe"

    def __init__(self, cfg):
        self.cfg = cfg
        self.props = []

    def rate_all(self, year, view):
        """Rate every pipe with the team's rubric; returns {risk_class: count} and keeps ratings for ranking."""
        self.ratings = {r["segment_id"]: adapter.rating(r, year, self.cfg) for r in view}
        counts = {}
        for v in self.ratings.values():
            counts[v["risk_class"]] = counts.get(v["risk_class"], 0) + 1
        return counts

    def _proposal(self, year, rec, treat):
        cfg, H = self.cfg, self.cfg["horizon_years"]
        p, L = rec["pipe"], rec["length_ft"]
        before = [adapter.pof(rec, year, t, None, cfg) for t in range(H)]
        after = [adapter.pof(rec, year, t, treat, cfg) for t in range(H)]
        full = cfg["pipe_per_ft"] * L * infl(cfg, year)
        work = "replace_pipe" if treat == "replace" else "reline_pipe"
        rt = self.ratings[rec["segment_id"]]
        why = (f"{rt['risk_class']} risk (index {rt['risk_index']:.0f}): {p['material'].replace('_', ' ')} main from "
               f"{p['install_year']}, {len(p['breaks'])} prior breaks, PoF {before[0]:.0f}"
               + (", serves a critical facility" if rec["critical"] else ""))
        return dict(
            contract_version="0.2",
            proposal_id=f"pipe-{year}-{rec['segment_id']}" + ("" if treat == "replace" else "-reline"),
            agent="pipe", segment_id=rec["segment_id"], year=year, work=work,
            work_cost=full if treat == "replace" else full * cfg["reline_frac"],
            exclusive_group=f"pipe-{rec['segment_id']}", bundle_id=None,
            pipe=dict(pof_before=before, pof_after=after, pof_lo=[b * 0.85 for b in before],
                      pof_hi=[min(100.0, b * 1.15 + 5) for b in before],  # ASSUMPTION: the rubric has no model error bar
                      cof_prime=adapter.cof_prime(rec, year, cfg), length_ft=L),
            road=None, rating=dict(risk_class=rt["risk_class"], risk_index=rt["risk_index"],
                                   recommended_action=rt["recommended_action"]),
            rationale=why, priced=None)

    def propose(self, year, view, board, max_n):
        self.view = {r["segment_id"]: r for r in view}
        self.rate_all(year, view)
        ranked = sorted(view, key=lambda r: -(self.ratings[r["segment_id"]]["risk_index"] or 0))
        self.props = []
        for rec in ranked[: max(1, max_n // 2)]:
            self.props += [self._proposal(year, rec, "replace"), self._proposal(year, rec, "reline")]
        return self.props

    def post_plans(self, year, board):
        done = set()
        for p in self.props:
            seg = p["segment_id"]
            if seg in done:
                continue
            done.add(seg)
            board.add(year, 1, "pipe", "post_plan", seg,
                      f"Plan to replace main on {self.view[seg]['street']} ({seg}): {p['rationale']}.",
                      {"proposal_id": p["proposal_id"]})

    def _mine(self):
        return {p["segment_id"] for p in self.props}

    def _tag(self, year, seg):
        for p in self.props:
            if p["segment_id"] == seg:
                p["bundle_id"] = bundle_id(year, seg)

    def _add(self, year, seg):
        rec = self.view[seg]
        self.props += [self._proposal(year, rec, "replace"), self._proposal(year, rec, "reline")]

    def _pof(self, year, seg):
        return adapter.pof(self.view[seg], year, 0, None, self.cfg)

    def respond(self, year, board):
        """Round 2: accept road join requests; ask to join road plans where my own data says the pipe is worn."""
        for m in board.get(year, 2, "road", "join_request"):
            seg = m["segment_id"]
            pof = self._pof(year, seg)
            if seg in self._mine():
                self._tag(year, seg)
                board.add(year, 2, "pipe", "accept", seg, f"Accept: I am already planning to dig {seg}. One opening for both.")
            elif pof >= 35:
                self._add(year, seg)
                self._tag(year, seg)
                board.add(year, 2, "pipe", "accept", seg,
                          f"Accept and revise: road work opens {seg} anyway; main is worn (PoF {pof:.0f}), so I add replacement.")
            else:
                board.add(year, 2, "pipe", "decline", seg, f"Decline on {seg}: main is in fair shape (PoF {pof:.0f}).")
        for m in board.get(year, 1, "road", "post_plan"):
            seg = m["segment_id"]
            if seg in self._mine():
                continue
            pof = self._pof(year, seg)
            if pof >= 35:
                self._add(year, seg)
                self._tag(year, seg)
                board.add(year, 2, "pipe", "join_request", seg,
                          f"Join request: road is resurfacing {seg}; my main is worn (PoF {pof:.0f}), replace it in the same dig.")
