import logging
import math

import httpx

from backend.app.config import get_settings
from backend.app.utils.exceptions import TravelProviderError

logger = logging.getLogger(__name__)
EXCHANGE_RATE_URL = "https://v6.exchangerate-api.com/v6"


async def get_rates_to_target(target_currency: str) -> tuple[dict[str, float], str]:
    settings = get_settings()
    if not settings.exchange_rate_api_key:
        raise TravelProviderError(
            "ExchangeRate-API",
            "EXCHANGE_RATE_API_KEY is not configured; currency conversion was skipped.",
        )

    url = (
        f"{EXCHANGE_RATE_URL}/{settings.exchange_rate_api_key}/latest/"
        f"{target_currency}"
    )
    try:
        async with httpx.AsyncClient(timeout=settings.external_api_timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
    except httpx.TimeoutException as exc:
        raise TravelProviderError(
            "ExchangeRate-API", "Exchange rate lookup timed out."
        ) from exc
    except httpx.HTTPStatusError as exc:
        logger.warning("ExchangeRate-API returned HTTP %s.", exc.response.status_code)
        raise TravelProviderError(
            "ExchangeRate-API", "Exchange rate lookup is temporarily unavailable."
        ) from exc
    except httpx.RequestError as exc:
        logger.warning(
            "ExchangeRate-API request failed (%s).", exc.__class__.__name__
        )
        raise TravelProviderError(
            "ExchangeRate-API", "Could not connect to the exchange rate service."
        ) from exc
    except (ValueError, TypeError) as exc:
        raise TravelProviderError(
            "ExchangeRate-API", "Exchange rate service returned invalid data."
        ) from exc

    if (
        not isinstance(payload, dict)
        or payload.get("result") != "success"
        or payload.get("base_code") != target_currency
        or not isinstance(payload.get("conversion_rates"), dict)
    ):
        raise TravelProviderError(
            "ExchangeRate-API", "Exchange rate service returned invalid data."
        )

    rates_to_target = {target_currency: 1.0}
    for currency, target_to_source in payload["conversion_rates"].items():
        if not isinstance(currency, str):
            continue
        try:
            rate = float(target_to_source)
        except (TypeError, ValueError):
            continue
        if math.isfinite(rate) and rate > 0:
            rates_to_target[currency] = 1 / rate

    updated_at = payload.get("time_last_update_utc")
    if not isinstance(updated_at, str) or not updated_at.strip():
        raise TravelProviderError(
            "ExchangeRate-API", "Exchange rate service omitted its update time."
        )
    return rates_to_target, updated_at.strip()
