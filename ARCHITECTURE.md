# Architecture

## Request Flow

1. A browser requests `/`.
2. FastAPI calls SQLite helper functions in `app.py`.
3. `templates/index.html` renders Growth/Milk/Poop sub-tabs within Entry, Dashboard, and History, plus the Growth-only Journal feed, Settings, summary data, forms, charts, and latest records.
4. The form posts to `/measurements`.
5. The server maps single-metric or full-entry form data into the same measurement shape.
6. The server validates the form data, inserts a row into SQLite, and redirects back to `/`.

Milk and poop forms post to `/milk` and `/poop`. The profile form posts to `/profile`, which upserts the single baby profile row and redirects back to the Settings tab. Dashboard charts are built from SQLite metric queries, passed to the template as JSON, and rendered by the local vendored Plotly.js bundle in `static/vendor/`. CSV export and JSON API routes use the same database helpers as the HTML page.

## File Responsibilities

- `app.py`: FastAPI app, route handlers, validation model, SQLite helpers, CSV export, JSON API.
- `babylog.db`: SQLite database file created automatically at startup.
- `requirements.txt`: Python runtime dependencies.
- `templates/index.html`: Home page markup.
- `static/style.css`: Mobile-first app styling.
- `static/uploads/`: Locally stored Growth photos with generated filenames.
- `README.md`: Human setup and usage guide.
- `AI_CONTEXT.md`: AI-facing project context and constraints.
- `ARCHITECTURE.md`: Technical structure and contracts.
- `ROADMAP.md`: Planned product phases.
- `CHANGELOG.md`: Human-readable change history.

## Database Schema

Table: `measurements`

```sql
CREATE TABLE IF NOT EXISTS measurements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    measured_at TEXT NOT NULL,
    weight_kg REAL,
    height_cm REAL,
    head_circumference_cm REAL,
    note TEXT,
    photo_filename TEXT,
    created_at TEXT NOT NULL
);
```

Measurement date-times are stored as ISO text with minute precision. `created_at` is stored as an ISO UTC timestamp. `photo_filename` contains only a generated local filename; image bytes are stored under `static/uploads/`. A Growth row is valid when it contains at least one metric or a photo.

Table: `baby_profile`

```sql
CREATE TABLE IF NOT EXISTS baby_profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    name TEXT NOT NULL,
    sex TEXT,
    born_at TEXT,
    updated_at TEXT NOT NULL
);
```

`baby_profile` intentionally stores one baby only. `sex` is `female`, `male`, or `NULL` and is used only for WHO growth standard overlays. `born_at` is stored as ISO text with minute precision when provided.

Table: `milk_logs`

```sql
CREATE TABLE IF NOT EXISTS milk_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fed_at TEXT NOT NULL,
    milk_ml REAL NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL
);
```

Table: `poop_logs`

```sql
CREATE TABLE IF NOT EXISTS poop_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pooped_on TEXT NOT NULL,
    count INTEGER NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL
);
```

Poop `count` may be `0` because no-poop days are meaningful tracking data.

## Route List

- `GET /`: Render the home page.
- `POST /measurements`: Save metrics or a photo-only Growth record from the multipart HTML form and redirect to `/`.
- `POST /milk`: Save a milk feeding amount from the Entry tab and redirect to `/`.
- `POST /poop`: Save a daily poop count from the Entry tab and redirect to `/`.
- `POST /measurements/{id}/edit`: Update a growth record.
- `POST /measurements/{id}/delete`: Delete a growth record.
- `POST /milk/{id}/edit`: Update a milk record.
- `POST /milk/{id}/delete`: Delete a milk record.
- `POST /poop/{id}/edit`: Update a poop record.
- `POST /poop/{id}/delete`: Delete a poop record.
- `POST /profile`: Save the single baby profile from the Settings tab and redirect to `/?tab=settings`.
- `GET /export.csv`: Export all measurements as CSV.
- `GET /api/measurements`: Return all measurements as JSON.
- `POST /api/measurements`: Create a measurement from JSON and return the created record.
- `GET /journal/entries?before=YYYY-MM-DD`: Return the next Journal day-card HTML batch.

The JSON API does not accept photo uploads. Photos use the multipart Growth form.

## Journal Contract

- Journal uses existing `measurements` rows and does not have a separate table.
- Only dates containing at least one Growth record are shown.
- Day cards sort newest first and load in batches of 10 recorded days.
- The initial page contains the newest batch; `IntersectionObserver` requests older batches near the scroll boundary.
- `before` is an exclusive date cursor, avoiding duplicate day cards between batches.
- The partial `templates/journal_days.html` is shared by initial and appended cards.
- The `idx_measurements_measured_at` SQLite index supports ordered date-range reads.
- The main page accepts `journal_date=YYYY-MM-DD` to start the feed at a recorded date.
- The calendar receives the lightweight distinct-date list, not all measurement rows.
- On phones the calendar uses `position: sticky` at the top; at 768px it moves to a 220px sticky right column.
- Calendar collapse state is client-only browser local storage and does not change server data.
- Every same-day photo and note is retained in the card.
- Weight and Height appear once per day, using the arithmetic average of all same-day values or `-` when absent.
- Head circumference is intentionally omitted from Journal.
- Age uses the profile `born_at` date and calendar months plus remaining days.
- Journal is currently read-only; edits and deletes remain in History.

## History Pagination

- Growth, Milk, and Poop each render the latest 10 records initially.
- `growth_limit`, `milk_limit`, and `poop_limit` control independent visible counts.
- The server fetches one extra row to decide whether to show `Load older records`.
- Each load increases the selected category by 10 and preserves the other limits.
- Edit and delete forms carry the visible limit through their redirect.

## Dashboard Contract

- Weight chart uses `weight_kg` values ordered by `measured_at ASC, id ASC`.
- Height chart uses `height_cm` values ordered by `measured_at ASC, id ASC`.
- Head circumference chart uses `head_circumference_cm` values ordered by `measured_at ASC, id ASC`.
- X-axis positions are scaled by actual `measured_at` timestamps, not by equal point spacing.
- WHO P3/P50/P97 reference curves are loaded from `data/who/standards.json`.
- WHO curves are shown only when `baby_profile.sex` and `baby_profile.born_at` are set.
- WHO reference x-axis positions are based on age in days from `born_at`.
- Charts use local Plotly.js from `static/vendor/plotly-3.6.0.min.js`; do not load Plotly from a CDN.
- Milk chart uses Plotly bars and can switch between daily totals and each feeding. The event view starts on the latest 24-hour window and allows horizontal panning while preserving that time span.
- Poop chart uses Plotly bars for daily counts.
- Empty metric charts show an empty state instead of a blank SVG.

## API Contract

### GET `/api/measurements`

Returns all measurements sorted by `measured_at DESC, id DESC`.

Response shape:

```json
[
  {
    "id": 1,
    "measured_at": "2026-06-19T10:30",
    "weight_kg": 4.25,
    "height_cm": 54.3,
    "head_circumference_cm": 38.1,
    "note": "Morning check",
    "created_at": "2026-06-19T03:10:00+00:00"
  }
]
```

### POST `/api/measurements`

Request body:

```json
{
  "measured_at": "2026-06-19T10:30",
  "weight_kg": 4.25,
  "height_cm": 54.3,
  "head_circumference_cm": 38.1,
  "note": "Morning check"
}
```

Rules:

- `measured_at` is required and should include date plus `HH:MM`.
- At least one of `weight_kg`, `height_cm`, or `head_circumference_cm` is required.
- Number fields may be omitted or `null`.
- `note` may be omitted, `null`, or an empty string.

Success returns the created record with status `201`.

## Current Limitations

- No editing or deleting records.
- No date range filters for charts.
- No WHO growth percentile calculations.
- No authentication.
- No multi-child support.
- No migrations.
- No automated tests yet.
