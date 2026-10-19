import tempfile
import time
import unittest
from pathlib import Path

from codex_status_line import session_log
from helpers import (
    empty_rate_limits,
    plan_rate_limits,
    session_meta,
    token_count,
    turn_context,
    usage_record,
    write_rollout,
)


class FindSessionForProcessTest(unittest.TestCase):
    def test_ignores_logs_older_than_the_process(self):
        with tempfile.TemporaryDirectory() as directory:
            now = time.time()
            write_rollout(directory, "rollout-old.jsonl", [session_meta("/a")], now - 100)
            found = session_log.find_session_for_process(Path(directory), "/a", now - 10)
            self.assertIsNone(found)

    def test_prefers_matching_cwd_over_newer_log(self):
        with tempfile.TemporaryDirectory() as directory:
            now = time.time()
            matching = write_rollout(directory, "rollout-a.jsonl", [session_meta("/a")], now - 5)
            write_rollout(directory, "rollout-b.jsonl", [session_meta("/b")], now - 1)
            found = session_log.find_session_for_process(Path(directory), "/a", now - 10)
            self.assertEqual(found, matching)

    def test_falls_back_to_newest_log_when_no_cwd_matches(self):
        with tempfile.TemporaryDirectory() as directory:
            now = time.time()
            write_rollout(directory, "rollout-a.jsonl", [session_meta("/a")], now - 5)
            newest = write_rollout(directory, "rollout-b.jsonl", [session_meta("/b")], now - 1)
            found = session_log.find_session_for_process(Path(directory), "/elsewhere", now - 10)
            self.assertEqual(found, newest)


class FindSessionByIdTest(unittest.TestCase):
    def test_finds_log_named_after_the_session(self):
        with tempfile.TemporaryDirectory() as directory:
            nested = Path(directory) / "2026" / "10" / "19"
            nested.mkdir(parents=True)
            log_name = "rollout-2026-10-19T10-00-00-abc-123.jsonl"
            expected = write_rollout(nested, log_name, [], time.time())
            found = session_log.find_session_by_id(Path(directory), "abc-123")
            self.assertEqual(found, expected)


class SummarizeSessionTest(unittest.TestCase):
    def test_reads_provider_latest_model_context_tokens_and_unique_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_rollout(
                directory,
                "rollout-a.jsonl",
                [
                    session_meta("/a", model_provider="openrouter"),
                    turn_context("openai/gpt-5-mini"),
                    usage_record(
                        "gen-1", input_tokens=900, cached_input_tokens=100, output_tokens=50
                    ),
                    token_count(1000, 10000, input_tokens=900, output_tokens=100),
                    turn_context("openai/gpt-6-luna"),
                    usage_record("gen-2"),
                    usage_record("gen-2"),
                    token_count(
                        2500,
                        10000,
                        input_tokens=3000,
                        cached_input_tokens=800,
                        output_tokens=400,
                        rate_limits=empty_rate_limits(),
                    ),
                ],
                time.time(),
            )
            summary = session_log.summarize_session(path)
            self.assertEqual(summary.provider_id, "openrouter")
            self.assertEqual(summary.cwd, "/a")
            self.assertEqual(summary.model, "openai/gpt-6-luna")
            self.assertEqual(summary.context_used_tokens, 2500)
            self.assertEqual(summary.context_window_tokens, 10000)
            self.assertEqual(summary.input_tokens, 3000)
            self.assertEqual(summary.cached_input_tokens, 800)
            self.assertEqual(summary.output_tokens, 400)
            self.assertEqual(summary.response_ids, ["gen-1", "gen-2"])
            first_request = summary.request_usage["gen-1"]
            self.assertEqual(first_request.input_tokens, 900)
            self.assertEqual(first_request.cached_input_tokens, 100)
            self.assertEqual(first_request.output_tokens, 50)
            self.assertIsNone(summary.primary_limit)
            self.assertIsNone(summary.secondary_limit)

    def test_reads_plan_limit_windows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_rollout(
                directory,
                "rollout-a.jsonl",
                [
                    session_meta("/a", model_provider="openai"),
                    token_count(100, 1000, rate_limits=plan_rate_limits(12.5, 40.0)),
                ],
                time.time(),
            )
            summary = session_log.summarize_session(path)
            self.assertEqual(summary.primary_limit.used_percent, 12.5)
            self.assertEqual(summary.primary_limit.window_minutes, 300)
            self.assertEqual(summary.secondary_limit.used_percent, 40.0)
            self.assertEqual(summary.secondary_limit.resets_at, 1_800_400_000)

    def test_keeps_last_known_limits_when_a_later_snapshot_is_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_rollout(
                directory,
                "rollout-a.jsonl",
                [
                    token_count(100, 1000, rate_limits=plan_rate_limits(12.5, 40.0)),
                    token_count(200, 1000, rate_limits=None),
                ],
                time.time(),
            )
            summary = session_log.summarize_session(path)
            self.assertEqual(summary.primary_limit.used_percent, 12.5)

    def test_skips_a_half_written_last_line(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_rollout(directory, "rollout-a.jsonl", [usage_record("gen-1")], time.time())
            with path.open("a") as file:
                file.write('{"type": "token_usage_rec')
            summary = session_log.summarize_session(path)
            self.assertEqual(summary.response_ids, ["gen-1"])


if __name__ == "__main__":
    unittest.main()
