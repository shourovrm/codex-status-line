import json
import os
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from codex_status_line import cli, status
from codex_status_line.render import render_plain
from codex_status_line.session_log import RateLimitWindow, SessionSummary
from helpers import plan_rate_limits, session_meta, token_count, turn_context, write_rollout


class IdentityPartsTest(unittest.TestCase):
    def test_shows_model_home_relative_folder_and_branch(self):
        parts = status.identity_parts("openai/gpt-6-luna", "/home/u/project", "/home/u", "main")
        self.assertEqual(render_plain(parts), "gpt-6-luna · ~/project · main")

    def test_leaves_out_branch_and_falls_back_to_codex_without_a_model(self):
        parts = status.identity_parts(None, "/srv", "/home/u", None)
        self.assertEqual(render_plain(parts), "codex · /srv")


class OpenRouterPartsTest(unittest.TestCase):
    def test_shows_session_today_and_month_against_the_limit(self):
        key_info = {"usage_daily": 0.0312, "usage_monthly": 3.39, "limit": 20}
        parts = status.openrouter_parts(0.0013, 0.0, True, key_info)
        self.assertEqual(
            render_plain(parts), "session $0.0013 · today $0.0312 · █░░░░ month $3.39/$20.00"
        )

    def test_marks_an_estimated_total_with_a_tilde(self):
        key_info = {"usage_daily": 0.5, "usage_monthly": 12.0, "limit": None}
        parts = status.openrouter_parts(0.25, 0.01, True, key_info)
        self.assertEqual(render_plain(parts), "session ~$0.2600 · today $0.5000 · month $12.00")

    def test_marks_requests_without_any_figure_with_a_plus(self):
        key_info = {"usage_daily": 0.5, "usage_monthly": 12.0, "limit": None}
        parts = status.openrouter_parts(0.25, 0.0, False, key_info)
        self.assertEqual(render_plain(parts), "session $0.2500+ · today $0.5000 · month $12.00")


class PlanPartsTest(unittest.TestCase):
    def test_shows_each_window_with_reset_time(self):
        now = datetime(2026, 10, 19, 9, 0)
        summary = SessionSummary(
            primary_limit=RateLimitWindow(40, 300, datetime(2026, 10, 19, 14, 30).timestamp()),
            secondary_limit=RateLimitWindow(21, 10080, datetime(2026, 10, 22, 10, 0).timestamp()),
        )
        self.assertEqual(
            render_plain(status.plan_parts(summary, now)),
            "5h ██░░░ 40% ↻14:30 · week █░░░░ 21% ↻Thu 10:00",
        )


class HookTest(unittest.TestCase):
    def test_prints_a_system_message_for_a_plan_session(self):
        with tempfile.TemporaryDirectory() as directory:
            log_path = write_rollout(
                directory,
                "rollout-x.jsonl",
                [
                    session_meta(directory, model_provider="openai"),
                    turn_context("gpt-6-luna"),
                    token_count(
                        5000, 100000, input_tokens=5000, rate_limits=plan_rate_limits(40, 21)
                    ),
                ],
                time.time(),
            )
            hook_input = {"transcript_path": str(log_path), "cwd": directory, "session_id": "x"}
            with mock.patch.dict(os.environ, {"CODEX_HOME": directory}):
                output = json.loads(cli.run_hook(hook_input))
            message = output["systemMessage"]
            self.assertTrue(message.startswith("gpt-6-luna · "), message)
            self.assertIn("░░░░░ ctx 5%", message)
            self.assertIn("5h ██░░░ 40%", message)
            self.assertIn("week █░░░░ 21%", message)

    def test_names_the_missing_key_variable_for_an_openrouter_session(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "config.toml").write_text(
                '[model_providers.router]\nbase_url = "https://openrouter.ai/api/v1"\n'
                'env_key = "TEST_ROUTER_KEY"\n'
            )
            log_path = write_rollout(
                directory,
                "rollout-x.jsonl",
                [session_meta(directory, model_provider="router"), token_count(10, 100)],
                time.time(),
            )
            hook_input = {"transcript_path": str(log_path), "cwd": directory, "session_id": "x"}
            environment = {"CODEX_HOME": directory}
            with mock.patch.dict(os.environ, environment):
                os.environ.pop("TEST_ROUTER_KEY", None)
                output = json.loads(cli.run_hook(hook_input))
            self.assertIn("set TEST_ROUTER_KEY to see cost", output["systemMessage"])


if __name__ == "__main__":
    unittest.main()
