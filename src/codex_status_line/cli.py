"""Command line: `codex-status-line tmux` for a tmux bar, `codex-status-line hook` for Codex."""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from . import costs, openrouter, providers, status
from .processes import find_descendant_named, list_processes, process_start_time
from .render import Piece, render_plain, render_tmux
from .session_log import (
    SessionSummary,
    find_session_by_id,
    find_session_for_process,
    summarize_session,
)

# Each uncached cost is one HTTP call. Capping them keeps a refresh short when a long
# session is opened for the first time; the rest are fetched on later refreshes.
MAX_COST_LOOKUPS_PER_RUN = 10
# ps reports start times to the second, so allow a little slack when matching logs.
PROCESS_START_SLACK_SECONDS = 2


def git_branch(cwd):
    result = subprocess.run(
        ["git", "-C", cwd, "branch", "--show-current"],
        capture_output=True,
        text=True,
        timeout=2,
        # A non-zero exit just means the folder is not a git repository.
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def openrouter_billing_parts(summary, provider_config):
    key_variable = providers.openrouter_key_variable(provider_config)
    api_key = os.environ.get(key_variable)
    if not api_key:
        return [[Piece(f"set {key_variable} to see cost", "bad")]]

    cost_cache = openrouter.GenerationCostCache()
    billed_cost, pending_ids = costs.session_cost(
        summary.response_ids,
        cost_cache.costs,
        lambda response_id: openrouter.fetch_generation_cost(response_id, api_key),
        MAX_COST_LOOKUPS_PER_RUN,
    )
    cost_cache.save()
    price = None
    if pending_ids and summary.model:
        price = openrouter.model_price(summary.model)
    estimated_cost, all_estimated = costs.estimate_pending_cost(
        pending_ids, summary.request_usage, price
    )
    return status.openrouter_parts(
        billed_cost, estimated_cost, all_estimated, openrouter.key_info(api_key)
    )


def api_key_billing_parts(summary):
    price = openrouter.model_price(summary.model) if summary.model else None
    if price is None:
        return [status.tokens_part(summary)]
    return [status.estimate_part(costs.estimate_cost(summary, price))]


def billing_parts(summary):
    config_path = providers.codex_home() / "config.toml"
    provider_config = providers.load_provider_config(config_path, summary.provider_id)
    kind = providers.classify_session(summary, provider_config)
    if kind == providers.OPENROUTER:
        return openrouter_billing_parts(summary, provider_config)
    if kind == providers.CHATGPT_PLAN:
        return status.plan_parts(summary, datetime.now())
    has_used_tokens = summary.input_tokens or summary.output_tokens
    if not has_used_tokens:
        return []
    if kind == providers.OPENAI_API_KEY:
        return api_key_billing_parts(summary)
    return [status.tokens_part(summary)]


def status_parts(session_path, cwd, fallback_model):
    summary = summarize_session(session_path) if session_path else SessionSummary()
    model = summary.model or fallback_model
    parts = status.identity_parts(model, cwd, str(Path.home()), git_branch(cwd))
    context = status.context_part(summary)
    if context:
        parts.append(context)
    if session_path:
        parts.extend(billing_parts(summary))
    return parts


def run_tmux(pane_pid, cwd):
    codex_pid = find_descendant_named(list_processes(), pane_pid, "codex")
    if codex_pid is None:
        # The active pane is not running Codex, so the bar shows nothing.
        return ""
    started_at = process_start_time(codex_pid) - PROCESS_START_SLACK_SECONDS
    sessions_dir = providers.codex_home() / "sessions"
    session_path = find_session_for_process(sessions_dir, cwd, started_at)
    return render_tmux(status_parts(session_path, cwd, None))


def run_hook(hook_input):
    transcript_path = hook_input.get("transcript_path")
    if transcript_path:
        session_path = Path(transcript_path)
    else:
        sessions_dir = providers.codex_home() / "sessions"
        session_path = find_session_by_id(sessions_dir, hook_input["session_id"])
    parts = status_parts(session_path, hook_input["cwd"], hook_input.get("model"))
    return json.dumps({"systemMessage": render_plain(parts)})


def parse_arguments(argv):
    parser = argparse.ArgumentParser(
        prog="codex-status-line",
        description="Show model, context and cost of a Codex CLI session.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    tmux_parser = commands.add_parser("tmux", help="print a tmux segment for the active pane")
    tmux_parser.add_argument("--pane-pid", type=int, required=True, help="tmux #{pane_pid}")
    tmux_parser.add_argument("--cwd", required=True, help="tmux #{pane_current_path}")
    commands.add_parser("hook", help="run as a Codex Stop hook (reads hook JSON on stdin)")
    return parser.parse_args(argv)


def main(argv=None):
    arguments = parse_arguments(argv)
    if arguments.command == "tmux":
        try:
            print(run_tmux(arguments.pane_pid, arguments.cwd))
        except Exception as error:
            # tmux throws stderr away, so the error has to appear in the bar to be seen.
            print(f"#[fg=red]codex-status-line: {type(error).__name__}: {error}#[default]")
            raise
        return 0

    try:
        print(run_hook(json.load(sys.stdin)))
    except Exception as error:
        message = f"codex-status-line failed: {type(error).__name__}: {error}"
        print(json.dumps({"systemMessage": message}))
        raise
    return 0
