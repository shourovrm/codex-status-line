"""Turn status parts into text: tmux style codes for the bar, plain text for the Codex hook."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Piece:
    text: str
    style: str | None = None


TMUX_STYLES = {
    "model": "#[fg=cyan,bold]",
    "branch": "#[fg=green]",
    "cost": "#[fg=magenta]",
    "good": "#[fg=green]",
    "warn": "#[fg=yellow]",
    "bad": "#[fg=red]",
}
TMUX_SEPARATOR = "#[fg=colour240] │ #[default]"
PLAIN_SEPARATOR = " · "
# Meters turn yellow at half full and red at 80 %, like most usage bars.
WARN_FRACTION = 0.5
BAD_FRACTION = 0.8
THOUSAND = 1000
MILLION = 1_000_000


def meter(fraction, width=5):
    fraction = min(max(fraction, 0.0), 1.0)
    filled_cells = round(fraction * width)
    return "█" * filled_cells + "░" * (width - filled_cells)


def level_style(fraction):
    if fraction < WARN_FRACTION:
        return "good"
    if fraction < BAD_FRACTION:
        return "warn"
    return "bad"


def format_money(amount):
    if amount < 1:
        return f"${amount:.4f}"
    return f"${amount:.2f}"


def format_tokens(count):
    if count >= MILLION:
        return f"{count / MILLION:.1f}M"
    if count >= THOUSAND:
        return f"{count / THOUSAND:.1f}k"
    return str(count)


def short_model_name(model):
    return model.rsplit("/", 1)[-1]


def window_label(window_minutes):
    if window_minutes is None:
        return "limit"
    if window_minutes == 7 * 24 * 60:
        return "week"
    if window_minutes % (24 * 60) == 0:
        return f"{window_minutes // (24 * 60)}d"
    if window_minutes % 60 == 0:
        return f"{window_minutes // 60}h"
    return f"{window_minutes}m"


def format_reset_time(resets_at, now):
    reset = datetime.fromtimestamp(resets_at)
    if reset.date() == now.date():
        return reset.strftime("%H:%M")
    return reset.strftime("%a %H:%M")


def render_tmux(parts):
    rendered_parts = []
    for part in parts:
        text = ""
        for piece in part:
            # tmux reads "#" as the start of a format, so a literal one must be doubled.
            escaped = piece.text.replace("#", "##")
            if piece.style:
                text += f"{TMUX_STYLES[piece.style]}{escaped}#[default]"
            else:
                text += escaped
        rendered_parts.append(text)
    return TMUX_SEPARATOR.join(rendered_parts)


def render_plain(parts):
    return PLAIN_SEPARATOR.join("".join(piece.text for piece in part) for part in parts)
