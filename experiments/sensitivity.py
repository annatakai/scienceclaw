"""Sensitivity sweep (docs/evidence_plan.md sections 1 and 3). ALL DATA SIMULATED.

One-at-a-time sweeps over the assumptions that move results most (low and high value, others at base), then the top three
by swing together (all eight low/high corners). For every setting, paired by seed over isolated, pooled and coordinated:
  dig savings (coordinated)            what shared digs save
  coordinated minus isolated, total    the headline difference (negative = coordination is cheaper)
  coordinated minus pooled, total      the board alone
Writes outputs/results/sensitivity.json, sensitivity.txt, tornado.html and tornado.png (two tornado charts).
Only conclusions that hold across every tested range are stated; the sign flips are listed.
Not swept: the pipe failure-model weights (they live in the team's scoring.py, which we do not edit).
Usage: python3 -m experiments.sensitivity [n_seeds=10] [--max-segments 800]"""
import argparse
import itertools
import json
import pathlib
import statistics as st

from experiments.compare import ci, run_all
from sim import reserve, snapshot
from sim.config import CFG

STRATS = ["isolated", "pooled", "coordinated"]
# name -> (low, high, why this range). Ranges are tested ranges, not claims about the real world.
PARAMS = {
    "dig_fixed": (25_000, 100_000, "trench cost per opening, half and double the $50k assumption"),
    "lam": (0.06, 0.6, "pavement life lost per cut, the literature range quoted in docs/assumptions_register.md"),
    "breaks_per_mile_year": (0.10, 0.60, "breaks per mile per year, one third and double the 0.30 assumption"),
    "c_social_max": (100_000, 1_000_000, "worst-case social cost of a failure, one fifth and double"),
    "emergency_multiplier": (1.5, 6.0, "emergency repair multiple, half and double"),
    "u0": (0.10, 0.60, "road user cost per vehicle-mile at worst condition, one third and double"),
    "reserve_max_fraction": (0.10, 0.25, "reserve cap; 0.10 to 0.25 is the range in docs/interfaces.md (0.25 is the base)"),
    "discount_rate": (0.03, 0.07, "discount rate, 3% to 7% per docs/evidence_plan.md"),
    "proposal_fraction": (0.015, 0.09, "menu size: share of segments each agent may propose on, half and triple (added after the zero-benefit control)"),
}


def measure(n, cfg):
    runs = run_all(n, reserve.ensure(cfg), strategies=STRATS)
    pair = lambda a, b, k="total_cost": [(x[k] - y[k]) / 1e6 for x, y in zip(runs[a], runs[b])]
    ds = [r["dig_savings"] / 1e6 for r in runs["coordinated"]]
    ci_, cp = pair("coordinated", "isolated"), pair("coordinated", "pooled")
    f = lambda v: dict(mean=st.mean(v), ci=ci(v), lower_in=sum(x < 0 for x in v), n=len(v))
    return dict(dig_savings=dict(mean=st.mean(ds), ci=ci(ds)), vs_isolated=f(ci_), vs_pooled=f(cp),
                total={s: st.mean(r["total_cost"] for r in runs[s]) / 1e6 for s in STRATS})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("n_seeds", nargs="?", type=int, default=10)
    ap.add_argument("--max-segments", type=int, default=800)
    ap.add_argument("--redraw", action="store_true", help="redraw the tornado charts from outputs/results/sensitivity.json")
    a = ap.parse_args()
    if a.redraw:
        return tornado(json.load(open("outputs/results/sensitivity.json")), pathlib.Path("outputs/results"))
    base_cfg = dict(CFG, max_segments=a.max_segments)
    out = dict(n_seeds=a.n_seeds, scope=f"compact {a.max_segments}-segment area", base=measure(a.n_seeds, base_cfg), one_at_a_time={}, top3={})
    for name, (lo, hi, why) in PARAMS.items():
        out["one_at_a_time"][name] = dict(why=why, base_value=CFG[name], low=dict(value=lo, **measure(a.n_seeds, dict(base_cfg, **{name: lo}))),
                                          high=dict(value=hi, **measure(a.n_seeds, dict(base_cfg, **{name: hi}))))
        print("done", name, flush=True)
    swing = lambda p: abs(out["one_at_a_time"][p]["high"]["vs_isolated"]["mean"] - out["one_at_a_time"][p]["low"]["vs_isolated"]["mean"])
    top = sorted(PARAMS, key=swing, reverse=True)[:3]
    out["top3"]["params"] = top
    out["top3"]["corners"] = []
    for combo in itertools.product((0, 1), repeat=3):
        over = {p: PARAMS[p][i] for p, i in zip(top, combo)}
        out["top3"]["corners"].append(dict(settings=over, **measure(a.n_seeds, dict(base_cfg, **over))))
        print("corner", over, flush=True)
    path = pathlib.Path("outputs/results/sensitivity.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1, default=str))
    snapshot.write(path, base_cfg, seeds=a.n_seeds, params=PARAMS)
    text = summarize(out)
    path.with_suffix(".txt").write_text(text)
    print(text)
    tornado(out, path.parent)


def summarize(o):
    L = [f"Sensitivity, {o['n_seeds']} paired seeds, {o['scope']}. ALL DATA SIMULATED. Negative = coordination is cheaper.",
         f"Base: dig savings {o['base']['dig_savings']['mean']:.2f}M, coordinated minus isolated {o['base']['vs_isolated']['mean']:+.2f}M "
         f"(±{o['base']['vs_isolated']['ci']:.2f}), coordinated minus pooled {o['base']['vs_pooled']['mean']:+.2f}M (±{o['base']['vs_pooled']['ci']:.2f})", "",
         f"{'parameter':<22}{'low -> high':<22}{'dig savings $M':<22}{'coord - isolated $M':<30}{'coord - pooled $M'}"]
    flips = []
    for p, r in o["one_at_a_time"].items():
        lo, hi = r["low"], r["high"]
        L.append(f"{p:<22}{str(lo['value']) + ' -> ' + str(hi['value']):<22}{lo['dig_savings']['mean']:>6.2f} -> {hi['dig_savings']['mean']:<8.2f}"
                 f"{lo['vs_isolated']['mean']:>+8.2f} -> {hi['vs_isolated']['mean']:<+10.2f}{lo['vs_pooled']['mean']:>+8.2f} -> {hi['vs_pooled']['mean']:+.2f}")
        for lab, key in (("coordinated minus isolated", "vs_isolated"), ("coordinated minus pooled", "vs_pooled")):
            for side in ("low", "high"):
                m = r[side][key]
                if m["mean"] - m["ci"] > 0 or m["mean"] + m["ci"] < 0:
                    if m["mean"] > 0:
                        flips.append(f"{p}={r[side]['value']}: {lab} is {m['mean']:+.2f}M (±{m['ci']:.2f}), coordination is WORSE")
                elif key == "vs_pooled" or True:
                    flips.append(f"{p}={r[side]['value']}: {lab} is {m['mean']:+.2f}M (±{m['ci']:.2f}), not distinguishable from zero")
    L += ["", f"Top three by swing in coordinated minus isolated: {', '.join(o['top3']['params'])}; all eight corners:"]
    for c in o["top3"]["corners"]:
        L.append(f"  {c['settings']}: vs isolated {c['vs_isolated']['mean']:+.2f}M (±{c['vs_isolated']['ci']:.2f}), vs pooled "
                 f"{c['vs_pooled']['mean']:+.2f}M (±{c['vs_pooled']['ci']:.2f}), dig savings {c['dig_savings']['mean']:.2f}M")
    allm = [r[s]["vs_isolated"] for r in o["one_at_a_time"].values() for s in ("low", "high")] + [c["vs_isolated"] for c in o["top3"]["corners"]]
    worse = [m for m in allm if m["mean"] > 0]
    L += ["", f"Coordinated is cheaper than isolated in {len(allm) - len(worse)} of {len(allm)} tested settings"
          + (" (the sign flips in the others)." if worse else " (the sign never flips in the tested ranges).")]
    allb = [r[s]["vs_pooled"] for r in o["one_at_a_time"].values() for s in ("low", "high")] + [c["vs_pooled"] for c in o["top3"]["corners"]]
    notsig = [m for m in allb if m["mean"] + m["ci"] >= 0]
    L.append(f"The board alone (coordinated minus pooled) is distinguishable from zero in the cheaper direction in {len(allb) - len(notsig)} of {len(allb)} settings.")
    L += ["", "Settings where a difference is not distinguishable from zero or is worse:"] + (["  " + f for f in flips] or ["  none"])
    return "\n".join(L) + "\n"


def tornado(o, outdir):
    """Two tornado charts as inline SVG: dig savings, and coordinated minus isolated total cost. Bars run from the low-setting
    value to the high-setting value; the line is the base."""
    def chart(title, getter, unit):
        base = getter(o["base"])
        rows = sorted(((p, getter(r["low"]), getter(r["high"]), r["low"]["value"], r["high"]["value"]) for p, r in o["one_at_a_time"].items()),
                      key=lambda x: -abs(x[2] - x[1]))
        vals = [base] + [v for r in rows for v in r[1:3]]
        lo, hi = min(vals), max(vals)
        pad = (hi - lo) * 0.08 or 1
        lo, hi = lo - pad, hi + pad
        W, X0, X1, H = 880, 230, 700, 26
        sx = lambda v: X0 + (v - lo) / (hi - lo) * (X1 - X0)
        h = 70 + H * len(rows) + 40
        s = [f'<svg viewBox="0 0 {W} {h}" width="{W}" role="img" aria-label="{title}"><text x="10" y="22" font-size="15" font-weight="600">{title}</text>',
             '<text x="10" y="40" font-size="11" fill="#7a5b00">SIMULATED DATA. Bars span the result at the low and high tested value; other assumptions at base.</text>']
        for i, (p, a_, b_, la, lb) in enumerate(rows):
            y = 60 + i * H
            x0, x1 = sorted((sx(a_), sx(b_)))
            s.append(f'<text x="10" y="{y + 16}" font-size="12">{p}</text><text x="{X0 - 6}" y="{y + 16}" font-size="10" text-anchor="end" fill="#52606b">{la} / {lb}</text>')
            s.append(f'<rect x="{x0:.1f}" y="{y + 3}" width="{max(1.5, x1 - x0):.1f}" height="{H - 8}" fill="#2563eb" opacity="0.75"><title>{p}: {a_:.2f} at {la}, {b_:.2f} at {lb}</title></rect>')
            s.append(f'<text x="{X1 + 12}" y="{y + 16}" font-size="11" fill="#52606b">{a_:.2f} to {b_:.2f}</text>')
        s.append(f'<line x1="{sx(base):.1f}" x2="{sx(base):.1f}" y1="52" y2="{60 + H * len(rows)}" stroke="#111" stroke-dasharray="4 3"/>'
                 f'<text x="{sx(base):.1f}" y="{h - 14}" font-size="11" text-anchor="middle">dashed line: base {base:.2f}</text>')
        if lo < 0 < hi and unit.startswith("$M diff"):
            s.append(f'<line x1="{sx(0):.1f}" x2="{sx(0):.1f}" y1="52" y2="{60 + H * len(rows)}" stroke="#b3261e"/><text x="{sx(0):.1f}" y="48" font-size="11" text-anchor="middle" fill="#b3261e">0 = no difference</text>')
        s.append(f'<text x="{W - 10}" y="22" font-size="11" text-anchor="end" fill="#52606b">{unit}</text></svg>')
        return "".join(s)
    html = ("<!doctype html><meta charset=utf-8><title>Sensitivity tornado</title><body style='font:13px system-ui;margin:16px;max-width:800px'>"
            f"<p><b>SIMULATED DATA.</b> {o['n_seeds']} paired seeds per setting, {o['scope']}.</p>"
            + chart("Dig savings from shared digs, coordinated", lambda m: m["dig_savings"]["mean"], "$M per ten-year run")
            + chart("Coordinated minus isolated, total cost (negative = coordination cheaper)", lambda m: m["vs_isolated"]["mean"], "$M difference per ten-year run")
            + "</body>")
    p = outdir / "tornado.html"
    p.write_text(html)
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            pg = b.new_page(viewport={"width": 840, "height": 900})
            pg.goto(p.resolve().as_uri())
            pg.screenshot(path=str(outdir / "tornado.png"), full_page=True)
            b.close()
    except Exception as e:
        print("tornado.png not written:", e)


if __name__ == "__main__":
    main()
