"""Claude-driven budget agent: same interface as BudgetAgent.allocate. The model picks which candidates to fund and
writes the reasons; dollars, returns and urgency come from sim/costs.py via the tools, and the tool enforces the cap."""
from agents.budget_agent.agent import BudgetAgent
from agents.budget_agent.tools import BudgetTools
from agents.llm_support import StepFailed, attempt_then_fallback, retry_note

SYSTEM = ("You are the budget agent of a city. Pipe and road agents submitted repair proposals; you decide which to fund. "
          "Prefer higher return and urgent work, and prefer shared-dig bundles when they save a dig. Never calculate; use the numbers "
          "the tools return. Fund in as few calls as possible (fund takes a list), then reject any you deliberately pass over. "
          "Every reason is at most 280 characters. When finished, reply 'done'.")


class LLMBudgetAgent(BudgetAgent):
    def __init__(self, cfg, llm):
        super().__init__(cfg)
        self.llm = llm

    def allocate(self, props, year, mode):
        if mode != "pooled":
            return super().allocate(props, year, mode)
        cfg = self.cfg
        spendable = cfg["annual_capital_budget"] * (1 - cfg["reserve_fraction"])

        def attempt(err):
            t = BudgetTools(self, props, spendable)
            if not any(c["eligible"] for c in t.cands.values()):
                return t   # nothing can be funded: no decision for the model to make
            self.llm.run("budget", year, SYSTEM,
                         f"Year {year}. Call list_candidates, fund what is worth funding within the money left, and reject the "
                         f"notable ones you pass over." + retry_note(err),
                         t.specs(), t.handlers)
            if not t.funded and not t.rejected:
                raise StepFailed("no candidate was funded or rejected" + (f" ({t.errors} tool errors)" if t.errors else ""))
            return t

        t = attempt_then_fallback(self.llm, "budget", year, "allocate", attempt, lambda: None)
        if t is None:
            return super().allocate(props, year, mode)
        chosen = [t.cands[i] for i in t.funded]
        assert sum(c["cost"] for c in chosen) <= spendable + 1e-6, "budget cap violated"
        notes = {}
        for cid, why in list(t.rejected.items()) + list(t.funded.items()):
            for m in t.cands[cid]["members"]:
                if cid in t.funded or m["proposal_id"] not in notes:
                    notes[m["proposal_id"]] = why
        return self._decisions(props, chosen, spendable, notes)
