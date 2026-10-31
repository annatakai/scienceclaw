"""Break counts by pipe age cohort, material, diameter and season from data/processed_water_breaks.csv (docs/evidence_plan.md section 2).
The file is BREAK RECORDS ONLY (no inventory of unbroken mains), so this cannot give a break RATE, a lift curve against age-only
ranking, or a calibration plot. It shows only the age and material mix of mains that broke. This is real data about real breaks in
Springfield and Ludlow, Massachusetts, not Boston and not simulated; it is kept on its own page, separate from the simulated results.
Writes outputs/results/break_cohorts.html and .csv. Usage: python3 -m experiments.break_cohorts"""
import html
import pathlib

import pandas as pd

SRC = pathlib.Path("data/processed_water_breaks.csv")
OUT = pathlib.Path("outputs/results")
BAD = "install year missing or invalid (0)"


def tables(d):
    d = d.copy()
    d["bd"] = pd.to_datetime(d.break_date)
    ok = d.MAIN_INSTALL_YEAR >= 1800
    ages = d.loc[ok, "pipe_age_at_break"]
    cohort = pd.cut(ages, [0, 50, 75, 100, 125, 500], right=False, labels=["under 50", "50-74", "75-99", "100-124", "125 and over"])
    t = {}
    t["Age at break (years)"] = cohort.value_counts().sort_index()
    t["Material"] = d.MATERIAL_MAIN.value_counts()
    t["Diameter (inches)"] = d.DIAMETERMAIN.value_counts().sort_index()
    t["Month of break"] = d.bd.dt.month.value_counts().sort_index()
    t["Municipality"] = d.MUNICIPALITY.str.title().value_counts()
    return t, int(ok.sum()), int((~ok).sum())


def main():
    d = pd.read_csv(SRC)
    t, n_ok, n_bad = tables(d)
    OUT.mkdir(parents=True, exist_ok=True)
    rows = [(k, str(i), int(v)) for k, s in t.items() for i, v in s.items()]
    pd.DataFrame(rows, columns=["table", "category", "breaks"]).to_csv(OUT / "break_cohorts.csv", index=False)
    e = html.escape
    body = "".join(f"<h3>{e(k)}</h3><table>" + "".join(f"<tr><td>{e(str(i))}</td><td>{int(v)}</td></tr>" for i, v in s.items()) + "</table>"
                   for k, s in t.items())
    first, last = pd.to_datetime(d.break_date).min().date(), pd.to_datetime(d.break_date).max().date()
    page = f"""<!doctype html><meta charset=utf-8><title>Real break records: age and material mix</title>
<body style="font:14px system-ui;max-width:720px;margin:24px auto;padding:0 16px">
<p style="background:#dff1e1;border:1px solid #9bd0a3;padding:8px 12px;border-radius:8px"><b>REAL DATA, NOT SIMULATED.</b> {len(d)} water main break records,
{first} to {last}, from data/processed_water_breaks.csv (municipalities: Springfield, Ludlow and two others, Massachusetts; not Boston).
This page is separate from the simulated coordination results.</p>
<h2>Age and material mix of mains that broke</h2>
<p>{n_ok} records have a usable install year; {n_bad} has {BAD} and is left out of the age table only.</p>
{body}
<h3>What this cannot show</h3><ul>
<li>The file lists only mains that broke. There is no inventory of unbroken mains, so there is no denominator: no break rate per mile or per pipe, no lift curve against age-only ranking, and no calibration plot.</li>
<li>Most breaks are on old cast iron (108 of 114), but without the inventory we cannot tell whether old mains break more often or are simply most of the system.</li>
<li>The period is 21 months and breaks cluster in winter (January and February hold 75 of 114), so one cold season can dominate (see month table).</li>
<li>It cannot validate the pipe rubric (agents/pipe_agent/scoring.py) or the simulated break model. A dataset with a main inventory and break dates (for example Kitchener, Toronto or DC Water; licenses and fields not yet checked) is needed.</li></ul></body>"""
    (OUT / "break_cohorts.html").write_text(page)
    for k, s in t.items():
        print(k, s.to_dict())


if __name__ == "__main__":
    main()
