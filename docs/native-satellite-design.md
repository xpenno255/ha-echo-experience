# Native Kiosk Satellite runtime: design

Status: revision 2, implemented on branch `native-satellite` as 0.8.0 (a minor version because it adds a feature),
offline-tested, awaiting the live test (2026-10-17). Section 10 lists what changed from the Phase 1 draft. The same build must keep the current browser runtime working without changes.

**Goal.** Echo Experience currently depends on the Voice Satellite browser integration (`voice_satellite`). It should
also work when the Echo Show 8 runs Kiosk Satellite's native Voice Satellite, which is a plain ESPHome Assist
satellite. The runtime is chosen per profile, and it is auto-detected by default, so the rollout can be reversed without
reinstalling.

**Sources.** These were read at the following versions:

| Source | Version |
| --- | --- |
| Kiosk Satellite (`~/src-ref/kiosk-satellite`) | `28113b6`, 2026-10-17. The Echo runs app 2026.10.27. |
| voice-satellite-card-integration (`~/src-ref/voice-satellite-card-integration`) | `78f0f4b`, v2026.9.13. This is the installed version. |
| HA core | 2026.10.1 wheel |
| HACS | 2.0.5 tag. This is the installed version. |
| `xpenno255/extended_openai_conversation` (the Echo Home agent) | `homelab` branch `4bde405` |

**Live data.** These are read-only observations from HA and the Kiosk admin API, taken on 2026-10-17 while the Echo
was on the dashboard runtime.

**Abbreviations.** In citations below:
- KS = kiosk-satellite/app
- VM = `KS/lib/managers/voice/voice_manager.dart`
- VSI = voice-satellite-card-integration/custom_components/voice_satellite

## 1. Two identities, one Echo

| | Dashboard runtime (today) | Native runtime |
| --- | --- | --- |
| Satellite entity | `assist_satellite.echo_show_8`, platform `voice_satellite` | `assist_satellite.amzn_echo_show_8_assist_satellite`, platform `esphome` |
| Device | `3cbf784cee34a3c4249e1cd03060b6dc`, "Voice Satellite Integration / Browser Satellite" | `f778d5de1d79969a9248a6d584b08e7f`, the Kiosk ESPHome device, config entry `01M2KD1HY0ZR19EPPN026M24B0` |
| Available when | A browser holds `voice_satellite/subscribe_events` (VSI `assist_satellite.py:194-204`) | Kiosk settings `voice.enabled` and `voice.runtime == native` are both on (`KS/lib/managers/btproxy/bt_proxy_manager.dart:233-236`) |
| State today | `idle` | `unavailable` (restored), `supported_features: 3` |

Native mode is "a standard Assist satellite, like a Voice PE" (`kiosk-satellite/docs/voice-satellite.md:17`). It
advertises the ESPHome voice feature flags VOICE_ASSISTANT, API_AUDIO, TIMERS, ANNOUNCE and START_CONVERSATION
(`KS/android/.../btproxy/VoiceCodec.kt:16-30`). It does not advertise SPEAKER, and it has no ESPHome media_player.

Pipeline debug confirms how the native attempt failed. Run `01M54RENFEXVAYTQRJQ67ESAE3` (11:02Z) had
`satellite_id = assist_satellite.amzn_echo_show_8_assist_satellite` and `device_id = f778d5de…`. The model called
`echo-experience__echo_weather`, and the agent answered "function … does not exist". The browser run
`01M54S9WNDRQPRN96VK3GHD3YW` asked the same question with `device_id 3cbf784c…` and succeeded.

The Kiosk ESPHome device already owns this profile's `kiosk_*` entities, for example
`select.amzn_echo_show_8_dashboard_view`. So the native identity can be derived from the existing
`/config/echo_experience.json` without editing it (see section 3).

## 2. Coupling points and their native replacements

| # | Where (this repo) | Browser coupling | Native replacement (evidence) |
| --- | --- | --- | --- |
| C1 | `__init__.py:458` `ExperienceAPI.async_get_api_instance`, `core.py:43` `route_profile` | Tools are offered only when `context.device_id == profile.device_id` (the browser device) | Match on **any** identity of the profile. `llm_context.device_id` is the ESPHome device for native turns (pipeline run above). |
| C2 | `__init__.py:393` `echo_timer` start | Calls `voice_satellite.start_timer` on `p['satellite']`. The service only finds `voice_satellite` entities (VSI `__init__.py:43-48`). | Call core `TimerManager.start_timer(device_id=<native device>, …)` directly. This is exactly what the VSI service does internally (VSI `__init__.py:267-324`). The ESPHome satellite registers a timer handler when TIMERS is advertised (HA `esphome/assist_satellite.py:292-299`). The Kiosk's own `vs_start_timer` would also work, but it uses the Kiosk's HA token and the intent REST API (VM:2956-2991), so it is not used. |
| C3 | `__init__.py:69` + `timer_event` (`:167`) | `voice_satellite_timer` bus event: fields `entity_id`, `device_id`, `event_type`, `timer_id`, `name`, `total_seconds`, `seconds_left`, `is_active` (VSI `assist_satellite.py:1731-1759`) | `esphome.kiosk_satellite_timer`, documented as carrying the same fields, plus HA's `device_id` (`kiosk-satellite/docs/voice-satellite.md:53,304-332`; VM:3075-3097). It also adds `event_type: dismissed` when the alert is silenced by a tap, the stop word or `vs_cancel` (VM:3392-3410). HA fires ESPHome device events without the "allow actions" option and adds `device_id` (HA `esphome/manager.py:314-336`). Native events have no `entity_id`, so route them by `device_id`. |
| C4 | `__init__.py:68` + `chat` (`:223`) | `voice_satellite_chat` (stt/tts text and tool names). The card's `fire_chat_event` websocket command produces it (VSI `__init__.py:625-679`, card `src/pipeline/events.js:387-426`). | **Nothing in native mode fires it.** There is no match in KS `lib/`, `android/` or `remote-ui/`, and `esphome.kiosk_satellite_voice` carries only state and reason, with no text (`kiosk-satellite/docs/events.md:20-41`). Replacement: HA core's chat-log subscription. See section 4. |
| C5 | `__init__.py:176-195` `dismiss`, card `dismissNativeAlert`/`hostsSatellite` (`www/echo-experience.js:8-48,112-134`) | The card asks the page's Voice Satellite session (`window.__vsSession.timer.dismissAlert()`) | In native mode the page engine is suppressed (`window.__vsEngine = true`, `KS/lib/managers/browser/vs_suppress_script.dart:26`), so `hostsSatellite()` is false and the card stays silent. Replace this with a server-side path. First call `esphome.<node>_vs_list_timers` (response: `timers[].finished` is true while ringing, `docs/voice-satellite.md:240-262`). If something rings, call `esphome.<node>_vs_cancel` and wait for the `dismissed` timer events. When something rings, `vs_cancel` dismisses the alert and returns without touching the current turn (VM:2652-2656). Node `ks-amzn-echo-show-8` maps to the services `esphome.ks_amzn_echo_show_8_vs_*` (HA `esphome/manager.py:1525-1527`, Kiosk setting `esphome.node_name`). |
| C6 | `ducking.py:257` | Watches `p['satellite']` plus `additional_satellites` | Add the native satellite. ESPHome satellite states are `listening`, `processing`, `responding` and `idle`, which are already in `ACTIVE_STATES`. The Kiosk's own ducking affects only its local Sendspin engine because `sendspin.player` is empty, so the Sonos speakers are not ducked twice. |
| C7 | `stop_route.py:136-144` `build_owners` | Owners are `p['device_id']` plus the companions | Add the native device id. `origin_device` already resolves `satellite_id` through the entity registry. |
| C8 | `__init__.py:131-136` `timers(p)`, `:394` creation check, `:406,416,420` ownership | `t.device_id == p['device_id']` | Accept any identity's device id. A timer belongs to the device that started it, and it stays there if the runtime is switched while it runs. |
| C9 | `__init__.py:84` `dismiss_timer_service`, `:478` websocket `access()` | Permission is checked on `p['satellite']` | Check the identity that matches the request. `access()` allows the request if the user may read or control any of the profile's satellites. The browser entity remains after an uninstall of `voice_satellite`. |
| C10 | `__init__.py:224` `chat`, `:168` `timer_event` | Route by `entity_id == p['satellite']` | Route by any identity's satellite (browser event) or device id (native events). |
| C11 | Card `www/echo-experience.js:58` | Re-renders on `p.satellite` state changes | Also watch the native satellite. This is cosmetic. |
| C12 | `publish()` `__init__.py:154-163`: `kiosk_now_playing`, `kiosk_screensaver`, `kiosk_navigation`, `kiosk_hold` | These are ESPHome Kiosk entities, not `voice_satellite` | **No change.** The dashboard WebView stays up in native mode, and the overlay is drawn over it natively (`kiosk-satellite/docs/voice-satellite.md:15-16`). Echo Experience's card keeps running and subscribing over the page's HA connection. |
| C13 | `profiles.json`, README, `DUCKING.md`, `VOICE_STOP.md`, `verify_routing.py:21` (uses `voice_satellite/fire_chat_event`) | Docs and tooling | Update the docs. `verify_routing.py` stays dashboard-only, and that is noted. |

Coupling points I checked that turned out not to be couplings:
- `select.amzn_echo_show_8_dashboard_view` and the other `kiosk_*` entities.
- `capture.py` (an ESPHome screenshot entity).
- The HomeGuide wrapper.
- Music.
- Conversions.
- `binary_sensor/button …_alarm_*`. These belong to the Kiosk **Alarms** feature, not to Assist timers.

## 3. Profile schema and runtime selection

The profile is extended without needing the JSON file edited. The fields below are all optional, and today's file
validates unchanged.

```jsonc
{
  "id": "echo_show_8",
  "satellite": "assist_satellite.echo_show_8",   // dashboard identity (unchanged)
  "device_id": "3cbf784cee34a3c4249e1cd03060b6dc",
  "native": {                                     // optional; derived when absent
    "satellite": "assist_satellite.amzn_echo_show_8_assist_satellite",
    "device_id": "f778d5de1d79969a9248a6d584b08e7f",
    "node": "ks_amzn_echo_show_8"                 // ESPHome service prefix
  },
  "runtime": "auto"                               // auto | dashboard | native; default auto
}
```

**Derivation when `native` is absent**, done at setup and on reload:
1. Find the device that owns `kiosk_navigation`, falling back to `kiosk_screensaver`, `kiosk_now_playing` and then
   `kiosk_hold`. The device must belong to an `esphome` config entry.
2. Take that device's single non-disabled `assist_satellite` entity on platform `esphome`.
3. Read `node` from the ESPHome entry's `device_info.name` with `-` replaced by `_`. This is the same rule HA uses
   to build the service names.

If any step is ambiguous, the native identity is left out and a repair issue `native_identity` explains why. The
dashboard runtime then keeps working as it does today.

Validation: every satellite and device id, across all identities of all profiles, must be unique.

**Runtime selection.** Most paths do not need to choose a runtime, because they key off the identity a request or
event came from:

| Path | Source of the identity |
| --- | --- |
| LLM tools | `llm_context.device_id` |
| Stop route | `satellite_id` |
| Timer events | The event's own source |
| Chat display | The conversation's origin device (section 4) |
| Dismissal | The device that owns the ringing timer |

Only actions with no origin need the *active* identity. Those are a timer started from the card, and
`echo_experience.dismiss_timer` called with a device id that has no ringing timer. For them:
- `runtime: dashboard` or `native` forces that identity.
- `runtime: auto` picks native when the native satellite is available and `TimerManager.is_timer_device(native device)`
  is true. Otherwise it picks dashboard.

**Override without `/config` access.** The options flow gains one select per profile, `runtime_<id>`, with the
values auto, dashboard and native. It is persisted in `core.config_entries` (`.storage`). Saving the options reloads
the entry, as options changes already do (`__init__.py:88`). An entry `runtime` value overrides the JSON value.

**Switching the live profile, using HA API calls only:**
- **To native.** No HA call is needed with `auto`. To pin it, use the REST options flow:
  `POST /api/config/config_entries/options/flow {"handler": "<echo_experience entry id>"}`, then
  `POST /api/config/config_entries/options/flow/<flow_id> {"manage_dashboard": true, "runtime_echo_show_8": "native"}`.
- **Back.** Send the same two calls with `"dashboard"`, or with `"auto"`.
- **Note:** a reload forgets ringing alarms and the current screen result, as `echo_experience.reload` already does.
  Do not switch while a timer runs or rings.

**Switching the Echo** is not an HA call. It is a Kiosk remote-admin call: `POST /api/commands/vsMigrate` (the app's
own wizard path) or `PATCH /api/settings` with `voice.enabled=true, voice.runtime=native`. `vsRollback` sets
`voice.enabled=false, voice.runtime=dashboard` (VM:1484-1520, 1627-1755). There is no HA entity for `voice.runtime`.
The ESPHome "Voice Satellite" switch only starts and stops the dashboard engine (`docs/esphome.md:53`).

## 4. Showing the answer in native mode (C4)

**Mechanism.** HA core exposes `homeassistant.components.conversation.chat_log.async_subscribe_chat_logs(hass, cb)`.
The callback receives `(conversation_id, ChatLogEventType, data)`, and `CONTENT_ADDED` carries `content.as_dict()`
for user, assistant and tool-result content (HA `conversation/chat_log.py:38-56,395-505`). This is the same source the
Kiosk overlay reads its tool lines and panels from (VM:2700-2732, `KS/lib/managers/voice/chat_log.dart:91-129`).

**Correlating a conversation with an Echo.** Chat-log events carry no device. However,
`ExperienceAPI.async_get_api_instance(llm_context)` runs inside the agent's `async_get_chat_log` block. That is true
for the Echo Home fork (`conversation.py:131-156`, where `llm.async_get_api` is called inside the `with`) and for
standard agents (`ChatLog.async_provide_llm_data`). At that point:
1. `chat_log.current_chat_log.get().conversation_id` is set.
2. `llm_context.device_id` is the origin device.
3. The integration records `conversation_id -> (profile, identity)` and drops entries older than one hour.

**Turning chat-log content into a display event.** Only conversations whose origin identity is **native** are used.
Dashboard-origin conversations keep using `voice_satellite_chat`, so nothing is published twice. For those native
conversations:
- The last `user` content becomes `stt_text`.
- `assistant` contents with `tool_calls` contribute tool names.
- The first `assistant` content with text and no `tool_calls` after the latest user content becomes `tts_text`.
- These are passed to the existing `chat()` logic unchanged. That logic merges the answer into a recent tool result,
  or publishes `answer`, and never shows timer replies.

**Fallback.** The conversation is not mapped when the agent never asks for LLM APIs (for example a turn handled by
local intents). Nothing is shown in that case, which matches today's "no fallback" rule. `extended_openai_conversation`
also fires `extended_openai_conversation.conversation.finished` with `user_input.device_id` (fork `conversation.py:218-226`).
That event is agent-specific, so it is not used.

**Behaviour in native mode.** The Kiosk overlay shows the spoken answer while the turn runs. The dashboard is paused
under it and shows the answer view once the overlay closes (`voice.answer_linger 0`). Kiosk result panels do not
match the `echo_*` tools: weather panels require a tool name ending in `get_weather_forecast`
(`KS/lib/managers/voice/chat_log.dart:26-74`). So nothing is drawn twice.

## 5. Timers in native mode

| Step | Behaviour |
| --- | --- |
| Start (tool or card) | `TimerManager.start_timer(device_id, h, m, s, language=hass.config.language, name=…)`, after `is_timer_device(device_id)` is checked. Otherwise the error is "the Echo's voice satellite is not connected". The creation check is unchanged. Dashboard-identity starts keep calling `voice_satellite.start_timer`, so there is zero change there. |
| Events | A listener on `esphome.kiosk_satellite_timer` filters by native device id and feeds `timer_event()`. `finished` records ringing, tagged with the identity. `dismissed` calls `forget()` for that id and publishes, which is the equivalent of the card's silence report. |
| Pause, resume, cancel, +1 min | Core `TimerManager`, unchanged. ESPHome forwards the updates to the Kiosk. |
| Dismiss (tool, stop route, service) | For a native-tagged ringing timer: `vs_list_timers`. If none is `finished`, the result is `not_ringing` and the entry is forgotten. Otherwise `vs_cancel`, then wait up to 4 s for `dismissed` events covering the requested ids. The result is `dismissed`, or `unconfirmed` on timeout. A missing service (native not running) gives `unconfirmed`. The dashboard path is unchanged. |
| Kiosk display | Kiosk draws its own finished-timer alert pill (`voice.timer_alert_pill true`). Running-timer pills are off (`voice.timer_pills false`), which matches today's "Hide on-screen countdown". The dashboard still shows countdowns and the Finished cards. |

## 6. Gaps that native mode cannot cover

1. **Dismissal by name.** The Kiosk silences **all** ringing timers at once (`_dismissAlert`, VM:3392-3410).
   "Stop the pasta timer" while two timers ring silences both. The result reports every id that was actually dismissed.
2. **No HA-side alert state other than polling the action.** `vs_list_timers` is used for that. The ESPHome entities
   `VS Timers` and `VS Next timer` exist only with "Expose kiosk entities" on. That setting is on here, but the
   entities only exist while native mode runs.
3. **The bare "stop" word.** In the dashboard runtime, `voice.stop_word` is off and "stop" reaches the stop route
   through the pipeline. Native mode behaves the same. If the Kiosk's own stop word is enabled, it silences an alert
   or cuts an answer locally without a pipeline, and the `dismissed` event keeps HA's state honest. It never stops
   music.
4. **Answer display depends on the conversation mapping** (section 4). Non-LLM turns show nothing on the dashboard.
   The Kiosk overlay still shows them.
5. **Kiosk overlay tool lines and result panels** need an admin `ha.token` on the Kiosk (VM:1566-1580,
   `docs/voice-satellite.md:40`). Echo Experience does not need them, and `voice.show_tools` is off. No action is
   required.
6. **Private HA APIs.** The design adds `conversation.chat_log` (module-level, not exported) to the private APIs
   already relied on (`TimerManager`, `register_trigger`, Lovelace storage). Each feature is isolated and raises a
   repair issue on failure.
7. **Timers started under one runtime stay with that device.** If the runtime is switched while a timer runs, the
   old device rings, or nothing rings if its satellite is gone. Switch only when idle.

## 7. Deployment through HACS (no `/config` access)

HACS 2.0.5 accepts a branch name as `version`:
1. `hacs/repository/download` passes it as `ref` (`hacs/websocket/repository.py:216-243`).
2. `_ensure_download_capabilities` fetches `hacs.json` at that ref.
3. `async_install_repository` sets `ref = "tags/<branch>"` because it is not the default branch
   (`repositories/base.py` at 2.0.5:934).
4. `download_repository_zip` strips `tags/`, tries `archive/refs/tags/<ref>.zip`, and falls back to
   `archive/refs/heads/<ref>.zip` (2.0.5:657-676, `utils/url.py`).

Pushing the feature branch runs only the `checks` job. `release` is gated on `refs/heads/main`
(`.github/workflows/checks.yml`). So no tag or release is published.

| Step | Calls |
| --- | --- |
| Install | WS `{"type":"hacs/repository/download","repository":"1374903411","version":"native-satellite"}`, then `homeassistant.restart` (idle, no timers), then press `button.amzn_echo_show_8_reload_page` so the Kiosk loads the new `?v=` card |
| Rollback | WS `hacs/repository/download` with `"version":"v0.7.0"`, then restart, then reload the page. 0.7.0 ignores the new options keys. |

The branch build carries manifest version `0.8.0`. HACS will then show `native-satellite` as installed. Its update
entity may offer `v0.7.0`, which must not be accepted.

## 8. Test plan

### Offline (`tests/`, CI)

- **`core`:**
  - Explicit and derived native identity.
  - Uniqueness across identities.
  - `route_profile` matches either identity.
  - Ambiguous derivation leaves the native identity out and raises a repair issue.
- **`ExperienceAPI`:**
  - Tools are offered for native and dashboard device ids, and not for others.
  - Conversation mapping is recorded only inside a chat-log context.
- **Timers:**
  - Native start goes through `TimerManager.start_timer`, and dashboard start still goes through
    `voice_satellite.start_timer`.
  - `is_timer_device` false gives an error.
  - Auto, dashboard and native selection for card starts.
  - `timers()` spans both devices.
- **`esphome.kiosk_satellite_timer`:**
  - `started`, `finished` and `dismissed` are handled, and events from other devices are ignored.
  - Ringing is tagged with its identity.
- **Native dismiss:**
  - `finished` in `vs_list_timers` leads to `vs_cancel`, then the `dismissed` events, then `dismissed`.
  - Nothing finished gives `not_ringing`.
  - A timeout gives `unconfirmed`.
  - A missing service gives `unconfirmed`.
  - Partial dismissal events.
  - `vs_cancel` is never called when nothing rings.
- **Chat log:**
  - Native conversation leads to `answer` or a merge into a recent tool result.
  - Dashboard-origin conversations are ignored.
  - Timer tools are suppressed.
  - Unmapped conversations are ignored.
  - Mappings expire.
- **Other components:**
  - `stop_route` owners include the native device, and bare "stop" from the native satellite dismisses natively.
  - `ducking` watches the native satellite.
  - Options flow: the runtime select is saved and overrides the JSON value.
- **Card (`test_card.cjs`):** the native satellite is in the watched list. The card ignores `dismiss` requests when
  it does not host Voice Satellite (an existing test, kept).
- **Regression:** the full existing suite passes unchanged, with 134 tests passing on the branch base.

### Live, Phase 3, after approval only

The checks are scripted in `scripts/live_native_check.py`, to be written in Phase 2. It reads the token from
`~/.config/ha/agent-token`, never prints it, and prompts before every step that changes anything.

| ID | Step | Pass criterion |
| --- | --- | --- |
| L0 | Pre-checks (read-only) | No timers on either device. Both satellites' states are recorded. Echo Experience is v0.7.0. |
| L1 | Install the branch through HACS, restart, reload the page | Repairs are clean. `echo_experience` loads. The derived native identity is logged. |
| L2 | Dashboard regression | Text `assist_pipeline/run` with `device_id 3cbf…` asking for the weather produces the `echo_weather` call and the weather view. By voice: "what's the weather", then a 10 s named timer, the dashboard ring, "stop", and the reply "Timer stopped." |
| L3 | Native gating while still in dashboard runtime | Text run with `device_id f778…` asking for the weather produces the `echo_weather` tool, with no "does not exist" error. This step wakes the Echo screen. |
| L4 | Switch the Echo to native (Kiosk API) | `assist_satellite.amzn_echo_show_8_assist_satellite` becomes available, and the timer device is registered. |
| L5 | Native by voice: weather, conversion, music search (no play), "what time is it" | The tools run. The dashboard shows the result views and then the answer text. |
| L6 | Native timer: "set a 10 second test timer" | The timer appears in the dashboard countdown. On `finished` the Kiosk alert pill and the dashboard Finished card show. "Okay Nabu, stop" leads to `vs_cancel`, the `dismissed` event, and "Timer stopped.". Repeat with a tap on the pill: the dashboard clears via `dismissed`. |
| L7 | Ducking | Play music quietly, then ask a question. The Sonos speakers duck and restore (DUCKING.md procedure). |
| L8 | Switch back to dashboard (`vsRollback`) | L2 passes again with no HA change. |
| L9 | Full rollback rehearsal (optional) | HACS `v0.7.0`, restart. The Echo works on the dashboard runtime. |

## 9. Open questions

1. Is `runtime: auto` acceptable as the default, with the options-flow override as the safety valve? Or should the
   live profile be pinned explicitly?
2. Is it acceptable that a native dismissal silences every ringing timer (gap 1)?
3. Should the Kiosk's local stop word (`voice.stop_word`) be enabled in native mode? This is a Kiosk setting change.
   It also cuts answers.
4. Should the dashboard keep publishing the `answer` view in native mode, even though the Kiosk overlay already shows
   the answer while speaking? Proposed: yes, for parity.
5. For the Echo switch, should the coordinator use `vsMigrate`/`vsRollback` or a raw `PATCH voice.runtime`?
   `vsMigrate` may also rewrite the ESPHome device's Assistant and wake-word selects, which already hold the right
   values.

## 10. Changes from the Phase 1 draft (implementation, 2026-10-17)

- **Answers (section 4): no chat-log subscription.** `async_subscribe_chat_logs` does not see the final answer:
  assistant content added through `async_add_assistant_content` / `async_add_delta_content_stream` (how the Echo Home
  fork streams) fires no `CONTENT_ADDED` (HA `conversation/chat_log.py:437-470`, only tool results at :497 and
  `async_add_assistant_content_without_tools` at :430 notify), and a new conversation gets no `UPDATED` at the end
  (:160-172). Instead `ExperienceAPI.async_get_api_instance` takes the live `ChatLog` from
  `conversation.chat_log.current_chat_log` (present in 2026.9.2 and 2026.10.1) and a `native.TurnWatcher` task follows
  that object until the first assistant message with text and no tool calls after the turn's user message (polled
  every 0.25 s, at most 120 s, cancelled on unload or when the conversation's next turn starts). It works for voice and
  for text runs with `device_id`, for any agent that builds its LLM API inside its chat log, and needs no `hass.data` key.
- **Pin semantics (decision 1).** An options pin (`runtime_<profile>` dashboard/native) overrides the profile file,
  auto-detection *and* the "timer on the asking satellite" rule. Observations are never filtered by the pin: browser
  events, Kiosk events and chat-log answers are attributed by their own origin, and a ringing alarm is silenced where it
  rings (each ringing entry carries its `runtime`; a mixed list is handled per runtime).
- **Derivation** logs (info) instead of raising a repair issue: a dashboard-only Echo without native mode is normal.
  The ESPHome node name is resolved lazily at first use (`entry.runtime_data.device_info.name`, else
  `entry.data['device_name']`) because the ESPHome entry may not be connected when Echo Experience loads.
- **Native dismiss** never sends `vs_cancel` unless `vs_list_timers` shows one of the requested timers as `finished`;
  on a missing `dismissed` event it re-reads the list before deciding. `also_silenced` names the others the Kiosk
  silenced (decision 2). The Kiosk stop word is not used (decision 3). Answers keep the dashboard answer view
  (decision 4); the overlay/dashboard combination is a live-test item. The Echo switch uses `vsMigrate` with
  `groups: []` (no settings or selects rewritten) and `vsRollback` (decision 5; VM:1627-1755).
- **Fail-soft guards:** registry access (derivation), `TimerManager.start_timer` signature and `is_timer_device`,
  `hass.services.has_service('esphome', …)` before each Kiosk action, the chat-log context variable; each logs once.
- **Live checks:** `scripts/live_native_check.py` (phases A/B, pre-flight, mid-interaction abort, text runs with
  `device_id`, read-only music status, a 2-minute "echo test" timer cancelled immediately, `--runbook`).
