# BabyLog

BabyLog is a minimal self-hosted baby growth tracking web app. It runs as a local FastAPI server on a Mac and can be opened from an iPhone browser on the same Wi-Fi network for quick data entry.

This is an MVP. It intentionally avoids accounts, authentication, migrations, Docker, ORMs, frontend frameworks, and CDN assets.

WHO reference curves are visual guidance only. BabyLog is not a medical device and does not provide medical advice.

## MVP Features

- Mobile-first Entry tab with Growth, Milk, and Poop sub-tabs for no-scroll access to each form.
- Full entry mode for saving weight, height, and head circumference together.
- Photo-only Growth entries stored locally with optional notes.
- Date and time capture for each measurement.
- Settings tab for one baby profile with name and born date/time.
- Dashboard tab with Growth, Milk, and Poop sub-tabs for focused charts.
- Infinite-scroll Journal feed with one card per Growth day, all photos and notes, averaged Weight/Height, and calendar age.
- Compact Journal calendar that stays at the top on phones and in a sticky right sidebar on iPad and Mac.
- WHO P3/P50/P97 growth reference curves on the Dashboard when baby sex and born date/time are set.
- Local vendored Plotly.js bundle for offline dashboard charts.
- Milk tracking with per-feeding entry, daily totals, and a draggable 24-hour feeding chart.
- Poop tracking with daily count entry and Dashboard bar chart.
- History tab with Growth, Milk, and Poop sub-tabs for focused records.
- History loads the latest 10 records first and can reveal older records in groups of 10.
- Inline editing and confirmed deletion for growth, milk, and poop records.
- SQLite storage in `babylog.db`.
- Local growth photo storage in `static/uploads/`.
- Latest 10 measurements on the History tab.
- Summary cards for latest weight, latest height, latest head circumference, and total records.
- CSV export at `/export.csv`.
- JSON API for listing and creating measurements.

## Setup

```bash
cd /Users/hiepqvbn/projects/babylog
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

Open on the Mac:

```text
http://localhost:8000
```

## Open From iPhone

Make sure the Mac and iPhone are on the same Wi-Fi network. Find the Mac IP address, then open this URL in iPhone Safari:

```text
http://MAC_IP_ADDRESS:8000
```

Example:

```text
http://192.168.1.25:8000
```

## Find Mac IP Address

Option 1:

```bash
ipconfig getifaddr en0
```

Option 2:

```bash
ifconfig | grep "inet "
```

Use the local network address, usually something like `192.168.x.x` or `10.0.x.x`.

## Export CSV

Open this route in a browser:

```text
http://localhost:8000/export.csv
```

From iPhone, use:

```text
http://MAC_IP_ADDRESS:8000/export.csv
```

CSV includes each photo's local filename but not the image bytes. Back up both
`babylog.db` and `static/uploads/` to preserve the complete BabyLog history.

## JSON API

List measurements:

```bash
curl http://localhost:8000/api/measurements
```

Create a measurement:

```bash
curl -X POST http://localhost:8000/api/measurements \
  -H "Content-Type: application/json" \
  -d '{"measured_at":"2026-06-19T10:30","weight_kg":4.25,"height_cm":54.3,"head_circumference_cm":38.1,"note":"Morning check"}'
```
