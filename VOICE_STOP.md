# Fast voice stop

Home Assistant sentence triggers run before the conversation agent, even when the pipeline's “prefer local intents” setting is off. Since 0.6.0 Echo Experience registers the phrases itself (`stop_route.py`) through the same `register_trigger` hook the `conversation` automation trigger uses; the generated automation **Stop Sonos in Voice Assistant Area** (`1757961047860`) is retired and its last generated form is kept in `automations/legacy_voice_music_stop.json` for reference.

## Phrases

`stop`, `stop music`, `stop sonos`, `stop the music`, `stop the sonos`, `stop playing music`, `turn off the music`, `stop sonos in here`. Nothing else: “stop the timer”, “stop the pasta timer” and the like go to the conversation agent, whose `echo_timer` tool dismisses ringing alarms and cancels running timers with the Echo's context. A sentence route cannot tell those two apart, so it does not try.

## Stop from a relay input (0.11.0)

The sentence route above only runs for the default conversation agent, so Echo Relay answers stop itself through the same `StopRoute`. It takes more than the fixed phrase list, because speech-to-text rarely returns a bare "stop". `stop_kind` sorts a phrase of at most six words that starts with "stop" (one or two stray leading words such as "so", "alexa" or "no" are dropped):

- **plain**: nothing but stop and filler ("Stop, stop!", "stop it please", "stop talking").
- **music**: names the music (music, sonos, song, radio, playing).
- **named**: stops something else ("stop the timer", "stop the pasta timer", "stop the alarm").

Order, for the Echo the input satellite feeds:

1. **A sounding alarm.** Plain and named phrases silence it ("Timer stopped."). A music phrase goes straight to step 3.
2. **The Echo's own voice.** A plain stop while the Kiosk's Voice Satellite sensor reads `processing` or `responding` calls `vs_cancel`, which ends the turn on screen, and replies with nothing. If the sensor went idle less than two seconds ago the stop was said during the answer: nothing happens and the music keeps playing. Home Assistant's `assist_satellite` entity is no use here; it stays idle through a `vs_show` turn.
3. **Music.** `media_player.media_stop` on the selected speaker, "Stopped."

Since 0.11.1 the wake word itself ends the answer: when an input satellite starts listening while the sensor reads `processing` or `responding` and nothing is sounding, the relay calls `vs_cancel` straight away, so the Echo's voice is not in the request. A plain stop in that turn is then counted as step 2 and leaves the music alone.

A named phrase with nothing sounding is declined (`None`) and goes on to the conversation agent, so only "stop timer" or "stop <name> timer" can cancel a running timer. A stop the Echo hears itself never takes step 2: that turn is the one on its own screen.

## Routing

1. **Origin.** The satellite entity's device, else the request's device id (the precedence the automation trigger platform uses).
2. **Owned device** (an Echo profile's `device_id` or one of its `ducking.additional_satellites`, resolved through the entity registry when the route is built): bare `stop` first asks `dismiss_for_device` to silence a ringing alarm. `dismissed` → “Timer stopped.”; `unconfirmed`/`failed` → “I couldn't confirm the timer alarm stopped. Tap the alert or say stop again.” and music is left alone. Otherwise, and for every explicit music phrase, `media_player.media_stop` runs on the Echo's *selected* speaker (default: its configured player) and replies “Stopped.” after the call returns. A service error replies “I couldn't stop the music on <speaker>.”
3. **Unknown device:** a real area is required (device area, parent-device area for child devices) and only enabled `media_player` entities of the native `sonos` integration in that area are targets, using each entity's own area when set. No target → “I couldn't identify the music speaker for this device.”
4. Requests are independent; two Echos stopping at once each await their own service call.

A voice device claimed by two profiles is a configuration error: the route is not registered and repair issue *Voice stop route not registered* names the device. Previously only differing music targets were rejected; this is deliberately stricter.

## One owner at a time

HA runs every matched sentence trigger and speaks the first non-`None` reply, so the route and the old automation must never both be active. Handover is explicit:

- On load, if automation `1757961047860` exists and is enabled, the route is **not** registered and repair issue *Disable the old voice stop automation* appears. Disable or delete the automation, then reload Echo Experience.
- If the automation is switched on again while the route is registered, every request re-checks the live automation object first and answers `None`, leaving the reply to the automation, and logs a warning. Reload Echo Experience to withdraw the route fully. There is a short window during that switch in which both could act; do the change while nothing is playing.
- Rollback order: disable the Echo Experience entry, install 0.5.1 files, **restart Core** (an entry reload keeps the imported 0.6 module and its route), then re-enable the entry and the automation. Full steps in the README.

## Validation

Unit tests cover registration and withdrawal, the conflict rule, satellite/device precedence, companion routing, unknown-device area filtering (no area, non-Sonos, other area), dismissed/unconfirmed/not-ringing outcomes, explicit phrases skipping the timer service, service errors and concurrent origins. A hassil-driven test proves the phrase list matches exactly the intended sentences. Live post-transcription latency with real playback must be re-measured after deployment and recorded here before issue #3 is closed; the 0.4.x figures (0.09 s idle, 0.75 s with three players active) came from the automation route.
