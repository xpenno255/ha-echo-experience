# ha-echo-experience

Private source: https://github.com/xpenno255/ha-echo-experience

A shared Home Assistant dashboard and Assist tool integration for LineageOS Echos running Kiosk Satellite + Voice Satellite. Each device has its own satellite, music output, timer ownership and display results. The current installed profile is **Kitchen Echo** (`echo_show_8`).

Dashboard: <https://homeassistant.xpennohome.uk/echo-home/echo_show_8>

## Source and setup

The private repository contains the integration, installed dashboard definition and frontend, device profiles, agent settings, design history, tests and retired automation reference. Credentials, screenshots, audit logs and backups stay outside Git.

Versioned GitHub releases start at **v0.4.1**. After checks pass on main, a new manifest version is tagged and released automatically using its changelog notes. See [RELEASING.md](RELEASING.md) for the release and deployment process. Feature requests and bugs are tracked in the repository's GitHub Issues.

### Install (0.6.0 and later)

Since 0.6.0 the integration is self-contained: it serves its own card, registers the Lovelace resource, fills the Echo Home dashboard and owns the fast voice stop route. There is no deployment script.

1. Add this repository to HACS as a custom repository of type **Integration** and install it. HACS does not support private repositories, so the repository must be public, or install manually by copying `custom_components/echo_experience` from a release archive into `/config/custom_components/`.
2. Restart Core (not during an active timer).
3. Create `/config/echo_experience.json` from `profiles.json` (see “Add another Echo”).
4. Create an empty storage dashboard at **Settings → Dashboards → Add dashboard → New dashboard from scratch**, title “Echo Home”, URL `echo-home`, shown in the sidebar. Home Assistant only lets its own UI create dashboards; the integration fills it.
5. Add **Echo Experience** in Settings → Devices & services. Setup adds the card resource `/echo_experience/echo-experience.js?v=<version>`, fills the dashboard and registers the voice stop phrases.
6. Repairs lists anything that needs a hand: a legacy stop automation still enabled, a dashboard that looks hand-edited, YAML-mode resources. Each message says what to do.

Profile changes: edit `echo_experience.json`, then call `echo_experience.reload` (admin only) or reload the integration. Reload resets selected speakers to their defaults and forgets ringing alarms. Integration updates through HACS need a Core restart, and a Core restart never swaps a custom element a browser has already loaded: reload the Kiosk browser (Kiosk Satellite remote admin → reload page, or power-cycle the Echo) after every update so it fetches the new versioned card.

### Upgrading from 0.5.1 (SMB deployment)

1. Install 0.6.0 through HACS or by copying the release's `custom_components/echo_experience` over the existing folder, and restart Core while idle.
2. Setup replaces the `/local/echo-experience/echo-experience.js` resource with the integration-served one, adopts the existing `echo-home` dashboard (it matches the 0.5.1 generator output exactly, so it is recognised) and stamps it with a generated marker after saving a backup to `.storage/echo_experience.dashboard_backups`.
3. A repair issue asks you to disable automation **Stop Sonos in Voice Assistant Area** (id `1757961047860`). Disable it, then reload Echo Experience. The built-in route registers and the issue clears. Reload the Kiosk browser so it loads the integration-served card. Test bare “stop” and “stop music” from the Echo and the kitchen HA Voice.
4. Behaviour change: music stop now targets the Echo's *selected* speaker (the same one playback uses), not always the configured default. Selection resets to the default on reload or restart.
5. After a few days, delete the disabled automation and `www/echo-experience/` on the config share. `automations/legacy_voice_music_stop.json` keeps the last generated automation for reference.

**Rollback to 0.5.1.** An integration reload does not unload Python: Home Assistant keeps the imported 0.6 module until Core restarts, so the route would still be registered. Order matters:

1. While idle, disable the Echo Experience config entry (Settings → Devices & services → Echo Experience → ⋮ → Disable). Leave the legacy automation disabled for now.
2. Put the 0.5.1 files in place: HACS → Echo Experience → Redownload → 0.5.1, or copy `custom_components/echo_experience` from the 0.5.1 archive. Restore `www/echo-experience/echo-experience.js` on the config share from that archive.
3. Recreate the Lovelace resource `/local/echo-experience/echo-experience.js?v=<any new key>` (type module) and delete `/echo_experience/echo-experience.js?v=0.6.0`. If the dashboard changed, restore the newest entry from `.storage/echo_experience.dashboard_backups` through the raw configuration editor (drop the `echo_experience_generated` key).
4. **Restart Core** while idle. Only now is the 0.6 route gone.
5. Re-enable the Echo Experience entry, then re-enable automation `1757961047860`. Reload the Kiosk browser.

## Everyday use

- “Set a pasta timer for twelve minutes.” / “How long is left?” / “Pause the pasta timer.” / “Cancel the pasta timer.” / “Stop” or “Stop the timer” while its alarm sounds.
- “Play Absolute Radio.” / “Play Mammoth.” / “Pause the music.” / “Set the music volume to thirty percent.”
- “Will it rain tomorrow?” / “What is the weather this week?”
- “How do I defrost 400 grams of mince in my microwave?”
- “What is 350 Fahrenheit in Celsius?” / “Convert 250 grams to ounces.”
- Existing home commands such as “Turn on the kitchen lights.”

The home screen uses the approved muted gradient, with a large clock and current weather beside the date. The cloud button opens the blue/slate weather view. The overflow menu holds touch shortcuts for Home, Timers, Music, Weather, HomeGuide, Controls and Conversions. The answer view is voice-first, with larger question/answer text and conversion results; no manual conversion form is shown. HomeGuide has a **Keep open** pin using Kiosk Hold mode; **Done** releases a pin set by that page. A pin intentionally enabled by the user survives normal idle time; if the page reloads while pinned, use **Pinned** to release it. A guide remains in its view until navigation, even when the screensaver covers the display.

Playback on the profile's selected speaker switches an idle home screen to large artwork and available song/artist/album or station metadata. Pause retains the artwork, stop/idle returns an automatically opened player to home, and unrelated room playback cannot take over this Echo. Playback controls and speaker selection are behind the overflow menu. Guide/timer/weather views take precedence over an automatic music transition. `screensaver.md` documents the matching dim ambient view and Kiosk setup.

The Kitchen Echo routes music exclusively to Kitchen Sonos Group (`media_player.kitchen_sonos_group_ma`). The Echo itself remains the speech and timer-alarm output and displays Sonos artwork and playback metadata. The group contains the two Play:5s bonded as Kitchen Sonos, Dining Room Sonos (Play:1), and Move Sonos (Move 2). Other Echo profiles can have their own configured music targets; a configured default is restored on integration/Core restart. Voice requests naming a configured speaker override the current selection. Generic device controls use Home Assistant's existing entity permissions and more-info dialogs.

See [CONVERSIONS.md](CONVERSIONS.md) for supported units, the distance-conversion fix, upstream release review and HACS findings.

## Sonos ducking

The integration lowers playing kitchen Sonos speakers during voice activity on either the Echo or kitchen Voice device, then restores each speaker’s original volume. Shared speakers stay ducked until all active voice devices finish. See [DUCKING.md](DUCKING.md) for configuration, recovery and tests. The old YAML ducking automation remains disabled.

## Design and routing

`custom_components/echo_experience` provides authenticated WebSocket actions, per-device display events and an Assist LLM API named **Echo Experience**. It wraps the existing HomeGuide lookup so manual evidence can be displayed, and adds deterministic conversions, weather forecasts, music controls and native voice timer actions.

The **Echo Home** conversation agent is a separate subentry of the existing local model provider. The **Echo Home** pipeline copies Whisper, Kokoro and the Emma voice from `spark-vllm-8001`. Existing conversation agents and pipeline definitions remain available.

`custom_components/echo_experience/www/echo-experience.js` is a dependency-free custom Lovelace card. There is no assistant conversation state in a global dashboard helper. A profile is chosen explicitly by each dashboard view. Unknown device IDs receive no Echo-specific control tools; unknown profiles fail closed. Timer changes verify the timer belongs to the profile's device. Music targets are restricted to its configured speaker list. Tracks, artists and albums are resolved before playback; see [music matching](MUSIC_MATCHING.md) for supported aliases, ambiguity handling and validation.

The integration reacts to `voice_satellite_chat` and `voice_satellite_timer`. It does not infer control actions from spoken replies. Source lookups and tools publish structured results, while conversation events add the actual spoken answer. Namespaced tool names are normalised. Native Voice Satellite owns timer alarms and dismissal; this integration never creates a second alarm.

Home Assistant removes a finished timer from its timer manager before Voice Satellite fires the `finished` event, so a ringing alarm is not a timer any more. The integration records finished timers per Echo as *ringing* until dismissed. Voice Satellite (2026.9.7) offers no service or WebSocket command to dismiss its alert; its only paths are the on-screen double tap, Escape and its stop word. The Echo's own dashboard card therefore replays that gesture in the device's browser when asked and reports whether the `.vs-timer-alert` element actually disappeared. Only the browser that hosts the profile's Voice Satellite session may do this: the card checks that Voice Satellite's global `#voice-satellite-ui` element is mounted in its document and that the browser's satellite equals the profile's `satellite`. Voice Satellite identifies its satellite per browser: it hydrates `voice_satellite/get_panel_settings` into localStorage `vs-panel-config` (which carries `satellite_entity`) and, once validated against `hass.entities`, stores it in localStorage `vs-satellite-entity`; `window.__vsExternalSettings.get().satellite` exposes the same value. The card reads those in that order. Other dashboards (a phone or laptop) subscribed to the same profile never act on or report about its alarms. Mini-card layouts render their alert inside a shadow root and are not supported. Reports are bound to the requesting profile and to the timer ids in the request, so a foreign or stale report is ignored and a timer that finishes after the request keeps ringing. `echo_timer` operations `cancel`/`dismiss` and the `echo_experience.dismiss_timer` service both wait up to four seconds for that report and never claim success without it; the service also requires a calling user to be allowed to control the target satellite, and resolves companion satellites to their Echo through the entity registry. The fast sentence automation (see [VOICE_STOP.md](VOICE_STOP.md)) gives bare “stop” to a ringing alarm on the originating Echo first and to music otherwise; explicit music phrases skip timers, and “stop the timer”-style phrases go through the LLM tool. Alarms silenced on the device by tap or stop word are reported by the hosting card so the server's ringing list stays honest; unreported entries expire after an hour.

Weather uses the profile's weather entity for both speech and display. Forecasts are cached for ten minutes, with the retrieval time shown. Conversions use decimal arithmetic and defined units. Unspecified cup/pint/fluid-ounce standards and conversions between volume and mass are rejected for clarification.

## Add another Echo

1. Set up Kiosk Satellite and create a **distinct** Voice Satellite entry for the new physical device. Never assign two Echos to the same satellite or clone the existing Kiosk device identity.
2. Add a record to `profiles.json`, using the actual IDs from HA. `id`, `satellite` and `device_id` must be unique. Obtain `device_id` from the new Voice Satellite device, not the ESPHome device. Set its Music Assistant player, weather entity, room controls and optional Kiosk entities.
3. Copy the profile file to `/config/echo_experience.json` and call `echo_experience.reload` (or reload the integration). The dashboard views and the voice stop routes are rebuilt from the profiles; a voice device claimed by two profiles stops the route from registering and raises a repair issue. Profile changes do not need a Core restart. Restarting Core is required after changing Python source code.
4. Set that Echo's start/default dashboard to `/echo-home/<id>` and its voice pipeline to **Echo Home**. Reload its page to load the registered card resource.
5. In Kiosk Media Player → Now Playing, disable the Floating Player, automatic Now Playing launch and “Now Playing instead of the screensaver” so it cannot cover timer or guide content. Leave Sendspin and music ducking enabled. Keep Voice Satellite active only on the primary HA dashboard session.
6. In the Voice Satellite panel’s timer options, enable **Hide on-screen countdown**. The dashboard supplies countdown cards/chips; native completion alerts remain enabled.
   For the matching screensaver, select Kiosk Website mode with `https://<your-ha-host>/echo-home/<id>-screensaver`; set scheduled modes to Website too, with duplicate native widgets and At a Glance off. Each generated ambient view has its own explicit profile ID.
7. Verify a timer and a conversion on each device, then check that the other Echo's screen and timer list stay unchanged. Test music on the intended output at a suitable volume.

Example profile (replace all IDs with actual entities):

```json
{
  "id": "bedroom_echo",
  "name": "Bedroom Echo",
  "satellite": "assist_satellite.bedroom_echo",
  "device_id": "VOICE_SATELLITE_DEVICE_ID",
  "music_player": "media_player.bedroom_echo",
  "music_assistant_entry": "MUSIC_ASSISTANT_CONFIG_ENTRY_ID",
  "music_resolver_agent": "conversation.echo_music_resolver",
  "weather": "weather.met_office_weoley_castle",
  "dashboard": "echo-home/bedroom_echo",
  "kiosk_navigation": "select.bedroom_echo_dashboard_view",
  "kiosk_screensaver": "switch.bedroom_echo_screensaver_active",
  "kiosk_now_playing": "switch.bedroom_echo_now_playing",
  "kiosk_hold": "switch.bedroom_echo_hold_mode",
  "speakers": [{"entity_id": "media_player.bedroom_echo", "name": "This Echo"}],
  "controls": []
}
```

The verification tools read credentials from the untracked `.env` file or environment variables; credentials are not included in this project. `tooling.py` resolves the private audit directory (`.audit_path` or `echo_backup_dir`). Dashboard writes are tracked in `.storage/echo_experience.dashboard` (last generated config) and `.storage/echo_experience.dashboard_backups` (previous five configs).

## Recovery and practical limits

- To return the current Echo to the previous experience, select pipeline **spark-vllm-8001** and default dashboard **section-test/0**. The previous active page was **section-test/heating**. Re-enable Kiosk’s Floating Player and two automatic Now Playing settings if desired, and turn off Voice Satellite’s “Hide on-screen countdown” setting when returning to an older dashboard. Existing dashboards and old View Assist configuration are preserved.
- Removing/disabling Echo Experience does not remove native timers or Music Assistant. Select the old pipeline first so it does not depend on the removed LLM API.
- Voice timers follow Home Assistant's native lifecycle: browser navigation/reload preserves them while HA keeps running; Core restart does not promise to restore them. Do not restart Core during an active timer.
- Current screen results and the selected speaker are in memory and reset on integration/Core restart. Manual follow-up context is retained by the conversation agent per voice session, not globally across Echos.
- The source uses the installed HA 2026.9.2 TimerManager API to read paused timers accurately and enforce ownership, `conversation.get_agent_manager().register_trigger` for the stop phrases, and Lovelace's `dashboards`/`resources` storage objects. None of these is a public API; `hacs.json` states a minimum HA version only. Each feature is isolated so a failure becomes a repair issue or log line, not a failed setup. Recheck these interfaces when upgrading HA.
- Voice Satellite mini-card layouts render their timer alert inside a shadow root and are not supported for voice dismissal.
- Only one physical Kiosk Echo was installed during development. Automated two-profile tests verify routing and ownership; end-to-end multi-device audio/display validation requires the additional physical Echo.

## Validation

Python tests run against the same HA version as the installation:

```sh
python -m unittest discover -s tests -v
node tests/test_card.cjs custom_components/echo_experience/www/echo-experience.js
```

`verify_live.py` runs text-only requests through the dedicated pipeline using the Echo's device context. It deliberately does not claim microphone or acoustic verification. Focused deployment snapshots and live results are in the audit directory.

[TOP20_TESTS.md](TOP20_TESTS.md) documents the 386-case favourite-artist corpus, fresh music-advisor benchmark, offline CI replay and read-only live-library checks.

## Fast voice stop

[VOICE_STOP.md](VOICE_STOP.md) documents the built-in sentence route that handles “stop” and the explicit music phrases before the conversation agent. Routes come from the profiles at load time. Unknown devices never match every unassigned media player.
