"""Build the parts of the status line. Each part is a list of styled pieces."""

from .render import (
    Piece,
    format_money,
    format_reset_time,
    format_tokens,
    level_style,
    meter,
    window_label,
)


def home_relative(path, home):
    if path == home or path.startswith(home + "/"):
        return "~" + path[len(home) :]
    return path


def identity_parts(cwd, home, branch):
    # The model name is left out: Codex's own footer already shows it.
    parts = [[Piece(home_relative(cwd, home))]]
    if branch:
        parts.append([Piece(branch, "branch")])
    return parts


def meter_pieces(fraction):
    return [Piece(meter(fraction), level_style(fraction))]


def context_part(summary):
    if not summary.context_used_tokens or not summary.context_window_tokens:
        return None
    fraction = summary.context_used_tokens / summary.context_window_tokens
    return meter_pieces(fraction) + [Piece(f" ctx {fraction:.0%}")]


def openrouter_parts(billed_cost, estimated_cost, all_estimated):
    # OpenRouter bills a request 5 to 10 seconds after it ends. Until then its cost is
    # estimated ("~"); "+" means some requests have no figure at all yet.
    estimate_marker = "~" if estimated_cost else ""
    missing_marker = "" if all_estimated else "+"
    total_text = format_money(billed_cost + estimated_cost)
    return [[Piece(f"session {estimate_marker}{total_text}{missing_marker}", "cost")]]


def plan_window_part(window, now):
    fraction = window.used_percent / 100
    pieces = [Piece(f"{window_label(window.window_minutes)} ")]
    pieces += meter_pieces(fraction)
    pieces.append(Piece(f" {window.used_percent:.0f}%"))
    if window.resets_at:
        pieces.append(Piece(f" ↻{format_reset_time(window.resets_at, now)}"))
    return pieces


def plan_parts(summary, now):
    parts = []
    for window in (summary.primary_limit, summary.secondary_limit):
        if window:
            parts.append(plan_window_part(window, now))
    return parts


def estimate_part(estimated_cost):
    return [Piece(f"session ~{format_money(estimated_cost)} est.", "cost")]


def tokens_part(summary):
    total_tokens = summary.input_tokens + summary.output_tokens
    return [Piece(f"{format_tokens(total_tokens)} tokens")]
