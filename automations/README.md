# Automation ownership

Echo Experience owns voice-triggered views, native timer display routing, playback
view switching, Sonos ducking and, since 0.6.0, the fast voice stop route in its
integration/frontend code. No extra YAML automation is required for those behaviours.

`legacy_voice_music_stop.json` is the last generated form of automation
`1757961047860` (Stop Sonos in Voice Assistant Area). It must be disabled or deleted
in Home Assistant while Echo Experience 0.6.0+ is loaded; the integration refuses to
register its own route while that automation is enabled. Keep the file only for
rollback to 0.5.1 (see README).

`legacy_sonos_ducking.yaml` preserves the former kitchen Voice-device automation
for reference and rollback. It is disabled in Home Assistant and must remain
disabled while integration ducking is enabled. Do not import it alongside the new
implementation: two volume-restoration controllers would conflict.

Native Kiosk idle and clock schedules are documented in `../screensaver.md`.
Voice Satellite owns the voice pipeline, timer alarms and conversation overlay;
its installed settings are documented in the project README and screensaver notes.
