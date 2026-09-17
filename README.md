# Echo Experience

Private source: https://github.com/xpenno255/echo-experience

A shared Home Assistant dashboard and Assist tool integration for LineageOS Echos running Kiosk Satellite + Voice Satellite. Each device has its own satellite, music output, timer ownership and display results. The current installed profile is **Kitchen Echo** (`echo_show_8`).

Dashboard: <https://homeassistant.xpennohome.uk/echo-home/echo_show_8>

## Source and setup

The private repository contains the integration, installed dashboard definition and frontend, device profiles, agent settings, design history, tests and retired automation reference. Credentials, screenshots, audit logs and backups stay outside Git.

For local deployment, copy `.env.example` to `.env` and fill in the Home Assistant and Samba credentials. Install `requirements-dev.txt` in a Python 3.14 virtual environment. Run `python deploy.py` to copy the owned files and register the dashboard. Add Echo Experience through Home Assistant integrations after its initial installation. Python integration changes need a Core restart; profile changes need only an integration reload. Frontend changes need a kiosk reload. Private deployment backups default to `.backups/`.

## Everyday use

- “Set a pasta timer for twelve minutes.” / “How long is left?” / “Pause the pasta timer.” / “Cancel the pasta timer.”
- “Play Absolute Radio.” / “Play Mammoth.” / “Pause the music.” / “Set the music volume to thirty percent.”
- “Will it rain tomorrow?” / “What is the weather this week?”
- “How do I defrost 400 grams of mince in my microwave?”
- “What is 350 Fahrenheit in Celsius?” / “Convert 250 grams to ounces.”
- Existing home commands such as “Turn on the kitchen lights.”

The home screen uses the approved muted gradient, with a large clock and current weather beside the date. The cloud button opens the blue/slate weather view. The overflow menu holds touch shortcuts for Home, Timers, Music, Weather, HomeGuide, Controls and Conversions. The answer view includes a manual converter. HomeGuide has a **Keep open** pin using Kiosk Hold mode; **Done** releases a pin set by that page. A pin intentionally enabled by the user survives normal idle time; if the page reloads while pinned, use **Pinned** to release it. A guide remains in its view until navigation, even when the screensaver covers the display.

Playback on the profile's selected speaker switches an idle home screen to large artwork and available song/artist/album or station metadata. Pause retains the artwork, stop/idle returns an automatically opened player to home, and unrelated room playback cannot take over this Echo. Playback controls and speaker selection are behind the overflow menu. Guide/timer/weather views take precedence over an automatic music transition. `screensaver.md` documents the matching dim ambient view and Kiosk setup.

The Kitchen Echo routes music exclusively to Kitchen Sonos Group (`media_player.kitchen_sonos_group_ma`). The Echo itself remains the speech and timer-alarm output and displays Sonos artwork and playback metadata. The group contains the two Play:5s bonded as Kitchen Sonos, Dining Room Sonos (Play:1), and Move Sonos (Move 2). Other Echo profiles can have their own configured music targets; a configured default is restored on integration/Core restart. Voice requests naming a configured speaker override the current selection. Generic device controls use Home Assistant's existing entity permissions and more-info dialogs.

## Sonos ducking

The integration lowers playing kitchen Sonos speakers during voice activity on either the Echo or kitchen Voice device, then restores each speaker’s original volume. Shared speakers stay ducked until all active voice devices finish. See [DUCKING.md](DUCKING.md) for configuration, recovery and tests. The old YAML ducking automation remains disabled.

## Design and routing

`custom_components/echo_experience` provides authenticated WebSocket actions, per-device display events and an Assist LLM API named **Echo Experience**. It wraps the existing HomeGuide lookup so manual evidence can be displayed, and adds deterministic conversions, weather forecasts, music controls and native voice timer actions.

The **Echo Home** conversation agent is a separate subentry of the existing local model provider. The **Echo Home** pipeline copies Whisper, Kokoro and the Emma voice from `spark-vllm-8001`. Existing conversation agents and pipeline definitions remain available.

`www/echo-experience.js` is a dependency-free custom Lovelace card. There is no assistant conversation state in a global dashboard helper. A profile is chosen explicitly by each dashboard view. Unknown device IDs receive no Echo-specific control tools; unknown profiles fail closed. Timer changes verify the timer belongs to the profile's device. Music targets are restricted to its configured speaker list.

The integration reacts to `voice_satellite_chat` and `voice_satellite_timer`. It does not infer control actions from spoken replies. Source lookups and tools publish structured results, while conversation events add the actual spoken answer. Namespaced tool names are normalised. Native Voice Satellite owns timer alarms and dismissal; this integration never creates a second alarm.

Weather uses the profile's weather entity for both speech and display. Forecasts are cached for ten minutes, with the retrieval time shown. Conversions use decimal arithmetic and defined units. Unspecified cup/pint/fluid-ounce standards and conversions between volume and mass are rejected for clarification.

## Add another Echo

1. Set up Kiosk Satellite and create a **distinct** Voice Satellite entry for the new physical device. Never assign two Echos to the same satellite or clone the existing Kiosk device identity.
2. Add a record to `profiles.json`, using the actual IDs from HA. `id`, `satellite` and `device_id` must be unique. Obtain `device_id` from the new Voice Satellite device, not the ESPHome device. Set its Music Assistant player, weather entity, room controls and optional Kiosk entities.
3. Copy the profile file to `/config/echo_experience.json`, regenerate the dashboard using `deploy.py`, and reload the **Echo Experience** integration through HA. Profile changes do not need a Core restart. Restarting Core is required after changing Python source code.
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

`deploy.py` reads credentials from the untracked `.env` file or environment variables; credentials are not included in this project. It writes only owned files, preserves a before-copy of replaced files, adds/updates `echo-home`, and registers the card with a content-derived cache key. The path in `.audit_path` identifies private deployment evidence.

## Recovery and practical limits

- To return the current Echo to the previous experience, select pipeline **spark-vllm-8001** and default dashboard **section-test/0**. The previous active page was **section-test/heating**. Re-enable Kiosk’s Floating Player and two automatic Now Playing settings if desired, and turn off Voice Satellite’s “Hide on-screen countdown” setting when returning to an older dashboard. Existing dashboards and old View Assist configuration are preserved.
- Removing/disabling Echo Experience does not remove native timers or Music Assistant. Select the old pipeline first so it does not depend on the removed LLM API.
- Voice timers follow Home Assistant's native lifecycle: browser navigation/reload preserves them while HA keeps running; Core restart does not promise to restore them. Do not restart Core during an active timer.
- Current screen results and the selected speaker are in memory and reset on integration/Core restart. Manual follow-up context is retained by the conversation agent per voice session, not globally across Echos.
- The source uses the installed HA 2026.9.2 TimerManager API to read paused timers accurately and enforce ownership. Recheck this interface when upgrading HA.
- Only one physical Kiosk Echo was installed during development. Automated two-profile tests verify routing and ownership; end-to-end multi-device audio/display validation requires the additional physical Echo.

## Validation

Python tests run against the same HA version as the installation:

```sh
python -m unittest discover -s tests -v
node tests/test_card.cjs www/echo-experience.js
```

`verify_live.py` runs text-only requests through the dedicated pipeline using the Echo's device context. It deliberately does not claim microphone or acoustic verification. Focused deployment snapshots and live results are in the audit directory.
