"""make cip: run isolated and coordinated on the same seed, build the capital plan, write outputs/cip/.
Usage: python3 -m cip.build [--seed 42] [--neighborhood NAME] [--max-segments N] [--out outputs/cip] [--no-pdf]
Writes report.json, decision_list.csv, funding_table.csv, capital_plan.html (self-contained, printable), capital_plan.pdf
(rendered with Playwright), run_<strategy>_seed<N>.json (runner output), config_snapshot.json. ALL DATA SIMULATED."""
import argparse
import json
import multiprocessing as mp
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from cip import adapter, report  # noqa: E402
from sim import reserve, snapshot  # noqa: E402
from sim.config import CFG  # noqa: E402
from sim.runner import simulate  # noqa: E402


def _run(job):
    strategy, seed, cfg, out = job
    return simulate(strategy, seed=seed, cfg=cfg, cip_dir=out)


def build(seed=42, cfg=None, out="outputs/cip", pdf=True, strategy="coordinated"):
    cfg = reserve.ensure(dict(cfg or CFG))
    out = pathlib.Path(out)
    out.mkdir(parents=True, exist_ok=True)
    with mp.Pool(2) as pool:
        runs = pool.map(_run, [(s, seed, cfg, str(out)) for s in ("isolated", strategy)])
    iso, run = runs
    rep = report.build_report(**adapter.to_report_inputs(run, iso))
    rep["run"] = {k: run[k] for k in ("strategy", "seed", "total_cost", "spend", "emerg", "user_cost", "dig_savings", "interest",
                                      "cost_of_ownership") if k in run}
    rep["run"]["isolated"] = {k: iso[k] for k in ("total_cost", "spend", "emerg", "user_cost", "openings") if k in iso}
    (out / "report.json").write_text(json.dumps(rep, indent=1, default=str))
    (out / "decision_list.csv").write_text(report.to_csv(rep))
    (out / "funding_table.csv").write_text(report.funding_csv(rep))
    (out / "capital_plan.html").write_text(report.to_page(rep))
    snapshot.write(out / "report", run["cip"]["config"], seed=seed, strategy=strategy, methodology=rep["methodology"])
    if pdf:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page()
            pg.goto((out / "capital_plan.html").resolve().as_uri())
            pg.pdf(path=str(out / "capital_plan.pdf"), format="Letter", print_background=True,
                   margin=dict(top="14mm", bottom="14mm", left="12mm", right="12mm"),
                   display_header_footer=True, header_template="<span></span>",
                   footer_template='<div style="font-size:8px;width:100%;text-align:center;color:#666">'
                                   'SIMULATED DATA &middot; Dig Once capital plan &middot; page <span class="pageNumber"></span> of '
                                   '<span class="totalPages"></span></div>')
            b.close()
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--neighborhood")
    ap.add_argument("--max-segments", type=int)
    ap.add_argument("--out", default="outputs/cip")
    ap.add_argument("--no-pdf", action="store_true")
    a = ap.parse_args()
    rep = build(a.seed, dict(CFG, neighborhood=a.neighborhood, max_segments=a.max_segments), a.out, not a.no_pdf)
    s = rep["summary"]
    print(f"funded {s['funded_projects']} projects, ${s['total_funded']:,.0f}; {s['street_openings']} street openings "
          f"({s.get('isolated_street_openings', '?')} isolated); {s['shared_digs']} shared digs; wrote {a.out}/")


if __name__ == "__main__":
    main()
