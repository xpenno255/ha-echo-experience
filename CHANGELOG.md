# Changes

## 0.8.3 - keep timers on screen

- While an Echo has a running timer or a ringing alarm, the integration turns on its Kiosk Hold mode (`kiosk_hold`), so the timers view stays at full brightness instead of dimming to the screensaver. The hold is released once no timer runs and no alarm rings; paused timers do not hold the screen. A hold someone else set (a pinned guide) is left alone, and taken back if released while a timer still runs. Ownership is stored in `.storage/echo_experience.screen_hold` so a hold left on across a restart is released. A failure to set this up raises a repair issue and does not affect anything else.
- Tests: 151 Python tests (hold on start, release on cancel and dismissal, ringing alarms, paused and other-room timers, someone else's hold, restart clean-up, unavailable switch, failed switch call).

## 0.8.2 - recover after restarts, Home Assistant 2026.10 tools

- Fix the "Unknown command" error that stayed on the Echo after Home Assistant restarted until a button was pressed. While Home Assistant starts, the Kiosk browser reconnects before Echo Experience has registered its commands. The card now retries with backoff (1 s, doubling, up to 30 s), subscribes again after every reconnect, so live updates come back, and clears the connection error once data arrives. Errors from actions are left alone.
- The Echo tools (`echo_timer`, `echo_weather`, `echo_convert`, `echo_music`, `echo_show`, `echo_guide`) now name their integration and return `llm.ToolResult` (with `error` set on failures) on Home Assistant 2026.10+, which removes the deprecation warnings that would become failures in 2027.10/2027.11. Older cores still get the plain result. HomeGuide answers are passed through either way.
- Tests run against Home Assistant 2026.10.1 (hassil 3.12.1, intents 2026.10.6): 143 Python tests and 148 frontend assertions, including restart recovery and tool tagging.

## 0.8.1 - answer, conversion and timer layouts

- Answers: the question sits muted above a large, left-aligned answer. Short answers get open space; long ones scroll inside a bounded panel above the navigation. A very long question is capped and scrolls on its own, so the answer always keeps room. Plain text only, line breaks kept, everything escaped; the empty state is unchanged.
- Conversions: the original amount and unit are secondary, the converted value and unit primary. Long values or unit names step the type down and wrap instead of overflowing. Same payload and en-GB number formatting.
- Timers: each card spells out its state with an icon and a word (Running, Paused, Finished), not colour alone. One timer gets a large countdown and larger controls (hour-long h:mm:ss countdowns step down to fit); two sit side by side, three or four in a balanced grid, more in a scrolling grid. Cards keep the server's order. Finished alarms are shown first with "Say stop or tap the alert"; there is no card-side dismiss button, so Voice Satellite keeps owning the alert and its dismissal. Pause/Resume, +1 min, Cancel, the name/minutes form and its validation are unchanged; the empty state keeps the form below it.
- Home: the clock is inset by the shell padding (the same edge as the other views and the approved mockup) and sized by both width and the card's height, resting just above the navigation. The weather button and timer strip use the same inset.
- Home timer chips are larger and easier to read across the room: the countdown grows from 19px to about 35px at 1024x640 (up to 38px), the name to about 24px, both scaled by width and the card's height. The strip stops before the weather button, long names end in an ellipsis, paused timers show an outlined "Paused" tag with a dimmed time, and extra rows scroll inside a strip capped above the clock. Tapping a chip still opens Timers. The timer strip on other views is unchanged.
- The card recomputes its height on window resize or rotation without re-rendering, so the navigation no longer stays below a stale height and a focused form keeps its text.
- Production-card fixture: `?view=answer&answer=short|long|long-question|conversion|zero|negative|large|long-unit|empty`, `?view=timers&timers=empty|single|paused|hours|multi|many|ringing|ringing-multi`, `links=1` for a preview list, `freeze=1` for a fixed clock and countdowns. Fixture timer actions change only local sample timers.
- Local Home comparison: `mockups/redesign/home-compare.html` flicks between the installed 0.8.0 card (`mockups/redesign/baseline/echo-experience-0.8.0.js`, a byte-for-byte copy of the file on Home Assistant) and the proposed 0.8.1 card, plain or with timers, at the same size and frozen time. Each runs in its own iframe. Preview only; nothing in it is deployed.
- Tests: frontend assertions for answer escaping and layouts, conversion zero/negative/large values, empty/single/multiple/paused/finished timers, unchanged action payloads, form preservation, ambient no-change, resize handling, and larger Home-only timer chips that still open Timers.

## 0.8.0 - redesigned card and per-Echo music backgrounds

- Integration options (Configure) now pick an Echo and its music background: **Artwork wash** (default), **Colour atmosphere** or **Full-bleed**. Choices are stored in the entry options under `music_styles`, keyed by profile id, so `echo_experience.json` needs no edits. Saving keeps *Manage the Echo Home dashboard*, other Echoes' choices and any other stored options, then reloads through the existing options-update path. Missing or invalid stored values, and Echoes removed from the profiles, fall back to Artwork wash.
- Each runtime profile carries `music_style`, sent to the card in the existing state snapshot (`profile.music_style`); no new websocket command.
- Every style keeps the same foreground: cover left, details and controls right. Only the background changes. Colour atmosphere falls back to the theme palette when the artwork cannot be sampled.
- Radio shows the station artwork the player supplies in `entity_picture` (Sonos provides a branded Absolute Radio picture). There is no separate logo lookup; players without artwork show the usual fallback.
- Card redesign: Home, Music, Weather, HomeGuide and Controls follow the approved mockups with live data. Reload the Kiosk browser after updating so it loads the new versioned card.

## 0.7.0 - music from other apps, artist phrases and shuffle

- Music started outside the Echo (Sonos app, Spotify Connect, AirPlay) now opens the music view with its artwork and title (#6). Profiles gain `native_players`, defaulting to `ducking.players`. When the selected Music Assistant player is idle, the first playing (then paused) native player counts as this Echo's playback; its group coordinator is used when it reports the same state. Music Assistant wins when both play. Other rooms still never open the view, and guide/timer/weather views and the ambient screensaver keep precedence.
- Pause, resume, next, previous, stop and shuffle (card buttons, `echo_music` and the voice stop route) target that same entity, so they reach a Sonos group started from the app instead of an idle queue. Play and volume still use the selected speaker; naming a speaker still overrides.
- `echo_music` gains `action: shuffle` and a `shuffle` flag on play (#1). Every play sets shuffle explicitly before queuing: artists shuffle by default, and songs and albums play in order, so an earlier shuffle never scrambles an album. The flag overrides this ("shuffle the album …"); radio and podcasts are left alone. Results carry the queue's actual `shuffle` attribute; the prompt tells the model to report only that. The tool description maps "play songs by", "play some", "play music by" and "shuffle <artist>" to artist requests.
- Tests: 134 Python and 55 frontend assertions (native detection and precedence, coordinator trust, control targeting, stop route, shuffle defaults/overrides/radio/unsupported speakers).

## 0.6.1 - dismiss native Kiosk timer alerts

- Fix a false "timer stopped" while the alarm kept sounding. Voice Satellite 2026.9.10 with Kiosk Satellite 2026.9.62+ hands finished-timer alerts to the native Android layer and no longer renders a `.vs-timer-alert` element, so the card saw "no alert", the server recorded the alarm as already silenced and the reply claimed success.
- The card now asks Voice Satellite's own browser session (`window.__vsSession.timer`): its `alertActive` flag decides whether anything is ringing and its `dismissAlert()` performs the dismissal (done chime, native alert cleared, blur and stop model reset). The Escape/double-tap DOM gesture remains only as a fallback for builds without the session global.
- When neither a session nor a DOM alert is available the card reports the state as unknown; the server answers "couldn't confirm" instead of "already silenced", and unsolicited silence reports require the session flag. Nothing is ever cleared on the absence of evidence.
- Tests: 124 Python and 47 frontend assertions (native session dismiss, still-ringing session, quiet session, unknown state, no silence report without evidence).

## 0.6.0 - single HACS-installable integration

- Everything the SMB deployment did now happens inside the integration: the card is served from `/echo_experience/echo-experience.js?v=<version>` and its Lovelace resource is created or updated (the old `/local` resource is removed; YAML-mode resources get a repair issue); the `echo-home` dashboard is filled from the profiles; the fast voice stop route is registered in code. `deploy.py`, `stop_automation.py`, `dashboard.json` and the `smbprotocol` requirement are gone; `tooling.py` keeps the audit path for the verification scripts.
- Dashboard safety: the integration never creates a dashboard (Home Assistant keeps that collection private to its UI; a repair issue explains how to add an empty `echo-home`). It writes only when the current config equals the last generated one, or the exact 0.5.1 generator output, so a 0.5.1 dashboard is adopted and any hand edit is preserved with a repair issue. Every overwrite is preceded by a backup (`.storage/echo_experience.dashboard_backups`, last five). Option *Manage the Echo Home dashboard* turns management off.
- Voice stop route (`stop_route.py`, closes the code side of #3): same phrase list as the automation; owned devices (Echo or ducking companion) dismiss a ringing alarm first on bare “stop” and otherwise stop the Echo's selected speaker; unknown devices keep the real-area, native-Sonos-only rule and honest reply. Explicit music phrases never touch timers. A device claimed by two profiles blocks registration with a repair issue. The route is registered only while automation `1757961047860` is absent or disabled, re-checks that on every request, and a repair issue guides the handover. Behaviour change: music stop targets the selected speaker rather than always the configured default.
- Generic timer phrases stay out of the sentence route; `echo_timer` handles “stop the timer” with the Echo's context.
- `echo_experience.reload` (admin only) re-reads `echo_experience.json` and rebuilds the dashboard and route; options changes reload automatically. A failure setting up the card, dashboard or route raises a repair issue instead of only logging. Ringing-timer guidance moved into the LLM API prompt so agents get it without a subentry edit.
- HACS metadata (`hacs.json`, manifest documentation/issue tracker, brand icons) and `translations/en.json` for the config flow, options and all repair issues. HACS needs the repository to be public; manual archive install is the alternative.
- Migration and rollback steps are in the README. Live post-transcription stop latency must be re-measured before #3 is closed.
- Tests: 123 Python (28 new for the route, dashboard, resource handling and setup wiring, plus a hassil-driven phrase test that CI runs via the pinned matcher requirements) and 38 frontend assertions.

## 0.5.1 - bind timer dismissal to the Echo's own browser

- Only the browser hosting the profile's Voice Satellite session acts on a dismissal request or reports a silenced alarm. The card requires Voice Satellite's global `#voice-satellite-ui` element in its document and that browser's satellite (`window.__vsExternalSettings.get().satellite`, else localStorage `vs-satellite-entity`, else `satellite_entity` in `vs-panel-config`, the same precedence Voice Satellite uses) to equal the profile's satellite. A phone or laptop showing the same dashboard now stays silent instead of reporting a non-existent alert as gone.
- Acknowledgments are bound to a profile and to the timer ids in the request. A report for another Echo's request or an unknown token is ignored and changes nothing; a confirmed dismissal or device-side silence clears only the listed alarms, so a timer that finishes after the request keeps ringing. The card sends `timers` with every report.
- `dismissed` is no longer an `echo_timer` operation: the card's reports go through `Experience.display_report`, and tool arguments are validated against the tool schema before execution, so the model cannot clear ringing state or pass malformed values.
- `echo_experience.dismiss_timer` checks that a calling user may control the target Echo's satellite and raises `Unauthorized` otherwise; automation and system contexts (no user) are allowed.
- Companion satellites listed in a profile's `ducking.additional_satellites` resolve to their Echo through the entity registry, so a Home Assistant Voice device's device id reaches the right ringing list.
- The stop automation drops its generic timer phrases ("stop the timer", "stop the alarm", "dismiss the timer", ...) and the service's `cancel_running` option: a sentence route cannot tell silencing an alarm from cancelling a countdown, and the LLM's `echo_timer` tool already handles both with the profile's context. Bare "stop" still silences a ringing alarm first, then stops music. Regenerate with `python stop_automation.py` or `deploy.py`.
- Gesture replay withholds the second tap when the first already cleared the alert. Voice Satellite mini-card layouts render their alert inside a shadow root and are not supported.
- Tests: 95 Python tests and 38 frontend assertions.

## 0.5.0 - dismiss a ringing timer by voice

- Fix "stop timer" failing while a finished timer is sounding (#5). Home Assistant removes a timer from its manager before Voice Satellite fires the finished event, so the cancel path found nothing. The integration now records finished timers per Echo as ringing until the alarm is dismissed.
- Dismiss through Voice Satellite's own mechanism. It exposes no service or WebSocket command for a ringing alert, so the Echo's dashboard card replays its native Escape/double-tap dismissal in the device's browser and reports back. Voice replies only claim success after that confirmation; otherwise they say the alarm could not be confirmed stopped.
- `echo_timer` gains a `dismiss` operation, `cancel` silences a ringing alarm first, `status` lists ringing alarms, and a new `echo_experience.dismiss_timer` service (device-scoped, optional name and `cancel_running`) serves the fast sentence route.
- The voice stop automation now runs bare "stop", "stop the timer", "stop the alarm", "dismiss the timer" and related phrases through that service on the originating Echo before any music stop. Explicit "stop music/Sonos" phrases never touch timers. "Stop the timer" with nothing ringing cancels the single running timer or asks which one. Run `python stop_automation.py` (or a normal `deploy.py`) to install the updated route.
- Timers view shows finished alarms as "Finished" cards and opens on completion unless a guide is pinned. Alarms silenced on the device by tap or stop word clear the server's ringing state.
- Add expiry-to-dismissal regressions: 10 Python tests (ringing tracking, display round-trip, unconfirmed and already-silenced outcomes, per-Echo scoping, service fallback, expiry) and 10 frontend assertions for the gesture replay and honest reporting. Physical Echo voice test still to be recorded after deployment.

## 0.4.1 - favourite-artist regression suite

- Add 386 artist, album and track matching cases across the user's 20 favourite artists, with independently sourced canonical metadata and synthetic release variants.
- Reject unrelated advisor-selected titles and name corrections even when the advisor reports high confidence. Require independent spelling/phonetic evidence and retain performer constraints.
- Recover short phonetic artist names such as Reeve/Reef when the catalog has a unique close match; support evidence from spoken letters and numeric title components.
- Rank spoken numeric titles before selecting a shortlist, fixing the live-library miss for Stone Sour's 30/30-150; test against more than 12 competing tracks.
- Record a fresh 386/386 real-advisor benchmark and replay those actual responses in offline CI. Preserve the 379/386 baseline and document the distinction from live-library and microphone testing.

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
