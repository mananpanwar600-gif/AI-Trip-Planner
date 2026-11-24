import logging


def test_httpx_urls_redact_query_api_keys(caplog) -> None:
    logger = logging.getLogger("httpx")
    with caplog.at_level(logging.INFO, logger="httpx"):
        logger.info(
            "HTTP Request: GET https://example.test/places?apiKey=do-not-log-this "
            '"HTTP/1.1 200 OK"'
        )

    assert "do-not-log-this" not in caplog.text
    assert "[redacted]" in caplog.text


def test_httpx_urls_redact_exchange_rate_api_keys(caplog) -> None:
    logger = logging.getLogger("httpx")
    with caplog.at_level(logging.INFO, logger="httpx"):
        logger.info(
            "HTTP Request: GET "
            "https://v6.exchangerate-api.com/v6/do-not-log-this/latest/USD "
            '"HTTP/1.1 200 OK"'
        )

    assert "do-not-log-this" not in caplog.text
    assert "[redacted]" in caplog.text
