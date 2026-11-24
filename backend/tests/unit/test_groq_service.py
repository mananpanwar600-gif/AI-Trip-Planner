import asyncio
import json
from datetime import date

import httpx
import pytest

from backend.app.schemas.trip import TripRequest
from backend.app.services import groq


def test_generate_plan_uses_groq_and_requested_currency(monkeypatch) -> None:
    itinerary = {
        "destination": "Kyoto",
        "overview": "A relaxed trip.",
        "days": [
            {
                "day": 1,
                "title": "Explore",
                "activities": [
                    {
                        "time": "09:00",
                        "name": "Visit a garden",
                        "description": "Take a walk.",
                        "location": "Kyoto",
                        "estimated_cost": 500,
                        "estimated_cost_currency": "JPY",
                    }
                ],
            }
        ],
        "estimated_budget": 2000,
        "tips": [],
    }
    captured_requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(itinerary)}},
                ]
            },
        )

    original_client = httpx.AsyncClient

    def mock_client(*, timeout: float) -> httpx.AsyncClient:
        return original_client(
            transport=httpx.MockTransport(handler),
            timeout=timeout,
        )

    monkeypatch.setattr(groq.httpx, "AsyncClient", mock_client)
    monkeypatch.setenv("GROQ_API_KEY", "test-api-key")
    monkeypatch.setenv("GROQ_MODEL", "test-model")
    monkeypatch.setenv("GROQ_TEMPERATURE", "0.7")
    monkeypatch.setenv("GROQ_TIMEOUT", "7")

    trip = TripRequest(
        destination="Kyoto",
        trip_days=1,
        start_date=date(2030, 1, 2),
        end_date=date(2030, 1, 2),
        currency="JPY",
        pace="relaxed",
        additional_preferences="Avoid long walks.",
    )
    plan = asyncio.run(
        groq.generate_trip_plan(trip)
    )

    assert plan.destination == "Kyoto"
    assert plan.currency == "JPY"
    assert captured_requests[0].url == groq.GROQ_CHAT_URL
    assert captured_requests[0].headers["Authorization"] == "Bearer test-api-key"
    request_payload = json.loads(captured_requests[0].content)
    assert request_payload["model"] == "test-model"
    assert request_payload["temperature"] == 0.7
    assert "No live travel context was available." in request_payload["messages"][1][
        "content"
    ]
    assert "leave time for breaks" in request_payload["messages"][1]["content"]
    assert "Avoid long walks" in request_payload["messages"][1]["content"]
    assert "travel dates: 2030-01-02 through 2030-01-02 (inclusive)" in (
        request_payload["messages"][1]["content"]
    )
    assert request_payload["response_format"] == {"type": "json_object"}


def test_generate_trip_plan_retries_413_with_reduced_context(monkeypatch) -> None:
    from backend.app.schemas.itinerary import ContextFact, TravelContext

    itinerary = {
        "destination": "Jaipur",
        "overview": "A state-focused visit.",
        "days": [
            {
                "day": 1,
                "title": "Explore Jaipur",
                "activities": [
                    {
                        "time": "09:00",
                        "name": "Visit a fort",
                        "description": "Explore a local landmark.",
                        "location": "Jaipur",
                        "estimated_cost": 500,
                        "estimated_cost_currency": "INR",
                    }
                ],
            }
        ],
        "estimated_total_cost": 500,
        "tips": [],
    }
    captured_payloads = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_payloads.append(json.loads(request.content))
        if len(captured_payloads) == 1:
            return httpx.Response(413)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(itinerary)}},
                ]
            },
        )

    original_client = httpx.AsyncClient

    def mock_client(*, timeout: float) -> httpx.AsyncClient:
        return original_client(
            transport=httpx.MockTransport(handler),
            timeout=timeout,
        )

    monkeypatch.setattr(groq.httpx, "AsyncClient", mock_client)
    monkeypatch.setenv("GROQ_API_KEY", "test-api-key")
    monkeypatch.setenv("GROQ_MODEL", "test-model")

    plan = asyncio.run(
        groq.generate_trip_plan(
            TripRequest(destination="Jaipur", trip_days=1, currency="INR"),
            TravelContext(
                facts=[
                    ContextFact(
                        source="Location",
                        detail=(
                            "Place: Jaipur; State/region: Rajasthan; Country: "
                            "India; Country code: IN"
                        ),
                    ),
                    ContextFact(
                        source="Tavily destination guide",
                        title="Rajasthan source",
                        detail="Research detail " * 500,
                        url="https://example.test/rajasthan",
                    ),
                ]
            ),
        )
    )

    assert plan.destination == "Jaipur"
    assert len(captured_payloads) == 2
    initial_prompt = captured_payloads[0]["messages"][1]["content"]
    reduced_prompt = captured_payloads[1]["messages"][1]["content"]
    assert "Tavily destination guide" in initial_prompt
    assert "State/region: Rajasthan" in reduced_prompt
    assert "Tavily destination guide" not in reduced_prompt


def test_itinerary_prompt_uses_indian_state_specific_guidance() -> None:
    from backend.app.schemas.itinerary import ContextFact, TravelContext

    prompt = groq._build_prompt(
        TripRequest(destination="Jaipur", currency="INR"),
        TravelContext(
            facts=[
                ContextFact(
                    source="Location",
                    detail=(
                        "Place: Jaipur; State/region: Rajasthan; Country: India; "
                        "Country code: IN"
                    ),
                )
            ]
        ),
    )

    assert "State/region: Rajasthan" in prompt
    assert "correct state or union territory" in prompt
    assert "Do not mix distant Indian states" in prompt


def test_rate_limited_primary_model_falls_back_and_keeps_fallback_for_repairs(
    monkeypatch,
) -> None:
    def day_entry(day_number: int) -> dict:
        return {
            "day": day_number,
            "title": f"Explore {day_number}",
            "activities": [
                {
                    "time": "09:00",
                    "name": f"Visit {day_number}",
                    "description": "Enjoy a local highlight.",
                    "location": "Kyoto",
                    "estimated_cost": 12,
                    "estimated_cost_currency": "USD",
                }
            ],
        }

    responses = [
        httpx.Response(429),
        httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "destination": "Kyoto",
                                    "overview": "A relaxed trip.",
                                    "days": [day_entry(1)],
                                    "estimated_total_cost": 24,
                                    "tips": [],
                                }
                            )
                        }
                    }
                ]
            },
        ),
        httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "days": [day_entry(2)],
                                    "estimated_total_cost": 24,
                                }
                            )
                        }
                    }
                ]
            },
        ),
    ]
    requested_models = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_models.append(json.loads(request.content)["model"])
        return responses.pop(0)

    original_client = httpx.AsyncClient

    def mock_client(*, timeout: float) -> httpx.AsyncClient:
        return original_client(
            transport=httpx.MockTransport(handler),
            timeout=timeout,
        )

    monkeypatch.setattr(groq.httpx, "AsyncClient", mock_client)
    monkeypatch.setenv("GROQ_API_KEY", "test-api-key")
    monkeypatch.setenv("GROQ_MODEL", "primary-model")
    monkeypatch.setenv("GROQ_MODEL_EXTRA", "fallback-model")

    plan = asyncio.run(
        groq.generate_trip_plan(TripRequest(destination="Kyoto", trip_days=2))
    )

    assert [day.day for day in plan.days] == [1, 2]
    assert requested_models == ["primary-model", "fallback-model", "fallback-model"]


def test_invalid_itinerary_json_retries_once_and_accepts_wrapped_json(
    monkeypatch,
) -> None:
    itinerary = {
        "destination": "Kyoto",
        "overview": "A relaxed trip.",
        "days": [
            {
                "day": 1,
                "title": "Explore",
                "activities": [
                    {
                        "time": "09:00",
                        "name": "Visit a garden",
                        "description": "Take a walk.",
                        "location": "Kyoto",
                        "estimated_cost": 12,
                        "estimated_cost_currency": "USD",
                    }
                ],
            }
        ],
        "estimated_total_cost": 12,
        "tips": [],
    }
    responses = ["not valid JSON", f"Here is the itinerary:\n{json.dumps(itinerary)}"]
    captured_payloads = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_payloads.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": responses.pop(0)}},
                ]
            },
        )

    original_client = httpx.AsyncClient

    def mock_client(*, timeout: float) -> httpx.AsyncClient:
        return original_client(
            transport=httpx.MockTransport(handler),
            timeout=timeout,
        )

    monkeypatch.setattr(groq.httpx, "AsyncClient", mock_client)
    monkeypatch.setenv("GROQ_API_KEY", "test-api-key")
    monkeypatch.setenv("GROQ_MODEL", "test-model")

    plan = asyncio.run(
        groq.generate_trip_plan(TripRequest(destination="Kyoto", trip_days=1))
    )

    assert plan.destination == "Kyoto"
    assert len(captured_payloads) == 2
    assert "previous response was not valid JSON" in captured_payloads[1]["messages"][-1][
        "content"
    ]


def test_missing_total_is_derived_from_activity_costs_and_disclosed(monkeypatch) -> None:
    itinerary = {
        "destination": "Kyoto",
        "overview": "A relaxed trip.",
        "days": [
            {
                "day": 1,
                "title": "Explore",
                "activities": [
                    {
                        "time": "09:00",
                        "name": "Visit a garden",
                        "description": "<br>Take a walk.",
                        "location": "Kyoto",
                        "estimated_cost": 12.5,
                        "estimated_cost_currency": "USD",
                    },
                    {
                        "time": "13:00",
                        "name": "Visit a temple",
                        "description": "See a local landmark.",
                        "location": "Kyoto",
                        "estimated_cost": 8,
                        "estimated_cost_currency": "USD",
                    },
                ],
            }
        ],
        "tips": [],
    }

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(itinerary)}},
                ]
            },
        )

    original_client = httpx.AsyncClient

    def mock_client(*, timeout: float) -> httpx.AsyncClient:
        return original_client(
            transport=httpx.MockTransport(handler),
            timeout=timeout,
        )

    monkeypatch.setattr(groq.httpx, "AsyncClient", mock_client)
    monkeypatch.setenv("GROQ_API_KEY", "test-api-key")

    plan = asyncio.run(
        groq.generate_trip_plan(TripRequest(destination="Kyoto", trip_days=1))
    )

    assert plan.estimated_total_cost == 20.5
    assert plan.days[0].activities[0].description == "Take a walk."
    assert any(
        "Some trip costs are not included" in warning
        for warning in plan.travel_context.warnings
    )


def test_streamed_plan_parses_groq_chunks_and_reports_tokens(monkeypatch) -> None:
    itinerary = {
        "destination": "Kyoto",
        "overview": "A relaxed trip.",
        "days": [
            {
                "day": 1,
                "title": "Explore",
                "activities": [
                    {
                        "time": "09:00",
                        "name": "Visit a garden",
                        "description": "Take a walk.",
                        "location": "Kyoto",
                        "estimated_cost": 12,
                        "estimated_cost_currency": "USD",
                    }
                ],
            }
        ],
        "estimated_total_cost": 12,
        "tips": [],
    }
    itinerary_json = json.dumps(itinerary)
    stream_body = (
        "data: "
        + json.dumps({"choices": [{"delta": {"content": itinerary_json}}]})
        + "\n\n"
        + "data: [DONE]\n\n"
    )
    captured_requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=stream_body,
        )

    original_client = httpx.AsyncClient

    def mock_client(*, timeout: float) -> httpx.AsyncClient:
        return original_client(
            transport=httpx.MockTransport(handler),
            timeout=timeout,
        )

    async def run() -> tuple[object, list[str]]:
        chunks = []

        async def collect(token: str) -> None:
            chunks.append(token)

        plan = await groq.generate_trip_plan(
            TripRequest(destination="Kyoto", trip_days=1),
            on_token=collect,
        )
        return plan, chunks

    monkeypatch.setattr(groq.httpx, "AsyncClient", mock_client)
    monkeypatch.setenv("GROQ_API_KEY", "test-api-key")
    monkeypatch.setenv("GROQ_MODEL", "test-model")
    plan, chunks = asyncio.run(run())

    assert plan.destination == "Kyoto"
    assert "".join(chunks) == itinerary_json
    assert json.loads(captured_requests[0].content)["stream"] is True


def test_streamed_plan_retries_when_groq_returns_the_wrong_day_count(
    monkeypatch,
) -> None:
    def itinerary(day_count: int) -> dict:
        return {
            "destination": "Kyoto",
            "overview": "A relaxed trip.",
            "days": [
                {
                    "day": day,
                    "title": f"Explore {day}",
                    "activities": [
                        {
                            "time": "09:00",
                            "name": "Visit a garden",
                            "description": "Take a walk.",
                            "location": "Kyoto",
                            "estimated_cost": 12,
                            "estimated_cost_currency": "USD",
                        }
                    ],
                }
                for day in range(1, day_count + 1)
            ],
            "estimated_total_cost": day_count * 12,
            "tips": [],
        }

    responses = [itinerary(1), itinerary(2)]
    captured_payloads = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_payloads.append(json.loads(request.content))
        content = json.dumps(responses.pop(0))
        stream_body = (
            "data: "
            + json.dumps({"choices": [{"delta": {"content": content}}]})
            + "\n\n"
            + "data: [DONE]\n\n"
        )
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=stream_body,
        )

    original_client = httpx.AsyncClient

    def mock_client(*, timeout: float) -> httpx.AsyncClient:
        return original_client(
            transport=httpx.MockTransport(handler),
            timeout=timeout,
        )

    async def run() -> tuple[object, list[str]]:
        chunks = []

        async def collect(token: str) -> None:
            chunks.append(token)

        plan = await groq.generate_trip_plan(
            TripRequest(destination="Kyoto", trip_days=2),
            on_token=collect,
        )
        return plan, chunks

    monkeypatch.setattr(groq.httpx, "AsyncClient", mock_client)
    monkeypatch.setenv("GROQ_API_KEY", "test-api-key")
    monkeypatch.setenv("GROQ_MODEL", "test-model")
    plan, chunks = asyncio.run(run())

    assert len(plan.days) == 2
    assert len(captured_payloads) == 2
    assert "missing day entries [2]" in captured_payloads[1]["messages"][-1][
        "content"
    ]
    assert len(chunks) == 2


def test_streamed_plan_fills_missing_calendar_days_in_batches(monkeypatch) -> None:
    def day_entry(day_number: int) -> dict:
        return {
            "day": day_number,
            "title": f"Explore {day_number}",
            "activities": [
                {
                    "time": "09:00",
                    "name": f"Activity {day_number}",
                    "description": "Enjoy a local highlight.",
                    "location": "Kyoto",
                    "estimated_cost": 10,
                    "estimated_cost_currency": "USD",
                }
            ],
        }

    responses = [
        {
            "destination": "Kyoto",
            "overview": "A date-aware journey.",
            "days": [day_entry(day) for day in range(1, 10)],
            "estimated_total_cost": 90,
            "tips": [],
        },
        {"days": [day_entry(day) for day in range(10, 13)]},
        {
            "days": [day_entry(day) for day in range(13, 16)],
            "estimated_total_cost": 450,
        },
    ]
    captured_payloads = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_payloads.append(json.loads(request.content))
        content = json.dumps(responses.pop(0))
        stream_body = (
            "data: "
            + json.dumps({"choices": [{"delta": {"content": content}}]})
            + "\n\n"
            + "data: [DONE]\n\n"
        )
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=stream_body,
        )

    original_client = httpx.AsyncClient

    def mock_client(*, timeout: float) -> httpx.AsyncClient:
        return original_client(
            transport=httpx.MockTransport(handler),
            timeout=timeout,
        )

    async def run() -> tuple[object, list[str]]:
        chunks = []

        async def collect(token: str) -> None:
            chunks.append(token)

        plan = await groq.generate_trip_plan(
            TripRequest(
                destination="Kyoto",
                trip_days=15,
                start_date=date(2030, 1, 1),
                end_date=date(2030, 1, 15),
            ),
            on_token=collect,
        )
        return plan, chunks

    monkeypatch.setattr(groq.httpx, "AsyncClient", mock_client)
    monkeypatch.setenv("GROQ_API_KEY", "test-api-key")
    monkeypatch.setenv("GROQ_MODEL", "test-model")
    plan, chunks = asyncio.run(run())

    assert [day.day for day in plan.days] == list(range(1, 16))
    assert plan.estimated_total_cost == 150
    assert len(captured_payloads) == 3
    assert "Day 15: 2030-01-15" in captured_payloads[1]["messages"][-1]["content"]
    assert "missing day entries [13, 14, 15]" in captured_payloads[2]["messages"][
        -1
    ]["content"]
    assert len(chunks) == 3


def test_followup_stream_returns_text_chunks(monkeypatch) -> None:
    stream_body = (
        'data: {"choices":[{"delta":{"content":"Try "}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"<br"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"/>the garden."}}]}\n\n'
        "data: [DONE]\n\n"
    )

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=stream_body,
        )

    original_client = httpx.AsyncClient

    def mock_client(*, timeout: float) -> httpx.AsyncClient:
        return original_client(
            transport=httpx.MockTransport(handler),
            timeout=timeout,
        )

    async def run() -> list[str]:
        from backend.app.schemas.followup import FollowUpMessage
        from backend.app.schemas.itinerary import TripPlan

        chunks = []

        async def collect(token: str) -> None:
            chunks.append(token)

        await groq.stream_trip_followup(
            TripRequest(destination="Kyoto"),
            TripPlan(
                destination="Kyoto",
                overview="A relaxed trip.",
                days=[
                    {
                        "day": 1,
                        "title": "Explore",
                        "activities": [
                            {
                                "time": "09:00",
                                "name": "Visit a garden",
                                "description": "Take a walk.",
                                "location": "Kyoto",
                                "estimated_cost": 12,
                                "estimated_cost_currency": "USD",
                            }
                        ],
                    }
                ],
                estimated_total_cost=12,
            ),
            "Can you suggest a garden?",
            [FollowUpMessage(role="user", content="I like nature.")],
            collect,
        )
        return chunks

    monkeypatch.setattr(groq.httpx, "AsyncClient", mock_client)
    monkeypatch.setenv("GROQ_API_KEY", "test-api-key")
    monkeypatch.setenv("GROQ_MODEL", "test-model")

    answer = "".join(asyncio.run(run()))
    assert answer == "Try \nthe garden."
    assert "<br" not in answer


def test_followup_payload_excludes_research_and_bounds_history(monkeypatch) -> None:
    captured_payloads = []
    stream_body = (
        'data: {"choices":[{"delta":{"content":"Here is the answer."}}]}\n\n'
        "data: [DONE]\n\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        captured_payloads.append(json.loads(request.content))
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=stream_body,
        )

    original_client = httpx.AsyncClient

    def mock_client(*, timeout: float) -> httpx.AsyncClient:
        return original_client(
            transport=httpx.MockTransport(handler),
            timeout=timeout,
        )

    async def run() -> None:
        from backend.app.schemas.followup import FollowUpMessage
        from backend.app.schemas.itinerary import (
            ContextFact,
            TravelContext,
            TripPlan,
        )

        async def collect(_token: str) -> None:
            return None

        history = [
            FollowUpMessage(
                role="user" if index % 2 == 0 else "assistant",
                content=f"Earlier message {index} " * 60,
            )
            for index in range(12)
        ]
        plan = TripPlan(
            destination="Kyoto",
            overview="A relaxed trip.",
            days=[
                {
                    "day": 1,
                    "title": "Explore",
                    "activities": [
                        {
                            "time": "09:00",
                            "name": "Visit a garden",
                            "description": "Take a walk.",
                            "location": "Kyoto",
                            "estimated_cost": 12,
                            "estimated_cost_currency": "USD",
                        }
                    ],
                }
            ],
            estimated_total_cost=12,
            travel_context=TravelContext(
                facts=[
                    ContextFact(
                        source="Tavily destination cost research",
                        title="Long research result",
                        detail="raw research " * 10_000,
                        url="https://example.test/research",
                    )
                ]
            ),
        )
        await groq.stream_trip_followup(
            TripRequest(destination="Kyoto"),
            plan,
            "What should I see?",
            history,
            collect,
        )

    monkeypatch.setattr(groq.httpx, "AsyncClient", mock_client)
    monkeypatch.setenv("GROQ_API_KEY", "test-api-key")
    monkeypatch.setenv("GROQ_MODEL", "test-model")

    asyncio.run(run())

    payload = captured_payloads[0]
    assert len(payload["messages"]) == 9
    assert "raw research" not in payload["messages"][1]["content"]
    assert "Visit a garden" in payload["messages"][1]["content"]
    assert payload["messages"][-1]["content"] == "What should I see?"


def test_followup_413_returns_an_actionable_error(monkeypatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(413)

    original_client = httpx.AsyncClient

    def mock_client(*, timeout: float) -> httpx.AsyncClient:
        return original_client(
            transport=httpx.MockTransport(handler),
            timeout=timeout,
        )

    async def run() -> None:
        from backend.app.schemas.itinerary import TripPlan

        async def collect(_token: str) -> None:
            return None

        await groq.stream_trip_followup(
            TripRequest(destination="Kyoto"),
            TripPlan(
                destination="Kyoto",
                overview="A relaxed trip.",
                days=[
                    {
                        "day": 1,
                        "title": "Explore",
                        "activities": [
                            {
                                "time": "09:00",
                                "name": "Visit a garden",
                                "description": "Take a walk.",
                                "location": "Kyoto",
                                "estimated_cost": 12,
                            }
                        ],
                    }
                ],
                estimated_total_cost=12,
            ),
            "What should I see?",
            [],
            collect,
        )

    monkeypatch.setattr(groq.httpx, "AsyncClient", mock_client)
    monkeypatch.setenv("GROQ_API_KEY", "test-api-key")
    monkeypatch.setenv("GROQ_MODEL", "test-model")

    with pytest.raises(groq.GroqServiceError, match="context is too large") as exc:
        asyncio.run(run())

    assert exc.value.status_code == 413


def test_followup_falls_back_when_primary_model_is_rate_limited(monkeypatch) -> None:
    responses = [
        httpx.Response(429),
        httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=(
                'data: {"choices":[{"delta":{"content":"Try the garden."}}]}\n\n'
                "data: [DONE]\n\n"
            ),
        ),
    ]
    requested_models = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_models.append(json.loads(request.content)["model"])
        return responses.pop(0)

    original_client = httpx.AsyncClient

    def mock_client(*, timeout: float) -> httpx.AsyncClient:
        return original_client(
            transport=httpx.MockTransport(handler),
            timeout=timeout,
        )

    async def run() -> list[str]:
        from backend.app.schemas.itinerary import TripPlan

        chunks = []

        async def collect(token: str) -> None:
            chunks.append(token)

        await groq.stream_trip_followup(
            TripRequest(destination="Kyoto", trip_days=1),
            TripPlan(
                destination="Kyoto",
                overview="A relaxed trip.",
                days=[
                    {
                        "day": 1,
                        "title": "Explore",
                        "activities": [
                            {
                                "time": "09:00",
                                "name": "Visit a garden",
                                "description": "Take a walk.",
                                "location": "Kyoto",
                                "estimated_cost": 12,
                                "estimated_cost_currency": "USD",
                            }
                        ],
                    }
                ],
                estimated_total_cost=12,
            ),
            "Can you suggest a garden?",
            [],
            collect,
        )
        return chunks

    monkeypatch.setattr(groq.httpx, "AsyncClient", mock_client)
    monkeypatch.setenv("GROQ_API_KEY", "test-api-key")
    monkeypatch.setenv("GROQ_MODEL", "primary-model")
    monkeypatch.setenv("GROQ_MODEL_EXTRA", "fallback-model")

    assert "".join(asyncio.run(run())) == "Try the garden."
    assert requested_models == ["primary-model", "fallback-model"]
