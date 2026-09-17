# Voice-controlled music ducking

Version 0.3.0 moves Sonos ducking into Echo Experience. The kitchen profile watches
both `assist_satellite.echo_show_8` and the existing kitchen Home Assistant Voice
satellite. It lowers only configured Sonos players that are playing; it also catches
music started during a voice request. Speech and timer audio still use the Echo.

Each speaker is reduced to 10% of its own current volume while Assist is listening,
processing or responding (the older thinking/speaking names are supported too).
The three configured Sonos entities cover four physical speakers because the two
Play:5s are a bonded stereo pair. No group-average volume is used.

After all voice devices sharing a speaker are idle for one second, the original
individual volume is restored. Follow-up conversations do not repeatedly multiply
the volume down. A voice disconnect releases ownership immediately; a stuck active
state is limited to two minutes. These defaults are configurable in `profiles.json`:

```json
"ducking": {
  "enabled": true,
  "players": ["media_player.kitchen_sonos", "media_player.dining_room_sonos", "media_player.move_sonos"],
  "additional_satellites": ["assist_satellite.home_assistant_voice_kitchen_assist_satellite"],
  "volume_factor": 0.1,
  "restore_delay": 1,
  "max_duration": 120
}
```

The profile's own satellite is always included. Additional Echo profiles can watch
different speakers or share these speakers. Only explicit profile membership grants
volume control; no room or entity names are guessed.

Original levels are written to Home Assistant's private storage before each volume
change. On unload/shutdown/restart, the integration restores owned volume levels;
unavailable speakers retain a recovery record and are retried when available.
If the user or another controller changes a speaker's volume away from our ducked
level, that new value is preserved. A change to exactly the ducked value cannot be
distinguished from no change. Sonos rounds to whole percentage points.

This is speaker-volume ducking, not a pause or Sonos snapshot/restore operation.
It does not modify playback queues or groups. Existing Kiosk ducking can continue
handling audio local to the Echo; the integration handles the separate Sonos output.
The old kitchen ducking automation remains disabled to prevent double restoration.

## Validation

Unit tests cover overlapping satellites, room isolation, all voice phases, delayed
state acknowledgements, playback beginning during speech, manual volume changes,
idle grace periods, disconnects, timeouts, failed volume calls, offline recovery and
integration unload. All 30 Python tests and 11 frontend assertions pass locally.

Live validation on 17 September 2026 used an actual announcement through the Echo
while the Sonos group played quietly. Kitchen/Dining/Move dropped from 18%/12%/15%
to 2%/1%/1%, then returned to exactly 18%/12%/15% after the satellite became idle.
The test stopped playback and restored the preceding speaker volumes. Detailed
event timings are retained only in the private audit. Listening/processing phases
and overlapping satellites are covered by automated tests; an acoustic wake-word
check remains useful on the physical devices.

To test acoustically, play music and ask the Echo for the weather. Music should drop
as the Echo starts listening, stay quiet through its answer and return afterwards.
Repeat with a follow-up and with the kitchen Voice device. While speaking, ask for
a new music volume and verify that the new setting survives the end of the answer.
