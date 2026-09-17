# Automation ownership

Echo Experience owns voice-triggered views, native timer display routing, playback
view switching and Sonos ducking in its integration/frontend code. No extra YAML
automation is required for those behaviours.

`legacy_sonos_ducking.yaml` preserves the former kitchen Voice-device automation
for reference and rollback. It is disabled in Home Assistant and must remain
disabled while integration ducking is enabled. Do not import it alongside the new
implementation: two volume-restoration controllers would conflict.

Native Kiosk idle and clock schedules are documented in `../screensaver.md`.
Voice Satellite owns the voice pipeline, timer alarms and conversation overlay;
its installed settings are documented in the project README and screensaver notes.
