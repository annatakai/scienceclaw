# Assumptions Register (v0.1, Oct 31, 2026)

Status tags: **Sourced** = comes from a document we read. **Assumption** = a placeholder we chose; needs a source or a sensitivity test. **Decision** = a design choice the team made. **Unknown** = we don't know yet.

All simulation numbers are simulated. This register is the place to record where each number came from.

## 1. Scope and design (Decisions)

| # | Item | Current choice |
|---|---|---|
| 1 | Asset scope v1 | Water distribution mains and roads only. Sewer, gas, bridges, metro are "later." |
| 2 | City model | One segment = one pipe + one road. 150 segments, 10 years, yearly steps. Generated grid first; real Boston streets optional. |
| 3 | Agents | Pipe, road, budget. Each sees only its own data plus the shared board. |
| 4 | Coordination | Two board rounds per year; one budget revision round; each agent submits up to 15 proposals (a menu, with alternatives). |
| 5 | Budget agent | Funds, rejects, and explains. Never creates proposals. Rule-based in code; Claude only writes explanations. |
| 6 | Experiments | Rule-based agents for many runs; Claude-driven agents for the demo and a small comparison. |
| 7 | Comparison | age-first, risk-first, isolated agents (fixed department budgets), coordinated agents, central planner, single agent, plus an ablation without the budget agent. |

## 2. Money and cost numbers (config.yaml)

| Item | Value | Status |
|---|---|---|
| Annual capital budget | $600,000 | Assumption |
| Reserve held back | 15% (test 10% to 25%) | Assumption. BWSC's 2026 budget has no dedicated emergency-repair reserve (see section 7 below). |
| Street opening (trench) cost | $50,000 per opening | Assumption |
| Pipe work | $300 per ft | Assumption |
| Repaving | $120 per ft | Assumption |
| Emergency repair multiplier | 3.0 | Assumption |
| Paving protection period | 5 years | Supported by Boston's "guaranteed street" (paved within 5 years). Modeled as a cost penalty (0.5), which is an Assumption; Boston actually blocks the permit. |
| Discount rate | 4% | Assumption |
| Cost inflation | 7% per year | Sourced: MassDOT FY27-31 CIP p.58 (asphalt +40% over five years). |
| Return hurdle | 1.0 | Assumption |
| Urgent threshold | 0.9 | Assumption |
| Urgency full-scale probability | 0.30 | Assumption |
| Critical facility urgency multiplier | 1.25 | Assumption |
| Tier 1 spending cap | 50% of spendable | Assumption |
| Fixed department split (baseline only) | pipe 60 / road 40 | Assumption |
| Fixtures and soft costs | Not yet modeled (idea: 25% multiplier in v1) | Unknown |

## 3. Funding sources

| Item | Value | Status |
|---|---|---|
| Funding mix (water program) | bonds 29.3%, rate revenue 30.3%, interest-free loan 21.1%, state loan 19.3% | Sourced: BWSC 2024-2026 CIP Table 11 |
| Interest-free loan | 10-year repayment | Sourced: BWSC CIP p.18 |
| State loan | below-market, 20 to 30 years; we use 2% and 25 years | Term Sourced; rate Assumption |
| Bonds | 4%, 20 years | Assumption |
| Rate revenue pays for renewal and replacement work | yes | Sourced: BWSC CIP p.17 |
| Pay from cheapest source first | yes | Decision |
| v1 uses two sources only (rate revenue, bonds) | optional | Decision |

## 4. Pipe agent (team spec)

| Item | Value | Status |
|---|---|---|
| PoF weights | age 20, material 20, breaks per km-year 25, soil 15, condition 20 | Assumption (team's own; not attributed to BWSC) |
| CoF weights | customers 35, facilities 30, flood 15, traffic 10, economic 10 | Assumption |
| Risk classes | Critical 75+, High 50-74.99, Moderate 25-49.99, Low below 25 | Assumption |
| Scores are heuristic indices, not probabilities | yes | Decision |
| Component thresholds and mappings | in `pipe_agent.py` | Defined in code |

## 5. Return formula

| Item | Status |
|---|---|
| Probability scale `C` set so total expected breaks match a target | Decision; target `N_target` is an Assumption |
| Worst-case social cost of a failure ($500,000 in the example) | Assumption |
| Consequence for dollars drops traffic and economic components and renormalizes | Decision (avoids double counting) |
| Road user cost: `u0 = $0.30` per vehicle-mile at worst condition, quadratic in condition | Assumption |
| Road condition model (traffic loading, PCR equations, per-road calibration) | Sourced: MassDOT report (provided by the team); `P_min` not yet chosen |
| Dig penalty: `lost_years = lambda x (L - a)` | Team's own derivation; `lambda` range 0.06 to 0.6 from the literature (as stated by the team); example uses 0.3 |
| Resurfacing cycle `L` = 15 years | Assumption (example) |
| Reline: share of age removed, treatment life | Assumption (not set) |
| Benefit horizon `H` = 10 years in the example | Assumption |
| Option choice by net value; ranking by ratio when budget binds | Decision |
| Financing factors (0.811, 0.800, 1.0) | Computed from the loan assumptions above |

## 6. Data

| Item | Status |
|---|---|
| Break datasets (Kitchener, Toronto, DC Water) will let us calibrate failure rates | Unknown: fields and licenses not checked |
| Boston pipe GIS is not public | Unverified |
| Gas and sewer data are not public, so they are simulated or omitted | Assumption |
| City table values (ages, materials, traffic) | Synthetic |

## 7. What the 2026 BWSC budget says about reserves (Sourced: BWSC 2026 budget, pp.98-101 and fund table)

Projected year-end 2026 balances:

| Fund | Balance | Purpose |
|---|---|---|
| Stabilization | $138.2M | Limits rate impact of extraordinary cost increases (for example MWRA charges) |
| Operating Reserve | $63.2M | Requirement: one-sixth (two months) of operating expenses and MWRA charges |
| Senior Debt Service Reserve | $50.5M cash (plus a $7.2M surety policy) | Bond security |
| MWRA Assessment Fund | $21.6M | Payment account for MWRA charges, not a reserve |
| Renewal and Replacement Reserve | $12.2M | Extra money for R&R projects; requirement is 25% of budgeted R&R spending; fully funded |
| Insurance Reserve | $7.7M | Damage claims over $10,000 |
| General | $2.9M | Held for a state trust obligation |

- No fund is described as a dedicated emergency water-main repair reserve.
- Reserve withdrawals are small and are transfers of interest income to the revenue fund (for example operating reserve $1.7M and R&R reserve $0.3M in 2026), not repair spending.
- Emergency repair costs are generally not capitalized, so they sit in the operating budget: Repair and Maintenance budgeted at $16.3M for 2026 ($14.6M in 2025), and Overtime (which covers emergencies such as main breaks) budgeted at $2.65M for 2026 after $4.0M in 2025 (unaudited).
- The 2026 budget totals about $501.0M. The 2026-2028 CIP is $389.6M, with $135.3M (34.7%) from bonds.
- Implication: replace the fixed 15% reserve with a reserve sized from the simulation (for example the 95th-percentile yearly emergency repair cost).

## 8. Business and pitch

| Item | Status |
|---|---|
| Customers are municipalities, prefectures, utilities; Japan and Canada are later markets | Assumption |
| Investability about 5.5 of 10, ceiling about 7 | My judgment, not an investor's view |
| COBUCS (Boston) records and clears plans but does not prioritize, budget, or compare utilities | Based on the 2014 user guide only; COBUCS 2.0 may differ |
| COBUCS savings claim (10,000+ conflicts, $40M+) | City statement of unknown date; verify |
| Prize terms, eligibility, and what the sponsors provide | Unknown |
| Fifth judging criterion (weights shown sum to 90%) | Unknown |
| Team size and skills | Unknown |
| Deadline Sunday 1 pm; about 20 to 22 working hours after sleep | Estimate |

## 9. Source dates to recheck before the pitch

Canadian infrastructure report cards (2012 to 2019), Boston water statistics (2013, 2016), Japan inspection figures (2013 to 2014 projections), and the COBUCS guide (2014).

## 10. The assumptions that move results most (test these first)

1. Trench cost and dig penalty (they create the bundling savings).
2. Break target `N_target` and worst-case failure cost (they set how big risk removed looks).
3. Road user cost `u0` (it sets the road job's value).
4. Reserve size.
5. Discount rate and benefit horizon.
Report only conclusions that hold across a range of each.
