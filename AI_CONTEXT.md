# AI Context

## Project Purpose

BabyLog is a small local-first baby growth tracking app. The primary use case is quick measurement entry from an iPhone browser while the FastAPI server runs on a Mac on the same Wi-Fi network.

## Current Product Scope

The MVP tracks date-time measurements:

- Weight in kilograms.
- Height in centimeters.
- Head circumference in centimeters.
- Milk amount in milliliters, timestamped per feeding.
- Poop count by date.
- Optional local baby photo on Growth records, including photo-only records.
- Optional note.

The home page has Entry, Dashboard, Journal, History, and Settings tabs. Journal is a newest-first read-only infinite-scroll feed that includes only dates containing Growth records. It loads 10 recorded days initially and automatically appends 10 older days near the bottom. Each day card shows every local photo and note from that date, one Weight value and one Height value, and calendar age when the baby birth date is configured. Daily Weight/Height values are arithmetic averages when multiple measurements exist and `-` when missing. Head circumference is intentionally omitted from Journal. Entry, Dashboard, and History each use Growth, Milk, and Poop sub-tabs so only one category is visible at a time. The `entry_type`, `dashboard_type`, and `history_type` query parameters preserve those selections.

Journal includes a compact calendar of recorded Growth dates. It is sticky at the top below 768px and becomes a sticky right sidebar at 768px and above. The caret collapse state is stored in browser local storage. Clicking a loaded date scrolls to its card; clicking an unloaded older date reloads with `journal_date=YYYY-MM-DD` and continues infinite scrolling backward. `Latest` returns to the newest batch.

History record cards support inline editing and confirmed deletion for all three categories. Update handlers reuse the same Pydantic validation models as create handlers.

History initially renders 10 records per category. `growth_limit`, `milk_limit`, and `poop_limit` query parameters independently reveal 10 more records while keeping older records editable. Edit/delete forms preserve the active category's visible limit.

The app also has a Settings tab for a single baby profile:

- Baby name.
- Sex, used only to choose WHO growth standard tables.
- Born date and time.
- Stored in `baby_profile` with one row, `id = 1`.

Growth entry supports three modes:

- Single: choose one metric, enter one value, optionally add a note.
- Full: enter weight, height, head circumference, and optionally add a note.
- Photo: upload one local image and optionally add a note without requiring a metric.

Dashboard charts:

- Use the local vendored Plotly.js bundle at `static/vendor/plotly-3.6.0.min.js`.
- Show separate trends for weight, height, and head circumference.
- Overlay WHO P3/P50/P97 reference curves when baby sex and born date/time are set.
- Show milk as a bar chart with daily total or each feeding scale. Each feeding opens in a draggable 24-hour x-axis window.
- Show poop as a daily count bar chart.
- Use local data from `data/who/standards.json`, extracted from official WHO expanded percentile tables.
- Do not use CDN assets; Dashboard charts must work from local static files.

## Tech Stack Decisions

- Python 3.
- FastAPI.
- SQLite using Python standard library `sqlite3`.
- Jinja2 templates.
- Plain HTML, CSS, and minimal browser-native behavior.
- No React or frontend framework.
- No SQLAlchemy or ORM.
- No migrations yet.
- No authentication in the MVP.
- No multi-child support in the MVP.

## What Not To Add Yet

Do not add these unless the product direction changes:

- User accounts.
- Login or sessions.
- Docker.
- React, Vue, Svelte, or another frontend framework.
- CSS frameworks or CDN assets.
- SQLAlchemy, Alembic, or a migration framework.
- External CDN assets.
- Complex settings or environment configuration.

## Coding Style

- Keep code readable and direct.
- Prefer small helper functions with clear names.
- Use standard library tools when they are enough.
- Keep SQLite SQL explicit and easy to inspect.
- Add comments only when they explain a non-obvious choice.
- Keep UI labels and code in English.

## Important Constraints

- Empty optional number fields must be saved as `NULL`.
- `measured_at` is required and should include date plus `HH:MM`.
- Milk logs require `fed_at` with date plus `HH:MM` and a positive `milk_ml`.
- Poop logs require `pooped_on` date and allow a daily count of `0` or more.
- Baby profile settings are local and single-child only.
- WHO reference curves are visual context only, not diagnosis or medical advice.
- Growth records require at least one measurement value or a photo.
- Photos are limited to 15 MB and validated by file signature before storage.
- SQLite stores generated photo filenames; image files live in `static/uploads/`.
- Deleting or replacing a Growth photo must remove the superseded local file.
- A complete backup requires both `babylog.db` and `static/uploads/`.
- Latest records sort by `measured_at DESC, id DESC`.
- CSV export sorts by `measured_at ASC, id ASC`.
- The app must remain comfortable on iPhone Safari.

## Future AI Agent Instructions

Before changing behavior, read:

1. `README.md`
2. `ARCHITECTURE.md`
3. `ROADMAP.md`
4. `CHANGELOG.md`
5. `app.py`

When adding features, keep changes narrow and update docs in the same change. Prefer the current simple architecture until there is a clear reason to introduce more structure.
