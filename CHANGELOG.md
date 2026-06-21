# Changelog

## 2026-06-21

- Added `.gitignore` rules to keep SQLite data and uploaded baby photos local.
- Added a Journal tab scaffold between Dashboard and History.
- Built the Growth-only Journal feed with day cards, photos, metrics, notes, times, and calendar age.
- Changed Journal day cards to retain all photos/notes while showing one averaged Weight and Height value.
- Added independent History pagination with `Load older records` controls for Growth, Milk, and Poop.
- Replaced full Journal rendering with automatic infinite scrolling in 10-day server batches.
- Added a collapsible Journal calendar with sticky mobile and right-sidebar tablet/desktop layouts.

## 2026-06-20

- Moved the main navigation to a compact, fixed bottom tab bar with icons and iPhone safe-area support.
- Added UI cache busting so mobile Safari receives current HTML and CSS after updates.
- Split quick entry into compact Growth, Milk, and Poop sub-tabs with icons.
- Added matching Growth, Milk, and Poop sub-tabs to Dashboard and History.
- Fixed date and time inputs overflowing their containers on mobile Safari.
- Strengthened the iPhone-specific date control sizing for Safari's native intrinsic width behavior.
- Added inline edit and confirmed delete actions for growth, milk, and poop history records.
- Changed the Milk each-feeding chart to a horizontally draggable 24-hour window.
- Added locally stored Growth photos, photo-only entry mode, History previews, and file-aware edit/delete behavior.

## 2026-06-19 - History Care Records Update

- Show latest milk records in the History tab.
- Show latest poop records in the History tab.

## 2026-06-19 - Poop Count Update

- Allow poop count `0` for days when the baby does not poop.

## 2026-06-19 - Care Metrics Update

- Added milk tracking with timestamped amount in milliliters.
- Added poop tracking with daily count.
- Added milk and poop quick entry forms.
- Added Dashboard bar charts for milk and poop using local Plotly.js.

## 2026-06-19 - Plotly Dashboard Update

- Replaced custom inline SVG chart rendering with local vendored Plotly.js.
- Added `static/vendor/plotly-3.6.0.min.js` for offline chart rendering without CDN access.
- Updated Dashboard chart code to render baby measurements and WHO reference curves as Plotly traces.

## 2026-06-19 - WHO Standards Update

- Added local WHO growth standards extract for weight-for-age, length/height-for-age, and head circumference-for-age.
- Added sex field to baby settings for WHO standard selection.
- Added WHO P3/P50/P97 reference overlays to Dashboard charts.
- Documented WHO data sources and visual-reference limitation.

## 2026-06-19 - Dashboard Update

- Added Dashboard tab with growth charts for weight, height, and head circumference.
- Render charts with plain inline SVG and JavaScript without chart libraries.
- Added latest value and last-change summary to each chart card.

## 2026-06-19 - Baby Settings Update

- Added Settings tab for a single baby profile.
- Added `baby_profile` SQLite table with baby name and optional born date/time.
- Show the configured baby name in the app header.

## 2026-06-19 - Quick Entry Update

- Added Entry and History tabs.
- Added single-metric quick entry mode for fast weight, height, or head circumference logging.
- Added full entry mode for saving multiple metrics together.
- Changed measurement input from date-only to date and time with `HH:MM`.

## 2026-06-19 - Initial MVP

- Initial BabyLog MVP.
- Added FastAPI app with SQLite storage.
- Added mobile-first home page with quick measurement entry.
- Added latest records, summary cards, CSV export, and JSON API.
- Added AI-facing documentation for future development.
