from datetime import UTC, datetime
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from backend.app.database.models import TripSummary
from backend.app.schemas.itinerary import (
    BudgetBreakdown,
    ContextFact,
    CostRange,
    TravelContext,
    TripPlan,
)
from backend.app.schemas.trip import TripRequest
from backend.app.services.groq import GroqServiceError
from backend.app.streamlit_ui import (
    _create_plan,
    _research_table_rows,
    _stream_answer,
)


def test_trip_form_uses_numeric_inputs_and_currency_options() -> None:
    app_path = Path(__file__).resolve().parents[3] / "streamlit_app.py"
    app = AppTest.from_file(app_path).run(timeout=30)

    assert not app.exception
    assert {control.label for control in app.number_input} >= {
        "Travelers",
        "Budget (0 means flexible)",
    }
    assert not any(
        control.label == "Trip length (days)" for control in app.number_input
    )
    assert not app.slider
    currency = next(control for control in app.selectbox if control.label == "Currency")
    assert {"USD", "INR", "EUR", "GBP"} <= set(currency.options)
    assert any(
        control.label == "Accommodation and food style"
        for control in app.selectbox
    )
    assert any(
        "Travelers" == control.label for control in app.number_input
    )
    assert not any(
        "quote per traveler" in control.label.lower()
        or "visa fee per traveler" in control.label.lower()
        for control in app.number_input
    )
    assert not app.checkbox
    dates = next(
        control for control in app.date_input if control.label == "Trip dates"
    )
    assert dates.value == ()
    assert any(control.value == "Recent history" for control in app.subheader)


def test_followup_chat_history_can_be_cleared() -> None:
    app_path = Path(__file__).resolve().parents[3] / "streamlit_app.py"
    app = AppTest.from_file(app_path).run(timeout=30)
    app.session_state["current_trip"] = TripRequest(destination="Kyoto", trip_days=1)
    app.session_state["current_plan"] = _sample_plan()
    app.session_state["followup_messages"] = [
        {"role": "user", "content": "Earlier question"}
    ]
    app.run(timeout=30)

    clear_button = next(
        button for button in app.button if button.label == "Clear chat history"
    )
    clear_button.click().run(timeout=30)

    assert app.session_state["followup_messages"] == []
    assert not any(
        markdown.value == "Earlier question" for markdown in app.markdown
    )


def test_budget_summary_displays_low_high_and_priced_category_count() -> None:
    app_path = Path(__file__).resolve().parents[3] / "streamlit_app.py"
    app = AppTest.from_file(app_path).run(timeout=30)
    trip = TripRequest(destination="Kyoto", trip_days=1, travelers=2, currency="INR")
    plan = _sample_plan()
    plan.currency = "INR"
    plan.budget_breakdown = BudgetBreakdown(
        activities=CostRange(
            low=41_812.30,
            high=41_812.30,
            currency="INR",
        ),
        lodging=CostRange(low=2_912.62, high=5_825.24, currency="INR"),
        unpriced_categories=["visa fees"],
    )
    app.session_state["current_trip"] = trip
    app.session_state["current_plan"] = plan
    app.run(timeout=30)

    metrics = {metric.label: metric.value for metric in app.metric}

    assert metrics["Low estimate"] == "44,724.92 INR"
    assert metrics["High estimate"] == "47,637.54 INR"
    assert metrics["Categories priced"] == "2 of 8"


def test_research_table_keeps_only_linked_results_and_cleans_snippets() -> None:
    rows = _research_table_rows(
        [
            ContextFact(
                source="Tavily destination cost research",
                title="Australia budget",
                detail=(
                    "Typical costs are AUD 20–50. "
                    "[](http://localhost:8501/#broken) More details."
                ),
                url="https://example.test/australia",
            ),
            ContextFact(
                source="Destination research",
                detail="A result without a source link.",
            ),
            ContextFact(
                source="Tavily visa price search",
                detail="Visa result Source: http://localhost:8501/#invalid",
            ),
        ]
    )

    assert rows == [
        {
            "Research area": "Destination prices",
            "Finding": "Australia budget",
            "Summary": "Typical costs are AUD 20–50. More details.",
            "Source": "https://example.test/australia",
        }
    ]


def test_linked_research_is_rendered_as_a_table() -> None:
    app_path = Path(__file__).resolve().parents[3] / "streamlit_app.py"
    app = AppTest.from_file(app_path).run(timeout=30)
    trip = TripRequest(destination="Kyoto", trip_days=1)
    plan = _sample_plan()
    plan.travel_context = TravelContext(
        facts=[
            ContextFact(
                source="Tavily destination cost research",
                title="Kyoto budget guide",
                detail="Budget lodging and meals.",
                url="https://example.test/kyoto",
            )
        ]
    )
    app.session_state["current_trip"] = trip
    app.session_state["current_plan"] = plan
    app.run(timeout=30)

    assert not app.exception
    assert len(app.dataframe) == 1


def test_saved_trip_can_be_deleted_from_sidebar(monkeypatch) -> None:
    app_path = Path(__file__).resolve().parents[3] / "streamlit_app.py"
    trip_id = "saved-trip"
    monkeypatch.setattr(
        "backend.app.streamlit_ui.list_recent_trips",
        lambda: [
            TripSummary(
                trip_id=trip_id,
                destination="Kyoto",
                trip_days=1,
                created_at=datetime.now(UTC),
            )
        ],
    )
    deleted_trip_ids = []
    monkeypatch.setattr(
        "backend.app.streamlit_ui.delete_saved_trip",
        lambda selected_id: deleted_trip_ids.append(selected_id) or True,
    )

    app = AppTest.from_file(app_path).run(timeout=30)
    app.session_state["current_trip"] = TripRequest(
        destination="Kyoto",
        trip_days=1,
    )
    current_plan = _sample_plan()
    current_plan.trip_id = trip_id
    app.session_state["current_plan"] = current_plan
    app.run(timeout=30)

    next(button for button in app.button if button.label == "Delete").click().run(
        timeout=30
    )
    next(
        button for button in app.button if button.label == "Confirm delete"
    ).click().run(timeout=30)

    assert deleted_trip_ids == [trip_id]
    assert app.session_state["current_plan"] is None


def _sample_plan() -> TripPlan:
    return TripPlan(
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
    )


def test_streamlit_plan_uses_research_stream_and_saves(
    monkeypatch,
) -> None:
    progress_messages = []
    progress_values = []
    saved = []

    class Progress:
        def write(self, message: str) -> None:
            progress_messages.append(message)

    class ProgressBar:
        def progress(self, value: int, text: str) -> None:
            progress_values.append((value, text))

    async def fake_context(_trip):
        return TravelContext()

    async def fake_plan(_trip, _context, on_token):
        await on_token("x" * 300)
        return _sample_plan()

    def fake_save(_trip, plan):
        plan.trip_id = "saved-trip"
        saved.append(plan)

    monkeypatch.setattr("backend.app.streamlit_ui.collect_travel_context", fake_context)
    monkeypatch.setattr("backend.app.streamlit_ui.plan_trip", fake_plan)
    monkeypatch.setattr("backend.app.streamlit_ui.save_trip", fake_save)

    plan = _create_plan(
        TripRequest(destination="Kyoto", trip_days=1),
        Progress(),
        ProgressBar(),
    )

    assert plan.trip_id == "saved-trip"
    assert saved == [plan]
    assert any("Research gathered" in message for message in progress_messages)
    assert any("300 characters" in message for message in progress_messages)
    assert progress_values[-1][1] == (
        "MakeMyJourney is building your day-by-day plan"
    )
    assert progress_values[-1][0] == 35


def test_streamlit_followup_yields_tokens_and_surfaces_errors(monkeypatch) -> None:
    async def fake_stream(_trip, _plan, _question, _history, on_token):
        await on_token("Consider ")
        await on_token("a slower morning.")

    monkeypatch.setattr("backend.app.streamlit_ui.stream_trip_followup", fake_stream)
    chunks = list(
        _stream_answer(
            TripRequest(destination="Kyoto", trip_days=1),
            _sample_plan(),
            "Can day two be slower?",
            [],
        )
    )
    assert "".join(chunks) == "Consider a slower morning."

    async def fail_stream(_trip, _plan, _question, _history, _on_token):
        raise GroqServiceError("Groq is rate-limiting requests.", status_code=503)

    monkeypatch.setattr("backend.app.streamlit_ui.stream_trip_followup", fail_stream)
    with pytest.raises(GroqServiceError, match="rate-limiting"):
        list(
            _stream_answer(
                TripRequest(destination="Kyoto", trip_days=1),
                _sample_plan(),
                "Can day two be slower?",
                [],
            )
        )
