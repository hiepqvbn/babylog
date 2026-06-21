# Roadmap

## Phase 1: MVP

- Create local FastAPI app.
- Store measurements in SQLite.
- Add mobile-first quick entry form.
- Show latest records and summary cards.
- Add CSV export.
- Add simple JSON API.
- Write AI-facing documentation.

## Phase 2: Charts and Dashboard

- Add weight, height, and head circumference trend charts. Done in first simple SVG pass.
- Add date range filters.
- Add clearer dashboard views for recent growth.

## Phase 3: Edit and Delete Records

- Add edit flow for correcting mistakes. Done with inline History forms.
- Add delete flow with confirmation. Done for all record types.
- Keep changes simple and mobile-friendly. Done with compact icon actions.

## Phase 4: WHO Growth Percentile Support

- Research official WHO growth standard data. Done for dashboard reference curves.
- Add P3/P50/P97 percentile reference overlays. Done in first simple SVG pass.
- Add percentile calculations for individual measurements.
- Document data source and calculation method. Started in `data/who/README.md` and `ARCHITECTURE.md`.
- Avoid adding percentile support without source verification.

## Phase 5: PWA and Add-to-Home-Screen Polish

- Add manifest and app icons.
- Improve iPhone home screen behavior.
- Consider lightweight offline-friendly polish.

## Phase 6: Optional Authentication

- Add authentication only if the app is exposed beyond a trusted local network.
- Keep local-only usage simple.
- Avoid account complexity until it is needed.
