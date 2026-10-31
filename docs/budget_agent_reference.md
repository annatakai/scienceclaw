# Budget Agent Reference: what two real CIPs teach us

Sources (both uploaded by the team):
- **BWSC** = Boston Water and Sewer Commission, Capital Improvement Program 2024-2026 (Nov 2023). Page numbers below are the printed page numbers.
- **MassDOT** = FY2027-2031 Capital Investment Plan (final, approved June 17, 2026).

All dollar figures from these documents are real. Everything in our simulation built from them is still simulated.

## 1. BWSC CIP 2024-2026 (Boston water and sewer)

**Size and structure (pp.3-4, 19)**
- Three-year program, $318.0M total: Water $99.3M (31.3%), Sewer $118.0M (37.1%), Support $39.9M (12.5%), Stormwater $60.7M (19.1%).
- Reported as annual cash flow by category and by funding source (Table 11). We copy this format for our CIP export.

**Five funding sources (pp.4, 17-19)**
| Source | Share of CIP | Notes |
|---|---|---|
| Commission bonds | 36.6% | Primary source |
| Rate revenue | 35.2% | Pays for renewal and replacement (R&R): main relining, same-size main replacement, sewer rehab |
| State Revolving Fund (SRF) | 15.0% | Below-market loans, typically 20-30 years |
| MWRA water assistance (LWSAP) | 6.6% | Interest-free loans, repaid over 10 years; about $5.3M per year allocated to BWSC |
| MWRA I/I assistance | 6.6% | Sewer-side program |

**Water program only (Table 11, p.19), used as our default `funding_mix`:** bonds $29.1M (29.3%), rate revenue $30.1M (30.3%), LWSAP $21.0M (21.1%), SRF $19.1M (19.3%).

**How water mains are selected (pp.8, 34)**
- Risk-based: probability of failure x consequence of failure (examples given: hospital flooding, critical customers without water).
- Highest ranking first. Pipes near other selected pipes are grouped into geographic contracts.
- Inputs: the 2016 pipe ranking system update, main breaks, customer complaints, maintenance records, pressure and fire-flow tests, machine learning software, and construction planned by other agencies.
- All street excavations are coordinated with City and State paving programs. If the city plans to resurface a road within a few years, BWSC tries to replace the old main first.
- Sewer and drain pipes in those streets are inspected and fixed in the same project; the CIP says this "avoids disruption of the streets and saves project costs" (p.33).

**Program pace (pp.6, 8, 33)**
- Originally 17 miles of water pipe per year. A study recommended 11 miles per year through 2030; the 2016 update recommended 8 miles per year. 7.1 miles are scheduled for 2024.
- Since 1978: 394.1 miles of mains replaced and 282.2 miles cleaned and lined.
- Average of just over 35 water pipe failures per year.
- Stated financial approach: conservative projections, adequate reserves, a balance between debt and rate funding (pp.2-3).

## 2. MassDOT FY27-31 CIP (state roads, bridges, transit)

- About $20.7B over five years (letter, p.3). Funded by federal, state (bonds, grant anticipation notes, Fair Share revenue), MassDOT tolls, and other sources (pp.37-39).
- **Process (pp.34-36):** starts the fall before; identifies needs and priorities; reviews available funds; sets program sizes using scoring rubrics or asset management systems plus project readiness; coordinates with the state finance office on the bond cap; 21-day public review; board approval. This is a good model for our yearly loop.
- **Bond cap (p.38):** the state sets an annual administrative limit on bond-funded capital spending to keep debt manageable. Our `annual_capital_budget` plays the same role.
- **Chapter 90 (pp.8, 39, 47):** the state's grant program that funds municipal roadway projects. About $1.4B in this CIP. It is the realistic funding source for the road agent's city roads.
- **Pavement (pp.58-59):** low-cost treatments applied at the right time extend useful life and lower lifetime cost. Asphalt cost rose 40% over five years while spending stayed flat, and the share of Interstate pavement in good condition fell about 12% to 80% against an 88% target. We use this for `cost_inflation` (about 7% per year) and for the road agent's preservation-vs-reconstruction logic.
- Scope note: this plan is for state-owned roads, bridges, and transit. It frames the funding categories; it does not give local pipe or road scoring.

## 3. What changes in our design

1. **Real funding sources.** The budget agent allocates funded work across bonds, rate revenue, an interest-free loan, and an SRF-style loan, cheapest eligible source first. (Added to `interfaces.md`.)
2. **Eligibility rules.** Rate revenue pays for renewal and replacement work (same-size replacement, repaving), per BWSC.
3. **CIP table export** grouped by year and funding source, like BWSC Table 11. (Added.)
4. **Inflation** in costs over time. (Added.)
5. **A program-pace policy** is optional: BWSC targets about 8 miles per year for Boston. Scale to our city size if we want a pace constraint.

## 4. What this does to our pitch (be honest about it)

- **Good news:** BWSC's own CIP describes exactly our approach (risk = likelihood x consequence, grouped contracts, coordinating excavations with paving). That confirms the method is credible.
- **Hard news:** it also means Boston's utility already coordinates with the city's paving program. We cannot say nobody coordinates. Our edge is doing it across all owners (water, sewer, gas, roads, transit), across multiple years, with funding choices, automatically and with written reasons, instead of by a few engineers and phone calls.
- **Caution:** BWSC plans are shaped by a consent decree, sewer separation, and water quality rules we are not modeling. Do not claim our simulation reproduces BWSC's plan.
