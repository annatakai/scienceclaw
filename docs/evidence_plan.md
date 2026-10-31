# Evidence Plan: backing our numbers (v0.1, Oct 31, 2026)

Goal: every number on a slide is one of three things, and the slide says which: **Sourced** (a document we can cite), **Calibrated** (fit to real data we can name), or **Simulated assumption** (shown with the range we tested). Nothing else goes on a slide.

Companion to `assumptions_register.md`. The register lists what is unsourced; this file says how to fix each item and in what order, given about 20 working hours.

## 1. Priority order (highest effect on results first)

| # | Number | Why it matters | Cheapest way to back it | Fallback |
|---|---|---|---|---|
| 1 | Trench cost per opening ($50,000) and dig penalty (lambda) | These create the bundling savings, our headline | Find 3-5 real street-opening and restoration unit costs (bid tabs, BWSC or Boston contract awards, other cities' utility cut fees). Find a pavement-cut study that supports a lambda range, and cite it. | Keep as ASSUMPTION, show result across the full range, say so |
| 2 | N_target (city-wide breaks per year) | Sets how large risk removed looks | BWSC reports just over 35 failures per year (budget_agent_reference.md). Divide by Boston miles of main to get a rate per mile; scale to our synthetic city. Cross-check with a published break-rate survey (find and cite; verify the figure before use). | Use rate range, report both ends |
| 3 | Failure model shape (PoF weights, age curve) | Whole ranking depends on it | Fit to a real break dataset (Kitchener, Toronto, DC Water). See section 2. | Present weights as an engineering heuristic, not a fitted model |
| 4 | Worst-case failure cost ($300k social, $378k emergency) | Sets dollars per failure | Emergency repair cost from real repair or overtime figures (BWSC 2026 budget: Repair and Maintenance $16.3M, Overtime $2.65M; divide by about 35 breaks for a rough per-break order of magnitude, label it rough). | Range |
| 5 | Road user cost u0 ($0.30 per vehicle-mile) | Sets the road job's value | Find a published vehicle operating cost per mile by pavement condition (FHWA or state DOT studies). | Range; road job is already marginal at 1.04 |
| 6 | Reserve size (15%) | Affects failures paid | Replace with the 95th percentile of simulated yearly emergency cost (already proposed in register section 7). | Test 10-25% |
| 7 | Discount rate, horizon | Standard | Cite a city's or MassDOT's rate; test 3-7% | Range |

## 2. Calibration and backtest (the strongest evidence we can build in a weekend)

1. Take one real break dataset with install year, material, diameter and break dates. Check license first.
2. Split by time: fit the failure model on earlier years, score pipes at the cutoff, then check which pipes actually broke afterwards.
3. Report a **lift curve**: "the top 20% of pipes by our risk score contained X% of later breaks." Compare against age-only ranking. This directly supports the claim that risk-first beats age-first and uses real data, not our simulation.
4. Show a calibration plot (predicted vs observed breaks per bucket). If it is poor, say so and widen the bounds.
5. Keep this on a clearly separate slide from the simulated coordination result: the backtest backs the *pipe model*; the simulation shows the *coordination benefit*.

## 3. Make the simulation results credible

- Run 30-50 seeds per strategy. Report mean and a confidence interval, and use **paired** comparisons (same city and seed across strategies).
- Sensitivity sweep over items 1-7 above (one at a time, then the top three together). Show a tornado chart of dig savings against each assumption.
- Report only claims that hold across the tested ranges, in the form: "Coordination saves between X% and Y% across the range tested." If the sign flips anywhere, say where.
- Report the single-agent and central-planner baselines honestly, including cases where they match or beat the multi-agent system. State what the multi-agent version offers that they do not (private data stays local, scales across owners).
- Include a no-coordination-benefit control: set trench cost to 0 and the penalty to 0 and confirm the coordination gap disappears. This shows the savings come from the mechanism we claim, not from a bug.

## 4. External evidence for the pitch (verify each before it goes on a slide)

- Atlanta and Hartford MDC documents: coordination with paving avoids cost (already in dig-once-research-summary.md).
- COBUCS "10,000+ conflicts, $40M+ saved": city statement of unknown date. Find the original and its date, or drop it.
- Dated sources (Canadian report cards, 2013-2016 Boston water statistics, Japan 2013-14 projections, 2014 COBUCS guide): recheck for newer figures, otherwise write the year on the slide.
- Do not state that Boston lacks coordination. BWSC's own CIP says it coordinates with paving. Our claim is cross-owner, multi-year, budget-aware coordination with written reasons.

## 5. Traceability (small, mostly mechanical)

- Add a `source` field next to every value in `config.yaml` (URL or "ASSUMPTION"), and have the experiment runner write the config snapshot next to every results CSV.
- Keep one **claims ledger**: each slide number, its status (Sourced, Calibrated, Simulated), the file or URL, and the date checked. Review it once before the pitch.
- Every chart carries "Simulated" in the title or footer unless it comes from the backtest.

## 6. Suggested time budget

1. 1.5 h: unit costs and break rate (items 1, 2, 4, 5) from documents.
2. 2 h: backtest on one real dataset (section 2).
3. 1 h: sensitivity sweep and seeds (section 3), run in the background while building the demo.
4. 0.5 h: claims ledger and slide labels.

If time runs out, drop in this order: calibration plot, item 5, item 4. Keep item 1 and the backtest lift curve.
