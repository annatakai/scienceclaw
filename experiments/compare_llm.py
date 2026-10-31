"""Small live comparison: coordinated vs coordinated_llm. Usage: python3 -m experiments.compare_llm [seeds=5] [years=3] [max_usd=5]
Needs ANTHROPIC_API_KEY and `pip install anthropic`. Stops if the run's model spend reaches max_usd. ALL DATA SIMULATED.
Seed 0's coordinated_llm run is recorded to demo/recorded/ for the demo replay (python3 -m demo.build_demo --llm 0)."""
import json, pathlib, statistics as st, sys
from agents.llm import LLM, BudgetExceeded, LLMUnavailable
from sim.config import CFG
from sim.runner import simulate

n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
years = int(sys.argv[2]) if len(sys.argv) > 2 else 3
cap = float(sys.argv[3]) if len(sys.argv) > 3 else 5.0
# a compact 800-segment area (not the full city): every Claude call costs money. Build the demo with the same --max-segments 800.
cfg = dict(CFG, sim_years=years, max_segments=800)
llm = LLM(cfg, max_usd=cap)
try:
    llm.client
except LLMUnavailable as e:
    sys.exit(f"Cannot run the live comparison: {e}.")
rows, stopped = [], None
for seed in range(n):
    base = simulate("coordinated", seed=seed, cfg=cfg)
    try:
        r = simulate("coordinated_llm", seed=seed, cfg=cfg, llm=llm, record=(seed == 0))
    except BudgetExceeded as e:
        stopped = f"stopped at seed {seed}: {e}"
        break
    if seed == 0:
        out = pathlib.Path(__file__).resolve().parent.parent / "demo" / "recorded"
        out.mkdir(exist_ok=True)
        (out / "coordinated_llm_seed0.json").write_text(json.dumps(r, separators=(",", ":")))
    rows.append((seed, base, r))
print(f"{len(rows)} seeds x {years} years, budget ${cfg['annual_budget_per_mile']:,}/mile/yr, 800 segments, model {cfg['llm_model']}")
print(f"{'seed':>4} {'rule total $M':>14} {'claude total $M':>16} {'diff $M':>9} {'rule dig sav $M':>16} {'claude dig sav $M':>18} {'fails r/c':>10}")
for seed, b, c in rows:
    print(f"{seed:>4} {b['total_cost']/1e6:>14.2f} {c['total_cost']/1e6:>16.2f} {(c['total_cost']-b['total_cost'])/1e6:>+9.2f} "
          f"{b['dig_savings']/1e6:>16.2f} {c['dig_savings']/1e6:>18.2f} {b['fail']:>5}/{c['fail']:<4}")
if len(rows) > 1:
    d = [c["total_cost"] - b["total_cost"] for _, b, c in rows]
    print(f"mean paired total-cost difference (claude - rule): {st.mean(d)/1e6:+.2f}M  (n={len(d)}, sd {st.stdev(d)/1e6:.2f}M)")
u = llm.usage
print(f"tokens in/out: {u['input_tokens']:,}/{u['output_tokens']:,}  requests {u['requests']}  tool calls {u['tool_calls']}  "
      f"API retries {u['retries']}  cost ${u['usd']:.4f} (cap ${cap:.2f})")
print(f"fallbacks to rule-based: {len(llm.fallbacks)}; failed attempts (validation or API): {len(llm.violations)}")
for v in llm.violations:
    print("  ", v)
if stopped:
    print(stopped)
