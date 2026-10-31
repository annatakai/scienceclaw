"""Budget agent. Ratings come from agents/budget_agent/scoring.py. Funds, rejects and explains; never creates
proposals; dollars come from the `priced` block (sim/costs.py), never from the language model."""
from agents.budget_agent.scoring import score_candidate


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
        return self._decisions(props, chosen, spendable)

    def _decisions(self, props, chosen, spendable, notes=None):
        """Per-proposal decisions for the chosen candidates. notes: optional {proposal_id: reason} that replaces the
        rule-based reason (the Claude-driven budget agent passes its own written reasons)."""
        cfg, notes = self.cfg, notes or {}
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
                why = notes.get(p["proposal_id"], why)
                decisions.append(dict(proposal_id=p["proposal_id"], segment_id=p["segment_id"], agent=p["agent"],
                                      work=p["work"], bundle_id=c["bundle"], funded=True, amount=amount,
                                      funding_source=src, return_per_dollar=c["ret"], reason=why,
                                      saving_share=c["saving"] / n if c["bundle"] else 0.0,
                                      **score_candidate(c["ret"], c["urg"], cfg["min_return"])))
            else:
                if pr["return_alone"] < cfg["min_return"] and pr["urgency"] < cfg["urgent_override"]:
                    why = f"Return {pr['return_alone']:.2f} is below the {cfg['min_return']:.1f} hurdle."
                else:
                    why = "Alternative funded for this asset, or it did not fit this year's budget."
                why = notes.get(p["proposal_id"], why)
                decisions.append(dict(proposal_id=p["proposal_id"], segment_id=p["segment_id"], agent=p["agent"],
                                      work=p["work"], bundle_id=None, funded=False, amount=0.0, funding_source=None,
                                      return_per_dollar=pr["return_alone"], reason=why, saving_share=0.0,
                                      **score_candidate(pr["return_alone"], pr["urgency"], cfg["min_return"])))
        return decisions
