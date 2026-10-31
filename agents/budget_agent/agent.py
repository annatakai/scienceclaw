"""Budget agent. Ratings come from agents/budget_agent/scoring.py. Funds, rejects and explains; never creates
proposals. Every dollar figure comes from sim/costs.py (priced blocks, bundle(), share_amount()), never from the language model."""
from agents.budget_agent.scoring import score_candidate
from sim import costs, reserve


class BudgetAgent:
    """Funds, rejects and explains. Never creates proposals."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.order = costs.source_order(cfg)   # cheapest source first (lowest present value of repayments per dollar)
        self.why_not = {}                      # proposal_id -> reason it was not funded, for the last allocate()

    # ------------------------------------------------------------ candidates
    def _single(self, p):
        pr = p["priced"]
        return dict(seg=p["segment_id"], members=[p], cost=pr["cost_alone"], B=pr["benefit_usd"], B_lo=pr["benefit_usd_lo"],
                    B_hi=pr["benefit_usd_hi"], urg=pr["urgency"], bundle=None, saving=0.0, wait=p["work"] == costs.WAIT)

    def _cands(self, props, pooled):
        out, by_seg = [], {}
        for p in props:
            by_seg.setdefault(p["segment_id"], []).append(p)
        for seg, ps in by_seg.items():
            core = [p for p in ps if p["work"] != costs.WAIT]
            waits = [p for p in ps if p["work"] == costs.WAIT]
            out += [self._single(p) for p in core]
            if pooled:
                for pp in (p for p in core if p["agent"] == "pipe"):
                    for rp in (p for p in core if p["agent"] == "road"):
                        if pp["bundle_id"] and pp["bundle_id"] == rp["bundle_id"]:
                            b = costs.bundle(pp["priced"], rp["priced"], self.cfg)
                            out.append(dict(seg=seg, members=[pp, rp], cost=b["cost"], B=b["B"], B_lo=b["B_lo"], B_hi=b["B_hi"],
                                            urg=pp["priced"]["urgency"], bundle=pp["bundle_id"], saving=b["saving"],
                                            marginal_ok=b["marginal_ok"], wait=False))
                if waits:   # waiting on every asset of the segment: one candidate, value = sum of the deferred jobs
                    pr = [w["priced"] for w in waits]
                    out.append(dict(seg=seg, members=waits, cost=sum(x["cost_alone"] for x in pr),
                                    B=sum(x["benefit_usd"] for x in pr), B_lo=sum(x["benefit_usd_lo"] for x in pr),
                                    B_hi=sum(x["benefit_usd_hi"] for x in pr), urg=max(x["urgency"] for x in pr),
                                    bundle=None, saving=0.0, wait=True))
            else:
                out += [self._single(p) for p in waits]
        for c in out:
            c["ret"] = c["B"] / c["cost"]
            c["npv"] = c["B"] - c["cost"]
            c["ret_lo"], c["ret_hi"] = c["B_lo"] / c["cost"], c["B_hi"] / c["cost"]
            c["needs_review"] = (not c["wait"]) and costs.review_flag(c["ret_lo"], c["ret_hi"], self.cfg["min_return"])
        return out

    def _passes(self, c):
        if c.get("wait") or c.get("marginal_ok") is False:
            return False
        return c["ret"] >= self.cfg["min_return"] or c["urg"] >= self.cfg["urgent_override"]

    def _pick(self, cands, group):
        """One candidate per asset group, chosen by NPV (return_formula.md 6.1). Waiting a year competes as an option;
        urgent (tier 1) work cannot wait."""
        passing = [c for c in cands if self._passes(c)]
        if self.cfg.get("select", "npv") != "npv":
            return passing
        best = {}
        for c in passing:
            k = group(c)
            if k not in best or c["npv"] > best[k]["npv"]:
                best[k] = c
        for w in (c for c in cands if c.get("wait")):
            k = group(w)
            b = best.get(k)
            if b is not None and b["urg"] < self.cfg["urgent_override"] and w["npv"] > b["npv"]:
                del best[k]
                why = f"Waiting a year is worth more: net value ${w['npv']:,.0f} if deferred vs ${b['npv']:,.0f} now."
                for c in cands:
                    if group(c) == k and not c.get("wait"):
                        for m in c["members"]:
                            self.why_not[m["proposal_id"]] = why
        return list(best.values())

    # ------------------------------------------------------------ funding sources
    def _ledger(self, pot):
        return {s: share * pot for s, share in self.cfg["funding_mix"].items()}

    def _assign(self, c, ledger):
        """Pay each member from the cheapest source with room, within each source's share and eligibility. Returns
        ({proposal_id: source}, remaining ledger) or None when some member has no source with room."""
        n, room, out = len(c["members"]), dict(ledger), {}
        elig = self.cfg["rate_revenue_eligible_work"]
        for m in sorted(c["members"], key=lambda m: -costs.share_amount(m["priced"], n)):
            amt = costs.share_amount(m["priced"], n)
            for s in self.order:
                if s == "rate_revenue" and m["work"] not in elig:
                    continue
                if room[s] >= amt - 1e-9:
                    room[s] -= amt
                    out[m["proposal_id"]] = s
                    break
            else:
                return None
        return out, room

    def _fund(self, cands, pot, funded, reasons, key):
        cfg = self.cfg
        used, ledger = set(), self._ledger(pot)
        urgent = [c for c in cands if c["urg"] >= cfg["urgent_override"]]
        rest = [c for c in cands if c["urg"] < cfg["urgent_override"]]
        # rank by return only when the budget binds; otherwise everything that passes fits and order does not matter
        binding = sum(c["cost"] for c in cands) > pot
        rk = (lambda c: -c["ret"]) if binding else (lambda c: -c["npv"])
        left, urgent_spent = pot, 0.0
        for c in sorted(urgent, key=rk) + sorted(rest, key=rk):
            if key(c) in used:
                continue
            why = None
            if c["cost"] > left:
                why = f"Does not fit this year's budget (needs ${c['cost']:,.0f}, ${left:,.0f} left)."
            elif c in urgent and urgent_spent + c["cost"] > cfg["urgent_cap_fraction"] * pot:
                why = "Urgent-work cap reached this year."
            else:
                got = self._assign(c, ledger)
                if got is None:
                    why = "No funding source with room and eligibility for it this year."
            if why:
                for m in c["members"]:
                    reasons[m["proposal_id"]] = why
                continue
            c["sources"], ledger = got
            funded.append(c)
            used.add(key(c))
            left -= c["cost"]
            if c in urgent:
                urgent_spent += c["cost"]
        return left

    # ------------------------------------------------------------ allocate
    def allocate(self, props, year, mode):
        """mode: 'pooled' (coordinated / central) or 'isolated' (fixed department budgets, no bundling)."""
        cfg = self.cfg
        spendable = reserve.spendable(cfg)
        chosen, reasons = [], {}
        self.why_not = {}
        if mode == "pooled":
            cands = self._cands(props, True)
            self._fund(self._pick(cands, lambda c: c["seg"]), spendable, chosen, reasons, key=lambda c: c["seg"])
        else:
            for dept, share in cfg["department_split"].items():
                cands = self._cands([p for p in props if p["agent"] == dept], False)
                self._fund(self._pick(cands, lambda c: c["members"][0]["exclusive_group"]), spendable * share, chosen, reasons,
                           key=lambda c: c["members"][0]["exclusive_group"])
        for pid, why in reasons.items():
            self.why_not.setdefault(pid, why)
        return self._decisions(props, chosen, spendable)

    def _decisions(self, props, chosen, spendable, notes=None):
        """Per-proposal decisions for the chosen candidates. notes: optional {proposal_id: reason} that replaces the
        rule-based reason (the Claude-driven budget agent passes its own written reasons)."""
        cfg, notes = self.cfg, notes or {}
        ledger = self._ledger(spendable)
        funded_ids = {}
        for c in chosen:
            if "sources" not in c:   # chosen by the Claude-driven agent: assign sources now, in the order funded
                got = self._assign(c, ledger)
                c["sources"], ledger = got if got else ({m["proposal_id"]: "bonds" for m in c["members"]}, ledger)
            for m in c["members"]:
                funded_ids[m["proposal_id"]] = c
        decisions = []
        for p in sorted(props, key=lambda p: p["proposal_id"]):
            c = funded_ids.get(p["proposal_id"])
            pr = p["priced"]
            base = dict(proposal_id=p["proposal_id"], segment_id=p["segment_id"], agent=p["agent"], work=p["work"], year=p["year"],
                        urgency=pr["urgency"])
            if c:
                n = len(c["members"])
                amount = costs.share_amount(pr, n)
                src = c["sources"][p["proposal_id"]]
                if c["bundle"]:
                    why = (f"Bundle return {c['ret']:.2f} (pipe + road share one dig, saves ${c['saving']:,.0f}); "
                           f"net value ${c['npv']:,.0f}.")
                else:
                    why = (f"Return {c['ret']:.2f}" + (" and urgent (tier 1)." if c["urg"] >= cfg["urgent_override"] else ".")
                           + (" Pipe cut carries a repaving penalty." if pr["penalty"] > 0 and p["agent"] == "pipe" else ""))
                if c["needs_review"]:
                    why += f" Needs engineering review: return could be {c['ret_lo']:.2f} to {c['ret_hi']:.2f}."
                decisions.append(dict(base, bundle_id=c["bundle"], funded=True, amount=amount, funding_source=src,
                                      return_per_dollar=c["ret"], return_lo=c["ret_lo"], return_hi=c["ret_hi"],
                                      needs_review=c["needs_review"], reason=notes.get(p["proposal_id"], why),
                                      net_cost=costs.net_cost(cfg, amount, src), loan_interest=costs.loan_interest(cfg, amount, src),
                                      saving_share=c["saving"] / n if c["bundle"] else 0.0,
                                      **score_candidate(c["ret"], c["urg"], cfg["min_return"])))
            else:
                if p["work"] == costs.WAIT:
                    why = "Waiting a year is the plan unless another option on this asset is funded."
                elif p["proposal_id"] in self.why_not:
                    why = self.why_not[p["proposal_id"]]
                elif pr["return_alone"] < cfg["min_return"] and pr["urgency"] < cfg["urgent_override"]:
                    why = f"Return {pr['return_alone']:.2f} is below the {cfg['min_return']:.1f} hurdle."
                    if pr["cost_if_combined"] and pr["benefit_usd"] / pr["cost_if_combined"] >= cfg["min_return"]:
                        why += (f" Would qualify as part of a shared dig (return {pr['benefit_usd'] / pr['cost_if_combined']:.2f}"
                                f" on the work alone).")
                else:
                    why = "Alternative funded for this asset, or it did not fit this year's budget."
                decisions.append(dict(base, bundle_id=None, funded=False, amount=0.0, funding_source=None,
                                      return_per_dollar=pr["return_alone"], return_lo=pr["return_lo"], return_hi=pr["return_hi"],
                                      needs_review=pr["needs_review"], reason=notes.get(p["proposal_id"], why), net_cost=0.0,
                                      loan_interest=0.0, saving_share=0.0,
                                      **score_candidate(pr["return_alone"], pr["urgency"], cfg["min_return"])))
        return decisions
