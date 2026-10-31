"""JSONL trace of every tool call, board message and fallback of an LLM run: traces/<strategy>_seed<seed>.jsonl."""
import json
import pathlib
import time

TRACE_DIR = pathlib.Path(__file__).resolve().parent.parent / "traces"


class Tracer:
    def __init__(self, strategy, seed, directory=None):
        d = pathlib.Path(directory) if directory else TRACE_DIR
        d.mkdir(parents=True, exist_ok=True)
        self.path = d / f"{strategy}_seed{seed}.jsonl"
        self.path.write_text("")
        self.year = None

    def log(self, agent, kind, name, inp=None, out=None, year=None):
        rec = dict(t=round(time.time(), 3), year=year if year is not None else self.year, agent=agent, kind=kind,
                   name=name, input=inp, output=out)
        with self.path.open("a") as f:
            f.write(json.dumps(rec, default=str) + "\n")

    def board(self, m):
        self.log(m["from"], "board", m["type"], dict(segment_id=m["segment_id"], round=m["round"]), m["text"], m["year"])

    def read(self):
        return [json.loads(l) for l in self.path.read_text().splitlines() if l]
