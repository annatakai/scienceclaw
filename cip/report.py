"""cip/report.py  (from docs/cip_report.py, contract v0.2; build_report, to_csv, to_html and the browser events
cip:select and map:year are kept).

Turns the budget agent's funding decisions into the report a city would get: an executive summary, a ranked decision
list, totals by funding source with debt service (BWSC Table 11 style), program pace, a "needs engineering review"
section, what was not funded and what would change the answer, and a methodology page. Pure function of
(decisions, proposals, city, config): the only dollars computed here are loan repayments, which follow loan_terms.
ALL ASSET DATA IS SIMULATED and the report says so.

Inputs (cip/adapter.py builds them from the runner output)
  decisions : list[dict]  one per proposal (interfaces.md section 7)
  proposals : list[dict]  priced proposals (section 5), joined by proposal_id
  city      : dict        segment_id -> {"street": str, "neighborhood": str}
  config    : dict        loan_terms, start_year, horizon_years, ...
"""
from __future__ import annotations

import csv
import html
import io
from collections import defaultdict

SOURCE_ORDER = ["interest_free_loan", "srf_loan", "rate_revenue", "bonds"]
SOURCE_LABEL = {"interest_free_loan": "Interest-free loan", "srf_loan": "State revolving loan",
                "rate_revenue": "Rate revenue", "bonds": "Bonds"}
WORK_LABEL = {"replace_pipe": "Replace water main", "reline_pipe": "Reline water main", "repave": "Repave",
              "preserve_road": "Preserve pavement", "reconstruct_road": "Reconstruct road", "wait": "Wait a year"}
TIER_LABEL = {1: "1 Urgent", 2: "2 Soon", 3: "3 Plan", 4: "4 Monitor"}
MILES = 5280.0


def tier_of(urgency: float | None) -> int | None:
    if urgency is None:
        return None
    if urgency >= 0.9:
        return 1
    if urgency >= 0.6:
        return 2
    if urgency >= 0.3:
        return 3
    return 4


def annual_payment(principal: float, rate: float, years: int) -> float:
    """Level annual payment on a loan (rate 0 => straight-line)."""
    if rate == 0:
        return principal / years
    return principal * rate / (1 - (1 + rate) ** -years)


def build_report(decisions, proposals, city, config, baseline=None, meta=None) -> dict:
    """baseline: optional {"street_openings", "total_funded"} from the isolated run on the same seed.
    meta: optional list of dict(name, status, source, checked, range, note) for the methodology page."""
    prop = {p["proposal_id"]: p for p in proposals}
    start = config["start_year"]
    end = start + config["horizon_years"] - 1
    loans = config.get("loan_terms", {})

    rows = []
    for d in decisions:
        p = prop.get(d["proposal_id"], {})
        priced = p.get("priced") or {}
        seg = p.get("segment_id")
        info = city.get(seg, {})
        funded = bool(d["funded"])
        rows.append({
            "year": p.get("year"), "segment_id": seg, "street": info.get("street", seg),
            "neighborhood": info.get("neighborhood", ""), "agent": p.get("agent"), "work": p.get("work"),
            "work_label": WORK_LABEL.get(p.get("work"), p.get("work")), "bundle_id": d.get("bundle_id"),
            "status": "Funded" if funded else "Not funded", "amount": d["amount"] if funded else 0, "ask": d["amount"],
            "funding_source": d.get("funding_source") if funded else None,
            "net_cost": d.get("net_cost", 0) if funded else 0, "loan_interest": d.get("loan_interest", 0) if funded else 0,
            "return_per_dollar": d.get("return_per_dollar"), "return_lo": d.get("return_lo"), "return_hi": d.get("return_hi"),
            "needs_review": bool(d.get("needs_review")), "urgency": priced.get("urgency"), "tier": tier_of(priced.get("urgency")),
            "benefit_usd": priced.get("benefit_usd"), "length_ft": p.get("length_ft", 0), "dig_saving": d.get("saving_share", 0),
            "reason": d.get("reason", ""), "rationale": p.get("rationale", ""), "proposal_id": d["proposal_id"],
        })

    funded = [r for r in rows if r["status"] == "Funded"]
    funded.sort(key=lambda r: (r["year"], r["tier"] or 9, -(r["return_per_dollar"] or 0)))
    for i, r in enumerate(funded, 1):
        r["rank"] = i
    # Not funded = assets with nothing funded that year (an alternative that lost to a funded option is not a gap),
    # and never the "wait" placeholder.
    got = {(r["segment_id"], r["agent"], r["year"]) for r in funded}
    declined = [r for r in rows if r["status"] != "Funded" and r["work"] != "wait"
                and (r["segment_id"], r["agent"], r["year"]) not in got]
    best = {}
    for r in declined:     # one row per asset and year: its best-return option
        k = (r["segment_id"], r["agent"], r["year"])
        if k not in best or (r["return_per_dollar"] or 0) > (best[k]["return_per_dollar"] or 0):
            best[k] = r
    declined = sorted(best.values(), key=lambda r: (r["year"], -(r["return_per_dollar"] or 0)))

    table = defaultdict(lambda: defaultdict(int))
    net = defaultdict(float)
    for r in funded:
        table[r["year"]][r["funding_source"]] += r["amount"]
        net[r["year"]] += r["net_cost"]
    debt = {y: 0.0 for y in range(start, end + 1)}
    for r in funded:
        t = loans.get(r["funding_source"])
        if not t:
            continue                       # rate revenue is cash, no debt service
        pay = annual_payment(r["amount"], t["rate"], t["years"])
        for y in range(r["year"] + 1, min(end, r["year"] + t["years"]) + 1):
            debt[y] += pay
    by_year = []
    for y in range(start, end + 1):
        src = {s: table[y].get(s, 0) for s in SOURCE_ORDER}
        by_year.append({"year": y, "by_source": src, "total": sum(src.values()), "debt_service": round(debt[y]),
                        "net_cost_pv": round(net[y])})

    # Program pace: miles of main replaced / relined and miles repaved per year, as a share of the network.
    net_miles = (config.get("miles") or 0) or None
    pace = []
    for y in range(start, end + 1):
        m = lambda w: sum(r["length_ft"] for r in funded if r["year"] == y and r["work"] in w) / MILES
        row = {"year": y, "replaced": m(("replace_pipe",)), "relined": m(("reline_pipe",)),
               "repaved": m(("repave", "reconstruct_road")), "preserved": m(("preserve_road",))}
        if net_miles:
            row["replaced_pct"] = 100 * row["replaced"] / net_miles
            row["repaved_pct"] = 100 * row["repaved"] / net_miles
        pace.append(row)

    bundles = {r["bundle_id"] for r in funded if r["bundle_id"]}
    openings = len({(r["bundle_id"] or r["proposal_id"]) for r in funded})
    summary = {
        "funded_projects": len(funded), "total_funded": sum(r["amount"] for r in funded), "street_openings": openings,
        "shared_digs": len(bundles), "dig_savings": round(sum(r["dig_saving"] for r in funded)),
        "net_cost_pv": round(sum(net.values())), "loan_interest": round(sum(r["loan_interest"] for r in funded)),
        "needs_review": sum(1 for r in funded if r["needs_review"]), "not_funded": len(declined),
        "years": [start, end], "network_miles": net_miles, "label": "SIMULATED DATA",
    }
    if baseline:
        summary["isolated_street_openings"] = baseline["street_openings"]
        summary["isolated_total_funded"] = baseline["total_funded"]
        summary["isolated_funded_projects"] = baseline.get("funded_projects")
    review = sorted([r for r in funded + declined if r["needs_review"]], key=lambda r: (r["year"], -(r["return_per_dollar"] or 0)))
    return {"summary": summary, "by_year": by_year, "pace": pace, "funded": funded, "not_funded": declined,
            "review": review, "reserve": config.get("reserve", []), "methodology": meta or [], "label": "SIMULATED DATA"}


CSV_COLS = ["rank", "year", "segment_id", "street", "work_label", "bundle_id", "tier", "amount", "funding_source",
            "return_per_dollar", "rationale"]


def to_csv(report) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_COLS)
    for r in report["funded"]:
        w.writerow([r.get(c) for c in CSV_COLS])
    return buf.getvalue()


def funding_csv(report) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["year"] + SOURCE_ORDER + ["total", "debt_service", "net_cost_pv"])
    for y in report["by_year"]:
        w.writerow([y["year"]] + [y["by_source"][s] for s in SOURCE_ORDER] + [y["total"], y["debt_service"], y["net_cost_pv"]])
    return buf.getvalue()


def _usd(n) -> str:
    return f"${n:,.0f}"


STYLE = """
.cip{font:13px/1.45 system-ui,-apple-system,sans-serif;color:#1d2a33;max-width:760px}
.cip h2{margin:0 0 2px;font-size:19px}.cip h3{margin:20px 0 6px;font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:#52606b}
.cip p.note{margin:4px 0;color:#52606b;font-size:12px}
.cip .sim{display:inline-block;background:#fff3cd;border:1px solid #e6c85c;padding:1px 8px;border-radius:10px;font-size:11px;margin-bottom:8px}
.cip .badge{display:inline-block;border-radius:8px;padding:0 6px;font-size:10px;font-weight:600;white-space:nowrap;background:#fff3cd;color:#7a5b00}
.cip .badge.Sourced{background:#dff1e1;color:#1d5c24}.cip .badge.Calibrated{background:#dbe9fb;color:#17467f}
.cip .tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:8px 0}
.cip .tile{background:#f3f6f8;border-radius:8px;padding:8px}.cip .tile b{display:block;font-size:17px}
.cip table{border-collapse:collapse;width:100%}.cip th,.cip td{padding:5px 6px;border-bottom:1px solid #e1e6ea;text-align:left;vertical-align:top}
.cip th{font-size:11px;color:#52606b;text-transform:uppercase}.cip small{color:#6b7882}
.cip tr[data-seg]:hover{background:#eef5fb;cursor:pointer}.cip tr.sel{background:#dcebf8}
.cip .tag{background:#e3f1e4;color:#256029;border-radius:8px;padding:0 6px;font-size:11px;white-space:nowrap}
.cip .rev{background:#fde8e6;color:#8a1c14;border-radius:8px;padding:0 6px;font-size:11px;white-space:nowrap}
.cip .t1{color:#b3261e;font-weight:600}.cip .t2{color:#b26a00}.cip .why{color:#44525c;font-size:12px}
.cip td.n,.cip th.n{text-align:right;font-variant-numeric:tabular-nums}
.cip code{background:#f3f6f8;padding:0 4px;border-radius:4px;font-size:12px}
"""

FORMULAS = [
    ("Return", "present value of expected dollar loss removed / gross cost. Options on one asset are chosen by NPV = benefit - gross cost; candidates are ranked by return only when the budget binds."),
    ("Failure probability", "p(t) = min(1, C x PoF(t) / 100), with C chosen so expected city-wide breaks equal N_target (breaks per mile x network miles)."),
    ("Dollars per failure", "F = emergency multiplier x planned pipe cost + (consequence index / 100) x worst-case social cost. Consequence excludes traffic and direct cost (no double counting)."),
    ("Pipe benefit", "sum over the treatment life of discount(t) x [expected loss before - expected loss after] x F. Reline removes a share of age; replace resets it. Waiting a year raises cost by the inflation rate and loses one year of benefit."),
    ("Road benefit", "sum of discount(t) x vehicle-miles x [user cost per mile before - after]; user cost per mile = u0 x ((100 - PCR) / 100)^2."),
    ("Gross cost", "pipe alone = dig + pipe work + repaving penalty; road alone = dig + road work; bundle = one dig + both works (no penalty). Penalty = repave cost x lost years / cycle, lost years = lambda x (cycle - street age)."),
    ("Shared dig", "A bundle wins on NPV when NPV(bundle) > NPV(pipe alone) + NPV(road alone). Each add-on must also clear the hurdle on its own work cost (marginal return)."),
    ("Uncertainty", "Returns are recomputed with the lower and upper pipe failure bounds. A project whose low return is under the hurdle while its high return reaches it is flagged for engineering review."),
    ("Priority tiers", "Urgency 0.9+ is Tier 1 Urgent (funded first, up to a cap), 0.6 to 0.9 Soon, 0.3 to 0.6 Plan, below 0.3 Monitor."),
    ("Financing", "Each project is paid from the cheapest source with room within its share and eligibility. Net cost = gross cost x present value of repayments per dollar (interest-free loan 0.811, state revolving loan 0.800, bonds 1.0, rate revenue 1.0). Ranking uses gross cost."),
    ("Reserve", "Emergency repairs are covered by a reserve sized from the 95th percentile of simulated yearly emergency repair cost, capped as a share of the budget."),
]


def _methodology(report, e):
    inputs = "".join(
        f"<tr><td><code>{e(m['name'])}</code></td><td>{e(str(m['value']))}</td><td><span class='badge {e(m['status'].split()[0])}'>{e(m['status'])}</span></td>"
        f"<td class='why'>{e(m['source'])}</td><td class='why'>{e(m['range'])}</td><td class='why'>{e(m['note'])}</td></tr>"
        for m in report["methodology"])
    forms = "".join(f"<tr><td><b>{e(a)}</b></td><td class='why'>{e(b)}</td></tr>" for a, b in FORMULAS)
    return (f"<h3>Methodology: formulas</h3><table>{forms}</table>"
            f"<h3>Methodology: inputs, status and range tested</h3>"
            f"<p class='note'>Sourced = a document we can cite. Calibrated = fit to real data we can name (none yet). "
            f"Simulated assumption = a placeholder chosen by the team; the range column says what has been tested.</p>"
            f"<table><tr><th>Input</th><th>Value</th><th>Status</th><th>Source</th><th>Range tested</th><th>Meaning</th></tr>{inputs}</table>")


def _tile(v, label, tag="Simulated"):
    return f'<div class="tile"><b>{v}</b>{label}<br><span class="badge {tag}">{tag}</span></div>'


def _funded_rows(report, e):
    out = []
    for r in report["funded"]:
        bundle = f' <span class="tag">shared dig {e(r["bundle_id"])}</span>' if r["bundle_id"] else ""
        rev = ' <span class="rev">engineering review</span>' if r["needs_review"] else ""
        out.append(
            f'<tr data-seg="{e(r["segment_id"] or "")}" data-year="{r["year"]}">'
            f'<td>{r["rank"]}</td><td>{r["year"]}</td>'
            f'<td><b>{e(r["street"] or "")}</b><br><small>{e(r["segment_id"] or "")}</small></td>'
            f'<td>{e(r["work_label"] or "")}{bundle}{rev}</td>'
            f'<td class="t{r["tier"]}">{e(TIER_LABEL.get(r["tier"], ""))}</td>'
            f'<td class="n">{_usd(r["amount"])}<br><small>{e(SOURCE_LABEL.get(r["funding_source"], ""))}</small></td>'
            f'<td class="n">{(r["return_per_dollar"] or 0):.2f}</td>'
            f'<td class="why">{e(r["rationale"])}</td></tr>')
    return "".join(out)


def _section(report, e, limit=30):
    s = report["summary"]
    head = "".join(f"<th class='n'>{SOURCE_LABEL[k]}</th>" for k in SOURCE_ORDER)
    yrows = "".join(
        f"<tr><td>{y['year']}</td>" + "".join(f"<td class='n'>{_usd(y['by_source'][k])}</td>" for k in SOURCE_ORDER)
        + f"<td class='n'><b>{_usd(y['total'])}</b></td><td class='n'>{_usd(y['debt_service'])}</td></tr>"
        for y in report["by_year"] if y["total"] or y["debt_service"])
    prow = "".join(
        f"<tr><td>{p['year']}</td><td class='n'>{p['replaced']:.2f}</td><td class='n'>{p['relined']:.2f}</td>"
        f"<td class='n'>{p['repaved']:.2f}</td><td class='n'>{p['preserved']:.2f}</td>"
        + (f"<td class='n'>{p['replaced_pct']:.2f}%</td><td class='n'>{p['repaved_pct']:.2f}%</td>" if "replaced_pct" in p else "<td></td><td></td>")
        + "</tr>" for p in report["pace"])
    rrows = "".join(
        f"<tr><td>{r['year']}</td><td>{e(r['street'] or '')}</td><td>{e(r['work_label'] or '')}</td><td>{r['status']}</td>"
        f"<td class='n'>{_usd(r['ask'])}</td><td class='n'>{r['return_lo']:.2f} to {r['return_hi']:.2f}</td></tr>"
        for r in report["review"][:limit])
    nrows = "".join(
        f'<tr data-seg="{e(r["segment_id"] or "")}" data-year="{r["year"]}"><td>{r["year"]}</td>'
        f'<td>{e(r["street"] or "")}</td><td>{e(r["work_label"] or "")}</td>'
        f'<td class="n">{_usd(r["ask"])}</td><td class="why">{e(r["reason"])}</td></tr>'
        for r in report["not_funded"][:limit])
    base = ""
    if "isolated_street_openings" in s:
        base = (f"<p class='note'>Isolated baseline (separate departments, fixed budget split, same seed): {s['isolated_funded_projects']} projects in "
                f"{s['isolated_street_openings']} street openings for {_usd(s['isolated_total_funded'])}. This plan: {s['funded_projects']} projects in "
                f"{s['street_openings']} openings for {_usd(s['total_funded'])}. The two fund different amounts of work, so compare dig savings "
                f"({_usd(s['dig_savings'])} from shared digs here, none in isolation) and cost per opening, not raw counts.</p>")
    reserve = ""
    if report["reserve"]:
        reserve = ("<h3>Emergency reserve balance by year <span class='badge'>Simulated</span></h3><table><tr><th>Year</th>"
                   "<th class='n'>Opening</th><th class='n'>Set aside</th><th class='n'>Emergency repairs</th>"
                   "<th class='n'>Shortfall</th><th class='n'>Closing</th></tr>"
                   + "".join(f"<tr><td>{x['year']}</td><td class='n'>{_usd(x['opening'])}</td><td class='n'>{_usd(x['set_aside'])}</td>"
                             f"<td class='n'>{_usd(x['emergency'])}</td><td class='n'>{_usd(x['shortfall'])}</td>"
                             f"<td class='n'>{_usd(x['closing'])}</td></tr>" for x in report["reserve"]) + "</table>")
    return f"""
<div class="tiles">
 {_tile(s['funded_projects'], 'projects funded')}{_tile(_usd(s['total_funded']), 'total funded')}
 {_tile(s['street_openings'], 'street openings')}{_tile(s['shared_digs'], 'shared digs')}
</div>
<div class="tiles">
 {_tile(_usd(s['dig_savings']), 'dig savings from shared digs')}{_tile(_usd(s['net_cost_pv']), 'net cost after financing')}
 {_tile(_usd(s['loan_interest']), 'loan interest over loan lives')}{_tile(s['needs_review'], 'funded, needs engineering review')}
</div>{base}
<h3>Funding by year and source <span class="badge Simulated">Simulated</span> <span class="badge Sourced">Source mix: Sourced</span></h3>
<p class="note">Source shares follow the BWSC 2024-2026 CIP water program (Table 11). Debt service is the repayment due that year on loans and bonds issued earlier.</p>
<table><tr><th>Year</th>{head}<th class='n'>Total</th><th class='n'>Debt service</th></tr>{yrows}</table>
<h3>Program pace: miles per year <span class="badge">Simulated</span></h3>
<p class="note">Network: {s['network_miles']} miles of street (real geometry); the pipes and pavement on them are simulated.</p>
<table><tr><th>Year</th><th class='n'>Main replaced</th><th class='n'>Main relined</th><th class='n'>Repaved</th><th class='n'>Preserved</th><th class='n'>Replaced, % of network</th><th class='n'>Repaved, % of network</th></tr>{prow}</table>
{reserve}
<h3>Recommended projects (ranked) <span class="badge">Simulated</span></h3>
<table><tr><th>#</th><th>Year</th><th>Street</th><th>Work</th><th>Priority</th><th class='n'>Funding</th><th class='n'>Return</th><th>Why</th></tr>{_funded_rows(report, e)}</table>
<h3>Needs engineering review</h3>
<p class="note">Return could fall below the hurdle or reach it, depending on the pipe failure bounds (low return under {1.0:.1f}, high return at or above). Showing {min(limit, len(report['review']))} of {len(report['review'])}.</p>
<table><tr><th>Year</th><th>Street</th><th>Work</th><th>Status</th><th class='n'>Cost</th><th class='n'>Return range</th></tr>{rrows}</table>
<h3>Not funded, and what would change the answer</h3>
<p class="note">Highest-return assets with no funded option. Showing {min(limit, len(report['not_funded']))} of {len(report['not_funded'])}.</p>
<table><tr><th>Year</th><th>Street</th><th>Work</th><th class='n'>Ask</th><th>Reason</th></tr>{nrows}</table>"""


SCRIPT = """<script>
(function(){
  // Click a row -> tell the map to focus that segment. Map code listens for "cip:select".
  document.querySelectorAll('.cip tr[data-seg]').forEach(function(tr){
    tr.addEventListener('click',function(){
      document.querySelectorAll('.cip tr.sel').forEach(function(x){x.classList.remove('sel')});
      tr.classList.add('sel');
      window.dispatchEvent(new CustomEvent('cip:select',{detail:{segment_id:tr.dataset.seg,year:+tr.dataset.year}}));
    });
  });
  // Map year slider -> filter list. Dispatch "map:year" with detail {year} (or null for all).
  window.addEventListener('map:year',function(ev){
    var y=ev.detail&&ev.detail.year;
    document.querySelectorAll('.cip tr[data-year]').forEach(function(tr){
      tr.style.display=(!y||+tr.dataset.year===y)?'':'none';
    });
  });
})();
</script>"""


def to_html(report, title="Dig Once: Capital Plan Recommendation") -> str:
    """Side-panel fragment (embed next to the map): summary, funding, pace, decision list, review, not funded."""
    s = report["summary"]
    e = html.escape
    return (f'<div class="cip"><style>{STYLE}</style><h2>{e(title)}</h2>'
            f'<span class="sim">{s["label"]} &middot; {s["years"][0]}&ndash;{s["years"][1]}</span>{_section(report, e)}{SCRIPT}</div>')


def to_page(report, title="Dig Once: Capital Plan Recommendation") -> str:
    """Self-contained, printable page: the panel plus the methodology."""
    s = report["summary"]
    e = html.escape
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title>
<style>body{{margin:24px auto;max-width:900px;padding:0 16px;background:#fff}}{STYLE}.cip{{max-width:none}}
@media print{{body{{margin:0;max-width:none}}.cip h3{{break-after:avoid}}.cip tr{{break-inside:avoid}}}}
.banner{{background:#fff3cd;border:1px solid #e6c85c;padding:8px 12px;border-radius:8px;margin:0 0 12px;font:13px system-ui}}</style></head><body>
<div class="banner"><b>SIMULATED DATA.</b> Street geometry is real; every pipe, pavement, break and cost figure below is simulated. Results are model outputs under stated assumptions, not predictions or a recommendation for real streets.</div>
<div class="cip"><h2>{e(title)}</h2><span class="sim">{s["label"]} &middot; {s["years"][0]}&ndash;{s["years"][1]}</span>
{_section(report, e, limit=40)}{_methodology(report, e)}{SCRIPT}</div></body></html>"""


if __name__ == "__main__":
    # Smoke test with made-up rows in the interfaces.md v0.2 shapes.
    cfg = {"start_year": 2027, "horizon_years": 3,
           "loan_terms": {"bonds": {"rate": 0.04, "years": 20}, "interest_free_loan": {"rate": 0.0, "years": 10},
                          "srf_loan": {"rate": 0.02, "years": 25}}}
    city = {"S041": {"street": "Example St", "neighborhood": "Demo"}, "S007": {"street": "Sample Ave", "neighborhood": "Demo"}}
    props = [
        {"proposal_id": "pipe-2027-S041", "agent": "pipe", "segment_id": "S041", "year": 2027, "work": "replace_pipe",
         "rationale": "Cast iron from 1925, three prior breaks.", "priced": {"urgency": 0.95, "benefit_usd": 515484}},
        {"proposal_id": "road-2027-S041", "agent": "road", "segment_id": "S041", "year": 2027, "work": "repave",
         "rationale": "Paved 2012; same dig as the main.", "priced": {"urgency": 0.4, "benefit_usd": 104235}},
        {"proposal_id": "pipe-2027-S007", "agent": "pipe", "segment_id": "S007", "year": 2027, "work": "reline_pipe",
         "rationale": "Moderate risk.", "priced": {"urgency": 0.5, "benefit_usd": 90000}},
    ]
    decs = [
        {"proposal_id": "pipe-2027-S041", "bundle_id": "B-2027-S041", "funded": True, "amount": 151000,
         "funding_source": "interest_free_loan", "return_per_dollar": 2.74, "reason": "Bundle."},
        {"proposal_id": "road-2027-S041", "bundle_id": "B-2027-S041", "funded": True, "amount": 75000,
         "funding_source": "rate_revenue", "return_per_dollar": 2.74, "reason": "Bundle."},
        {"proposal_id": "pipe-2027-S007", "bundle_id": None, "funded": False, "amount": 98000, "funding_source": None,
         "return_per_dollar": 0.9, "reason": "Below hurdle; combine with road work to qualify."},
    ]
    rep = build_report(decs, props, city, cfg)
    assert rep["summary"]["total_funded"] == 226000 and rep["summary"]["street_openings"] == 1
    assert rep["by_year"][1]["debt_service"] == round(151000 / 10)
    print(to_csv(rep))
    print("ok")
