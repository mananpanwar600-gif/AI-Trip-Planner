import logging
import re
from typing import Any

import httpx

from backend.app.config import get_settings
from backend.app.utils.exceptions import TravelProviderError

logger = logging.getLogger(__name__)


class _ApiKeyRedactionFilter(logging.Filter):
    _query_pattern = re.compile(
        r"([?&](?:apiKey|api_key)=)[^&\s\"']+",
        re.IGNORECASE,
    )
    _path_pattern = re.compile(
        r"(https://v6\.exchangerate-api\.com/v6/)[^/\s\"']+",
        re.IGNORECASE,
    )

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = self._query_pattern.sub(r"\1[redacted]", message)
        redacted = self._path_pattern.sub(r"\1[redacted]", redacted)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


httpx_logger = logging.getLogger("httpx")
httpx_logger.setLevel(logging.WARNING)
httpx_logger.addFilter(_ApiKeyRedactionFilter())
logging.getLogger("httpcore").setLevel(logging.WARNING)


async def get_json(
    provider: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    request_timeout = timeout or get_settings().external_api_timeout
    try:
        async with httpx.AsyncClient(timeout=request_timeout) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            payload = response.json()
    except httpx.TimeoutException as exc:
        raise TravelProviderError(provider, f"{provider} timed out.") from exc
    except httpx.HTTPStatusError as exc:
        logger.warning("%s returned HTTP %s.", provider, exc.response.status_code)
        raise TravelProviderError(
            provider, f"{provider} is temporarily unavailable."
        ) from exc
    except httpx.RequestError as exc:
        logger.warning("%s request failed (%s).", provider, exc.__class__.__name__)
        raise TravelProviderError(
            provider, f"Could not connect to {provider}."
        ) from exc
    except (ValueError, TypeError) as exc:
        raise TravelProviderError(
            provider, f"{provider} returned an invalid response."
        ) from exc

    if not isinstance(payload, dict):
        raise TravelProviderError(provider, f"{provider} returned an invalid response.")
    return payload
