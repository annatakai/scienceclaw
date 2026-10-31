# Interfaces and Structure (v0.2)

This file is the contract. If you change a field name or a function signature, tell the team first and edit this file in the same commit.

All data is **simulated**. Label every chart and slide that way.

## 1. Repo structure

```
project/
  README.md
  CLAUDE.md                 # project context for Claude Code (paste goals, rubric, rules)
  config.yaml               # all numbers and assumptions in one place
  contract/                 # OWNER: pipes person. Enums, ID helpers, schemas, validate(). Everyone imports it; nobody redefines it.
  docs/
    interfaces.md           # this file
    references/             # reference files the agents load (see section 10)
  sim/                      # OWNER: roads person
    city.py                 # City class, load_city(), view_for(), apply()
    failures.py             # yearly failure draws (uses pipe failure model)
    costs.py                # price(): the ONLY place dollars are computed (dig cost sharing, moratorium, emergency multiplier, index-to-dollar conversion, urgency, returns)
    metrics.py              # record() and summarize()
  agents/
    base.py                 # Agent base class, Board, message helpers   (OWNER: pipes person)
    pipe_agent.py           # OWNER: pipes person
    road_agent.py           # OWNER: roads person
    budget_agent.py         # OWNER: budget person
    llm.py                  # the Claude tool-use loop (copy of toy_agent pattern)  (OWNER: pipes person)
    rules.py                # rule-based versions of each agent, for fast experiments
  baselines/
    age_first.py            # OWNER: pipes person
    risk_first.py           # OWNER: pipes person
    central_planner.py      # OWNER: budget person
    single_agent.py         # OWNER: pipes person (after the board is done)
  experiments/
    run_all.py              # OWNER: budget person
    results/                # csv outputs, one file per experiment
  demo/
    app.py                  # map replay with a year slider  (OWNER: roads person)
  traces/                   # jsonl logs of every message and tool call
  tests/
```

## 2. Units and conventions

- Money is **simulated US dollars**, integers.
- Years are integers (2026, 2027, ...). Simulation starts at `config.start_year`.
- Probabilities are floats from 0 to 1.
- **Risk = expected loss in dollars next year** = probability of failure x consequence in dollars. Higher is worse.
- Every random draw uses `config.seed` so runs repeat exactly.
- Python 3.11, type hints on function signatures, snake_case names.
- Keep the math in code, never in the language model. Agents decide and explain; functions calculate.
- API keys live in environment variables. Never commit them.

## 3. The city table

One record per street segment. Each segment has one pipe and one road.

```json
{
  "segment_id": "S041",
  "street": "Example St",
  "neighborhood": "Example Neighborhood",
  "length_ft": 420,
  "x": 12,
  "y": 7,
  "pipe": {
    "asset_id": "P041",
    "owner": "pipe",
    "install_year": 1925,
    "material": "cast_iron",
    "diameter_in": 12,
    "break_years": [2011, 2016, 2022],
    "soil_corrosivity": 0.7
  },
  "road": {
    "asset_id": "R041",
    "owner": "road",
    "last_paved_year": 2012,
    "road_class": "arterial",
    "daily_traffic": 12000
  },
  "consequence": {
    "critical_facility_nearby": true,
    "customers_served": 340
  }
}
```

Allowed values:
- `material`: `cast_iron`, `ductile_iron`, `pvc`, `steel`
- `road_class`: `arterial`, `collector`, `local`
- `owner`: `pipe`, `road` (add `gas`, `sewer` later)

## 4. Config (`config.yaml`)

Every number the simulator or an agent uses lives here, with the source or the word ASSUMPTION next to it.

```yaml
seed: 42
start_year: 2026
horizon_years: 10
n_segments: 150
annual_capital_budget: 600000   # ASSUMPTION
reserve_fraction: 0.15          # ASSUMPTION: held back for emergency repairs. For comparison, BWSC's Renewal and Replacement Reserve Fund must be at least 25% of budgeted R&R spending (BWSC 2023 budget, pp.24-26); that is a fund balance, not a yearly set-aside. Test 0.10 to 0.25.
urgency_full_prob: 0.30         # ASSUMPTION: a pipe with this yearly failure probability or higher scores urgency 1.0
critical_facility_multiplier: 1.25   # ASSUMPTION: urgency boost when a hospital or other critical customer is affected
urgent_cap_fraction: 0.5        # ASSUMPTION: Tier 1 work may use at most this share of the spendable amount
costs:
  dig_fixed: 50000              # ASSUMPTION: cost to open one street segment, paid once per opening
  pipe_per_ft: 300              # ASSUMPTION
  repave_per_ft: 120            # ASSUMPTION
  emergency_multiplier: 3.0     # ASSUMPTION: a failure repair costs more than a planned one
  paving_moratorium_years: 5    # ASSUMPTION: penalty for digging a street paved within this many years
  moratorium_penalty: 0.5       # ASSUMPTION: extra fraction of repave cost when violated
discount_rate: 0.04             # ASSUMPTION
max_proposals_per_agent: 15     # ASSUMPTION: size of each agent's yearly menu
department_split: {pipe: 0.6, road: 0.4}   # ASSUMPTION: fixed budget shares used ONLY by the isolated_agents baseline
min_return_per_dollar: 1.0      # ASSUMPTION: hurdle; below this a proposal is rejected
urgent_override: 0.9            # ASSUMPTION: urgency above this can be funded below the hurdle
cost_inflation: 0.07            # per year; MassDOT FY27-31 CIP p.58: asphalt +40% over 5 years (about 7%/yr compounded)
funding_mix:                    # share of annual_capital_budget by source; default = BWSC 2024-2026 CIP water program, Table 11 (p.19). v1 may collapse to two sources (rate_revenue and bonds) by setting the others to 0.
  bonds: 0.293
  rate_revenue: 0.303
  interest_free_loan: 0.211
  srf_loan: 0.193
loan_terms:
  bonds: {rate: 0.04, years: 20}              # ASSUMPTION
  interest_free_loan: {rate: 0.0, years: 10}  # BWSC CIP p.18: MWRA LWSAP, interest-free, repaid over 10 years
  srf_loan: {rate: 0.02, years: 25}           # BWSC CIP p.18: "below-market", 20-30 years; rate is an ASSUMPTION
rate_revenue_eligible_work: [replace_pipe, repave]   # BWSC CIP p.17: renewal and replacement funded from rate revenue
```

## 5. Proposal (what an agent asks to fund)

```json
{
  "contract_version": "0.2",
  "proposal_id": "pipe-2027-S041",
  "agent": "pipe",
  "segment_id": "S041",
  "year": 2027,
  "work": "replace_pipe",
  "work_cost": 126000,
  "combinable_with": ["road"],
  "exclusive_group": "pipe-S041",
  "bundle_id": null,
  "pipe": {
    "pof_before": [70.0, 71.0, 72.0, 73.0, 74.0, 75.0, 76.0, 77.0, 78.0, 79.0],
    "pof_after": [12.0, 12.5, 13.0, 13.5, 14.0, 14.5, 15.0, 15.5, 16.0, 16.5],
    "pof_lo": [64.0, 65.0, 66.0, 67.0, 68.0, 69.0, 70.0, 71.0, 72.0, 73.0],
    "pof_hi": [76.0, 77.0, 78.0, 79.0, 80.0, 81.0, 82.0, 83.0, 84.0, 85.0],
    "cof_prime": 60.0,
    "length_ft": 420
  },
  "road": null,
  "rationale": "Cast iron from 1925, three prior breaks, serves a critical facility.",
  "priced": null
}
```

A road proposal fills `"road"` instead of `"pipe"` (and leaves `"pipe": null`):

```json
{
  "road": {
    "pcr_before": [66.0, 64.7, 63.3, 62.0, 60.7, 59.3, 58.0, 56.7, 55.4, 54.0],
    "pcr_after": [86.0, 84.7, 83.3, 82.0, 80.7, 79.3, 78.0, 76.7, 75.4, 74.0],
    "adt": 12000,
    "length_ft": 420,
    "street_age": 12
  }
}
```

The arrays have one value per year from the proposal year (`t = 0`) for `horizon_years` entries (10 by default). Unknown values are `null`, never `0`.

**The `priced` block** is filled by `sim/costs.py` (`price()`), never by the pipe or road agent. It is `null` when an agent posts a proposal.

```json
{
  "priced": {
    "urgency": 0.8,
    "cost_alone": 179024,
    "cost_if_combined": 126000,
    "benefit_usd": 515484,
    "benefit_usd_lo": 440000,
    "benefit_usd_hi": 590000,
    "return_alone": 2.88,
    "return_lo": 2.46,
    "return_hi": 3.30
  }
}
```

`work` is one of: `replace_pipe`, `reline_pipe` (cheaper, shorter life), `repave`, `preserve_road` (cheap treatment applied at the right time), `reconstruct_road`.

**Agents submit a menu, not one pick.** Each agent submits up to `max_proposals_per_agent` proposals per year, ranked by its own view, and includes cheaper or later alternatives for the same asset (for example reline instead of replace, or the same job a year later at a higher cost and risk). Proposals for the same asset share an `exclusive_group`; the budget agent funds at most one proposal per group. Agents do not self-censor to fit the budget. They never see the budget agent's remaining money, only the going return hurdle it posts after each round. The budget agent exists to choose among these options.

**Who fills what.** The pipe and road agents provide only their own quantities: `work_cost` (the work itself, with no trench cost and no dig penalty), the pipe index trajectories or road PCR trajectories, and a rationale. `sim/costs.py` then adds the trench cost, the dig penalty, the index-to-dollar conversion, the urgency, and the returns (see `return_formula.md`). In the `priced` block, `cost_alone` includes the full dig cost (`costs.dig_fixed`); `cost_if_combined` is the cost of the work itself with **no dig cost**, used when this proposal shares a dig with another proposal on the same segment and year (`null` if it cannot combine).

### Urgency tiers (computed by `sim/costs.py`, never by an agent or the language model)

`urgency` (0 to 1) = min(1.0, `p_fail_next_year` / `urgency_full_prob`) x (`critical_facility_multiplier` if a critical facility is affected, else 1.0), capped at 1.0. Roads have no failure probability, so road urgency follows a separate rule (see Open decisions).

| Tier | Name | Urgency | Meaning |
|---|---|---|---|
| 1 | Urgent ("first urgency") | 0.9 or higher | Likely to fail this year, or a critical customer is at risk. Funded first. |
| 2 | Soon | 0.6 to 0.9 | Fix within 1 to 3 years; best bundled with other work. |
| 3 | Plan | 0.3 to 0.6 | Schedule with paving or other planned work. |
| 4 | Monitor | below 0.3 | No action; keep watching. |

Tier 1 is the same threshold as `urgent_override`. The four-tier idea mirrors Japan's inspection grading, where the worst grade requires urgent safety measures.

`bundle_id` is `null` until round 2. When two agents agree to share a dig, both set the same `bundle_id` (for example `B-2027-S041`). The budget agent funds a bundle as one unit: bundle cost = `dig_fixed` once + the sum of each member's `cost_if_combined`.

## 6. Board messages

The board is a list of messages. Agents read it and post to it. It is the only channel between agents.

```json
{
  "msg_id": 17,
  "year": 2027,
  "round": 1,
  "from": "pipe",
  "type": "post_plan",
  "segment_id": "S041",
  "payload": {"proposal_id": "pipe-2027-S041"},
  "text": "I plan to replace the main on S041 in 2027."
}
```

`type` is one of: `post_plan`, `join_request`, `accept`, `decline`, `revise`, `hurdle`, `funding_decision`.
`round` is 1 or 2, and every year has exactly two rounds (no "done" message). Round 1: agents post plans. Then the board posts one `hurdle` message (the going return threshold; agents never see the remaining budget). Round 2: agents combine or revise. Then the budget agent posts its `funding_decision` messages.
`msg_id` is assigned by the Board, never by an agent.

## 7. Funding decision (budget agent output)

```json
{
  "proposal_id": "pipe-2027-S041",
  "bundle_id": "B-2027-S041",
  "funded": true,
  "amount": 151000,
  "funding_source": "interest_free_loan",
  "return_per_dollar": 2.08,
  "reason": "Bundle return above threshold; pipe and road share one dig on S041."
}
```

One decision is emitted per proposal. For a bundle, every member gets the same `bundle_id`, `return_per_dollar` is the bundle's, and the dig cost is split evenly among members: `amount` = `cost_if_combined` + dig share. For a stand-alone proposal, `amount` = `cost_alone`.

When the budget agent funds something with a lower return than a rejected proposal, `reason` must say why.

### Budget agent's job (each year)

1. **Compute the spendable amount:** `annual_capital_budget` x (1 - `reserve_fraction`).
2. **Build the candidate list:** each stand-alone proposal, and each bundle treated as one unit. Fund at most one proposal per `exclusive_group` (the best-return option wins; the others are rejected with the reason "alternative funded").
3. **Compute return:** `return_per_dollar` = total `priced.benefit_usd` / total gross cost, for each candidate (formulas in `return_formula.md`; bundles use the bundle cost).
4. **Apply the hurdle:** reject candidates below `min_return_per_dollar` (config), unless urgency is above `urgent_override` (config), in which case the decision must say so.
5. **Fund Tier 1 first.** Fund Tier 1 (urgency of `urgent_override` or higher) proposals first, best return first, up to `urgent_cap_fraction` of the spendable amount. Then **fund the rest in order of return** until the next candidate does not fit. Skip it and try smaller ones. Pay each funded decision from the cheapest source with room left (interest-free loan, then SRF loan, then rate revenue, then bonds), within each source's share of the budget (`funding_mix`) and its eligibility rules. Record `funding_source` on the decision and add loan interest to the cost of ownership (`loan_terms`).
6. **Post a funding decision for every proposal**, funded or not, with a reason. Rejected proposals say what would change the answer ("combine with road work to qualify", "does not fit this year's budget").
7. **Allow one revision round:** agents may revise rejected proposals once (for example by combining) and the budget agent re-runs steps 2 to 6 on the revised set.
8. **Track the reserve:** unspent money and the reserve cover emergency repairs from unplanned failures. Report the balance in the metrics.

The budget agent never creates proposals and never tells the pipe or road agent what to propose. It only funds, rejects, and explains.

## 8. Yearly loop

```
for year in range(start_year, start_year + horizon_years):
    city.age_assets(year)
    for agent in [pipe, road]:
        view = city.view_for(agent.owner)          # private view only
        proposals += agent.propose(year, view, board)
    for p in proposals: p["priced"] = costs.price(p, config, context)   # dollars computed here only
    board round 1: agents post plans
    board posts one `hurdle` message
    board round 2: agents may join, combine, or revise (re-price any revised proposal)
    decisions = budget.allocate(proposals, year, board)
    result = city.apply(decisions)                 # applies repairs, computes dig savings
    failures = city.simulate_failures(year)        # unplanned breaks, paid from reserve
    metrics.record(year, result, failures)
metrics.summarize()
```

## 9. Function signatures

```python
# sim/city.py
def load_city(config: dict) -> City: ...
class City:
    def view_for(self, owner: str) -> dict:        # only that owner's assets, plus public facts
    def age_assets(self, year: int) -> None
    def apply(self, decisions: list[dict]) -> dict # returns cost paid, digs opened, dig savings
    def simulate_failures(self, year: int) -> list[dict]

# agents/base.py
class Agent:
    name: str
    owner: str
    def propose(self, year: int, view: dict, board: "Board") -> list[dict]
    def respond(self, year: int, round: int, board: "Board") -> list[dict]  # messages

# sim/costs.py   (the ONLY place dollars are computed)
def price(proposal: dict, config: dict, context: dict) -> dict   # returns the `priced` block

# agents/budget_agent.py
def allocate(proposals: list[dict], year: int, board: "Board") -> list[dict]

# sim/metrics.py
def record(year: int, result: dict, failures: list[dict]) -> None
def summarize() -> dict   # see section 11
```

**Decentralization rule:** an agent only ever receives `city.view_for(its own owner)` and the board. It must never read the full city table or another agent's data.

## 10. Reference files (the "engineer knowledge")

Short markdown files in `docs/references/` that the agents load. Each states the method, the source, and the rules in plain language.

- `pipe_risk_method.md` (likelihood x consequence, inputs, source)
- `road_deterioration.md` (pavement age and traffic, repaving triggers, source)
- `cost_assumptions.md` (the numbers in config.yaml and where they came from)
- `coordination_rules.md` (avoid cutting newly paved streets, combine digs)

## 11. Outputs

**Metrics summary** (`summarize()`), one dict per run:

```json
{
  "strategy": "coordinated_agents",
  "seed": 42,
  "weighted_failures": 14.2,
  "total_cost": 5120000,
  "street_openings": 61,
  "dig_savings": 740000,
  "years_over_budget": 0
}
```

`strategy` is one of: `age_first`, `risk_first`, `isolated_agents`, `coordinated_agents`, `central_planner`, `single_agent`.

Definitions: `isolated_agents` = each agent has its own fixed budget (`department_split`) and no board, like separate departments. `coordinated_agents` = shared board plus the budget agent pooling the money. The gap between them is the value of coordination plus pooled budgeting. Add an ablation `coordinated_no_budget_agent` (board only, fixed splits) to measure the budget agent's own contribution.

**Results files:** `experiments/results/<experiment_name>.csv`, one row per run, with the same columns as the summary.

**CIP table** (the demo export; modeled on the BWSC 2024-2026 CIP "Totals by Category and Funding Source" table): one row per funded decision, grouped by year, then by funding source.

```json
{"year": 2027, "category": "water", "segment_id": "S041", "work": "replace_pipe", "bundle_id": "B-2027-S041", "amount": 151000, "funding_source": "interest_free_loan", "return_per_dollar": 2.08, "rationale": "Cast iron from 1925, three prior breaks, serves a critical facility."}
```

Also output year totals by `funding_source` and the running debt service, so the budget story is visible.

**Trace files:** `traces/<strategy>_seed<seed>.jsonl`, one JSON object per line, for every board message and every tool call:

```json
{"t": 0, "year": 2027, "agent": "pipe", "kind": "tool_call", "name": "get_pipe_risk", "input": {"segment_id": "S041"}, "output": {"risk": 410000}}
```

## 12. Rules everyone follows

1. One folder per owner. Do not edit someone else's file without telling them.
2. Small commits, merge to main often, run `tests/` before merging.
3. Change a format here first, then in code.
4. Every agent decision carries a `rationale` string.
5. Every number in `config.yaml` has a source or the word ASSUMPTION.
6. Rule-based agents (`rules.py`) for experiments, Claude agents for the demo and a smaller comparison.
7. Never commit API keys.

## 13. Open decisions (fill in together)

- Road urgency: the formula above needs a road failure probability, which roads don't have. Proposed: urgency = 1.0 if current PCR is at or below `P_min`, falling linearly to 0 at PCR 85 (both ASSUMPTION). Roads person to confirm `P_min`.
- Contract owner (who edits `contract/`): default is the pipes person, who also owns the Board.
- Number of segments and years (defaults above: 150 and 10)
- Annual budget and reserve (defaults above)
- Real Boston streets or a generated grid for v1 (start with a grid)
- Which owners besides pipe and road, if any, in v1 (none)
- Project name
