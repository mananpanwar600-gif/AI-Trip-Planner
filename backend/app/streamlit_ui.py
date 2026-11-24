import asyncio
import concurrent.futures
import html
import logging
import queue
import re
from collections.abc import Iterator
from datetime import date, timedelta
from urllib.parse import urlsplit

import streamlit as st
from pydantic import ValidationError

from backend.app.agents.planner import plan_trip
from backend.app.config import get_settings
from backend.app.database.repositories import save_trip
from backend.app.schemas.followup import FollowUpMessage, FollowUpRequest
from backend.app.schemas.itinerary import ContextFact, CostRange, TripPlan
from backend.app.schemas.trip import TripRequest
from backend.app.services.groq import GroqServiceError, stream_trip_followup
from backend.app.services.memory_service import (
    delete_saved_trip,
    list_recent_trips,
    load_trip,
)
from backend.app.services.travel_context import collect_travel_context
from backend.app.utils.exceptions import DatabaseUnavailable

logger = logging.getLogger(__name__)
BRAND_NAME = "MakeMyJourney"
INTEREST_OPTIONS = (
    "Food",
    "Culture",
    "Museums",
    "Nature",
    "Beaches",
    "Architecture",
    "Markets",
    "Nightlife",
    "Shopping",
    "Family activities",
    "Photography",
    "Wellness",
)
CURRENCY_OPTIONS = ("USD", "EUR", "GBP", "INR", "CAD", "AUD", "JPY", "CHF", "SGD", "AED")
PACE_OPTIONS = {
    "Relaxed": "relaxed",
    "Balanced": "balanced",
    "Active": "active",
}


def _create_plan(trip: TripRequest, progress, progress_bar) -> TripPlan:
    async def create() -> TripPlan:
        context = await collect_travel_context(trip)
        progress.write("Research gathered. Streaming your itinerary from Groq…")
        progress_bar.progress(30, text="Research complete · writing your itinerary")
        received_characters = 0
        last_reported_characters = 0

        async def report_token(token: str) -> None:
            nonlocal received_characters, last_reported_characters
            received_characters += len(token)
            if received_characters - last_reported_characters >= 300:
                progress.write(
                    f"Model response streamed: {received_characters:,} characters"
                )
                progress_value = min(95, 30 + received_characters // 60)
                progress_bar.progress(
                    progress_value,
                    text="MakeMyJourney is building your day-by-day plan",
                )
                last_reported_characters = received_characters

        plan = await plan_trip(trip, context, on_token=report_token)
        await asyncio.to_thread(save_trip, trip, plan)
        return plan

    return asyncio.run(create())


def _stream_answer(
    trip: TripRequest,
    plan: TripPlan,
    question: str,
    history: list[FollowUpMessage],
) -> Iterator[str]:
    events: queue.Queue[tuple[str, object]] = queue.Queue()

    async def answer() -> None:
        async def on_token(token: str) -> None:
            events.put(("chunk", token))

        await stream_trip_followup(trip, plan, question, history, on_token)

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=1,
        thread_name_prefix="groq-follow-up",
    ) as worker:
        future = worker.submit(asyncio.run, answer())
        while True:
            try:
                event, value = events.get(timeout=0.1)
            except queue.Empty:
                if future.done():
                    future.result()
                    return
                continue
            if event != "chunk" or not isinstance(value, str):
                raise TypeError("Groq returned a non-text response chunk.")
            yield value


def _format_budget_range(amount: CostRange, currency: str) -> str:
    amount_currency = amount.currency or currency
    if amount.low == amount.high:
        return f"{amount.low:,.2f} {amount_currency}"
    return (
        f"{amount.low:,.2f}–{amount.high:,.2f} "
        f"{amount_currency}"
    )


def _research_source_url(fact: ContextFact) -> str | None:
    if fact.url is not None:
        url = str(fact.url)
    else:
        match = re.search(
            r"\bSource:\s*\[?(https?://[^\s)\]]+)",
            fact.detail,
            flags=re.IGNORECASE,
        )
        if match is None:
            return None
        url = match.group(1).rstrip(".,;")

    try:
        parsed_url = urlsplit(url)
    except ValueError:
        return None
    hostname = (parsed_url.hostname or "").lower()
    if (
        parsed_url.scheme.lower() != "https"
        or not hostname
        or hostname == "localhost"
        or hostname.endswith((".localhost", ".local"))
    ):
        return None
    return url


def _clean_research_text(value: str, max_length: int) -> str:
    text = html.unescape(value)
    text = re.sub(
        r"\[\]\(http://localhost(?::\d+)?/[^)]*\)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\[([^\]]+)\]\(https?://[^)]+\)", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[#*_`|]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_length:
        text = text[: max_length - 1].rsplit(" ", 1)[0].rstrip(" ,;") + "…"
    return text


def _research_table_rows(facts: list[ContextFact]) -> list[dict[str, str]]:
    source_labels = {
        "Tavily destination cost research": "Destination prices",
        "Tavily destination guide": "Local highlights",
        "Tavily flight price search": "Flights",
        "Tavily visa price search": "Visa fees",
    }
    rows = []
    for fact in facts:
        source_url = _research_source_url(fact)
        if source_url is None:
            continue

        detail = fact.detail
        if fact.url is None:
            source_match = re.search(
                r"\bSource:\s*\[?https?://[^\s)\]]+",
                detail,
                flags=re.IGNORECASE,
            )
            if source_match is not None:
                detail = detail[: source_match.start()].strip()

        if fact.title:
            title = fact.title
        elif fact.url is not None:
            title = fact.source
        else:
            title, separator, detail = detail.partition(":")
            if separator:
                detail = detail.strip()
            else:
                title = fact.source

        title = _clean_research_text(title, 120)
        summary = _clean_research_text(detail, 280)
        if not title or not summary:
            continue
        rows.append(
            {
                "Research area": source_labels.get(fact.source, fact.source),
                "Finding": title,
                "Summary": summary,
                "Source": source_url,
            }
        )
    return rows


def _render_plan(plan: TripPlan, trip: TripRequest) -> None:
    st.divider()
    day_label = "day" if len(plan.days) == 1 else "days"
    st.header(f"{len(plan.days)} {day_label} in {plan.destination}")
    st.caption(
        f"{trip.travelers} traveler{'s' if trip.travelers != 1 else ''} · "
        f"{trip.pace.title()} pace · {trip.currency}"
        + (
            f" · {trip.start_date:%b %d, %Y}–{trip.end_date:%b %d, %Y}"
            if trip.start_date and trip.end_date
            else ""
        )
    )
    st.write(plan.overview)
    breakdown = plan.budget_breakdown
    unpriced = breakdown.unpriced_categories
    categories = (
        ("Activities", breakdown.activities),
        ("Lodging", breakdown.lodging),
        ("Meals", breakdown.meals),
        ("Local transport", breakdown.local_transport),
        ("Round-trip flights", breakdown.flights),
        ("Visa fees", breakdown.visa),
        ("Travel insurance", breakdown.insurance),
        ("Other", breakdown.other),
    )
    priced_categories = [
        (label, amount)
        for label, amount in categories
        if amount is not None
    ]
    priced_ranges = [
        value
        for _, value in priced_categories
    ]
    low_total = sum(value.low for value in priced_ranges)
    high_total = sum(value.high for value in priced_ranges)
    with st.container(border=True):
        st.caption("TRIP BUDGET · WHOLE-TRIP ESTIMATE")
        low_column, high_column, coverage_column = st.columns(3)
        low_display = (
            f"{low_total:,.2f} {plan.currency}"
            if priced_ranges
            else "Not available"
        )
        high_display = (
            f"{high_total:,.2f} {plan.currency}"
            if priced_ranges
            else "Not available"
        )
        low_column.metric("Low estimate", low_display)
        high_column.metric("High estimate", high_display)
        coverage_column.metric(
            "Categories priced",
            f"{len(priced_categories)} of {len(categories)}",
        )
        st.caption(
            f"For {trip.travelers} traveler"
            f"{'s' if trip.travelers != 1 else ''} · "
            f"{len(plan.days)} days · {trip.travel_style.title()} style"
        )

    with st.expander("Trip budget breakdown", expanded=True):
        st.caption(
            "Each amount is for the full trip; ranges reflect estimate uncertainty."
        )
        if priced_categories:
            category_columns = st.columns(2)
            for index, (label, amount) in enumerate(priced_categories):
                with category_columns[index % 2]:
                    st.metric(label, _format_budget_range(amount, plan.currency))
        else:
            st.info("No reliable price estimates are available for this trip yet.")
        if unpriced:
            st.warning("No reliable price included for: " + ", ".join(unpriced) + ".")
        if plan.travel_context.exchange_rate_updated_at:
            source_currencies = {
                amount.source_currency
                for amount in (
                    breakdown.activities,
                    breakdown.lodging,
                    breakdown.meals,
                    breakdown.local_transport,
                    breakdown.flights,
                    breakdown.visa,
                    breakdown.insurance,
                    breakdown.other,
                )
                if amount is not None
                and amount.source_currency
                and amount.source_currency != plan.currency
            }
            source_currencies.update(
                activity.estimated_cost_source_currency
                for day in plan.days
                for activity in day.activities
                if activity.estimated_cost_source_currency
                and activity.estimated_cost_source_currency != plan.currency
            )
            rate_summary = ", ".join(
                f"1 {source} = "
                f"{plan.travel_context.exchange_rates[source]:,.4f} {plan.currency}"
                for source in sorted(source_currencies)
                if source in plan.travel_context.exchange_rates
            )
            st.caption(
                "Foreign-currency estimates converted with ExchangeRate-API rates "
                f"updated {plan.travel_context.exchange_rate_updated_at}."
                + (f" Rates used: {rate_summary}." if rate_summary else "")
            )
        else:
            st.warning(
                "Exchange rates are unavailable; prices in other currencies are "
                "excluded from the total."
            )
        st.caption(
            "Tavily prices are sourced estimates, not booking quotes. Visa fees "
            "depend on passport and may differ from generic search results."
        )

    for day in plan.days:
        day_date = (
            trip.start_date + timedelta(days=day.day - 1)
            if trip.start_date
            else None
        )
        day_heading = f"Day {day.day:02d}"
        if day_date:
            day_heading += f" · {day_date:%a, %b %d}"
        with st.expander(f"{day_heading} · {day.title}", expanded=True):
            for activity in day.activities:
                st.markdown(f"**{activity.time} · {activity.name}**")
                st.caption(
                    f"{activity.location} · {activity.estimated_cost:,.2f} "
                    f"{activity.estimated_cost_currency or 'currency unspecified'} "
                    "per traveler"
                )
                st.write(activity.description)
                st.divider()

    if plan.tips:
        with st.expander("Helpful travel tips"):
            for tip in plan.tips:
                st.markdown(f"- {tip}")

    research_rows = _research_table_rows(plan.travel_context.facts)
    if research_rows:
        with st.expander("Research results and sources", expanded=False):
            st.caption(
                "Short summaries from linked sources. Open a source to verify "
                "current prices and requirements."
            )
            st.dataframe(
                research_rows,
                column_config={
                    "Source": st.column_config.LinkColumn(
                        "Source",
                        display_text="Open source",
                    )
                },
                hide_index=True,
                width="stretch",
                height=min(460, 120 + len(research_rows) * 44),
            )

    if plan.travel_context.warnings:
        with st.expander("Planning notes"):
            for warning in plan.travel_context.warnings:
                st.warning(warning)


def _render_followups(
    trip: TripRequest,
    plan: TripPlan,
) -> None:
    st.subheader("Make the plan yours")
    st.caption(
        "Ask about pacing, alternatives, food, transport, or a change of plans."
    )
    messages: list[dict[str, str]] = st.session_state.followup_messages
    if st.button(
        "Clear chat history",
        key="clear_followup_history",
        disabled=not messages,
    ):
        st.session_state.followup_messages = []
        st.rerun()

    for message in messages:
        avatar = "🧭" if message["role"] == "assistant" else "🙂"
        with st.chat_message(message["role"], avatar=avatar):
            st.markdown(message["content"])

    question = st.chat_input(
        "Ask a question about this trip",
        max_chars=1000,
        key="followup_question",
    )
    if not question:
        return
    try:
        request = FollowUpRequest(
            question=question,
            history=[
                FollowUpMessage(
                    role=message["role"],
                    content=message["content"][:1200],
                )
                for message in messages[-12:]
            ],
        )
    except ValidationError as exc:
        st.error(exc.errors(include_input=False)[0]["msg"])
        return

    messages.append({"role": "user", "content": request.question})
    with st.chat_message("user", avatar="🙂"):
        st.markdown(request.question)
    with st.chat_message("assistant", avatar="🧭"):
        try:
            answer = st.write_stream(
                _stream_answer(
                    trip,
                    plan,
                    request.question,
                    request.history,
                )
            )
        except GroqServiceError as exc:
            st.error(str(exc))
        except Exception:
            logger.exception("Could not stream a trip follow-up.")
            st.error("Could not answer that question. Please try again.")
        else:
            messages.append({"role": "assistant", "content": str(answer)})


def _load_saved_trip(trip_id: str) -> None:
    try:
        saved = load_trip(trip_id)
    except DatabaseUnavailable as exc:
        st.sidebar.error(str(exc))
        return
    if saved is None:
        st.sidebar.error("That saved trip could not be found.")
        return
    st.session_state.current_trip = saved.request
    st.session_state.current_plan = saved.plan
    st.session_state.followup_messages = []
    st.rerun()


def run_app() -> None:
    for key, default in (
        ("current_trip", None),
        ("current_plan", None),
        ("followup_messages", []),
        ("pending_delete_trip_id", None),
    ):
        if key not in st.session_state:
            st.session_state[key] = default

    st.set_page_config(
        page_title=BRAND_NAME,
        page_icon="🧭",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(
        """
        <style>
        .stApp { background: #f5f6f1; }
        [data-testid="stSidebar"] { background: #edf1e8; }
        h1, h2, h3 { letter-spacing: -0.035em; }
        .block-container { max-width: 1160px; padding-top: 2.4rem; }
        [data-testid="stForm"] {
            padding: 1.4rem; border: 1px solid #e1e7dd; border-radius: 16px;
            background: #fffefa;
        }
        div[data-testid="stMetric"] {
            padding: 1rem; border: 1px solid #e1e7dd; border-radius: 12px;
            background: #fffefa;
        }
        [data-testid="stMetricValue"] {
            font-size: clamp(1.15rem, 2vw, 1.65rem);
            line-height: 1.2;
            overflow-wrap: anywhere;
        }
        div.stButton > button[kind="primary"],
        div.stFormSubmitButton > button[kind="primary"] {
            border-radius: 10px; min-height: 2.8rem; font-weight: 650;
        }
        [data-testid="stProgressBar"] > div > div { background: #2e644d; }
        [data-testid="stChatMessage"] {
            border: 1px solid #e1e7dd; border-radius: 14px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    try:
        settings = get_settings()
    except RuntimeError as exc:
        st.error(f"Configuration error: {exc}")
        st.stop()
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO)
    )

    st.title(f"🧭 {BRAND_NAME}")
    st.markdown(
        "A thoughtful trip plan, grounded in your preferences and live destination research."
    )

    with st.sidebar:
        st.subheader("Recent history")
        try:
            recent_trips = list_recent_trips()
        except DatabaseUnavailable as exc:
            st.error(str(exc))
            recent_trips = []
        if recent_trips:
            recent_trip_ids = {summary.trip_id for summary in recent_trips}
            if st.session_state.pending_delete_trip_id not in recent_trip_ids:
                st.session_state.pending_delete_trip_id = None

            for summary in recent_trips:
                st.caption(f"{summary.destination} · {summary.trip_days} days")
                open_column, delete_column = st.columns(2)
                with open_column:
                    if st.button(
                        "Open",
                        key=f"open_trip_{summary.trip_id}",
                        width="stretch",
                    ):
                        _load_saved_trip(summary.trip_id)
                with delete_column:
                    if st.button(
                        "Delete",
                        key=f"delete_trip_{summary.trip_id}",
                        width="stretch",
                    ):
                        st.session_state.pending_delete_trip_id = summary.trip_id

                if st.session_state.pending_delete_trip_id != summary.trip_id:
                    continue
                st.warning(
                    f"Delete the saved trip to {summary.destination}? "
                    "This cannot be undone."
                )
                confirm_column, cancel_column = st.columns(2)
                with confirm_column:
                    confirm_delete = st.button(
                        "Confirm delete",
                        key=f"confirm_delete_trip_{summary.trip_id}",
                        width="stretch",
                    )
                with cancel_column:
                    cancel_delete = st.button(
                        "Cancel",
                        key=f"cancel_delete_trip_{summary.trip_id}",
                        width="stretch",
                    )
                if confirm_delete:
                    try:
                        deleted = delete_saved_trip(summary.trip_id)
                    except DatabaseUnavailable as exc:
                        st.error(str(exc))
                    else:
                        if deleted:
                            current_plan = st.session_state.get("current_plan")
                            if (
                                current_plan is not None
                                and current_plan.trip_id == summary.trip_id
                            ):
                                st.session_state.current_trip = None
                                st.session_state.current_plan = None
                                st.session_state.followup_messages = []
                            st.session_state.pending_delete_trip_id = None
                            st.rerun()
                        st.error("That saved trip could not be found.")
                if cancel_delete:
                    st.session_state.pending_delete_trip_id = None
                    st.rerun()
        else:
            st.caption("Your saved itineraries will appear here.")

    with st.container():
        st.subheader("Plan a trip")
        st.caption("Choose your dates; the trip length is calculated automatically.")
        with st.form("trip_details"):
            destination = st.text_input(
                "Where do you want to go?",
                placeholder="e.g. Kyoto, Japan",
                max_chars=100,
            )
            selected_dates = st.date_input(
                "Trip dates",
                value=(),
                min_value=date.today(),
                help=(
                    "Choose both dates. Trip length is calculated automatically; "
                    "weather is added when a forecast is available."
                ),
            )
            trip_start_date = None
            trip_end_date = None
            if isinstance(selected_dates, (tuple, list)):
                if selected_dates:
                    trip_start_date = selected_dates[0]
                if len(selected_dates) > 1:
                    trip_end_date = selected_dates[1]
            elif isinstance(selected_dates, date):
                trip_start_date = selected_dates

            if (
                trip_start_date is not None
                and trip_end_date is not None
                and trip_end_date >= trip_start_date
            ):
                st.caption(
                    f"Trip length: "
                    f"{(trip_end_date - trip_start_date).days + 1} days"
                )
            else:
                st.caption("Choose a start and end date to calculate trip length.")

            first, second = st.columns(2)
            with first:
                travelers = st.number_input(
                    "Travelers",
                    min_value=1,
                    max_value=20,
                    value=1,
                    step=1,
                )
            with second:
                budget = st.number_input(
                    "Budget (0 means flexible)",
                    min_value=0.0,
                    max_value=1_000_000.0,
                    value=0.0,
                    step=50.0,
                    format="%.0f",
                )

            with st.expander("More preferences", expanded=True):
                first, second = st.columns(2)
                with first:
                    origin = st.text_input(
                        "Starting from (optional)",
                        placeholder="e.g. Tokyo, Japan",
                        max_chars=100,
                    )
                    currency = st.selectbox(
                        "Currency",
                        options=CURRENCY_OPTIONS,
                        help="Choose the currency for your budget and itinerary estimates.",
                    )
                with second:
                    pace_label = st.radio(
                        "Preferred pace",
                        options=list(PACE_OPTIONS),
                        horizontal=True,
                        help="Relaxed leaves breathing room; active fits more into each day.",
                    )
                    interests = st.multiselect(
                        "What do you enjoy?",
                        options=INTEREST_OPTIONS,
                        max_selections=10,
                    )
                travel_style_label = st.selectbox(
                    "Accommodation and food style",
                    options=("Budget", "Mid-range", "Upscale"),
                    index=0,
                    help="Used to research lodging, meals, and local transport costs.",
                )
                custom_interests = st.text_input(
                    "Other interests",
                    placeholder="Add a few, separated by commas",
                    max_chars=600,
                )
                additional_preferences = st.text_area(
                    "Anything else we should know?",
                    placeholder=(
                        "Dietary needs, accessibility, must-see places, "
                        "or things you would rather avoid"
                    ),
                    max_chars=500,
                    height=90,
                )
            submitted = st.form_submit_button(
                "Build my itinerary",
                type="primary",
                width="stretch",
            )

    if submitted:
        all_interests = interests + [
            interest.strip()
            for interest in custom_interests.split(",")
            if interest.strip()
        ]
        if trip_start_date is None or trip_end_date is None:
            st.error("Choose both a start date and an end date.")
        elif (
            trip_end_date < trip_start_date
        ):
            st.error("The end date must be on or after the start date.")
        elif (trip_end_date - trip_start_date).days + 1 > 21:
            st.error("Choose dates that span no more than 21 days.")
        elif len(all_interests) > 10:
            st.error("Choose or enter no more than 10 interests.")
        else:
            try:
                trip = TripRequest(
                    destination=destination,
                    origin=origin or None,
                    trip_days=(trip_end_date - trip_start_date).days + 1,
                    start_date=trip_start_date,
                    end_date=trip_end_date,
                    travelers=int(travelers),
                    budget=budget or None,
                    currency=currency.strip().upper(),
                    travel_style=travel_style_label.lower().replace(" ", "-"),
                    interests=all_interests,
                    pace=PACE_OPTIONS[pace_label],
                    additional_preferences=additional_preferences,
                )
            except ValidationError as exc:
                errors = "; ".join(
                    error["msg"] for error in exc.errors(include_input=False)
                )
                st.error(f"Please check the trip details: {errors}")
            else:
                if not settings.groq_api_key:
                    st.error("Add GROQ_API_KEY to your local .env before planning.")
                elif not settings.groq_model:
                    st.error("Set GROQ_MODEL in your local .env before planning.")
                else:
                    try:
                        with st.status(
                            "Gathering live destination context…",
                            expanded=True,
                        ) as progress:
                            progress_bar = st.progress(
                                8,
                                text="Gathering destination research",
                            )
                            plan = _create_plan(trip, progress, progress_bar)
                            progress_bar.progress(100, text="Itinerary complete")
                            progress.update(
                                label="Your itinerary is ready and saved.",
                                state="complete",
                                expanded=False,
                            )
                        st.session_state.current_trip = trip
                        st.session_state.current_plan = plan
                        st.session_state.followup_messages = []
                    except (GroqServiceError, DatabaseUnavailable, RuntimeError) as exc:
                        st.error(str(exc))
                    except Exception:
                        logger.exception(
                            "MakeMyJourney could not create the itinerary."
                        )
                        st.error(
                            "Something went wrong while planning. Check the app logs."
                        )

    current_plan = st.session_state.get("current_plan")
    current_trip = st.session_state.get("current_trip")
    if current_plan is None or current_trip is None:
        st.info("Your itinerary will appear here after you build a trip.")
        return

    _render_plan(current_plan, current_trip)
    st.divider()
    _render_followups(current_trip, current_plan)
