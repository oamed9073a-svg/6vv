"""Слой работы с SQLite: таблица записей и вспомогательные запросы."""
import sqlite3
from datetime import datetime, timedelta

from config import DB_PATH
from salon import (
    SLOT_STEP_MIN,
    WORK_END_HOUR,
    WORK_START_HOUR,
    master_by_key,
    service_by_key,
)

STATUS_ACTIVE = "active"
STATUS_CANCELLED = "cancelled"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bookings (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER NOT NULL,
                client_name  TEXT NOT NULL,
                phone        TEXT NOT NULL,
                service_key  TEXT NOT NULL,
                master_key   TEXT NOT NULL,
                date         TEXT NOT NULL,   -- YYYY-MM-DD
                time         TEXT NOT NULL,   -- HH:MM
                duration_min INTEGER NOT NULL,
                status       TEXT NOT NULL DEFAULT 'active',
                created_at   TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_bookings_slot "
            "ON bookings (master_key, date, status)"
        )


def create_booking(
    user_id: int,
    client_name: str,
    phone: str,
    service_key: str,
    master_key: str,
    date: str,
    time: str,
    duration_min: int,
) -> int:
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO bookings
                (user_id, client_name, phone, service_key, master_key,
                 date, time, duration_min, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                client_name,
                phone,
                service_key,
                master_key,
                date,
                time,
                duration_min,
                STATUS_ACTIVE,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        return cur.lastrowid


def cancel_booking(booking_id: int) -> bool:
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE bookings SET status = ? WHERE id = ? AND status = ?",
            (STATUS_CANCELLED, booking_id, STATUS_ACTIVE),
        )
        return cur.rowcount > 0


def get_booking(booking_id: int) -> sqlite3.Row | None:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM bookings WHERE id = ?", (booking_id,)
        ).fetchone()


def active_bookings_by_user(user_id: int) -> list[sqlite3.Row]:
    with _connect() as conn:
        return conn.execute(
            """
            SELECT * FROM bookings
            WHERE user_id = ? AND status = ? AND date >= ?
            ORDER BY date, time
            """,
            (user_id, STATUS_ACTIVE, datetime.now().strftime("%Y-%m-%d")),
        ).fetchall()


def bookings_by_date(date: str) -> list[sqlite3.Row]:
    with _connect() as conn:
        return conn.execute(
            """
            SELECT * FROM bookings
            WHERE date = ? AND status = ?
            ORDER BY time, master_key
            """,
            (date, STATUS_ACTIVE),
        ).fetchall()


def _booked_intervals(master_key: str, date: str) -> list[tuple[int, int]]:
    """Возвращает занятые интервалы [начало, конец) в минутах от полуночи."""
    intervals = []
    for row in bookings_by_date(date):
        if row["master_key"] != master_key:
            continue
        h, m = map(int, row["time"].split(":"))
        start = h * 60 + m
        intervals.append((start, start + row["duration_min"]))
    return intervals


def available_slots(master_key: str, date: str, duration_min: int) -> list[str]:
    """Свободные времена начала для мастера на дату с учётом длительности услуги."""
    open_min = WORK_START_HOUR * 60
    close_min = WORK_END_HOUR * 60
    busy = _booked_intervals(master_key, date)

    now = datetime.now()
    is_today = date == now.strftime("%Y-%m-%d")
    cur_min = now.hour * 60 + now.minute

    slots: list[str] = []
    start = open_min
    while start + duration_min <= close_min:
        end = start + duration_min
        overlaps = any(start < b_end and b_start < end for b_start, b_end in busy)
        in_past = is_today and start <= cur_min
        if not overlaps and not in_past:
            slots.append(f"{start // 60:02d}:{start % 60:02d}")
        start += SLOT_STEP_MIN
    return slots


def upcoming_dates(days_ahead: int) -> list[str]:
    today = datetime.now().date()
    return [
        (today + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days_ahead)
    ]


def describe_booking(row: sqlite3.Row, with_client: bool = False) -> str:
    service = service_by_key(row["service_key"])
    master = master_by_key(row["master_key"])
    service_title = service.title if service else row["service_key"]
    master_name = master.name if master else row["master_key"]
    parts = [
        f"№{row['id']} — {row['date']} в {row['time']}",
        f"Услуга: {service_title}",
        f"Мастер: {master_name}",
    ]
    if with_client:
        parts.append(f"Клиент: {row['client_name']}, {row['phone']}")
    return "\n".join(parts)
