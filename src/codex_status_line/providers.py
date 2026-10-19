"""Work out who bills a Codex session: OpenRouter, a ChatGPT plan, an OpenAI API key or other."""

import os
import tomllib
from pathlib import Path

OPENROUTER = "openrouter"
CHATGPT_PLAN = "chatgpt-plan"
OPENAI_API_KEY = "openai-api-key"
OTHER = "other"

DEFAULT_OPENROUTER_KEY_VARIABLE = "OPENROUTER_API_KEY"


def codex_home():
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))


def load_provider_config(config_path, provider_id):
    """Return the [model_providers.<provider_id>] table from Codex's config.toml, or {}."""
    if not config_path.exists():
        return {}
    with config_path.open("rb") as file:
        config = tomllib.load(file)
    return config.get("model_providers", {}).get(provider_id, {})


def classify_session(summary, provider_config):
    # Users name their OpenRouter provider whatever they like, so the address decides.
    if "openrouter.ai" in provider_config.get("base_url", ""):
        return OPENROUTER
    # Only a ChatGPT sign-in gets usage-limit windows back from OpenAI.
    if summary.primary_limit or summary.secondary_limit:
        return CHATGPT_PLAN
    if summary.provider_id in (None, "openai"):
        return OPENAI_API_KEY
    return OTHER


def openrouter_key_variable(provider_config):
    return provider_config.get("env_key", DEFAULT_OPENROUTER_KEY_VARIABLE)
