"""Read the rollout logs Codex writes to ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl."""

import json
from dataclasses import dataclass, field


@dataclass
class RateLimitWindow:
    used_percent: float
    window_minutes: int | None
    resets_at: int | None


@dataclass
class TokenUsage:
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int


@dataclass
class SessionSummary:
    provider_id: str | None = None
    cwd: str | None = None
    model: str | None = None
    context_used_tokens: int | None = None
    context_window_tokens: int | None = None
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    response_ids: list[str] = field(default_factory=list)
    # Tokens of each request, used to estimate requests OpenRouter has not billed yet.
    request_usage: dict[str, TokenUsage] = field(default_factory=dict)
    primary_limit: RateLimitWindow | None = None
    secondary_limit: RateLimitWindow | None = None


def read_json_lines(path):
    with path.open() as file:
        for line in file:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                # Codex appends to the log while we read it, so the last line can be half written.
                continue


def read_session_cwd(path):
    for record in read_json_lines(path):
        if record.get("type") == "session_meta":
            return record["payload"].get("cwd")
    return None


def find_session_by_id(sessions_dir, session_id):
    matches = sorted(sessions_dir.rglob(f"rollout-*{session_id}.jsonl"))
    if not matches:
        return None
    return matches[-1]


def find_session_for_process(sessions_dir, cwd, started_after):
    """Return the newest log written since a Codex process started.

    A shared background Codex process writes every session's log, so a log cannot be
    traced to one terminal through open files. A log started in the same folder wins
    over a newer one, so two Codex sessions in two folders each find their own log.
    """
    candidates = []
    for path in sessions_dir.rglob("rollout-*.jsonl"):
        modified_at = path.stat().st_mtime
        if modified_at >= started_after:
            candidates.append((modified_at, path))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    for _, path in candidates:
        if read_session_cwd(path) == cwd:
            return path
    return candidates[0][1]


def parse_rate_limit_window(window):
    if not window or window.get("used_percent") is None:
        return None
    return RateLimitWindow(
        used_percent=window["used_percent"],
        window_minutes=window.get("window_minutes"),
        resets_at=window.get("resets_at"),
    )


def apply_token_count(summary, payload):
    info = payload.get("info") or {}
    total_usage = info.get("total_token_usage") or {}
    summary.input_tokens = total_usage.get("input_tokens", summary.input_tokens)
    summary.cached_input_tokens = total_usage.get(
        "cached_input_tokens", summary.cached_input_tokens
    )
    summary.output_tokens = total_usage.get("output_tokens", summary.output_tokens)
    last_usage = info.get("last_token_usage") or {}
    if "total_tokens" in last_usage:
        summary.context_used_tokens = last_usage["total_tokens"]
    if info.get("model_context_window"):
        summary.context_window_tokens = info["model_context_window"]

    rate_limits = payload.get("rate_limits") or {}
    # Not every snapshot carries the plan windows, so keep the last ones that did.
    primary = parse_rate_limit_window(rate_limits.get("primary"))
    secondary = parse_rate_limit_window(rate_limits.get("secondary"))
    if primary:
        summary.primary_limit = primary
    if secondary:
        summary.secondary_limit = secondary


def summarize_session(path):
    summary = SessionSummary()
    seen_response_ids = set()
    for record in read_json_lines(path):
        record_type = record.get("type")
        payload = record.get("payload") or {}
        if record_type == "session_meta":
            summary.provider_id = payload.get("model_provider")
            summary.cwd = payload.get("cwd")
        elif record_type == "turn_context" and payload.get("model"):
            summary.model = payload["model"]
        elif record_type == "token_usage_record":
            response_id = payload.get("response_id")
            if response_id and response_id not in seen_response_ids:
                seen_response_ids.add(response_id)
                summary.response_ids.append(response_id)
                usage = payload.get("usage") or {}
                summary.request_usage[response_id] = TokenUsage(
                    input_tokens=usage.get("input_tokens", 0),
                    cached_input_tokens=usage.get("cached_input_tokens", 0),
                    output_tokens=usage.get("output_tokens", 0),
                )
        elif record_type == "event_msg" and payload.get("type") == "token_count":
            apply_token_count(summary, payload)
    return summary
