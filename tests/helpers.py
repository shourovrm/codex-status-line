"""Builders for fake Codex rollout logs, matching the records Codex 0.163 writes."""

import json
import os
from pathlib import Path


def write_rollout(directory, name, records, modified_at):
    path = Path(directory) / name
    path.write_text("".join(json.dumps(record) + "\n" for record in records))
    os.utime(path, (modified_at, modified_at))
    return path


def session_meta(cwd, model_provider="openrouter"):
    return {"type": "session_meta", "payload": {"cwd": cwd, "model_provider": model_provider}}


def turn_context(model):
    return {"type": "turn_context", "payload": {"model": model}}


def usage_record(response_id, input_tokens=0, cached_input_tokens=0, output_tokens=0):
    usage = {
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "output_tokens": output_tokens,
    }
    return {"type": "token_usage_record", "payload": {"response_id": response_id, "usage": usage}}


def token_count(
    last_total_tokens,
    context_window,
    *,
    input_tokens=0,
    cached_input_tokens=0,
    output_tokens=0,
    rate_limits=None,
):
    return {
        "type": "event_msg",
        "payload": {
            "type": "token_count",
            "info": {
                "total_token_usage": {
                    "input_tokens": input_tokens,
                    "cached_input_tokens": cached_input_tokens,
                    "output_tokens": output_tokens,
                },
                "last_token_usage": {"total_tokens": last_total_tokens},
                "model_context_window": context_window,
            },
            "rate_limits": rate_limits,
        },
    }


def plan_rate_limits(primary_used, secondary_used):
    return {
        "primary": {
            "used_percent": primary_used,
            "window_minutes": 300,
            "resets_at": 1_800_000_000,
        },
        "secondary": {
            "used_percent": secondary_used,
            "window_minutes": 10080,
            "resets_at": 1_800_400_000,
        },
    }


def empty_rate_limits():
    # What an OpenRouter or API-key session logs: the snapshot exists but every window is null.
    return {"primary": None, "secondary": None, "credits": None, "plan_type": None}
