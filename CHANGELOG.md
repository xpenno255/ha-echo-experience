# Changes

## 0.4.0 — catalog and music-agent fallback

- Fix the first-attempt Mammoth II failure: duplicate album fields no longer filter album results as if they were tracks.
- Prefer standard studio releases over duplicate editions, while preserving requested albums/versions and distinct artists.
- Match spelling mistakes and phonetic names against the artist's actual MA albums/tracks; use a dedicated tool-free Gemma agent for bounded shortlist selection or name correction verified by another search.
- Reuse the model behind the earlier enhanced View Assist music agent without changing that agent or re-enabling its automation.
- Add catalog caching, model/time limits and regressions for invalid suggestions, explicit artist/version preservation and multi-Echo routing.


## 2026-09-18 — scoped voice stop automation

- Fix an older sentence automation that intercepted “Stop”, targeted 14 unrelated/unassigned media players and delayed its response by 30.5 seconds.
- Generate exact default Music Assistant player routes for each Echo and configured companion voice device. For other devices, require a real area and restrict targets to the native Sonos integration.
- Allow independent simultaneous stop requests across Echos; respond honestly when no speaker is identifiable.
- Keep the automation in the repository and refresh its routes during normal deployment. This configuration-only fix requires no Core restart.


## 0.3.3 — correct song requests misclassified as artists

- The 18 September physical Echo trace heard the song correctly but called `echo_music` with `media_type: artist`, query `Sweet Child of Mine` and artist `Guns N' Roses`.
- Clarify the agent prompt and tool description: media_type describes the title being requested, not the performer filter.
- Recover contradictory artist requests by resolving both songs and albums, proceeding only when there is a unique match. Preserve clarification when both categories match.
- Ignore redundant artist filters on genuine artist requests. Add four regression tests, including the exact failed play arguments and correct Sonos target/media type.


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
