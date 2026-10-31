# Return Formula (v0.1)

Goal: one number the budget agent can use to compare a pipe job, a road job, and a combined job in the same units.

**Return = present value of expected dollar loss removed, divided by gross cost.**

All dollars are simulated. The pipe agent's scores are heuristic indices, not probabilities, so the conversion to dollars (section 2) is an explicit, labeled model with calibration assumptions. Dollar results are model outputs under stated assumptions, not predictions.

## 1. Notation

| Symbol | Meaning |
|---|---|
| `r`, `d(t)` | discount rate; `d(t) = 1 / (1 + r)^t` |
| `H` | benefit horizon in years (treatment life, capped at the simulation horizon) |
| `g` | cost inflation per year (`cost_inflation`, 0.07) |
| `T` | trench (street opening) cost, paid once per opening (`costs.dig_fixed`) |
| `a` | action: `replace_pipe`, `reline_pipe`, `repave`, `preserve_road`, `reconstruct_road`, or `defer` |

## 2. Pipe agent: from indices to dollars

The pipe agent returns `PoF_index` and the factor scores (age, material, breaks, soil, condition; customers, facilities, flood, traffic, economic), each 0 to 100. It never returns dollars. The budget agent (via `sim/costs.py`) converts:

**2.1 Failure probability for year t**

```
p_i(t) = min(1, C * PoF_i(t) / 100)
C      = N_target / sum_over_all_pipes( PoF_i / 100 )
```

`C` is a calibration scale chosen so the expected number of breaks across the whole city equals a target (`N_target`) taken from a published or public break rate. This keeps the index relative but anchors the total. `N_target` is an ASSUMPTION until calibrated to a real dataset. `PoF_i(t)` is the pipe agent's scoring function evaluated with age + t.

**2.2 Consequence in dollars.** To avoid double counting, drop the traffic and economic components from the pipe's consequence (the road agent and the repair cost model own those) and renormalize:

```
CoF'_i = (0.35*Customers + 0.30*Facilities + 0.15*Flood) / 0.80        # 0-100
F_i    = emergency_multiplier * W_pipe_i  +  (CoF'_i / 100) * C_social_max
```

`W_pipe_i` is the planned pipe work cost; the first term is the emergency repair cost if it fails. `C_social_max` is the dollar cost of a worst-case failure (ASSUMPTION).

**2.3 Expected annual loss:** `EL_i(t) = p_i(t) * F_i`

## 3. Pipe benefit of an action

```
B_pipe(a) = sum_{t=0}^{H_a - 1}  d(t) * [ EL_before(t) - EL_after_a(t) ]
```

- `EL_before(t)`: do nothing; the pipe keeps aging (PoF with age + t).
- `replace_pipe`: after the job, age = 0, break history reset, condition reset.
- `reline_pipe`: effective age = (1 - rho) * age, where `rho` is the share of age removed (ASSUMPTION); treatment life `H_reline` is shorter than `H_replace`.
- `defer` (same job next year): costs multiplied by `(1 + g)`, and one year of benefit is lost while the pipe keeps aging.

## 4. Road benefit of an action

Road condition uses the PCR model (traffic loading, overlaid-flexible equation, per-road calibration), not a failure probability. Convert condition to dollars through road user cost:

```
VMT       = ADT * 365 * length_miles                     # vehicle-miles per year (grow with traffic growth)
u(PCR)    = u0 * ((100 - PCR) / 100)^2                   # extra user cost per vehicle-mile; u0 is an ASSUMPTION
B_user(a) = sum_t d(t) * VMT * [ u(PCR_before(t)) - u(PCR_after_a(t)) ]
```

Optional (v2): a need-by term. If doing nothing pushes PCR to `P_min` in year `t*`, acting early avoids a costlier reconstruction later:

```
B_need = d(t*) * max(0, C_reconstruct - C_preserve)
```

Use v1 (user cost only) first; test sensitivity to `u0`.

## 5. Cost side

```
T        = dig_fixed                                     # once per opening
W_pipe   = pipe_per_ft * length * (1+g)^years_deferred
W_road   = repave_per_ft * length * (1+g)^years_deferred
lost_years = max(0, lambda * (L - a_street))             # a_street = years since last paved or overlaid
Penalty  = W_road * lost_years / L                       # only if the pipe is dug and the road is NOT resurfaced in the same job
```

`lambda` is the fraction of pavement life lost per cut, `L` is the resurfacing cycle in years.

Gross cost of each option (this is what the return uses):

```
pipe alone : T + W_pipe + Penalty
road alone : T + W_road
bundle     : T + W_pipe + W_road                          # one opening, no penalty
```

Net cost after financing (reporting, after the source is chosen): `gross * f_source`, where `f_source` = present value of repayments per dollar borrowed. At a 4% discount rate: interest-free 10-year loan 0.811, SRF loan (2%, 25 years) 0.800, bonds at 4% 1.0, rate revenue (cash) 1.0. Rank on gross cost, then assign sources, so the ranking does not depend on the source choice.

## 6. Return and decisions

```
return = B / gross_cost            NPV = B - gross_cost
```

1. **Choose among options on the same asset by NPV, not by ratio.** A bundle beats funding the jobs separately when `NPV_bundle > NPV_pipe_alone + NPV_road_alone`. The difference equals the shared savings (the trench cost counted once plus the avoided penalty).
2. **Check add-ons at the margin.** Inside a bundle, the road job's marginal return is `B_road / W_road`. Keep the add-on only if its marginal return is at least `min_return_per_dollar`.
3. **When the budget binds, rank candidates by return** (ratio) and fund from the top. Tier 1 urgency is funded first, up to `urgent_cap_fraction`.
4. **Uncertainty:** recompute with the pipe agent's lower and upper PoF bounds to get `return_lo` and `return_hi`. Rank on the midpoint, and flag any candidate where `return_lo < hurdle <= return_hi` for engineering review. Never treat a missing value as zero risk.

Note on bundles: a bundle's overall ratio can be lower than the pipe job alone (it adds a lower-return road job). That is fine; the bundle still wins on NPV and makes the road job pay for itself.

## 7. Who computes what (no double counting)

| Quantity | Owner |
|---|---|
| PoF index, factor scores, uncertainty bounds, `W_pipe` | Pipe agent |
| PCR trajectory, `W_road`, `a_street`, `lambda`, `L` | Road agent |
| `T`, `Penalty`, dollar conversion (`C`, `F_i`), `B`, return, NPV, financing | Budget agent / `sim/costs.py` |

The pipe and road agents report their own work cost only. They do not include the trench or the penalty. The pipe consequence excludes traffic and direct-cost components because the road agent and the cost model already cover them.

## 8. Worked example (from `return_example.py`; illustrative numbers)

One 420 ft segment: 70-index cast iron main, street age 12, PCR about 66, 12,000 vehicles a day.

| Option | Benefit (PV) | Gross cost | Return | NPV |
|---|---|---|---|---|
| Pipe alone | $515,484 | $179,024 | 2.88 | $336,460 |
| Road alone | $104,235 | $100,400 | 1.04 | $3,835 |
| Bundle (one dig) | $619,720 | $226,400 | 2.74 | $393,320 |

- Separate NPV: $340,296. Bundle NPV: $393,320. The $53,024 difference is the shared trench cost plus the avoided penalty.
- The road job alone barely clears a 1.0 hurdle (1.04); inside the bundle its marginal return is 2.07.
- Dollars per pipe failure `F` = $678,000 (emergency repair $378,000 plus social cost $300,000).

## 9. Assumptions to calibrate (each needs a source or the word ASSUMPTION)

`N_target` (breaks per year for the whole city), `C_social_max`, `rho`, `u0`, `lambda` (literature range roughly 0.06 to 0.6), `L`, `H_replace`, `H_reline`, `P_min`, the uncertainty bounds, and the PoF drift rates. Run results across a range of each, and report conclusions that hold across the range.

## 10. Changes needed in `interfaces.md`

- Proposals carry `work_cost`, `benefit_usd` (replacing `risk_removed_usd`), and the inputs used (`pof_before`, `pof_after`, `pcr_before`, `pcr_after`), plus `return_lo` and `return_hi`.
- `cost_alone` and `cost_if_combined` are computed by `sim/costs.py` from the formulas above, not by the agents.
- Add the config values in section 9.
