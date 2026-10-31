"""demo/cip_report.py  (contract v0.2)

Turns the budget agent's funding decisions into the report a city would get:
a ranked decision list per year, totals by funding source (BWSC Table 11 style),
and running debt service. Pure function of (decisions, proposals, config):
no dollars are computed here except loan repayments, which follow loan_terms.

Inputs
  decisions : list[dict]  one per proposal (interfaces.md section 7)
  proposals : list[dict]  priced proposals (section 5), joined by proposal_id
  city      : dict        segment_id -> {"street": str, "neighborhood": str}
  config    : dict        config.yaml (loan_terms, start_year, horizon_years, ...)

Outputs
  build_report(...)  -> dict   (JSON for the Streamlit/JS panel)
  to_csv(report)     -> str    (one row per decision, for the city's spreadsheet)
  to_html(report)    -> str    (self-contained side panel; embed next to the map)
"""
from __future__ import annotations

import csv
import html
import io
from collections import defaultdict

SOURCE_ORDER = ["interest_free_loan", "srf_loan", "rate_revenue", "bonds"]
SOURCE_LABEL = {
    "interest_free_loan": "Interest-free loan",
    "srf_loan": "State revolving loan",
    "rate_revenue": "Rate revenue",
    "bonds": "Bonds",
}
WORK_LABEL = {
    "replace_pipe": "Replace water main",
    "reline_pipe": "Reline water main",
    "repave": "Repave",
    "preserve_road": "Preserve pavement",
    "reconstruct_road": "Reconstruct road",
}
TIER_LABEL = {1: "1 Urgent", 2: "2 Soon", 3: "3 Plan", 4: "4 Monitor"}


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


def build_report(decisions, proposals, city, config) -> dict:
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
        year = p.get("year")
        status = "Funded" if d["funded"] else "Not funded"
        rows.append({
            "year": year,
            "segment_id": seg,
            "street": info.get("street", seg),
            "neighborhood": info.get("neighborhood", ""),
            "agent": p.get("agent"),
            "work": p.get("work"),
            "work_label": WORK_LABEL.get(p.get("work"), p.get("work")),
            "bundle_id": d.get("bundle_id"),
            "status": status,
            "amount": d["amount"] if d["funded"] else 0,
            "ask": d["amount"],
            "funding_source": d.get("funding_source") if d["funded"] else None,
            "return_per_dollar": d.get("return_per_dollar"),
            "urgency": priced.get("urgency"),
            "tier": tier_of(priced.get("urgency")),
            "benefit_usd": priced.get("benefit_usd"),
            "reason": d.get("reason", ""),
            "rationale": p.get("rationale", ""),
            "proposal_id": d["proposal_id"],
        })

    funded = [r for r in rows if r["status"] == "Funded"]
    # Rank: year, then tier (urgent first), then return, high to low.
    funded.sort(key=lambda r: (r["year"], r["tier"] or 9, -(r["return_per_dollar"] or 0)))
    for i, r in enumerate(funded, 1):
        r["rank"] = i
    declined = [r for r in rows if r["status"] != "Funded"]
    declined.sort(key=lambda r: (r["year"], -(r["return_per_dollar"] or 0)))

    # Totals by year x funding source (Table 11 style).
    table = defaultdict(lambda: defaultdict(int))
    for r in funded:
        table[r["year"]][r["funding_source"]] += r["amount"]
    by_year = []
    for y in range(start, end + 1):
        src = {s: table[y].get(s, 0) for s in SOURCE_ORDER}
        by_year.append({"year": y, "by_source": src, "total": sum(src.values())})

    # Debt service: each funded dollar from a loan/bond repays level over its term.
    debt = {y: 0.0 for y in range(start, end + 1)}
    for r in funded:
        t = loans.get(r["funding_source"])
        if not t:
            continue  # rate revenue is cash, no debt service
        pay = annual_payment(r["amount"], t["rate"], t["years"])
        for y in range(r["year"] + 1, min(end, r["year"] + t["years"]) + 1):
            debt[y] += pay
    for row in by_year:
        row["debt_service"] = round(debt[row["year"]])

    # Bundles = one street opening shared by pipe and road work.
    bundles = {r["bundle_id"] for r in funded if r["bundle_id"]}
    openings = len({(r["bundle_id"] or r["proposal_id"]) for r in funded})
    summary = {
        "funded_projects": len(funded),
        "total_funded": sum(r["amount"] for r in funded),
        "street_openings": openings,
        "shared_digs": len(bundles),
        "not_funded": len(declined),
        "years": [start, end],
        "label": "SIMULATED DATA",
    }
    return {"summary": summary, "by_year": by_year, "funded": funded, "not_funded": declined}


CSV_COLS = ["rank", "year", "segment_id", "street", "work_label", "bundle_id", "tier",
            "amount", "funding_source", "return_per_dollar", "rationale"]


def to_csv(report) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_COLS)
    for r in report["funded"]:
        w.writerow([r.get(c) for c in CSV_COLS])
    return buf.getvalue()


def _usd(n) -> str:
    return f"${n:,.0f}"


def to_html(report, title="Dig Once: Capital Plan Recommendation") -> str:
    s = report["summary"]
    e = html.escape
    head = "".join(f"<th>{SOURCE_LABEL[k]}</th>" for k in SOURCE_ORDER)
    yrows = "".join(
        f"<tr><td>{y['year']}</td>"
        + "".join(f"<td>{_usd(y['by_source'][k])}</td>" for k in SOURCE_ORDER)
        + f"<td><b>{_usd(y['total'])}</b></td><td>{_usd(y['debt_service'])}</td></tr>"
        for y in report["by_year"] if y["total"] or y["debt_service"]
    )
    drows = []
    for r in report["funded"]:
        bundle = f' <span class="tag">shared dig {e(r["bundle_id"])}</span>' if r["bundle_id"] else ""
        drows.append(
            f'<tr data-seg="{e(r["segment_id"] or "")}" data-year="{r["year"]}">'
            f'<td>{r["rank"]}</td><td>{r["year"]}</td>'
            f'<td><b>{e(r["street"] or "")}</b><br><small>{e(r["segment_id"] or "")}</small></td>'
            f'<td>{e(r["work_label"] or "")}{bundle}</td>'
            f'<td class="t{r["tier"]}">{e(TIER_LABEL.get(r["tier"], ""))}</td>'
            f'<td>{_usd(r["amount"])}<br><small>{e(SOURCE_LABEL.get(r["funding_source"], ""))}</small></td>'
            f'<td>{(r["return_per_dollar"] or 0):.2f}</td>'
            f'<td class="why">{e(r["rationale"])}</td></tr>'
        )
    nrows = "".join(
        f'<tr data-seg="{e(r["segment_id"] or "")}" data-year="{r["year"]}"><td>{r["year"]}</td>'
        f'<td>{e(r["street"] or "")}</td><td>{e(r["work_label"] or "")}</td>'
        f'<td>{_usd(r["ask"])}</td><td class="why">{e(r["reason"])}</td></tr>'
        for r in report["not_funded"]
    )
    return f"""<div class="cip">
<style>
.cip{{font:13px/1.4 system-ui,sans-serif;color:#1d2a33;max-width:640px}}
.cip h2{{margin:0 0 2px;font-size:17px}} .cip h3{{margin:18px 0 6px;font-size:13px;text-transform:uppercase;letter-spacing:.04em;color:#52606b}}
.cip .sim{{display:inline-block;background:#fff3cd;border:1px solid #e6c85c;padding:1px 8px;border-radius:10px;font-size:11px;margin-bottom:8px}}
.cip .tiles{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}}
.cip .tile{{background:#f3f6f8;border-radius:8px;padding:8px}} .cip .tile b{{display:block;font-size:17px}}
.cip table{{border-collapse:collapse;width:100%}} .cip th,.cip td{{padding:5px 6px;border-bottom:1px solid #e1e6ea;text-align:left;vertical-align:top}}
.cip th{{font-size:11px;color:#52606b;text-transform:uppercase}} .cip small{{color:#6b7882}}
.cip tr[data-seg]:hover{{background:#eef5fb;cursor:pointer}} .cip tr.sel{{background:#dcebf8}}
.cip .tag{{background:#e3f1e4;color:#256029;border-radius:8px;padding:0 6px;font-size:11px;white-space:nowrap}}
.cip .t1{{color:#b3261e;font-weight:600}} .cip .t2{{color:#b26a00}} .cip .why{{color:#44525c;font-size:12px}}
</style>
<h2>{e(title)}</h2>
<span class="sim">{s['label']} &middot; {s['years'][0]}&ndash;{s['years'][1]}</span>
<div class="tiles">
 <div class="tile"><b>{s['funded_projects']}</b>projects funded</div>
 <div class="tile"><b>{_usd(s['total_funded'])}</b>total funded</div>
 <div class="tile"><b>{s['street_openings']}</b>street openings</div>
 <div class="tile"><b>{s['shared_digs']}</b>shared digs</div>
</div>
<h3>Funding by year and source</h3>
<table><tr><th>Year</th>{head}<th>Total</th><th>Debt service</th></tr>{yrows}</table>
<h3>Recommended projects (ranked)</h3>
<table><tr><th>#</th><th>Year</th><th>Street</th><th>Work</th><th>Priority</th><th>Funding</th><th>Return</th><th>Why</th></tr>{''.join(drows)}</table>
<h3>Not funded, and what would change the answer</h3>
<table><tr><th>Year</th><th>Street</th><th>Work</th><th>Ask</th><th>Reason</th></tr>{nrows}</table>
<script>
(function(){{
  // Click a row -> tell the map to focus that segment. Map code listens for "cip:select".
  document.querySelectorAll('.cip tr[data-seg]').forEach(function(tr){{
    tr.addEventListener('click',function(){{
      document.querySelectorAll('.cip tr.sel').forEach(function(x){{x.classList.remove('sel')}});
      tr.classList.add('sel');
      window.dispatchEvent(new CustomEvent('cip:select',{{detail:{{segment_id:tr.dataset.seg,year:+tr.dataset.year}}}}));
    }});
  }});
  // Map year slider -> filter list. Dispatch "map:year" with detail {{year}} (or null for all).
  window.addEventListener('map:year',function(ev){{
    var y=ev.detail&&ev.detail.year;
    document.querySelectorAll('.cip tr[data-year]').forEach(function(tr){{
      tr.style.display=(!y||+tr.dataset.year===y)?'':'none';
    }});
  }});
}})();
</script>
</div>"""


if __name__ == "__main__":
    # Smoke test with made-up rows in the interfaces.md v0.2 shapes.
    cfg = {"start_year": 2027, "horizon_years": 3,
           "loan_terms": {"bonds": {"rate": 0.04, "years": 20},
                          "interest_free_loan": {"rate": 0.0, "years": 10},
                          "srf_loan": {"rate": 0.02, "years": 25}}}
    city = {"S041": {"street": "Example St", "neighborhood": "Demo"},
            "S007": {"street": "Sample Ave", "neighborhood": "Demo"}}
    props = [
        {"proposal_id": "pipe-2027-S041", "agent": "pipe", "segment_id": "S041", "year": 2027,
         "work": "replace_pipe", "rationale": "Cast iron from 1925, three prior breaks.",
         "priced": {"urgency": 0.95, "benefit_usd": 515484}},
        {"proposal_id": "road-2027-S041", "agent": "road", "segment_id": "S041", "year": 2027,
         "work": "repave", "rationale": "Paved 2012; same dig as the main.",
         "priced": {"urgency": 0.4, "benefit_usd": 104235}},
        {"proposal_id": "pipe-2027-S007", "agent": "pipe", "segment_id": "S007", "year": 2027,
         "work": "reline_pipe", "rationale": "Moderate risk.", "priced": {"urgency": 0.5, "benefit_usd": 90000}},
    ]
    decs = [
        {"proposal_id": "pipe-2027-S041", "bundle_id": "B-2027-S041", "funded": True, "amount": 151000,
         "funding_source": "interest_free_loan", "return_per_dollar": 2.74, "reason": "Bundle."},
        {"proposal_id": "road-2027-S041", "bundle_id": "B-2027-S041", "funded": True, "amount": 75000,
         "funding_source": "rate_revenue", "return_per_dollar": 2.74, "reason": "Bundle."},
        {"proposal_id": "pipe-2027-S007", "bundle_id": None, "funded": False, "amount": 98000,
         "funding_source": None, "return_per_dollar": 0.9,
         "reason": "Below hurdle; combine with road work to qualify."},
    ]
    rep = build_report(decs, props, city, cfg)
    assert rep["summary"]["total_funded"] == 226000 and rep["summary"]["street_openings"] == 1
    assert rep["by_year"][1]["debt_service"] == round(151000 / 10)
    open("cip_preview.html", "w").write(
        "<!doctype html><meta charset=utf-8><body style='margin:16px'>" + to_html(rep))
    print(to_csv(rep))
    print("ok")
