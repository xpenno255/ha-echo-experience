# Changes

## 0.3.2 — music title resolution

- Resolve tracks, artists and albums before queuing the exact Music Assistant URI.
- Tolerate punctuation, accents, known spoken aliases (Guns and Roses, Sweet Child of Mine) and trailing album numbers in digits, words or Roman numerals.
- Match requested artist, album and version; ask for clarification when multiple matching items remain. Never fall back to an unchecked first result.
- Add read-only music search for diagnostics and voice queries. Radio, playlist and podcast playback keep their existing Music Assistant path.
- Validate 45 Python tests and 11 frontend assertions, plus live library resolution of five previously problematic phrases.


## 0.3.1 — 2026-09-17

- Remove the manual converter and redundant close button from the answer view; enlarge question, answer and conversion text for the 8-inch screen.
- Fix voice distance conversions using singular unit names such as `mile`, `metre` and `kilometre`; accept both US and UK spellings and normalise whitespace/underscores.
- Explain unsupported units clearly instead of reporting an unrelated cup/pint hint alone.
- Review Tools for Assist 1.9.0–1.10.2 and refresh stale HACS metadata so its available update appears.

## 0.3.0 — 2026-09-17

- Sonos music output for Kitchen Echo; local Echo audio retained for speech and alarms.
- Shared-speaker voice ducking in the integration with per-speaker restoration, idle grace, timeout, manual-volume preservation and restart recovery.
- Quiet gradient home and dim ambient view, larger weather/date text aligned above the first clock digit, forecast shortcut and focused artwork view.
- Device-scoped timers, weather, conversions and HomeGuide views.
- Initial private source repository, reproducible test workflow and credential-free deployment templates.
