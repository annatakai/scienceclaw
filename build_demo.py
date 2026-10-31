"""Run all strategies once (seed 42), then write demo.html (self-contained replay). ALL DATA SIMULATED."""
import json, sys, webbrowser, pathlib
from run import simulate, STRATEGIES

seed = int(sys.argv[1]) if len(sys.argv) > 1 else 42
runs = {s: simulate(s, seed=seed, record=True) for s in STRATEGIES}
segs = runs["coordinated"]["segs"]
data = dict(order=STRATEGIES, segs=segs, runs={s: dict(years=r["years"]) for s, r in runs.items()})
html = (pathlib.Path(__file__).parent / "template.html").read_text(encoding="utf-8")
html = html.replace("__DATA__", json.dumps(data, separators=(",", ":"))).replace("__SEED__", str(seed))
out = pathlib.Path(__file__).parent / "demo.html"
out.write_text(html, encoding="utf-8")
print(f"wrote {out} ({out.stat().st_size // 1024} KB)")
for s, r in runs.items():
    print(f"{s:<12} total cost ${r['total_cost']/1e6:6.1f}M  capital ${r['spend']/1e6:5.1f}M  exp failures {r['exp_fail']:5.1f}  dig savings ${r['dig_savings']/1e6:4.2f}M")
if "--no-open" not in sys.argv:
    webbrowser.open(out.resolve().as_uri())
