"""Config snapshot written next to every results file (docs/evidence_plan.md section 5): every value the run used, with
its source, status and date from sim/config_meta.py, plus the code version. ALL DATA SIMULATED."""
import datetime
import json
import pathlib
import subprocess

from sim.config_meta import META

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _git():
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=5)
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, timeout=5).stdout.strip()
        return out.stdout.strip() + (" (uncommitted changes)" if dirty else "")
    except Exception:
        return "unknown"


def snapshot(cfg, **extra):
    vals = {k: v for k, v in cfg.items() if not k.startswith("llm")}
    tagged = {}
    for k, v in vals.items():
        m = META.get(k)
        tagged[k] = dict(value=v, status=m[0], source=m[1], checked=m[2], range_tested=m[3]) if m else dict(value=v)
    for k in ("loan_terms.interest_free_loan", "loan_terms.srf_loan", "loan_terms.bonds"):
        m = META[k]
        tagged[k] = dict(value=vals["loan_terms"][k.split(".")[1]], status=m[0], source=m[1], checked=m[2], range_tested=m[3])
    return dict(written=datetime.datetime.now().isoformat(timespec="seconds"), code_version=_git(), label="ALL ASSET DATA SIMULATED",
                config=tagged, **extra)


def write(results_path, cfg, **extra):
    """Write <results_path>.config.json next to a results file."""
    p = pathlib.Path(str(results_path) + ".config.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(snapshot(cfg, **extra), indent=1, default=str))
    return p
