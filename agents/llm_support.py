"""Shared helpers for the Claude-driven agents (no SDK import here)."""
from agents.llm import BudgetExceeded, LLMUnavailable, ToolError


class StepFailed(Exception):
    """An attempt ended without a valid result."""


def check_rationale(text, cfg):
    mx = cfg["llm_rationale_max"]
    if not isinstance(text, str) or not text.strip():
        raise ToolError("rationale is required")
    if len(text) > mx:
        raise ToolError(f"rationale is {len(text)} characters; the limit is {mx}")
    return text.strip()


def spec(name, description, properties=None, required=()):
    return dict(name=name, description=description,
                input_schema=dict(type="object", properties=properties or {}, required=list(required)))


RATIONALE = {"type": "string", "description": "Why, in at most 280 characters. Quote numbers only as the tools returned them."}


def attempt_then_fallback(llm, agent, year, step, attempt, fallback):
    """Run attempt(prior_error) up to twice (reject and retry once); on a second failure log it and return fallback()."""
    err = None
    for i in range(2):
        try:
            return attempt(err)
        except (BudgetExceeded, LLMUnavailable):
            raise
        except Exception as e:  # StepFailed, or an API error that survived the retries
            err = f"{type(e).__name__}: {e}"
            llm.violations.append(dict(agent=agent, year=year, step=step, attempt=i + 1, error=err))
            llm._log(agent, year, "validation_failed", step, dict(attempt=i + 1), err)
    llm.fallbacks.append(dict(agent=agent, year=year, step=step, error=err))
    llm._log(agent, year, "fallback", step, None, "rule-based decision used after two failed attempts: " + err)
    return fallback()


def retry_note(err):
    return f"\n\nYour previous attempt was rejected: {err}\nFix this and try again." if err else ""


def validate_responses(items, allowed, cfg):
    """items: [{segment_id, action, rationale}]. allowed: {action: set of segment ids it may target}. All or nothing."""
    if not isinstance(items, list) or not items:
        raise ToolError("responses must be a non-empty list")
    errs, out, seen = [], [], set()
    for i, it in enumerate(items):
        try:
            act, seg = it.get("action"), it.get("segment_id")
            if act not in allowed:
                raise ToolError(f"action must be one of {sorted(allowed)}")
            if seg not in allowed[act]:
                raise ToolError(f"segment {seg} is not a valid target for '{act}' (valid: {sorted(allowed[act])})")
            if (act, seg) in seen:
                raise ToolError(f"duplicate {act} on {seg}")
            seen.add((act, seg))
            out.append(dict(segment_id=seg, action=act, rationale=check_rationale(it.get("rationale"), cfg)))
        except (ToolError, AttributeError) as e:
            errs.append(f"item {i}: {e}")
    if errs:
        raise ToolError("rejected, nothing applied. " + "; ".join(errs))
    return out


def validate_proposals(items, view, works, max_n, cfg):
    """items: [{segment_id, work, rationale}] over the agent's own view. All or nothing."""
    if not isinstance(items, list) or not items:
        raise ToolError("proposals must be a non-empty list")
    if len(items) > max_n:
        raise ToolError(f"at most {max_n} proposals; got {len(items)}")
    errs, out, seen = [], [], set()
    for i, it in enumerate(items):
        try:
            seg, work = it.get("segment_id"), it.get("work")
            if seg not in view:
                raise ToolError(f"unknown segment {seg}")
            if work not in works:
                raise ToolError(f"work must be one of {sorted(works)}")
            if (seg, work) in seen:
                raise ToolError(f"duplicate {work} on {seg}")
            seen.add((seg, work))
            out.append(dict(segment_id=seg, work=work, rationale=check_rationale(it.get("rationale"), cfg)))
        except (ToolError, AttributeError) as e:
            errs.append(f"item {i}: {e}")
    if errs:
        raise ToolError("rejected, nothing submitted. " + "; ".join(errs))
    return out


def board_view(board, year):
    """What any agent may read: the board messages of this year (text only, no payloads)."""
    return [dict(msg_id=m["msg_id"], round=m["round"], frm=m["from"], type=m["type"], segment_id=m["segment_id"],
                 text=m["text"]) for m in board.messages if m["year"] == year]


RESPONSE_ITEMS = lambda actions: {"type": "array", "items": {"type": "object", "required": ["segment_id", "action", "rationale"],
                                  "properties": {"segment_id": {"type": "string"}, "action": {"type": "string", "enum": actions},
                                                 "rationale": RATIONALE}}}
