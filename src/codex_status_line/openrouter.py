"""OpenRouter API calls, each cached on disk so a bar refreshing every few seconds stays cheap."""

import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API_ROOT = "https://openrouter.ai/api/v1"
REQUEST_TIMEOUT_SECONDS = 3
KEY_INFO_MAX_AGE_SECONDS = 60
MODEL_PRICES_MAX_AGE_SECONDS = 24 * 60 * 60
HTTP_NOT_FOUND = 404


def cache_dir():
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "codex-status-line"


def load_json_file(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text())


def save_json_file(path, value):
    # Write then rename, so another bar reading at the same moment never sees half a file.
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f".{os.getpid()}.tmp")
    temporary_path.write_text(json.dumps(value))
    temporary_path.replace(path)


def get(path, api_key=None):
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(API_ROOT + path, headers=headers)
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return json.load(response)["data"]


def fetch_generation_cost(response_id, api_key):
    """Return the billed cost of one request, or None while OpenRouter has not recorded it."""
    query = urllib.parse.urlencode({"id": response_id})
    try:
        data = get(f"/generation?{query}", api_key)
    except urllib.error.HTTPError as error:
        # OpenRouter answers 404 for a few seconds after a request, until its stats are written.
        if error.code == HTTP_NOT_FOUND:
            return None
        raise
    return data["total_cost"]


def cached(cache_name, max_age_seconds, fetch):
    cache_path = cache_dir() / cache_name
    entry = load_json_file(cache_path, None)
    if entry and time.time() - entry["fetched_at"] < max_age_seconds:
        return entry["data"]
    data = fetch()
    save_json_file(cache_path, {"fetched_at": time.time(), "data": data})
    return data


def key_info(api_key):
    """Spending and limit of one key. The cache file is named by a hash, never the key itself."""
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:16]
    return cached(f"key_{key_hash}.json", KEY_INFO_MAX_AGE_SECONDS, lambda: get("/key", api_key))


def model_price(model):
    """Per-token prices for a model, from OpenRouter's public list. None if it isn't listed."""
    models = cached("models.json", MODEL_PRICES_MAX_AGE_SECONDS, lambda: get("/models"))
    # OpenAI sessions log bare names such as gpt-6-luna; OpenRouter lists them as openai/gpt-6-luna.
    wanted_id = model if "/" in model else f"openai/{model}"
    for listed_model in models:
        if listed_model["id"] == wanted_id:
            return listed_model["pricing"]
    return None


class GenerationCostCache:
    """The request-id -> cost file shared by every bar and hook run."""

    def __init__(self):
        self.path = cache_dir() / "generation_costs.json"
        self.costs = load_json_file(self.path, {})

    def save(self):
        save_json_file(self.path, self.costs)
