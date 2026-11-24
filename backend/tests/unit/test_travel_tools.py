import asyncio
import json
from datetime import date

import httpx
import pytest

from backend.app.schemas.context import Coordinates
from backend.app.schemas.trip import TripRequest
from backend.app.tools import currency, geocoding, tavily, weather
from backend.app.tools import http as http_tools
from backend.app.utils.exceptions import TravelProviderError


def test_weather_tool_parses_open_meteo_forecast(monkeypatch) -> None:
    payload = {
        "daily": {
            "time": ["2026-11-24"],
            "weather_code": [1],
            "temperature_2m_max": [17],
            "temperature_2m_min": [8],
            "precipitation_probability_max": [20],
        }
    }

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    original_client = httpx.AsyncClient

    def mock_client(*, timeout: float) -> httpx.AsyncClient:
        return original_client(
            transport=httpx.MockTransport(handler),
            timeout=timeout,
        )

    monkeypatch.setattr(http_tools.httpx, "AsyncClient", mock_client)
    forecast = asyncio.run(
        weather.get_forecast(
            Coordinates(
                name="Kyoto",
                latitude=35.0,
                longitude=135.0,
            ),
            days=1,
        )
    )

    assert forecast[0].summary == "mainly clear"
    assert forecast[0].minimum_celsius == 8
    assert forecast[0].maximum_celsius == 17


def test_weather_tool_reports_incomplete_provider_data(monkeypatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"daily": {}})

    original_client = httpx.AsyncClient

    def mock_client(*, timeout: float) -> httpx.AsyncClient:
        return original_client(
            transport=httpx.MockTransport(handler),
            timeout=timeout,
        )

    monkeypatch.setattr(http_tools.httpx, "AsyncClient", mock_client)
    with pytest.raises(TravelProviderError, match="incomplete forecast"):
        asyncio.run(
            weather.get_forecast(
                Coordinates(
                    name="Kyoto",
                    latitude=35.0,
                    longitude=135.0,
                ),
                days=1,
            )
        )


def test_weather_tool_requests_the_selected_date_range(monkeypatch) -> None:
    requested_params = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_params.append(request.url.params)
        return httpx.Response(
            200,
            json={
                "daily": {
                    "time": ["2030-01-02", "2030-01-03"],
                    "weather_code": [1, 2],
                    "temperature_2m_max": [17, 18],
                    "temperature_2m_min": [8, 9],
                    "precipitation_probability_max": [20, 30],
                }
            },
        )

    original_client = httpx.AsyncClient

    def mock_client(*, timeout: float) -> httpx.AsyncClient:
        return original_client(
            transport=httpx.MockTransport(handler),
            timeout=timeout,
        )

    monkeypatch.setattr(http_tools.httpx, "AsyncClient", mock_client)
    start_date = date(2030, 1, 2)
    end_date = date(2030, 1, 3)
    forecast = asyncio.run(
        weather.get_forecast(
            Coordinates(name="Kyoto", latitude=35.0, longitude=135.0),
            days=2,
            start_date=start_date,
            end_date=end_date,
        )
    )

    assert len(forecast) == 2
    assert requested_params[0]["start_date"] == "2030-01-02"
    assert requested_params[0]["end_date"] == "2030-01-03"
    assert "forecast_days" not in requested_params[0]


def test_geocoder_preserves_indian_state_and_country_code(monkeypatch) -> None:
    async def get_location(_provider, _url, *, params, headers=None):
        return {
            "results": [
                {
                    "name": "Jaipur",
                    "admin1": "Rajasthan",
                    "country": "India",
                    "country_code": "in",
                    "latitude": 26.9,
                    "longitude": 75.8,
                }
            ]
        }

    monkeypatch.setattr(geocoding, "get_json", get_location)

    location = asyncio.run(geocoding.geocode_city("Jaipur"))

    assert location.region == "Rajasthan"
    assert location.country == "India"
    assert location.country_code == "IN"


def test_tavily_price_search_uses_route_dates_and_returns_sources(monkeypatch) -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.url, request.read()))
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Kyoto budget guide",
                        "url": "https://example.test/kyoto-costs",
                        "content": "Budget lodging and meals.",
                    }
                ]
            },
        )

    original_client = httpx.AsyncClient

    def mock_client(*, timeout: float) -> httpx.AsyncClient:
        return original_client(
            transport=httpx.MockTransport(handler),
            timeout=timeout,
        )

    monkeypatch.setattr(tavily.httpx, "AsyncClient", mock_client)
    monkeypatch.setenv("TAVILY_API_KEY", "test-tavily-key")
    trip = TripRequest(
        destination="Kyoto",
        origin="Delhi",
        start_date=date(2030, 1, 2),
        end_date=date(2030, 1, 4),
        currency="INR",
        travelers=2,
    )

    destination_facts = asyncio.run(tavily.search_destination_prices(trip))
    flight_facts = asyncio.run(tavily.search_flight_prices(trip))

    assert len(requests) == 2
    assert all(url == tavily.TAVILY_SEARCH_URL for url, _ in requests)
    payloads = [json.loads(body) for _, body in requests]
    assert payloads[0]["api_key"] == "test-tavily-key"
    assert "budget travel" in payloads[0]["query"]
    assert "from Delhi to Kyoto" in payloads[1]["query"]
    assert "2030-01-02 through 2030-01-04" in payloads[1]["query"]
    assert destination_facts[0].source == "Tavily destination cost research"
    assert destination_facts[0].title == "Kyoto budget guide"
    assert str(destination_facts[0].url) == "https://example.test/kyoto-costs"
    assert destination_facts[0].detail == "Budget lodging and meals."
    assert flight_facts[0].source == "Tavily flight price search"


def test_tavily_destination_guide_is_state_specific_for_india(monkeypatch) -> None:
    captured_payloads = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_payloads.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Rajasthan tourism",
                        "url": "https://example.test/rajasthan",
                        "content": "State-specific visitor information.",
                    }
                ]
            },
        )

    original_client = httpx.AsyncClient

    def mock_client(*, timeout: float) -> httpx.AsyncClient:
        return original_client(
            transport=httpx.MockTransport(handler),
            timeout=timeout,
        )

    monkeypatch.setattr(tavily.httpx, "AsyncClient", mock_client)
    monkeypatch.setenv("TAVILY_API_KEY", "test-tavily-key")

    facts = asyncio.run(
        tavily.search_destination_guide(
            TripRequest(destination="Jaipur"),
            region="Rajasthan",
            country="India",
            country_code="IN",
        )
    )

    assert len(facts) == 1
    assert facts[0].source == "Tavily destination guide"
    assert "Jaipur, Rajasthan, India" in captured_payloads[0]["query"]
    assert "Do not mix in unrelated Indian states" in captured_payloads[0]["query"]
    assert captured_payloads[0]["max_results"] == 3


def test_tavily_price_search_requires_a_configured_key(monkeypatch) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "")
    with pytest.raises(TravelProviderError, match="TAVILY_API_KEY"):
        asyncio.run(
            tavily.search_destination_prices(TripRequest(destination="Kyoto"))
        )


def test_exchange_rate_tool_returns_source_to_target_rates(monkeypatch) -> None:
    requested_urls = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(request.url)
        return httpx.Response(
            200,
            json={
                "result": "success",
                "base_code": "INR",
                "time_last_update_utc": "Tue, 24 Nov 2026 00:00:00 +0000",
                "conversion_rates": {
                    "INR": 1,
                    "USD": 0.012,
                    "JPY": 1.75,
                },
            },
        )

    original_client = httpx.AsyncClient

    def mock_client(*, timeout: float) -> httpx.AsyncClient:
        return original_client(
            transport=httpx.MockTransport(handler),
            timeout=timeout,
        )

    monkeypatch.setattr(currency.httpx, "AsyncClient", mock_client)
    monkeypatch.setenv("EXCHANGE_RATE_API_KEY", "test-exchange-key")

    rates, updated_at = asyncio.run(currency.get_rates_to_target("INR"))

    assert requested_urls[0].host == "v6.exchangerate-api.com"
    assert requested_urls[0].path.endswith("/latest/INR")
    assert rates["INR"] == 1
    assert rates["USD"] == pytest.approx(1 / 0.012)
    assert rates["JPY"] == pytest.approx(1 / 1.75)
    assert updated_at == "Tue, 24 Nov 2026 00:00:00 +0000"


def test_exchange_rate_tool_requires_a_configured_key(monkeypatch) -> None:
    monkeypatch.setenv("EXCHANGE_RATE_API_KEY", "")
    with pytest.raises(TravelProviderError, match="EXCHANGE_RATE_API_KEY"):
        asyncio.run(currency.get_rates_to_target("INR"))


@pytest.mark.parametrize(
    ("start_date", "end_date", "message"),
    [
        (date(2030, 1, 2), None, "Both start and end dates"),
        (date(2030, 1, 2), date(2030, 1, 1), "End date must be"),
        (date(2030, 1, 1), date(2030, 1, 17), "up to 16 days"),
    ],
)
def test_weather_tool_rejects_invalid_date_ranges(
    start_date, end_date, message
) -> None:
    with pytest.raises(TravelProviderError, match=message):
        asyncio.run(
            weather.get_forecast(
                Coordinates(name="Kyoto", latitude=35.0, longitude=135.0),
                days=1,
                start_date=start_date,
                end_date=end_date,
            )
        )
