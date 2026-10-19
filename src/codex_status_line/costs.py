"""Add up what a session cost, exactly from OpenRouter or estimated from token counts."""


def session_cost(response_ids, cost_cache, fetch_cost, max_lookups):
    """Return (billed cost, ids of requests not billed or not fetched yet).

    fetch_cost returns None for a request OpenRouter has not recorded yet. Costs found
    are stored in cost_cache, so each request is fetched only once.
    """
    billed_cost = 0.0
    pending_ids = []
    lookups_done = 0
    for response_id in response_ids:
        if response_id in cost_cache:
            billed_cost += cost_cache[response_id]
            continue
        if lookups_done >= max_lookups:
            pending_ids.append(response_id)
            continue
        lookups_done += 1
        cost = fetch_cost(response_id)
        if cost is None:
            pending_ids.append(response_id)
            continue
        cost_cache[response_id] = cost
        billed_cost += cost
    return billed_cost, pending_ids


def estimate_cost(usage, price):
    """Estimate cost from token counts and per-token prices.

    usage is anything with input_tokens, cached_input_tokens and output_tokens: one
    request's TokenUsage or a whole SessionSummary. price uses OpenRouter's /models
    format: decimal strings in dollars per token.
    """
    prompt_price = float(price["prompt"])
    cache_read_price = float(price.get("input_cache_read") or prompt_price)
    completion_price = float(price["completion"])
    uncached_input_tokens = usage.input_tokens - usage.cached_input_tokens
    return (
        uncached_input_tokens * prompt_price
        + usage.cached_input_tokens * cache_read_price
        + usage.output_tokens * completion_price
    )


def estimate_pending_cost(pending_ids, request_usage, price):
    """Return (estimated cost of the pending requests, whether all of them could be estimated)."""
    if not pending_ids:
        return 0.0, True
    if price is None:
        return 0.0, False
    estimated_cost = 0.0
    all_estimated = True
    for response_id in pending_ids:
        usage = request_usage.get(response_id)
        if usage is None:
            all_estimated = False
            continue
        estimated_cost += estimate_cost(usage, price)
    return estimated_cost, all_estimated
