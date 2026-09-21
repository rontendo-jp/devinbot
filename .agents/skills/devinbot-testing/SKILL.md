---
name: devinbot-dashboard-browser-testing
description: Run local dashboard browser tests with clear backend coverage limits and readable Japanese fonts.
---

# Dashboard browser testing

Start the frontend from `frontend/` using `npm run dev`. If Node is missing from PATH, locate the installed version under `~/.nvm/versions/node/` and add its `bin` directory. No frontend login is required.

## Backend coverage

The frontend defaults to localhost:8000. Local backend startup needs `backend/.env`. A deployed backend can be selected with `NEXT_PUBLIC_API_URL=https://devinbot-backend.onrender.com` at frontend startup, but browser requests from localhost may be blocked by CORS even when server-side HTTP probes succeed. WebSocket connectivity alone does not prove HTTP endpoints work.

For approved frontend-only tests, error and empty states provide useful coverage; explicitly mark metrics cards and populated session badges/timestamps untested if data never loads. Do not fabricate data or bypass CORS without approval.

## Japanese visual testing

Check `fc-list :lang=ja` before recording. Missing Japanese fonts can produce square glyphs unrelated to application behavior. Install a CJK font such as Noto Sans CJK JP in the user-local font directory, run `fc-cache -f`, and restart Chrome if refreshing the page does not refresh font fallback.

Locale preference uses localStorage key `devinbot.locale` with values `en` and `ja`; initial detection uses `navigator.language`. Verify actual pixels, storage, and `<html lang>` separately. Browser language emulation should keep its CDP connection open through reload; detached overrides may reset. Do not substitute a DOM assertion for visible translated text.

## Devin Secrets Needed

None for frontend error/empty-state tests. Full local backend coverage requires valid backend configuration according to `backend/.env.example`.
