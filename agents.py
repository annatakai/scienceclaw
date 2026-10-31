"""Agents + Board. Rule-based (deterministic); an LLM would only write the `text`/`rationale` strings.
Decentralisation: pipe and road agents only see their own city view plus the board."""
from sim import pof_index, cof_prime, pcr, infl


class Board:
    def __init__(self):
        self.messages = []

    def add(self, year, rnd, frm, typ, seg, text, payload=None):
        m = dict(msg_id=len(self.messages) + 1, year=year, round=rnd, **{"from": frm}, type=typ,
                 segment_id=seg, text=text, payload=payload or {})
        self.messages.append(m)
        return m

    def get(self, year, rnd, frm, typ):
        return [m for m in self.messages if m["year"] == year and m["round"] == rnd and m["from"] == frm
                and m["type"] == typ]


def bundle_id(year, seg):
    return f"B-{year}-{seg}"


class PipeAgent:
    name = owner = "pipe"

    def __init__(self, cfg):
        self.cfg = cfg
        self.props = []

    def _proposal(self, year, rec, treat):
        cfg = self.cfg
        H = cfg["horizon_years"]
        p, L = rec["pipe"], rec["length_ft"]
        cof = cof_prime(rec["customers"], rec["critical"], p["diameter_in"])
        before = [pof_index(p, L, year, t, cfg=cfg) for t in range(H)]
        after = [pof_index(p, L, year, t, treat, cfg=cfg) for t in range(H)]
        full = cfg["pipe_per_ft"] * L * infl(cfg, year)
        work = "replace_pipe" if treat == "replace" else "reline_pipe"
        w = full if treat == "replace" else full * cfg["reline_frac"]
        why = (f"{p['material'].replace('_', ' ')} main from {p['install_year']}, {len(p['breaks'])} prior breaks, "
               f"PoF index {before[0]:.0f}" + (", serves a critical facility" if rec["critical"] else ""))
        return dict(
            contract_version="0.2", proposal_id=f"pipe-{year}-{rec['segment_id']}" + ("" if treat == "replace" else "-reline"),
            agent="pipe", segment_id=rec["segment_id"], year=year, work=work, work_cost=w,
            exclusive_group=f"pipe-{rec['segment_id']}", bundle_id=None,
            pipe=dict(pof_before=before, pof_after=after, pof_lo=[b * 0.85 for b in before],
                      pof_hi=[min(100.0, b * 1.15 + 5) for b in before], cof_prime=cof, length_ft=L),
            road=None, rationale=why, priced=None)

    def _risk(self, year, rec):
        pof = pof_index(rec["pipe"], rec["length_ft"], year, cfg=self.cfg)
        return pof * (0.4 + 0.6 * cof_prime(rec["customers"], rec["critical"], rec["pipe"]["diameter_in"]) / 100)

    def propose(self, year, view, board, max_n):
        self.view = {r["segment_id"]: r for r in view}
        ranked = sorted(view, key=lambda r: -self._risk(year, r))
        self.props = []
        for rec in ranked[: max(1, max_n // 2)]:
            self.props += [self._proposal(year, rec, "replace"), self._proposal(year, rec, "reline")]
        return self.props

    def post_plans(self, year, board):
        done = set()
        for p in self.props:
            if p["segment_id"] in done:
                continue
            done.add(p["segment_id"])
            board.add(year, 1, "pipe", "post_plan", p["segment_id"],
                      f"Plan to replace main on {self.view[p['segment_id']]['street']} ({p['segment_id']}): {p['rationale']}.",
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

    def respond(self, year, board):
        """Round 2: accept road join requests; ask to join road plans where my own data says the pipe is worn."""
        for m in board.get(year, 2, "road", "join_request"):
            seg = m["segment_id"]
            pof = pof_index(self.view[seg]["pipe"], self.view[seg]["length_ft"], year, cfg=self.cfg)
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
            pof = pof_index(self.view[seg]["pipe"], self.view[seg]["length_ft"], year, cfg=self.cfg)
            if pof >= 35:
                self._add(year, seg)
                self._tag(year, seg)
                board.add(year, 2, "pipe", "join_request", seg,
                          f"Join request: road is resurfacing {seg}; my main is worn (PoF {pof:.0f}), replace it in the same dig.")


class RoadAgent:
    name = owner = "road"

    def __init__(self, cfg):
        self.cfg = cfg
        self.props = []

    def _proposal(self, year, rec):
        cfg = self.cfg
        H = cfg["horizon_years"]
        rd, L = rec["road"], rec["length_ft"]
        before = [pcr(rd, year, t) for t in range(H)]
        after = [pcr(rd, year, t, repaved=True) for t in range(H)]
        age = year - rd["last_paved"]
        why = f"{rd['road_class']} road, paved {rd['last_paved']}, {rd['adt']:,} vehicles/day, condition {before[0]:.0f}"
        return dict(
            contract_version="0.2", proposal_id=f"road-{year}-{rec['segment_id']}", agent="road",
            segment_id=rec["segment_id"], year=year, work="repave",
            work_cost=cfg["repave_per_ft"] * L * infl(cfg, year),
            exclusive_group=f"road-{rec['segment_id']}", bundle_id=None, pipe=None,
            road=dict(pcr_before=before, pcr_after=after, adt=rd["adt"], length_ft=L, street_age=age),
            rationale=why, priced=None)

    def _need(self, year, rec):
        p0 = pcr(rec["road"], year)
        return (100 - p0) * (rec["road"]["adt"] ** 0.5)

    def propose(self, year, view, board, max_n):
        self.view = {r["segment_id"]: r for r in view}
        ranked = sorted(view, key=lambda r: -self._need(year, r))
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


class BudgetAgent:
    """Funds, rejects and explains. Never creates proposals. Dollars come from priced blocks only."""

    def __init__(self, cfg):
        self.cfg = cfg

    def _cands(self, props, pooled):
        out = []
        by_seg = {}
        for p in props:
            by_seg.setdefault(p["segment_id"], []).append(p)
        for seg, ps in by_seg.items():
            pipes = [p for p in ps if p["agent"] == "pipe"]
            roads = [p for p in ps if p["agent"] == "road"]
            for p in ps:
                out.append(dict(seg=seg, members=[p], cost=p["priced"]["cost_alone"], B=p["priced"]["benefit_usd"],
                                urg=p["priced"]["urgency"], bundle=None, saving=0.0))
            if pooled:
                for pp in pipes:
                    for rp in roads:
                        if pp["bundle_id"] and pp["bundle_id"] == rp["bundle_id"]:
                            a, b = pp["priced"], rp["priced"]
                            cost = a["dig_cost"] + a["cost_if_combined"] + b["cost_if_combined"]
                            marginal = b["benefit_usd"] / b["cost_if_combined"]
                            out.append(dict(seg=seg, members=[pp, rp], cost=cost, B=a["benefit_usd"] + b["benefit_usd"],
                                            urg=a["urgency"], bundle=pp["bundle_id"],
                                            saving=a["cost_alone"] + b["cost_alone"] - cost,
                                            marginal_ok=marginal >= self.cfg["min_return"]))
        for c in out:
            c["ret"] = c["B"] / c["cost"]
            c["npv"] = c["B"] - c["cost"]
        return out

    def _passes(self, c):
        if c.get("marginal_ok") is False:
            return False
        return c["ret"] >= self.cfg["min_return"] or c["urg"] >= self.cfg["urgent_override"]

    def _fund(self, cands, pot, funded, reasons, key):
        cfg = self.cfg
        used = set()
        urgent = sorted([c for c in cands if c["urg"] >= cfg["urgent_override"]], key=lambda c: -c["ret"])
        rest = sorted([c for c in cands if c["urg"] < cfg["urgent_override"]], key=lambda c: -c["ret"])
        left, urgent_spent = pot, 0.0
        for c in urgent + rest:
            if key(c) in used:
                continue
            if c["cost"] > left:
                reasons[id(c)] = "does not fit this year's budget"
                continue
            if c in urgent and urgent_spent + c["cost"] > cfg["urgent_cap_fraction"] * pot:
                reasons[id(c)] = "urgent-work cap reached"
                continue
            funded.append(c)
            used.add(key(c))
            left -= c["cost"]
            if c in urgent:
                urgent_spent += c["cost"]
        return left

    def allocate(self, props, year, mode):
        """mode: 'pooled' (coordinated / central) or 'isolated' (fixed department budgets, no bundling)."""
        cfg = self.cfg
        spendable = cfg["annual_capital_budget"] * (1 - cfg["reserve_fraction"])
        chosen, reasons = [], {}
        if mode == "pooled":
            cands = self._cands(props, True)
            passing = [c for c in cands if self._passes(c)]
            if cfg.get("select", "npv") == "npv":
                best = {}
                for c in passing:
                    if c["seg"] not in best or c["npv"] > best[c["seg"]]["npv"]:
                        best[c["seg"]] = c
                passing = list(best.values())
            self._fund(passing, spendable, chosen, reasons, key=lambda c: c["seg"])
        else:
            for dept, share in cfg["department_split"].items():
                ps = [p for p in props if p["agent"] == dept]
                cands = self._cands(ps, False)
                passing = [c for c in cands if self._passes(c)]
                if cfg.get("select", "npv") == "npv":
                    best = {}
                    for c in passing:
                        g = c["members"][0]["exclusive_group"]
                        if g not in best or c["npv"] > best[g]["npv"]:
                            best[g] = c
                    passing = list(best.values())
                self._fund(passing, spendable * share, chosen, reasons,
                           key=lambda c: c["members"][0]["exclusive_group"])
        # build per-proposal decisions
        funded_ids = {}
        for c in chosen:
            for m in c["members"]:
                funded_ids[m["proposal_id"]] = c
        decisions = []
        rr_cap = spendable * cfg["rate_revenue_share"]
        rr_used = 0.0
        for p in sorted(props, key=lambda p: p["proposal_id"]):
            c = funded_ids.get(p["proposal_id"])
            pr = p["priced"]
            if c:
                n = len(c["members"])
                if c["bundle"]:
                    amount = pr["cost_if_combined"] + pr["dig_cost"] / n
                    why = (f"Bundle return {c['ret']:.2f} (pipe + road share one dig, saves ${c['saving']:,.0f}); "
                           f"net value ${c['npv']:,.0f}.")
                else:
                    amount = pr["cost_alone"]
                    why = (f"Return {c['ret']:.2f}" + (" and urgent (tier 1)." if c["urg"] >= cfg["urgent_override"] else ".")
                           + (" Pipe cut carries a repaving penalty." if pr["penalty"] > 0 and p["agent"] == "pipe" else ""))
                eligible = p["work"] in ("replace_pipe", "repave")
                if eligible and rr_used + amount <= rr_cap:
                    src, rr_used = "rate_revenue", rr_used + amount
                else:
                    src = "bonds"
                decisions.append(dict(proposal_id=p["proposal_id"], segment_id=p["segment_id"], agent=p["agent"],
                                      work=p["work"], bundle_id=c["bundle"], funded=True, amount=amount,
                                      funding_source=src, return_per_dollar=c["ret"], reason=why,
                                      saving_share=c["saving"] / n if c["bundle"] else 0.0))
            else:
                if pr["return_alone"] < cfg["min_return"] and pr["urgency"] < cfg["urgent_override"]:
                    why = f"Return {pr['return_alone']:.2f} is below the {cfg['min_return']:.1f} hurdle."
                else:
                    why = "Alternative funded for this asset, or it did not fit this year's budget."
                decisions.append(dict(proposal_id=p["proposal_id"], segment_id=p["segment_id"], agent=p["agent"],
                                      work=p["work"], bundle_id=None, funded=False, amount=0.0, funding_source=None,
                                      return_per_dollar=pr["return_alone"], reason=why, saving_share=0.0))
        return decisions
