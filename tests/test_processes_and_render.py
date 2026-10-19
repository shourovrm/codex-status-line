import unittest
from datetime import datetime

from codex_status_line import processes, render
from codex_status_line.render import Piece


class FindDescendantTest(unittest.TestCase):
    # pid, parent pid, command name, as `ps -A -o pid=,ppid=,comm=` prints them.
    PROCESS_TABLE = [(10, 1, "fish"), (20, 10, "node"), (30, 20, "codex"), (40, 1, "codex")]

    def test_finds_codex_started_by_a_wrapper_under_the_shell(self):
        found = processes.find_descendant_named(self.PROCESS_TABLE, 10, "codex")
        self.assertEqual(found, 30)

    def test_root_itself_can_be_codex(self):
        self.assertEqual(processes.find_descendant_named(self.PROCESS_TABLE, 40, "codex"), 40)

    def test_returns_none_when_the_pane_runs_no_codex(self):
        table = [(10, 1, "fish"), (20, 10, "vim")]
        self.assertIsNone(processes.find_descendant_named(table, 10, "codex"))


class ParseElapsedTimeTest(unittest.TestCase):
    def test_parses_every_ps_etime_shape(self):
        self.assertEqual(processes.parse_elapsed_time("05:07"), 307)
        self.assertEqual(processes.parse_elapsed_time("02:05:07"), 7507)
        self.assertEqual(processes.parse_elapsed_time("3-02:05:07"), 3 * 86400 + 7507)
        self.assertEqual(processes.parse_elapsed_time("  00:09\n"), 9)


class FormattingTest(unittest.TestCase):
    def test_meter_rounds_to_cells(self):
        self.assertEqual(render.meter(0.0), "░░░░░")
        self.assertEqual(render.meter(0.5), "██░░░")
        self.assertEqual(render.meter(1.7), "█████")

    def test_money_shows_more_digits_for_small_amounts(self):
        self.assertEqual(render.format_money(0.0014588), "$0.0015")
        self.assertEqual(render.format_money(3.391), "$3.39")

    def test_tokens_are_shortened(self):
        self.assertEqual(render.format_tokens(950), "950")
        self.assertEqual(render.format_tokens(12_345), "12.3k")
        self.assertEqual(render.format_tokens(2_500_000), "2.5M")

    def test_window_label_names_common_plan_windows(self):
        self.assertEqual(render.window_label(300), "5h")
        self.assertEqual(render.window_label(10080), "week")
        self.assertEqual(render.window_label(1440), "1d")
        self.assertEqual(render.window_label(None), "limit")

    def test_reset_time_shows_clock_today_and_weekday_later(self):
        now = datetime(2026, 10, 19, 9, 0)
        later_today = datetime(2026, 10, 19, 14, 30).timestamp()
        in_three_days = datetime(2026, 10, 22, 10, 0).timestamp()
        self.assertEqual(render.format_reset_time(later_today, now), "14:30")
        self.assertEqual(render.format_reset_time(in_three_days, now), "Thu 10:00")


class RenderTest(unittest.TestCase):
    PARTS = [[Piece("main", "branch")], [Piece("░░░░░", "good"), Piece(" ctx 4%")]]

    def test_plain_has_no_style_codes(self):
        self.assertEqual(render.render_plain(self.PARTS), "main · ░░░░░ ctx 4%")

    def test_tmux_wraps_styled_pieces(self):
        line = render.render_tmux(self.PARTS)
        self.assertIn("#[fg=green]main#[default]", line)
        self.assertIn("#[fg=green]░░░░░#[default] ctx 4%", line)

    def test_tmux_escapes_hash_in_text(self):
        line = render.render_tmux([[Piece("branch#1")]])
        self.assertEqual(line, "branch##1")


if __name__ == "__main__":
    unittest.main()
