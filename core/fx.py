import json
import logging
import math
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_CURRENCY = "GBP"
DISPLAY_CURRENCIES = ("USD", "EUR", "AUD")
CACHE_SECONDS = 6 * 60 * 60
FAILURE_RETRY_SECONDS = 5 * 60

logger = logging.getLogger(__name__)

_cache = {
    "expires_at": 0,
    "rates": None,
    "has_live_data": False,
}


def _copy_rates():
    return dict(_cache["rates"] or {"GBP": 1.0})


def _valid_rate(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(value) or value <= 0:
        return None

    return value


def get_exchange_rates():
    """
    Return GBP-based display rates for the trip planner.

    Rates are cached in memory for six hours. If the provider is
    unavailable, the last successful rates remain usable. Before the
    first successful lookup, LeavePrints falls back to GBP and retries
    after a short cooldown rather than blocking every page request.
    """
    now = time.time()

    if _cache["rates"] and now < _cache["expires_at"]:
        # Always return a copy. Edit-trip may temporarily inject a saved
        # historic rate and must never mutate the process-wide FX cache.
        return _copy_rates()

    params = urlencode({
        "base": BASE_CURRENCY,
        "symbols": ",".join(DISPLAY_CURRENCIES),
    })

    url = f"https://api.frankfurter.dev/v1/latest?{params}"

    req = Request(
        url,
        headers={
            "User-Agent": "LeavePrints/1.0",
            "Accept": "application/json",
        },
    )

    try:
        with urlopen(req, timeout=5) as response:
            data = json.load(response)

        if not isinstance(data, dict):
            raise ValueError("FX provider returned an invalid response.")

        api_rates = data.get("rates")
        if not isinstance(api_rates, dict):
            raise ValueError("FX provider returned no rates.")

        rates = {"GBP": 1.0}

        for currency in DISPLAY_CURRENCIES:
            rate = _valid_rate(api_rates.get(currency))
            if rate is not None:
                rates[currency] = rate

        # A partial response is still useful, but the planner will show
        # a limited-FX notice for any missing display currencies.
        _cache["rates"] = rates
        _cache["expires_at"] = now + CACHE_SECONDS
        _cache["has_live_data"] = True

        return dict(rates)

    except Exception:
        logger.exception("FX rate lookup failed")

        if _cache["rates"] and _cache["has_live_data"]:
            # Preserve the previous successful snapshot.
            _cache["expires_at"] = now + FAILURE_RETRY_SECONDS
            return _copy_rates()

        # First-run/offline fallback. Cache briefly so an outage does not
        # add the provider timeout to every planner page request.
        _cache["rates"] = {"GBP": 1.0}
        _cache["expires_at"] = now + FAILURE_RETRY_SECONDS
        _cache["has_live_data"] = False

        return {"GBP": 1.0}
