"""The ONLY module that talks to the model (Anthropic SDK). One wrapper for every Claude-driven agent:
tool-use loop (max tool calls per agent per year), retries with backoff, token and dollar counter, tracing.
The model never does arithmetic: every number it sees comes from a tool that calls existing code."""
import os
import time


class LLMUnavailable(RuntimeError):
    """No SDK or no ANTHROPIC_API_KEY."""


class BudgetExceeded(RuntimeError):
    """The dollar cap for the run was reached."""


class ToolError(Exception):
    """A tool refused its input. The message goes back to the model as an error tool result."""


_RETRY_NAMES = {"APIConnectionError", "APITimeoutError", "InternalServerError", "RateLimitError", "OverloadedError"}


def _retryable(e):
    code = getattr(e, "status_code", None)
    return type(e).__name__ in _RETRY_NAMES or code in (408, 409, 429) or (isinstance(code, int) and code >= 500)


def _blocks(content):
    out = []
    for b in content:
        if b.type == "text":
            out.append({"type": "text", "text": b.text})
        elif b.type == "tool_use":
            out.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
    return out


class LLM:
    def __init__(self, cfg, client=None, tracer=None, max_usd=None, sleep=time.sleep, retries=4, backoff=1.0):
        self.cfg, self.tracer, self.max_usd = cfg, tracer, max_usd
        self._client, self.sleep, self.retries, self.backoff = client, sleep, retries, backoff
        self.usage = dict(requests=0, tool_calls=0, input_tokens=0, output_tokens=0, usd=0.0, retries=0)
        self.fallbacks = []   # one entry per time an agent fell back to its rule-based decision
        self.violations = []  # one entry per failed attempt (validation error, API failure)

    @property
    def client(self):
        if self._client is None:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise LLMUnavailable("ANTHROPIC_API_KEY is not set")
            try:
                import anthropic
            except ImportError as e:
                raise LLMUnavailable("the anthropic package is not installed (pip install anthropic)") from e
            self._client = anthropic.Anthropic(max_retries=0)  # we retry ourselves so retries are counted
        return self._client

    def _log(self, agent, year, kind, name, inp=None, out=None):
        if self.tracer:
            self.tracer.log(agent, kind, name, inp, out, year)

    def _create(self, **kw):
        for i in range(self.retries):
            try:
                return self.client.messages.create(**kw)
            except Exception as e:
                if isinstance(e, LLMUnavailable) or not _retryable(e) or i == self.retries - 1:
                    raise
                self.usage["retries"] += 1
                self.sleep(self.backoff * 2 ** i)

    def _count(self, resp):
        u = resp.usage
        pin, pout = self.cfg["llm_prices"][self.cfg["llm_model"]]
        i, o = getattr(u, "input_tokens", 0) or 0, getattr(u, "output_tokens", 0) or 0
        self.usage["requests"] += 1
        self.usage["input_tokens"] += i
        self.usage["output_tokens"] += o
        self.usage["usd"] += (i * pin + o * pout) / 1e6

    def run(self, agent, year, system, user, tools, handlers, stop_when=None):
        """Tool-use loop. At most cfg['llm_max_tool_calls'] tool calls; extra calls get an error result and the loop ends.
        Stops when the model replies without a tool call or stop_when() is true. Returns the number of tool calls used."""
        cap = self.cfg["llm_max_tool_calls"]
        messages = [{"role": "user", "content": user}]
        used = 0
        while True:
            if self.max_usd is not None and self.usage["usd"] >= self.max_usd:
                raise BudgetExceeded(f"LLM spend ${self.usage['usd']:.2f} reached the ${self.max_usd:.2f} cap")
            resp = self._create(model=self.cfg["llm_model"], max_tokens=self.cfg["llm_max_tokens"], system=system,
                                messages=messages, tools=tools,
                                extra_body={"output_config": {"effort": self.cfg["llm_effort"]}})
            self._count(resp)
            self._log(agent, year, "usage", "request", None, dict(self.usage))
            uses = [b for b in resp.content if b.type == "tool_use"]
            if not uses:
                return used
            messages.append({"role": "assistant", "content": _blocks(resp.content)})
            results, over = [], False
            for tu in uses:
                if used >= cap:
                    out, err, over = {"error": f"tool call limit ({cap}) reached"}, True, True
                else:
                    used += 1
                    self.usage["tool_calls"] += 1
                    try:
                        out, err = handlers[tu.name](**tu.input), False
                    except ToolError as e:
                        out, err = {"error": str(e)}, True
                    except (KeyError, TypeError) as e:  # unknown tool or malformed arguments
                        out, err = {"error": f"bad tool call {tu.name}: {e}"}, True
                self._log(agent, year, "tool_call", tu.name, tu.input, out)
                results.append({"type": "tool_result", "tool_use_id": tu.id, "content": _json(out), "is_error": err})
            messages.append({"role": "user", "content": results})
            if over or (stop_when and stop_when()):
                return used


def _json(x):
    import json
    return json.dumps(x, default=str)
