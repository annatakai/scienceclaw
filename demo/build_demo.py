"""Run the strategies once (default seed 42, full network), write demo/site/ (index.html, app.js, style.css, vendor/,
data/*.json|bin) and serve it on http://localhost:8000. ALL ASSET DATA SIMULATED.

Usage: python3 -m demo.build_demo [seed] [--neighborhood NAME] [--max-segments N] [--years N] [--llm]
                                  [--no-open] [--no-serve] [--port 8000]
--llm adds a recorded coordinated_llm run (experiments/compare_llm.py, 800-segment area: build with --max-segments 800).
Presentation only: every number comes from the simulation record (sim/runner.py, record=True)."""
import argparse
import functools
import http.server
import json
import multiprocessing as mp
import pathlib
import shutil
import sys
import time
import webbrowser

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from cip import adapter, report  # noqa: E402
from sim import reserve, snapshot  # noqa: E402
from sim.config import CFG  # noqa: E402
from sim.runner import STRATEGIES, simulate  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
SRC, SITE = HERE / "src", HERE / "site"
FIELDS = ["risk", "cls", "pcr", "cond", "inst", "mat", "brk", "paved"]   # uint8 planes per frame in <strategy>.bin
OFFSET = {"inst": 1800, "paved": 1990}
PLAN_TYPES = ("post_plan",)


def _run(job):
    s, seed, cfg = job
    return s, simulate(s, seed=seed, cfg=cfg, record=True, cip=True)


def plane(vals, name):
    off = OFFSET.get(name, 0)
    return bytes(max(0, min(255, int(v) - off)) for v in vals)


def pack_bin(run):
    frames = [run["state0"]] + [y["state"] for y in run["years"]]
    return b"".join(plane(f[k], k) for f in frames for k in FIELDS)


def pack_json(run):
    reasons, rid = [], {}

    def rr(text):
        if text not in rid:
            rid[text] = len(reasons)
            reasons.append(text)
        return rid[text]

    years = []
    for y in run["years"]:
        plans = {}
        for m in y["messages"]:
            if m["type"] == "post_plan" and m["seg"] is not None:
                plans.setdefault(m["seg"], []).append(m["frm"])
        years.append(dict(
            year=y["year"], n_proposals=y["n_proposals"], n_rejected=y["n_rejected"], metrics=y["metrics"],
            plans=[[s, "".join(a[0] for a in sorted(set(ag)))] for s, ag in plans.items()],  # p = pipe, r = road
            funded=[[d["seg"], d["agent"][0], d["work"], int(d["bundle"]), d["amount"], d["ret"], rr(d["reason"])] for d in y["decisions"]],
            rejected=[[d["seg"], d["agent"][0], d["work"], rr(d["reason"])] for d in y["rejected"]],
            failures=[[f["seg"], f["cost"]] for f in y["failures"]],
            messages=[[m["round"], m["frm"], m["type"], m["seg"], m["text"]] for m in y["messages"]],
        ))
    return dict(years=years, reasons=reasons)


def write_cip(runs, order, idx):
    """data/cip_<strategy>.json: the ranked decision list for each strategy (rows for the Decision list tab), and for the
    agents + board run the printable plan (capital_plan.html, capital_plan.pdf when Playwright is available)."""
    iso = runs.get("isolated")
    for s in order:
        r = runs[s]
        if "cip" not in r:
            continue
        rep = report.build_report(**adapter.to_report_inputs(r, iso if s != "isolated" else None))
        rows = [[x["rank"], x["year"], idx[x["segment_id"]], x["street"], x["work_label"], x["tier"], round(x["amount"]),
                 report.SOURCE_LABEL.get(x["funding_source"], ""), round(x["return_per_dollar"] or 0, 2), int(bool(x["bundle_id"])),
                 x["rationale"], int(x["needs_review"]), x["segment_id"]] for x in rep["funded"]]
        (SITE / "data" / f"cip_{s}.json").write_text(json.dumps(dict(summary=rep["summary"], rows=rows), separators=(",", ":")))
        if s == "coordinated":
            (SITE / "data" / "capital_plan.html").write_text(report.to_page(rep))
    ok = False
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page()
            pg.goto((SITE / "data" / "capital_plan.html").resolve().as_uri())
            pg.pdf(path=str(SITE / "data" / "capital_plan.pdf"), format="Letter", print_background=True)
            b.close()
        ok = True
    except Exception as e:   # no Playwright or browser: the button opens the printable page instead
        print("capital_plan.pdf not written:", e)
    return ok


def write_site(runs, order, args, miles):
    if SITE.exists():
        shutil.rmtree(SITE)
    (SITE / "data").mkdir(parents=True)
    for f in ("index.html", "app.js", "style.css"):
        shutil.copy(SRC / f, SITE / f)
    shutil.copytree(SRC / "vendor", SITE / "vendor")
    base = runs["coordinated"]
    feats = []
    for i, s in enumerate(base["segs"]):
        feats.append(dict(type="Feature", id=i, properties=dict(
            id=s["id"], street=s["street"], nb=s["neighborhood"], cls=s["road_class"], len=s["length_ft"],
            crit=int(s["critical"]), cust=s["customers"], adt=s["adt"]),
            geometry=dict(type="LineString", coordinates=[[round(x, 5), round(y, 5)] for x, y in s["coords"]])))
    (SITE / "data" / "segments.geojson").write_text(json.dumps(dict(type="FeatureCollection", features=feats), separators=(",", ":")))
    totals = {}
    for s in order:
        r = runs[s]
        (SITE / "data" / f"{s}.bin").write_bytes(pack_bin(r))
        (SITE / "data" / f"{s}.json").write_text(json.dumps(pack_json(r), separators=(",", ":")))
        totals[s] = dict(total_cost=r["total_cost"], spend=r["spend"], emerg=r["emerg"], user_cost=r["user_cost"],
                         fail=r["fail"], dig_savings=r["dig_savings"], openings=r["openings"], exp_fail=r["exp_fail"])
    cip_pdf = write_cip(runs, order, {s["id"]: i for i, s in enumerate(base["segs"])})
    meta = dict(cip_pdf=cip_pdf, order=order, n=len(feats), fields=FIELDS, offset=OFFSET, frames=len(base["years"]) + 1, seed=args.seed,
                start_year=base["years"][0]["year"], miles=miles, cfg=base["cfg"], totals=totals,
                scope=args.neighborhood or ("compact %d-segment area" % args.max_segments if args.max_segments else "all of Boston"),
                nbs=sorted({s["neighborhood"] for s in base["segs"] if s["neighborhood"]}),
                llm_order=[s for s in order if s.endswith("_llm")])
    (SITE / "data" / "meta.json").write_text(json.dumps(meta, separators=(",", ":")))
    snapshot.write(SITE / "data" / "run", runs["coordinated"]["cip"]["config"], seed=args.seed, scope=meta["scope"])
    size = sum(p.stat().st_size for p in (SITE / "data").iterdir())
    print(f"wrote {SITE} (data {size / 1e6:.1f} MB: {len(feats)} segments, {miles:.0f} miles)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("seed", nargs="?", type=int, default=42)
    ap.add_argument("--neighborhood")
    ap.add_argument("--max-segments", type=int)
    ap.add_argument("--years", type=int)
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--no-serve", action="store_true")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    cfg = reserve.ensure(dict(CFG, neighborhood=args.neighborhood, max_segments=args.max_segments))
    if args.years:
        cfg["sim_years"] = args.years
    order = list(STRATEGIES)
    rec = None
    if args.llm:
        path = HERE / "recorded" / f"coordinated_llm_seed{args.seed}.json"
        if not path.exists():
            sys.exit(f"no recording at {path}. Make one with: python3 -m experiments.compare_llm (needs ANTHROPIC_API_KEY)")
        rec = json.loads(path.read_text())
        if "state0" not in rec:
            sys.exit("that recording predates the map data (no per-segment state); record it again with experiments.compare_llm")
        cfg["sim_years"] = len(rec["years"])
        order.insert(order.index("coordinated") + 1, "coordinated_llm")
    t = time.time()
    with mp.Pool(min(len(STRATEGIES), mp.cpu_count())) as pool:
        runs = dict(pool.map(_run, [(s, args.seed, cfg) for s in STRATEGIES]))
    print(f"simulated {len(STRATEGIES)} strategies in {time.time() - t:.0f}s (parallel)")
    if rec:
        if len(rec["segs"]) != len(runs["coordinated"]["segs"]):
            sys.exit("the recording covers a different area; build with --max-segments 800")
        runs["coordinated_llm"] = rec
    write_site(runs, order, args, runs["coordinated"]["miles"])
    for s in order:
        r = runs[s]
        print(f"{s:<16} total cost ${r['total_cost'] / 1e6:8.1f}M  capital ${r['spend'] / 1e6:6.1f}M  exp failures {r['exp_fail']:7.1f}  dig savings ${r['dig_savings'] / 1e6:5.2f}M")
    if args.no_serve:
        return
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(SITE))
    handler.log_message = lambda *a, **k: None
    # OSM and other tile servers reject pages opened as file:// (no Referer), so serve over http
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    url = f"http://localhost:{args.port}/"
    print(f"serving {url}  (Ctrl+C to stop)")
    if not args.no_open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
