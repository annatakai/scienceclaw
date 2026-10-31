"""Benchmarks and baselines (docs/evidence_plan.md section 3). ALL DATA SIMULATED. Dollars still come from sim/costs.py.

  central_ilp   one planner with full data on EVERY segment and every option (no menu limit), same objective and the same
                budget as the agents: choose at most one option per segment (stand-alone work, shared-dig bundle, or wait) to
                maximise total net value subject to the spendable amount. Solved EXACTLY as a multiple-choice knapsack by dynamic
                programming on a cost grid (costs rounded up to the grid, so the plan is always feasible; the grid is fine
                enough that the rounding loss is under 0.1% of the budget). No tier-1 cap and no source-room constraint (sources are
                assigned afterwards), so it is a relaxation of the agents' problem, and a fair upper bound for the same objective.
  central_greedy same full menu as central_ilp but funded by the agents' own greedy rule: separates the effect of the menu size from the optimiser
  single_agent  one agent with both views and no board: same menu size as the three agents, bundles wherever its own picks overlap
  age_first     oldest pipes and oldest pavement first, fixed 60/40 department split, no hurdle, no bundling
  risk_first    highest-risk pipes (team rubric) and most-worn roads first, fixed 60/40 split, no hurdle, no bundling
"""
import numpy as np

from agents.budget_agent.agent import BudgetAgent
from sim import reserve

GRID = 4000   # cost cells in the knapsack


def solve_mckp(groups, W):
    """groups: list of option lists [(units:int >= 0, value:float)]. Maximise total value with total units <= W, at most one
    option per group. Exact on the integer grid. Returns the chosen option index per group (or -1)."""
    G = len(groups)
    dp = np.zeros(W + 1)
    choice = np.full((G, W + 1), -1, dtype=np.int16)
    for g, opts in enumerate(groups):
        new, ch = dp.copy(), choice[g]
        for j, (w, v) in enumerate(opts):
            if w > W or v <= 0:
                continue
            cand = np.full(W + 1, -np.inf)
            cand[w:] = dp[: W + 1 - w] + v
            better = cand > new
            new = np.where(better, cand, new)
            ch[better] = j
        dp = new
    picks, w = [-1] * G, W
    for g in range(G - 1, -1, -1):
        j = choice[g][w]
        if j >= 0:
            picks[g] = int(j)
            w -= groups[g][j][0]
    return picks


class OptimalPlanner(BudgetAgent):
    """Same interface as BudgetAgent.allocate, but picks the NPV-maximising plan exactly."""

    def allocate(self, props, year, mode):
        self.why_not = {}
        spendable = reserve.spendable(self.cfg)
        cands = self._cands(props, True)
        unit = max(1.0, spendable / GRID)
        by_seg = {}
        for c in cands:
            if c.get("wait") or self._passes(c):
                by_seg.setdefault(c["seg"], []).append(c)
        segs = list(by_seg)
        groups = [[(int(np.ceil(c["cost"] / unit - 1e-9)) if not c.get("wait") else 0, c["npv"]) for c in by_seg[s]] for s in segs]
        picks = solve_mckp(groups, int(spendable // unit))
        chosen = []
        for s, j in zip(segs, picks):
            if j >= 0 and not by_seg[s][j].get("wait"):
                chosen.append(by_seg[s][j])
            elif j >= 0:
                for m in by_seg[s][j]["members"]:
                    self.why_not[m["proposal_id"]] = "The optimal plan waits a year on this asset."
        # sources are assigned in value order; a plan that does not fit the source shares falls back to bonds (see _decisions)
        chosen.sort(key=lambda c: -c["ret"])
        return self._decisions(props, chosen, spendable)


class RankPlanner(BudgetAgent):
    """age_first / risk_first: fund assets top-down by one score, per department pot, with no hurdle and no bundling."""

    def __init__(self, cfg, kind):
        super().__init__(cfg)
        self.kind = kind

    def plan(self, year, pipe, road, city):
        cfg = self.cfg
        pv, rv = pipe.view, road.view
        if self.kind == "age_first":
            pk = lambda s: -(year - pv[s]["pipe"]["install_year"])
            rk = lambda s: -(year - rv[s]["road"]["last_paved"])
        else:
            pk = lambda s: -(pipe.ratings[s]["risk_index"] or 0)
            rk = lambda s: -(road.ratings[s]["wear_index"] * rv[s]["road"]["adt"] ** 0.5)
        k = cfg["max_proposals"]
        pipe.props = [pipe._proposal(year, pv[s], "replace") for s in sorted(pv, key=pk)[:k]]
        road.props = [road._proposal(year, rv[s], "repave") for s in sorted(rv, key=rk)[:k]]
        props = pipe.props + road.props
        for p in props:
            p["priced"] = city.price(p, year)
        spendable = reserve.spendable(cfg)
        chosen = []
        for dept, share in cfg["department_split"].items():
            left = spendable * share
            for p in (pipe.props if dept == "pipe" else road.props):
                c = self._single(p)
                c["ret"], c["npv"], c["ret_lo"], c["ret_hi"] = c["B"] / c["cost"], c["B"] - c["cost"], c["B_lo"] / c["cost"], c["B_hi"] / c["cost"]
                c["needs_review"] = False
                if c["cost"] <= left:
                    chosen.append(c)
                    left -= c["cost"]
        return props, self._decisions(props, chosen, spendable)
