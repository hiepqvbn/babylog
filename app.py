from __future__ import annotations

import csv
import io
import json
import sqlite3
from calendar import monthrange
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator, model_validator


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "babylog.db"
WHO_STANDARDS_PATH = BASE_DIR / "data" / "who" / "standards.json"
PHOTO_UPLOAD_DIR = BASE_DIR / "static" / "uploads"
MAX_PHOTO_BYTES = 15 * 1024 * 1024
HISTORY_PAGE_SIZE = 10
MAX_HISTORY_RECORDS = 1000
JOURNAL_BATCH_DAYS = 10

app = FastAPI(title="BabyLog")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

METRICS = {
    "weight_kg": {"label": "Weight", "unit": "kg", "decimals": 2},
    "height_cm": {"label": "Height", "unit": "cm", "decimals": 1},
    "head_circumference_cm": {"label": "Head circumference", "unit": "cm", "decimals": 1},
}


class MeasurementInput(BaseModel):
    measured_at: datetime
    weight_kg: Optional[float] = Field(default=None, ge=0)
    height_cm: Optional[float] = Field(default=None, ge=0)
    head_circumference_cm: Optional[float] = Field(default=None, ge=0)
    note: Optional[str] = None
    photo_filename: Optional[str] = None

    @field_validator("measured_at", mode="before")
    @classmethod
    def parse_measured_at(cls, value: Any) -> Any:
        if isinstance(value, date) and not isinstance(value, datetime):
            return datetime.combine(value, time())
        if isinstance(value, str) and len(value) == 10:
            return datetime.combine(date.fromisoformat(value), time())
        return value

    @model_validator(mode="after")
    def require_one_measurement(self) -> "MeasurementInput":
        if (
            self.weight_kg is None
            and self.height_cm is None
            and self.head_circumference_cm is None
            and self.photo_filename is None
        ):
            raise ValueError("Provide at least one measurement or photo.")
        return self


class BabyProfileInput(BaseModel):
    name: str
    sex: Optional[str] = None
    born_at: Optional[datetime] = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Baby name is required.")
        return cleaned

    @field_validator("sex")
    @classmethod
    def clean_sex(cls, value: Optional[str]) -> Optional[str]:
        if value in (None, ""):
            return None
        if value not in {"female", "male"}:
            raise ValueError("Choose female or male for WHO growth standards.")
        return value

    @field_validator("born_at", mode="before")
    @classmethod
    def parse_born_at(cls, value: Any) -> Any:
        if value is None or value == "":
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return datetime.combine(value, time())
        if isinstance(value, str) and len(value) == 10:
            return datetime.combine(date.fromisoformat(value), time())
        return value


class MilkLogInput(BaseModel):
    fed_at: datetime
    milk_ml: float = Field(gt=0)
    note: Optional[str] = None

    @field_validator("fed_at", mode="before")
    @classmethod
    def parse_fed_at(cls, value: Any) -> Any:
        if isinstance(value, date) and not isinstance(value, datetime):
            return datetime.combine(value, time())
        if isinstance(value, str) and len(value) == 10:
            return datetime.combine(date.fromisoformat(value), time())
        return value


class PoopLogInput(BaseModel):
    pooped_on: date
    count: int = Field(default=1, ge=0)
    note: Optional[str] = None


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS measurements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                measured_at TEXT NOT NULL,
                weight_kg REAL,
                height_cm REAL,
                head_circumference_cm REAL,
                note TEXT,
                photo_filename TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        measurement_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(measurements)").fetchall()
        }
        if "photo_filename" not in measurement_columns:
            conn.execute("ALTER TABLE measurements ADD COLUMN photo_filename TEXT")
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_measurements_measured_at
            ON measurements (measured_at DESC, id DESC)
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS baby_profile (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                name TEXT NOT NULL,
                sex TEXT,
                born_at TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(baby_profile)").fetchall()
        }
        if "sex" not in columns:
            conn.execute("ALTER TABLE baby_profile ADD COLUMN sex TEXT")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS milk_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fed_at TEXT NOT NULL,
                milk_ml REAL NOT NULL,
                note TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS poop_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pooped_on TEXT NOT NULL,
                count INTEGER NOT NULL,
                note TEXT,
                created_at TEXT NOT NULL
            )
            """
        )


@app.on_event("startup")
def on_startup() -> None:
    init_db()


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "measured_at": row["measured_at"],
        "weight_kg": row["weight_kg"],
        "height_cm": row["height_cm"],
        "head_circumference_cm": row["head_circumference_cm"],
        "note": row["note"],
        "photo_filename": row["photo_filename"],
        "created_at": row["created_at"],
    }


def milk_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "fed_at": row["fed_at"],
        "milk_ml": row["milk_ml"],
        "note": row["note"],
        "created_at": row["created_at"],
    }


def poop_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "pooped_on": row["pooped_on"],
        "count": row["count"],
        "note": row["note"],
        "created_at": row["created_at"],
    }


def profile_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "sex": row["sex"],
        "born_at": row["born_at"],
        "updated_at": row["updated_at"],
    }


def blank_to_none(value: Optional[str]) -> Optional[float]:
    if value is None or value.strip() == "":
        return None
    return float(value)


def normalize_note(note: Optional[str]) -> Optional[str]:
    if note is None:
        return None
    cleaned = note.strip()
    return cleaned or None


def detect_photo_extension(content: bytes) -> Optional[str]:
    if content.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return ".webp"
    if len(content) >= 12 and content[4:8] == b"ftyp":
        brand = content[8:12]
        if brand in {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1"}:
            return ".heic"
    return None


async def prepare_uploaded_photo(photo: Optional[UploadFile]) -> Optional[tuple[str, bytes]]:
    if photo is None or not photo.filename:
        return None

    content = await photo.read(MAX_PHOTO_BYTES + 1)
    if len(content) > MAX_PHOTO_BYTES:
        raise ValueError("Photo must be 15 MB or smaller.")

    extension = detect_photo_extension(content)
    if extension is None:
        raise ValueError("Choose a JPEG, PNG, WebP, GIF, HEIC, or HEIF photo.")
    return f"{uuid4().hex}{extension}", content


def store_photo(photo_data: tuple[str, bytes]) -> str:
    filename, content = photo_data
    PHOTO_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (PHOTO_UPLOAD_DIR / filename).write_bytes(content)
    return filename


def remove_stored_photo(filename: Optional[str]) -> None:
    if not filename or filename != Path(filename).name:
        return
    path = PHOTO_UPLOAD_DIR / filename
    if path.is_file():
        path.unlink()


def get_baby_profile() -> Optional[dict[str, Any]]:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM baby_profile WHERE id = 1").fetchone()
    return None if row is None else profile_row_to_dict(row)


def format_born_at_for_input(born_at: Optional[str]) -> str:
    return "" if not born_at else born_at[:16]


def load_who_standards() -> dict[str, Any]:
    if not WHO_STANDARDS_PATH.exists():
        return {"metrics": {}, "metadata": {}}
    return json.loads(WHO_STANDARDS_PATH.read_text(encoding="utf-8"))


def create_milk_log(data: MilkLogInput) -> dict[str, Any]:
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    fed_at = data.fed_at.isoformat(timespec="minutes")

    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO milk_logs (fed_at, milk_ml, note, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (fed_at, data.milk_ml, normalize_note(data.note), created_at),
        )
        row = conn.execute("SELECT * FROM milk_logs WHERE id = ?", (cursor.lastrowid,)).fetchone()

    return milk_row_to_dict(row)


def create_poop_log(data: PoopLogInput) -> dict[str, Any]:
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    pooped_on = data.pooped_on.isoformat()

    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO poop_logs (pooped_on, count, note, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (pooped_on, data.count, normalize_note(data.note), created_at),
        )
        row = conn.execute("SELECT * FROM poop_logs WHERE id = ?", (cursor.lastrowid,)).fetchone()

    return poop_row_to_dict(row)


def save_baby_profile(data: BabyProfileInput) -> dict[str, Any]:
    updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    born_at = None if data.born_at is None else data.born_at.isoformat(timespec="minutes")

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO baby_profile (id, name, sex, born_at, updated_at)
            VALUES (1, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                sex = excluded.sex,
                born_at = excluded.born_at,
                updated_at = excluded.updated_at
            """,
            (data.name, data.sex, born_at, updated_at),
        )
        row = conn.execute("SELECT * FROM baby_profile WHERE id = 1").fetchone()

    return profile_row_to_dict(row)


def create_measurement(data: MeasurementInput) -> dict[str, Any]:
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    measured_at = data.measured_at.isoformat(timespec="minutes")

    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO measurements (
                measured_at,
                weight_kg,
                height_cm,
                head_circumference_cm,
                note,
                photo_filename,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                measured_at,
                data.weight_kg,
                data.height_cm,
                data.head_circumference_cm,
                normalize_note(data.note),
                data.photo_filename,
                created_at,
            ),
        )
        row = conn.execute(
            "SELECT * FROM measurements WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()

    return row_to_dict(row)


def update_measurement(measurement_id: int, data: MeasurementInput) -> bool:
    measured_at = data.measured_at.isoformat(timespec="minutes")
    with get_db() as conn:
        cursor = conn.execute(
            """
            UPDATE measurements
            SET measured_at = ?, weight_kg = ?, height_cm = ?,
                head_circumference_cm = ?, note = ?, photo_filename = ?
            WHERE id = ?
            """,
            (
                measured_at,
                data.weight_kg,
                data.height_cm,
                data.head_circumference_cm,
                normalize_note(data.note),
                data.photo_filename,
                measurement_id,
            ),
        )
    return cursor.rowcount > 0


def get_measurement(measurement_id: int) -> Optional[dict[str, Any]]:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM measurements WHERE id = ?", (measurement_id,)
        ).fetchone()
    return None if row is None else row_to_dict(row)


def delete_measurement(measurement_id: int) -> bool:
    with get_db() as conn:
        cursor = conn.execute("DELETE FROM measurements WHERE id = ?", (measurement_id,))
    return cursor.rowcount > 0


def update_milk_log(log_id: int, data: MilkLogInput) -> bool:
    fed_at = data.fed_at.isoformat(timespec="minutes")
    with get_db() as conn:
        cursor = conn.execute(
            """
            UPDATE milk_logs
            SET fed_at = ?, milk_ml = ?, note = ?
            WHERE id = ?
            """,
            (fed_at, data.milk_ml, normalize_note(data.note), log_id),
        )
    return cursor.rowcount > 0


def delete_milk_log(log_id: int) -> bool:
    with get_db() as conn:
        cursor = conn.execute("DELETE FROM milk_logs WHERE id = ?", (log_id,))
    return cursor.rowcount > 0


def update_poop_log(log_id: int, data: PoopLogInput) -> bool:
    with get_db() as conn:
        cursor = conn.execute(
            """
            UPDATE poop_logs
            SET pooped_on = ?, count = ?, note = ?
            WHERE id = ?
            """,
            (data.pooped_on.isoformat(), data.count, normalize_note(data.note), log_id),
        )
    return cursor.rowcount > 0


def delete_poop_log(log_id: int) -> bool:
    with get_db() as conn:
        cursor = conn.execute("DELETE FROM poop_logs WHERE id = ?", (log_id,))
    return cursor.rowcount > 0


def normalize_history_limit(value: int) -> int:
    return min(max(value, HISTORY_PAGE_SIZE), MAX_HISTORY_RECORDS)


def history_redirect(
    record_type: str,
    error: Optional[str] = None,
    visible_limit: int = HISTORY_PAGE_SIZE,
) -> RedirectResponse:
    query = {"tab": "history", "history_type": record_type}
    limit_params = {
        "growth": "growth_limit",
        "milk": "milk_limit",
        "poop": "poop_limit",
    }
    if record_type in limit_params:
        query[limit_params[record_type]] = str(normalize_history_limit(visible_limit))
    if error:
        query["history_error"] = error
    return RedirectResponse(f"/?{urlencode(query)}", status_code=303)


def list_measurements(order: str = "DESC", limit: Optional[int] = None) -> list[dict[str, Any]]:
    if order not in {"ASC", "DESC"}:
        raise ValueError("Unsupported sort order.")

    sql = f"SELECT * FROM measurements ORDER BY measured_at {order}, id {order}"
    params: tuple[Any, ...] = ()

    if limit is not None:
        sql += " LIMIT ?"
        params = (limit,)

    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()

    return [row_to_dict(row) for row in rows]


def list_milk_logs(limit: Optional[int] = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM milk_logs ORDER BY fed_at DESC, id DESC"
    params: tuple[Any, ...] = ()

    if limit is not None:
        sql += " LIMIT ?"
        params = (limit,)

    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()

    return [milk_row_to_dict(row) for row in rows]


def list_poop_logs(limit: Optional[int] = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM poop_logs ORDER BY pooped_on DESC, id DESC"
    params: tuple[Any, ...] = ()

    if limit is not None:
        sql += " LIMIT ?"
        params = (limit,)

    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()

    return [poop_row_to_dict(row) for row in rows]


def latest_value(column: str) -> Optional[float]:
    if column not in {"weight_kg", "height_cm", "head_circumference_cm"}:
        raise ValueError("Unsupported summary column.")

    with get_db() as conn:
        row = conn.execute(
            f"""
            SELECT {column}
            FROM measurements
            WHERE {column} IS NOT NULL
            ORDER BY measured_at DESC, id DESC
            LIMIT 1
            """
        ).fetchone()

    return None if row is None else row[column]


def total_records() -> int:
    with get_db() as conn:
        row = conn.execute("SELECT COUNT(*) AS total FROM measurements").fetchone()
    return int(row["total"])


def today_iso() -> str:
    return date.today().isoformat()


def total_milk_today() -> float:
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(milk_ml), 0) AS total
            FROM milk_logs
            WHERE substr(fed_at, 1, 10) = ?
            """,
            (today_iso(),),
        ).fetchone()
    return float(row["total"])


def total_poop_today() -> int:
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(count), 0) AS total
            FROM poop_logs
            WHERE pooped_on = ?
            """,
            (today_iso(),),
        ).fetchone()
    return int(row["total"])


def list_metric_points(column: str) -> list[dict[str, Any]]:
    if column not in METRICS:
        raise ValueError("Unsupported metric column.")

    with get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT measured_at, {column} AS value
            FROM measurements
            WHERE {column} IS NOT NULL
            ORDER BY measured_at ASC, id ASC
            """
        ).fetchall()

    points = []
    for row in rows:
        measured_at = row["measured_at"]
        points.append(
            {
                "measured_at": measured_at,
                "label": measured_at.replace("T", " "),
                "value": row["value"],
            }
        )
    return points


def parse_local_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def age_days_at(measured_at: str, born_at: str) -> float:
    age = parse_local_datetime(measured_at) - parse_local_datetime(born_at)
    return max(age.total_seconds() / 86400, 0)


def add_calendar_months(start: date, months: int) -> date:
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, monthrange(year, month)[1])
    return date(year, month, day)


def calendar_age_label(on_date: date, born_at: Optional[str]) -> Optional[str]:
    if not born_at:
        return None

    born_on = parse_local_datetime(born_at).date()
    if on_date < born_on:
        return None

    months = (on_date.year - born_on.year) * 12 + on_date.month - born_on.month
    month_anniversary = add_calendar_months(born_on, months)
    if month_anniversary > on_date:
        months -= 1
        month_anniversary = add_calendar_months(born_on, months)

    days = (on_date - month_anniversary).days
    month_word = "month" if months == 1 else "months"
    day_word = "day" if days == 1 else "days"
    return f"{months} {month_word} {days} {day_word}"


def average_measurements(values: list[float]) -> Optional[float]:
    return None if not values else sum(values) / len(values)


def list_journal_date_keys(
    before: Optional[str] = None,
    limit: Optional[int] = JOURNAL_BATCH_DAYS,
) -> list[str]:
    params: list[Any] = []
    where_clause = ""
    if before:
        date.fromisoformat(before)
        where_clause = "WHERE measured_at < ?"
        params.append(f"{before}T00:00")
    limit_clause = ""
    if limit is not None:
        limit_clause = "LIMIT ?"
        params.append(limit)

    with get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT DISTINCT substr(measured_at, 1, 10) AS date_key
            FROM measurements
            {where_clause}
            ORDER BY date_key DESC
            {limit_clause}
            """,
            params,
        ).fetchall()
    return [row["date_key"] for row in rows]


def list_measurements_for_journal_dates(date_keys: list[str]) -> list[dict[str, Any]]:
    if not date_keys:
        return []

    oldest = date.fromisoformat(date_keys[-1])
    newest = date.fromisoformat(date_keys[0])
    range_end = newest + timedelta(days=1)
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM measurements
            WHERE measured_at >= ? AND measured_at < ?
            ORDER BY measured_at DESC, id DESC
            """,
            (oldest.isoformat(), range_end.isoformat()),
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def build_journal_days(
    baby_profile: Optional[dict[str, Any]],
    measurements: Optional[list[dict[str, Any]]] = None,
) -> list[dict[str, Any]]:
    days: dict[str, dict[str, Any]] = {}
    born_at = None if baby_profile is None else baby_profile.get("born_at")

    for measurement in measurements if measurements is not None else list_measurements():
        date_key = measurement["measured_at"][:10]
        if date_key not in days:
            journal_date = date.fromisoformat(date_key)
            days[date_key] = {
                "date": date_key,
                "date_label": f"{journal_date.strftime('%B')} {journal_date.day}, {journal_date.year}",
                "age_label": calendar_age_label(journal_date, born_at),
                "photos": [],
                "notes": [],
                "weight_values": [],
                "height_values": [],
            }

        time_label = measurement["measured_at"][11:16]
        day = days[date_key]
        if measurement["photo_filename"]:
            day["photos"].append(
                {
                    "filename": measurement["photo_filename"],
                    "time_label": time_label,
                }
            )
        if measurement["note"]:
            day["notes"].append(
                {"text": measurement["note"], "time_label": time_label}
            )
        if measurement["weight_kg"] is not None:
            day["weight_values"].append(measurement["weight_kg"])
        if measurement["height_cm"] is not None:
            day["height_values"].append(measurement["height_cm"])

    for day in days.values():
        day["average_weight"] = average_measurements(day.pop("weight_values"))
        day["average_height"] = average_measurements(day.pop("height_values"))

    return list(days.values())


def get_journal_page(
    baby_profile: Optional[dict[str, Any]],
    before: Optional[str] = None,
) -> dict[str, Any]:
    date_keys = list_journal_date_keys(before, JOURNAL_BATCH_DAYS + 1)
    visible_keys = date_keys[:JOURNAL_BATCH_DAYS]
    measurements = list_measurements_for_journal_dates(visible_keys)
    has_more = len(date_keys) > JOURNAL_BATCH_DAYS
    return {
        "days": build_journal_days(baby_profile, measurements),
        "has_more": has_more,
        "next_before": visible_keys[-1] if has_more and visible_keys else None,
    }


def standard_value_for_day(rows: list[dict[str, Any]], day: float, percentile: str) -> float:
    if day <= rows[0]["day"]:
        return rows[0][percentile]
    if day >= rows[-1]["day"]:
        return rows[-1][percentile]

    low_index = int(day)
    high_index = min(low_index + 1, len(rows) - 1)
    low = rows[low_index]
    high = rows[high_index]
    fraction = day - low["day"]
    return low[percentile] + (high[percentile] - low[percentile]) * fraction


def sampled_reference_days(max_age_days: int) -> list[int]:
    if max_age_days <= 0:
        return [0]
    step = 7 if max_age_days <= 365 else 30
    days = list(range(0, max_age_days + 1, step))
    if days[-1] != max_age_days:
        days.append(max_age_days)
    return days


def build_who_reference_lines(
    metric: str,
    points: list[dict[str, Any]],
    baby_profile: Optional[dict[str, Any]],
    who_standards: dict[str, Any],
) -> list[dict[str, Any]]:
    if not baby_profile or not baby_profile.get("born_at") or not baby_profile.get("sex"):
        return []

    rows = (
        who_standards.get("metrics", {})
        .get(metric, {})
        .get(baby_profile["sex"], [])
    )
    if not rows:
        return []

    if points:
        max_age = max(age_days_at(point["measured_at"], baby_profile["born_at"]) for point in points)
    else:
        max_age = age_days_at(datetime.now().strftime("%Y-%m-%dT%H:%M"), baby_profile["born_at"])

    max_age_days = min(max(int(max_age) + 7, 30), rows[-1]["day"])
    born_at = parse_local_datetime(baby_profile["born_at"])
    days = sampled_reference_days(max_age_days)
    lines = []

    for percentile, label in [("p3", "WHO P3"), ("p50", "WHO P50"), ("p97", "WHO P97")]:
        lines.append(
            {
                "key": percentile,
                "label": label,
                "points": [
                    {
                        "measured_at": (born_at + timedelta(days=day)).isoformat(timespec="minutes"),
                        "label": (born_at + timedelta(days=day)).strftime("%Y-%m-%d"),
                        "value": round(standard_value_for_day(rows, day, percentile), 3),
                    }
                    for day in days
                ],
            }
        )

    return lines


def build_growth_charts(baby_profile: Optional[dict[str, Any]]) -> list[dict[str, Any]]:
    who_standards = load_who_standards()
    charts = []
    for column, config in METRICS.items():
        points = list_metric_points(column)
        latest = points[-1]["value"] if points else None
        previous = points[-2]["value"] if len(points) > 1 else None
        change = None if latest is None or previous is None else latest - previous

        charts.append(
            {
                "key": column,
                "label": config["label"],
                "unit": config["unit"],
                "decimals": config["decimals"],
                "latest": latest,
                "change": change,
                "points": points,
                "reference_lines": build_who_reference_lines(
                    column,
                    points,
                    baby_profile,
                    who_standards,
                ),
            }
        )
    return charts


def list_milk_event_points() -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT fed_at, milk_ml
            FROM milk_logs
            ORDER BY fed_at ASC, id ASC
            """
        ).fetchall()

    return [
        {
            "measured_at": row["fed_at"],
            "label": row["fed_at"].replace("T", " "),
            "value": row["milk_ml"],
        }
        for row in rows
    ]


def list_daily_milk_points() -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT substr(fed_at, 1, 10) AS day, SUM(milk_ml) AS value
            FROM milk_logs
            GROUP BY day
            ORDER BY day ASC
            """
        ).fetchall()

    return [
        {
            "measured_at": row["day"],
            "label": row["day"],
            "value": row["value"],
        }
        for row in rows
    ]


def list_daily_poop_points() -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT pooped_on AS day, SUM(count) AS value
            FROM poop_logs
            GROUP BY pooped_on
            ORDER BY pooped_on ASC
            """
        ).fetchall()

    return [
        {
            "measured_at": row["day"],
            "label": row["day"],
            "value": row["value"],
        }
        for row in rows
    ]


def build_care_charts() -> list[dict[str, Any]]:
    milk_events = list_milk_event_points()
    milk_daily = list_daily_milk_points()
    poop_daily = list_daily_poop_points()

    return [
        {
            "key": "milk_ml",
            "label": "Milk",
            "unit": "ml",
            "decimals": 0,
            "kind": "bar",
            "default_scale": "daily",
            "scales": {
                "daily": {
                    "label": "Daily total",
                    "points": milk_daily,
                    "hover_time_format": "%Y-%m-%d",
                },
                "events": {
                    "label": "Each feeding",
                    "points": milk_events,
                    "hover_time_format": "%Y-%m-%d %H:%M",
                },
            },
            "today_total": total_milk_today(),
        },
        {
            "key": "poop_count",
            "label": "Poop",
            "unit": "times",
            "decimals": 0,
            "kind": "bar",
            "default_scale": "daily",
            "scales": {
                "daily": {
                    "label": "Daily count",
                    "points": poop_daily,
                    "hover_time_format": "%Y-%m-%d",
                },
            },
            "today_total": total_poop_today(),
        },
    ]


def build_single_metric(
    metric_type: Optional[str],
    metric_value: Optional[str],
) -> dict[str, Optional[float]]:
    values = {
        "weight_kg": None,
        "height_cm": None,
        "head_circumference_cm": None,
    }

    if metric_type not in values:
        raise ValueError("Choose a metric.")

    values[metric_type] = blank_to_none(metric_value)
    return values


@app.get("/", response_class=HTMLResponse)
def home(
    request: Request,
    error: Optional[str] = None,
    profile_error: Optional[str] = None,
    tab: str = "entry",
    entry_type: str = "growth",
    dashboard_type: str = "growth",
    history_type: str = "growth",
    history_error: Optional[str] = None,
    growth_limit: int = HISTORY_PAGE_SIZE,
    milk_limit: int = HISTORY_PAGE_SIZE,
    poop_limit: int = HISTORY_PAGE_SIZE,
    journal_date: Optional[str] = None,
) -> HTMLResponse:
    active_tab = (
        tab
        if tab in {"entry", "dashboard", "journal", "history", "settings"}
        else "entry"
    )
    active_entry = entry_type if entry_type in {"growth", "milk", "poop"} else "growth"
    active_dashboard = (
        dashboard_type if dashboard_type in {"growth", "milk", "poop"} else "growth"
    )
    active_history = (
        history_type if history_type in {"growth", "milk", "poop"} else "growth"
    )
    baby_profile = get_baby_profile()
    growth_limit = normalize_history_limit(growth_limit)
    milk_limit = normalize_history_limit(milk_limit)
    poop_limit = normalize_history_limit(poop_limit)
    growth_history = list_measurements(limit=growth_limit + 1)
    milk_history = list_milk_logs(limit=milk_limit + 1)
    poop_history = list_poop_logs(limit=poop_limit + 1)
    growth_charts = build_growth_charts(baby_profile)
    care_charts = build_care_charts()
    journal_date_keys = list_journal_date_keys(limit=None)
    journal_focus_date: Optional[str] = None
    if journal_date:
        try:
            date.fromisoformat(journal_date)
        except ValueError:
            journal_date = None
        if journal_date in journal_date_keys:
            journal_focus_date = journal_date

    journal_before = None
    if journal_focus_date:
        journal_before = (
            date.fromisoformat(journal_focus_date) + timedelta(days=1)
        ).isoformat()
    journal_page = get_journal_page(baby_profile, journal_before)
    calendar_initial_date = (
        journal_focus_date
        or (journal_date_keys[0] if journal_date_keys else today_iso())
    )
    summary = {
        "latest_weight": latest_value("weight_kg"),
        "latest_height": latest_value("height_cm"),
        "latest_head": latest_value("head_circumference_cm"),
        "total_records": total_records(),
    }
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "now_local": datetime.now().strftime("%Y-%m-%dT%H:%M"),
            "today": today_iso(),
            "error": error,
            "profile_error": profile_error,
            "active_tab": active_tab,
            "active_entry": active_entry,
            "active_dashboard": active_dashboard,
            "active_history": active_history,
            "history_error": history_error,
            "baby_profile": baby_profile,
            "profile_born_at_input": format_born_at_for_input(
                None if baby_profile is None else baby_profile["born_at"]
            ),
            "growth_charts": growth_charts,
            "growth_charts_json": json.dumps(growth_charts),
            "care_charts": care_charts,
            "care_charts_json": json.dumps(care_charts),
            "summary": summary,
            "measurements": growth_history[:growth_limit],
            "milk_logs": milk_history[:milk_limit],
            "poop_logs": poop_history[:poop_limit],
            "growth_limit": growth_limit,
            "milk_limit": milk_limit,
            "poop_limit": poop_limit,
            "growth_has_more": len(growth_history) > growth_limit,
            "milk_has_more": len(milk_history) > milk_limit,
            "poop_has_more": len(poop_history) > poop_limit,
            "journal_days": journal_page["days"],
            "journal_has_more": journal_page["has_more"],
            "journal_next_before": journal_page["next_before"],
            "journal_date_keys_json": json.dumps(journal_date_keys),
            "journal_initial_date": calendar_initial_date,
            "journal_focus_date": journal_focus_date,
        },
        headers={"Cache-Control": "no-store"},
    )


@app.get("/journal/entries", response_class=HTMLResponse)
def journal_entries(request: Request, before: str) -> HTMLResponse:
    try:
        journal_page = get_journal_page(get_baby_profile(), before)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid Journal date cursor.") from exc

    return templates.TemplateResponse(
        "journal_days.html",
        {"request": request, "journal_days": journal_page["days"]},
        headers={
            "Cache-Control": "no-store",
            "X-Journal-Has-More": "true" if journal_page["has_more"] else "false",
            "X-Journal-Next-Before": journal_page["next_before"] or "",
        },
    )


@app.post("/measurements")
async def save_measurement(
    measured_at: str = Form(...),
    entry_mode: str = Form("single"),
    metric_type: Optional[str] = Form(None),
    metric_value: Optional[str] = Form(None),
    weight_kg: Optional[str] = Form(None),
    height_cm: Optional[str] = Form(None),
    head_circumference_cm: Optional[str] = Form(None),
    note: Optional[str] = Form(None),
    photo: Optional[UploadFile] = File(None),
) -> RedirectResponse:
    stored_filename: Optional[str] = None
    try:
        photo_data = await prepare_uploaded_photo(photo)
        if entry_mode == "single":
            values = build_single_metric(metric_type, metric_value)
        elif entry_mode == "full":
            values = {
                "weight_kg": blank_to_none(weight_kg),
                "height_cm": blank_to_none(height_cm),
                "head_circumference_cm": blank_to_none(head_circumference_cm),
            }
        elif entry_mode == "photo":
            values = {
                "weight_kg": None,
                "height_cm": None,
                "head_circumference_cm": None,
            }
        else:
            raise ValueError("Choose a growth entry mode.")

        data = MeasurementInput(
            measured_at=measured_at,
            weight_kg=values["weight_kg"],
            height_cm=values["height_cm"],
            head_circumference_cm=values["head_circumference_cm"],
            note=note,
            photo_filename=None if photo_data is None else photo_data[0],
        )
        if photo_data is not None:
            stored_filename = store_photo(photo_data)
        create_measurement(data)
    except ValueError as exc:
        remove_stored_photo(stored_filename)
        return RedirectResponse(
            f"/?{urlencode({'error': str(exc), 'entry_type': 'growth'})}",
            status_code=303,
        )
    except Exception:
        remove_stored_photo(stored_filename)
        raise

    return RedirectResponse("/?entry_type=growth", status_code=303)


@app.post("/milk")
def save_milk(
    fed_at: str = Form(...),
    milk_ml: str = Form(...),
    note: Optional[str] = Form(None),
) -> RedirectResponse:
    try:
        data = MilkLogInput(fed_at=fed_at, milk_ml=float(milk_ml), note=note)
        create_milk_log(data)
    except ValueError as exc:
        return RedirectResponse(
            f"/?{urlencode({'error': str(exc), 'entry_type': 'milk'})}",
            status_code=303,
        )

    return RedirectResponse("/?entry_type=milk", status_code=303)


@app.post("/poop")
def save_poop(
    pooped_on: str = Form(...),
    count: int = Form(1),
    note: Optional[str] = Form(None),
) -> RedirectResponse:
    try:
        data = PoopLogInput(pooped_on=pooped_on, count=count, note=note)
        create_poop_log(data)
    except ValueError as exc:
        return RedirectResponse(
            f"/?{urlencode({'error': str(exc), 'entry_type': 'poop'})}",
            status_code=303,
        )

    return RedirectResponse("/?entry_type=poop", status_code=303)


@app.post("/measurements/{measurement_id}/edit")
async def edit_measurement(
    measurement_id: int,
    measured_at: str = Form(...),
    weight_kg: Optional[str] = Form(None),
    height_cm: Optional[str] = Form(None),
    head_circumference_cm: Optional[str] = Form(None),
    note: Optional[str] = Form(None),
    photo: Optional[UploadFile] = File(None),
    remove_photo: Optional[str] = Form(None),
    history_limit: int = Form(HISTORY_PAGE_SIZE),
) -> RedirectResponse:
    current = get_measurement(measurement_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Measurement not found.")

    stored_filename: Optional[str] = None
    try:
        photo_data = await prepare_uploaded_photo(photo)
        photo_filename = current["photo_filename"]
        if photo_data is not None:
            photo_filename = photo_data[0]
        elif remove_photo == "true":
            photo_filename = None

        data = MeasurementInput(
            measured_at=measured_at,
            weight_kg=blank_to_none(weight_kg),
            height_cm=blank_to_none(height_cm),
            head_circumference_cm=blank_to_none(head_circumference_cm),
            note=note,
            photo_filename=photo_filename,
        )
        if photo_data is not None:
            stored_filename = store_photo(photo_data)
        if not update_measurement(measurement_id, data):
            raise HTTPException(status_code=404, detail="Measurement not found.")
    except ValueError as exc:
        remove_stored_photo(stored_filename)
        return history_redirect("growth", str(exc), history_limit)
    except Exception:
        remove_stored_photo(stored_filename)
        raise

    if current["photo_filename"] != photo_filename:
        remove_stored_photo(current["photo_filename"])
    return history_redirect("growth", visible_limit=history_limit)


@app.post("/measurements/{measurement_id}/delete")
def remove_measurement(
    measurement_id: int,
    history_limit: int = Form(HISTORY_PAGE_SIZE),
) -> RedirectResponse:
    current = get_measurement(measurement_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Measurement not found.")
    if not delete_measurement(measurement_id):
        raise HTTPException(status_code=404, detail="Measurement not found.")
    remove_stored_photo(current["photo_filename"])
    return history_redirect("growth", visible_limit=history_limit)


@app.post("/milk/{log_id}/edit")
def edit_milk_log(
    log_id: int,
    fed_at: str = Form(...),
    milk_ml: str = Form(...),
    note: Optional[str] = Form(None),
    history_limit: int = Form(HISTORY_PAGE_SIZE),
) -> RedirectResponse:
    try:
        data = MilkLogInput(fed_at=fed_at, milk_ml=float(milk_ml), note=note)
        if not update_milk_log(log_id, data):
            raise HTTPException(status_code=404, detail="Milk record not found.")
    except ValueError as exc:
        return history_redirect("milk", str(exc), history_limit)
    return history_redirect("milk", visible_limit=history_limit)


@app.post("/milk/{log_id}/delete")
def remove_milk_log(
    log_id: int,
    history_limit: int = Form(HISTORY_PAGE_SIZE),
) -> RedirectResponse:
    if not delete_milk_log(log_id):
        raise HTTPException(status_code=404, detail="Milk record not found.")
    return history_redirect("milk", visible_limit=history_limit)


@app.post("/poop/{log_id}/edit")
def edit_poop_log(
    log_id: int,
    pooped_on: str = Form(...),
    count: int = Form(...),
    note: Optional[str] = Form(None),
    history_limit: int = Form(HISTORY_PAGE_SIZE),
) -> RedirectResponse:
    try:
        data = PoopLogInput(pooped_on=pooped_on, count=count, note=note)
        if not update_poop_log(log_id, data):
            raise HTTPException(status_code=404, detail="Poop record not found.")
    except ValueError as exc:
        return history_redirect("poop", str(exc), history_limit)
    return history_redirect("poop", visible_limit=history_limit)


@app.post("/poop/{log_id}/delete")
def remove_poop_log(
    log_id: int,
    history_limit: int = Form(HISTORY_PAGE_SIZE),
) -> RedirectResponse:
    if not delete_poop_log(log_id):
        raise HTTPException(status_code=404, detail="Poop record not found.")
    return history_redirect("poop", visible_limit=history_limit)


@app.post("/profile")
def save_profile(
    name: str = Form(...),
    sex: Optional[str] = Form(None),
    born_at: Optional[str] = Form(None),
) -> RedirectResponse:
    try:
        profile = BabyProfileInput(name=name, sex=sex, born_at=born_at)
        save_baby_profile(profile)
    except ValueError as exc:
        query = urlencode({"tab": "settings", "profile_error": str(exc)})
        return RedirectResponse(f"/?{query}", status_code=303)

    return RedirectResponse("/?tab=settings", status_code=303)


@app.get("/export.csv")
def export_csv() -> Response:
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "id",
            "measured_at",
            "weight_kg",
            "height_cm",
            "head_circumference_cm",
            "note",
            "photo_filename",
            "created_at",
        ],
    )
    writer.writeheader()
    writer.writerows(list_measurements(order="ASC"))

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=babylog-measurements.csv"},
    )


@app.get("/api/measurements")
def api_list_measurements() -> list[dict[str, Any]]:
    return list_measurements()


@app.post("/api/measurements", status_code=201)
def api_create_measurement(data: MeasurementInput) -> dict[str, Any]:
    if data.photo_filename is not None:
        raise HTTPException(
            status_code=400,
            detail="Upload photos through the Growth form, not the JSON API.",
        )
    try:
        return create_measurement(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
