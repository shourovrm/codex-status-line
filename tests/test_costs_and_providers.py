import tempfile
import unittest
from pathlib import Path

from codex_status_line import costs, providers
from codex_status_line.session_log import RateLimitWindow, SessionSummary, TokenUsage


class SessionCostTest(unittest.TestCase):
    def test_uses_cache_and_counts_not_yet_billed_requests_as_pending(self):
        cost_cache = {"gen-1": 0.5}
        fetched_ids = []

        def fetch_cost(response_id):
            fetched_ids.append(response_id)
            return {"gen-2": 0.25}.get(response_id)

        billed_cost, pending_ids = costs.session_cost(
            ["gen-1", "gen-2", "gen-3"], cost_cache, fetch_cost, max_lookups=10
        )
        self.assertAlmostEqual(billed_cost, 0.75)
        self.assertEqual(pending_ids, ["gen-3"])
        self.assertEqual(fetched_ids, ["gen-2", "gen-3"])
        self.assertEqual(cost_cache["gen-2"], 0.25)
        self.assertNotIn("gen-3", cost_cache)

    def test_stops_looking_up_after_the_limit(self):
        def fetch_cost(_response_id):
            return 1.0

        billed_cost, pending_ids = costs.session_cost(
            ["gen-1", "gen-2", "gen-3"], {}, fetch_cost, max_lookups=2
        )
        self.assertAlmostEqual(billed_cost, 2.0)
        self.assertEqual(pending_ids, ["gen-3"])


class EstimateCostTest(unittest.TestCase):
    def test_charges_cached_input_at_the_cache_price(self):
        summary = SessionSummary(input_tokens=1000, cached_input_tokens=400, output_tokens=100)
        price = {"prompt": "0.000002", "completion": "0.00001", "input_cache_read": "0.0000005"}
        # 600 uncached * 2e-6 + 400 cached * 5e-7 + 100 output * 1e-5
        self.assertAlmostEqual(costs.estimate_cost(summary, price), 0.0012 + 0.0002 + 0.001)

    def test_charges_cached_input_at_full_price_when_no_cache_price_is_listed(self):
        summary = SessionSummary(input_tokens=1000, cached_input_tokens=400, output_tokens=0)
        price = {"prompt": "0.000002", "completion": "0.00001"}
        self.assertAlmostEqual(costs.estimate_cost(summary, price), 0.002)


class EstimatePendingCostTest(unittest.TestCase):
    PRICE = {"prompt": "0.000001", "completion": "0.000002"}

    def test_estimates_every_pending_request_with_known_usage(self):
        usage = {"gen-1": TokenUsage(1000, 0, 500), "gen-2": TokenUsage(2000, 0, 0)}
        estimated_cost, all_estimated = costs.estimate_pending_cost(
            ["gen-1", "gen-2"], usage, self.PRICE
        )
        self.assertAlmostEqual(estimated_cost, 0.002 + 0.002)
        self.assertTrue(all_estimated)

    def test_reports_requests_it_cannot_estimate(self):
        usage = {"gen-1": TokenUsage(1000, 0, 0)}
        estimated_cost, all_estimated = costs.estimate_pending_cost(
            ["gen-1", "gen-2"], usage, self.PRICE
        )
        self.assertAlmostEqual(estimated_cost, 0.001)
        self.assertFalse(all_estimated)

    def test_without_a_price_nothing_is_estimated(self):
        usage = {"gen-1": TokenUsage(1000, 0, 0)}
        self.assertEqual(costs.estimate_pending_cost(["gen-1"], usage, None), (0.0, False))
        self.assertEqual(costs.estimate_pending_cost([], usage, None), (0.0, True))


class ProviderConfigTest(unittest.TestCase):
    def test_reads_one_provider_table(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.toml"
            config_path.write_text(
                "[model_providers.or]\n"
                'base_url = "https://openrouter.ai/api/v1"\n'
                'env_key = "MY_KEY"\n'
            )
            config = providers.load_provider_config(config_path, "or")
            self.assertEqual(config["env_key"], "MY_KEY")

    def test_missing_file_or_provider_gives_empty_config(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(providers.load_provider_config(Path(directory) / "none.toml", "x"), {})


class ClassifySessionTest(unittest.TestCase):
    def test_openrouter_is_recognised_by_base_url_whatever_the_provider_id(self):
        summary = SessionSummary(provider_id="my-router")
        config = {"base_url": "https://openrouter.ai/api/v1"}
        self.assertEqual(providers.classify_session(summary, config), providers.OPENROUTER)

    def test_limit_windows_mean_a_chatgpt_plan(self):
        window = RateLimitWindow(used_percent=10, window_minutes=300, resets_at=None)
        summary = SessionSummary(provider_id="openai", primary_limit=window)
        self.assertEqual(providers.classify_session(summary, {}), providers.CHATGPT_PLAN)

    def test_openai_without_limit_windows_is_an_api_key(self):
        summary = SessionSummary(provider_id="openai")
        self.assertEqual(providers.classify_session(summary, {}), providers.OPENAI_API_KEY)

    def test_anything_else_is_other(self):
        summary = SessionSummary(provider_id="ollama")
        config = {"base_url": "http://localhost:11434/v1"}
        self.assertEqual(providers.classify_session(summary, config), providers.OTHER)


if __name__ == "__main__":
    unittest.main()
