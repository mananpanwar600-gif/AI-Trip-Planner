import json
import uuid
from datetime import UTC, datetime

from backend.app.database.database import connect
from backend.app.database.models import SavedTrip, TripSummary
from backend.app.schemas.itinerary import TripPlan
from backend.app.schemas.trip import TripRequest


def save_trip(request: TripRequest, plan: TripPlan) -> str:
    trip_id = str(uuid.uuid4())
    created_at = datetime.now(UTC)
    plan.trip_id = trip_id
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO trips (trip_id, destination, created_at, request_json, plan_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                trip_id,
                plan.destination,
                created_at.isoformat(),
                request.model_dump_json(),
                plan.model_dump_json(),
            ),
        )
    return trip_id


def list_trips(limit: int = 20) -> list[TripSummary]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT trip_id, destination, created_at, request_json
            FROM trips
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        TripSummary(
            trip_id=row["trip_id"],
            destination=row["destination"],
            created_at=datetime.fromisoformat(row["created_at"]),
            trip_days=json.loads(row["request_json"])["trip_days"],
        )
        for row in rows
    ]


def get_trip(trip_id: str) -> SavedTrip | None:
    with connect() as connection:
        row = connection.execute(
            """
            SELECT trip_id, created_at, request_json, plan_json
            FROM trips
            WHERE trip_id = ?
            """,
            (trip_id,),
        ).fetchone()
    if row is None:
        return None
    return SavedTrip(
        trip_id=row["trip_id"],
        created_at=datetime.fromisoformat(row["created_at"]),
        request=TripRequest.model_validate_json(row["request_json"]),
        plan=TripPlan.model_validate_json(row["plan_json"]),
    )


def delete_trip(trip_id: str) -> bool:
    with connect() as connection:
        cursor = connection.execute(
            "DELETE FROM trips WHERE trip_id = ?",
            (trip_id,),
        )
    return cursor.rowcount > 0