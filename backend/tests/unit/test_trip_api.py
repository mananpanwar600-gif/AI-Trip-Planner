import json
from datetime import date, timedelta

from fastapi.testclient import TestClient

from backend.app.api.routes import destinations as destination_routes
from backend.app.api.routes import trips as trip_routes
from backend.app.api.routes import weather as weather_routes
from backend.app.main import app
from backend.app.schemas.context import Coordinates, WeatherDay
from backend.app.schemas.itinerary import TravelContext, TripPlan
from backend.app.schemas.trip import TripRequest
from backend.app.services.groq import GroqServiceError

client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "groq" in response.json()["providers"]


def test_root_describes_streamlit_interface() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["name"] == "MakeMyJourney"
    assert response.json()["interface"] == "Streamlit"
    assert response.json()["api_docs"] == "/docs"


def test_destination_search_uses_geocoding_provider(monkeypatch) -> None:
    async def fake_geocode(query):
        assert query == "Kyoto"
        return Coordinates(
            name="Kyoto",
            country="Japan",
            latitude=35.0,
            longitude=135.0,
        )

    monkeypatch.setattr(destination_routes, "geocode_city", fake_geocode)
    response = client.get("/api/destinations/search", params={"query": "Kyoto"})

    assert response.status_code == 200
    assert response.json()["destination"]["country"] == "Japan"


def test_weather_endpoint_returns_forecast(monkeypatch) -> None:
    async def fake_geocode(_query):
        return Coordinates(
            name="Kyoto",
            latitude=35.0,
            longitude=135.0,
        )

    async def fake_forecast(_location, _days):
        return [
            WeatherDay(
                date="2026-11-24",
                minimum_celsius=8,
                maximum_celsius=17,
                summary="mainly clear",
            )
        ]

    monkeypatch.setattr(weather_routes, "geocode_city", fake_geocode)
    monkeypatch.setattr(weather_routes, "get_forecast", fake_forecast)
    response = client.get(
        "/api/weather",
        params={"destination": "Kyoto", "days": 1},
    )

    assert response.status_code == 200
    assert response.json()["forecast"][0]["summary"] == "mainly clear"


def test_weather_endpoint_accepts_a_date_range(monkeypatch) -> None:
    expected_start_date = date.today() + timedelta(days=2)
    expected_end_date = expected_start_date + timedelta(days=1)

    async def fake_geocode(_query):
        return Coordinates(
            name="Kyoto",
            latitude=35.0,
            longitude=135.0,
        )

    async def fake_forecast(
        _location, days, *, start_date=None, end_date=None
    ):
        assert days == 2
        assert start_date == expected_start_date
        assert end_date == expected_end_date
        return [
            WeatherDay(
                date=expected_start_date.isoformat(),
                minimum_celsius=8,
                maximum_celsius=17,
                summary="mainly clear",
            )
        ]

    monkeypatch.setattr(weather_routes, "geocode_city", fake_geocode)
    monkeypatch.setattr(weather_routes, "get_forecast", fake_forecast)
    response = client.get(
        "/api/weather",
        params={
            "destination": "Kyoto",
            "start_date": expected_start_date.isoformat(),
            "end_date": expected_end_date.isoformat(),
        },
    )

    assert response.status_code == 200
    assert response.json()["forecast"][0]["date"] == expected_start_date.isoformat()


def test_weather_endpoint_rejects_incomplete_or_unavailable_dates() -> None:
    today = date.today()
    incomplete = client.get(
        "/api/weather",
        params={"destination": "Kyoto", "start_date": today.isoformat()},
    )
    outside_window = today + timedelta(days=16)
    unavailable = client.get(
        "/api/weather",
        params={
            "destination": "Kyoto",
            "start_date": outside_window.isoformat(),
            "end_date": outside_window.isoformat(),
        },
    )

    assert incomplete.status_code == 422
    assert unavailable.status_code == 422


def test_trip_request_rejects_invalid_duration() -> None:
    response = client.post(
        "/api/trips/plan",
        json={"destination": "Kyoto", "trip_days": 22},
    )

    assert response.status_code == 422


def test_trip_request_rejects_blank_destination() -> None:
    response = client.post(
        "/api/trips/plan",
        json={"destination": "  "},
    )

    assert response.status_code == 422


def test_create_plan_returns_and_persists_generated_itinerary(
    monkeypatch, tmp_path
) -> None:
    start_date = date.today() + timedelta(days=2)
    end_date = start_date + timedelta(days=1)
    monkeypatch.setenv(
        "DATABASE_URL",
        f"sqlite+aiosqlite:///{tmp_path / 'trips.db'}",
    )

    async def fake_generate_trip_plan(trip):
        assert trip.destination == "Kyoto"
        assert trip.trip_days == 2
        assert trip.start_date == start_date
        assert trip.end_date == end_date
        return TripPlan(
            destination="Kyoto",
            currency=trip.currency,
            overview="A relaxed introduction to the city.",
            days=[
                {
                    "day": day,
                    "title": f"Day {day}",
                    "activities": [
                        {
                            "time": "09:00",
                            "name": "Visit a garden",
                            "description": "Take a quiet morning walk.",
                            "location": "Kyoto",
                            "estimated_cost": 10,
                        }
                    ],
                }
                for day in range(1, trip.trip_days + 1)
            ],
            estimated_total_cost=100,
            tips=["Carry cash for smaller shops."],
        )

    monkeypatch.setattr(trip_routes, "generate_trip_plan", fake_generate_trip_plan)
    response = client.post(
        "/api/trips/plan",
        json={
            "destination": "Kyoto",
            "trip_days": 1,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "currency": "JPY",
            "interests": ["food"],
        },
    )

    assert response.status_code == 200
    assert response.json()["destination"] == "Kyoto"
    assert response.json()["currency"] == "JPY"
    assert len(response.json()["days"]) == 2
    trip_id = response.json()["trip_id"]
    recent = client.get("/api/trips")
    saved = client.get(f"/api/trips/{trip_id}")
    saved_trip = trip_routes.get_trip(trip_id)
    assert recent.status_code == 200
    assert recent.json()[0]["trip_id"] == trip_id
    assert saved.status_code == 200
    assert saved.json()["destination"] == "Kyoto"
    assert saved_trip is not None
    assert saved_trip.request.start_date == start_date
    assert saved_trip.request.end_date == end_date


def test_saved_trip_can_be_deleted_from_history(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        f"sqlite+aiosqlite:///{tmp_path / 'delete-trip.db'}",
    )
    request = TripRequest(destination="Kyoto", trip_days=1)
    plan = TripPlan(
        destination="Kyoto",
        overview="A relaxed introduction to the city.",
        days=[
            {
                "day": 1,
                "title": "Explore",
                "activities": [
                    {
                        "time": "09:00",
                        "name": "Visit a garden",
                        "description": "Take a quiet morning walk.",
                        "location": "Kyoto",
                        "estimated_cost": 10,
                    }
                ],
            }
        ],
        estimated_total_cost=10,
    )
    trip_id = trip_routes.save_trip(request, plan)

    from backend.app.database.repositories import delete_trip

    assert delete_trip(trip_id) is True
    assert trip_routes.get_trip(trip_id) is None
    assert delete_trip(trip_id) is False


def test_streamed_plan_returns_itinerary_and_persists_it(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        f"sqlite+aiosqlite:///{tmp_path / 'streamed-trips.db'}",
    )

    async def fake_context(_trip):
        return TravelContext()

    async def fake_plan(trip, _context, on_token):
        await on_token('{"destination":"Kyoto"}')
        return TripPlan(
            destination="Kyoto",
            currency=trip.currency,
            overview="A relaxed introduction to the city.",
            days=[
                {
                    "day": 1,
                    "title": "Explore",
                    "activities": [
                        {
                            "time": "09:00",
                            "name": "Visit a garden",
                            "description": "Take a quiet morning walk.",
                            "location": "Kyoto",
                            "estimated_cost": 10,
                        }
                    ],
                }
            ],
            estimated_total_cost=10,
        )

    monkeypatch.setattr(trip_routes, "collect_travel_context", fake_context)
    monkeypatch.setattr(trip_routes, "plan_trip", fake_plan)
    response = client.post(
        "/api/trips/plan/stream",
        json={"destination": "Kyoto", "trip_days": 1},
    )

    assert response.status_code == 200
    assert "event: progress" in response.text
    assert "event: delta" in response.text
    assert "event: complete" in response.text
    complete_frame = next(
        frame
        for frame in response.text.split("\n\n")
        if frame.startswith("event: complete")
    )
    complete_data = json.loads(complete_frame.split("data:", maxsplit=1)[1])
    assert complete_data["trip_id"]
    assert client.get(f"/api/trips/{complete_data['trip_id']}").status_code == 200


def test_followup_stream_uses_saved_trip_and_streams_answer(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        f"sqlite+aiosqlite:///{tmp_path / 'followup-trips.db'}",
    )
    request = TripRequest(destination="Kyoto", trip_days=1)
    plan = TripPlan(
        destination="Kyoto",
        overview="A relaxed introduction to the city.",
        days=[
            {
                "day": 1,
                "title": "Explore",
                "activities": [
                    {
                        "time": "09:00",
                        "name": "Visit a garden",
                        "description": "Take a quiet morning walk.",
                        "location": "Kyoto",
                        "estimated_cost": 10,
                    }
                ],
            }
        ],
        estimated_total_cost=10,
    )
    trip_id = trip_routes.save_trip(request, plan)

    async def fake_followup(_trip, _plan, question, history, on_token):
        assert question == "Can you make it more relaxed?"
        assert history == []
        await on_token("Start the morning slowly.")

    monkeypatch.setattr(trip_routes, "stream_trip_followup", fake_followup)
    response = client.post(
        f"/api/trips/{trip_id}/follow-up/stream",
        json={"question": "Can you make it more relaxed?"},
    )

    assert response.status_code == 200
    assert "event: delta" in response.text
    assert "Start the morning slowly." in response.text
    assert "event: complete" in response.text


def test_plan_generation_error_is_returned_to_client(monkeypatch) -> None:
    async def fail_generation(_trip):
        raise GroqServiceError("Groq is unavailable.", status_code=503)

    monkeypatch.setattr(trip_routes, "generate_trip_plan", fail_generation)
    response = client.post("/api/trips/plan", json={"destination": "Kyoto"})

    assert response.status_code == 503
    assert response.json()["detail"] == "Groq is unavailable."


def test_missing_groq_key_is_reported(monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "")
    response = client.post("/api/trips/plan", json={"destination": "Kyoto"})

    assert response.status_code == 503
    assert "GROQ_API_KEY" in response.json()["detail"]
