"""Road agent. Ratings come from agents/road_agent/scoring.py. It sees only the road view of the city plus the board."""
from agents.board import bundle_id
from agents.road_agent import scoring
from sim.config import infl


class RoadAgent:
    name = owner = "road"

    def __init__(self, cfg):
        self.cfg = cfg
        self.props = []

    def rate_all(self, year, view):
        self.ratings = {r["segment_id"]: scoring.score_road(
            dict(last_paved_year=r["road"]["last_paved"], aadt=r["road"]["adt"]), year) for r in view}
        counts = {}
        for v in self.ratings.values():
            counts[v["condition_rating"]] = counts.get(v["condition_rating"], 0) + 1
        return counts

    def _proposal(self, year, rec):
        cfg, H = self.cfg, self.cfg["horizon_years"]
        rd, L = rec["road"], rec["length_ft"]
        rt = self.ratings[rec["segment_id"]]
        before = [scoring.pcr(rd, year, t) for t in range(H)]
        after = [scoring.pcr(rd, year, t, repaved=True) for t in range(H)]
        why = (f"{rt['condition_rating']} {rd['road_class']} road (condition {rt['pcr']:.0f}), paved {rd['last_paved']}, "
               f"{rd['adt']:,} vehicles/day")
        return dict(
            contract_version="0.2", proposal_id=f"road-{year}-{rec['segment_id']}", agent="road",
            segment_id=rec["segment_id"], year=year, work="repave",
            work_cost=cfg["repave_per_ft"] * L * infl(cfg, year),
            exclusive_group=f"road-{rec['segment_id']}", bundle_id=None, pipe=None,
            road=dict(pcr_before=before, pcr_after=after, adt=rd["adt"], length_ft=L, street_age=rt["street_age"]),
            rating=dict(condition_rating=rt["condition_rating"], pcr=rt["pcr"], recommended_action=rt["recommended_action"]),
            rationale=why, priced=None)

    def propose(self, year, view, board, max_n):
        self.view = {r["segment_id"]: r for r in view}
        self.rate_all(year, view)
        ranked = sorted(view, key=lambda r: -(self.ratings[r["segment_id"]]["wear_index"] * r["road"]["adt"] ** 0.5))
        self.props = [self._proposal(year, rec) for rec in ranked[:max_n]]
        return self.props

    def post_plans(self, year, board):
        for p in self.props:
            board.add(year, 1, "road", "post_plan", p["segment_id"],
                      f"Plan to repave {self.view[p['segment_id']]['street']} ({p['segment_id']}): {p['rationale']}.",
                      {"proposal_id": p["proposal_id"]})

    def _mine(self):
        return {p["segment_id"] for p in self.props}

    def _tag(self, year, seg):
        for p in self.props:
            if p["segment_id"] == seg:
                p["bundle_id"] = bundle_id(year, seg)

    def join(self, year, board):
        """Round 2, step 1: for every segment a pipe plan will dig, offer to resurface in the same opening."""
        for m in board.get(year, 1, "pipe", "post_plan"):
            seg = m["segment_id"]
            age = year - self.view[seg]["road"]["last_paved"]
            if seg in self._mine():
                self._tag(year, seg)
                board.add(year, 2, "road", "join_request", seg, f"Join request: I also plan to repave {seg}; do it in one dig.")
            elif age >= 6:
                self.props.append(self._proposal(year, self.view[seg]))
                self._tag(year, seg)
                board.add(year, 2, "road", "join_request", seg,
                          f"Revise and join: pipe is digging {seg}; street is {age} yrs old, resurface it in the same opening.")
            else:
                board.add(year, 2, "road", "decline", seg,
                          f"Decline on {seg}: paved only {age} yrs ago. Pipe cut will carry a repaving penalty.")

    def accept(self, year, board):
        """Round 2, step 3: accept pipe join requests on streets I already planned."""
        for m in board.get(year, 2, "pipe", "join_request"):
            seg = m["segment_id"]
            if seg in self._mine():
                self._tag(year, seg)
                board.add(year, 2, "road", "accept", seg, f"Accept: pipe work on {seg} shares my opening.")
