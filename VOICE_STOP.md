# Fast voice stop

Home Assistant sentence-triggered automations run before the Echo conversation agent, even when the pipeline's “prefer local intents” setting is off. The existing **Stop Sonos in Voice Assistant Area** automation (`1757961047860`) handles “stop”, “stop music” and its related phrases.

At 08:16 BST on 18 September, the pipeline heard “Stop” and spent 30.5 seconds in that automation before replying “Done”. The automation trace showed one media_stop call targeting 14 entities, including TVs, duplicate Music Assistant players, other rooms and the Echo. The old template classified any media player with `group_members` as Sonos. The Echo's missing area matched other entities whose area was also missing. The trace identifies the broad blocking service call, not which individual player consumed the delay.

`stop_automation.py` now builds the automation from `profiles.json`:

- Each Echo device ID maps to that profile's configured default Music Assistant player.
- Companion satellites listed in the ducking configuration map to the same player, using their device IDs from the entity registry.
- Unknown devices require a real area and can only target native Sonos media players in that area. A missing area produces no target and an honest response.
- Requests from different Echos can run independently. Conflicting mappings for a shared voice device are rejected when generating the configuration.

The current Echo Show and kitchen HA Voice both target `media_player.kitchen_sonos_group_ma`. The automation keeps its existing ID and phrase list. It replies “Stopped” after the service returns. The model, speech recognition and TTS settings are unchanged.

Run `python stop_automation.py` after editing music targets or companion devices. Normal `deploy.py` deployment also refreshes this route; `--files-only` does not. The script uses HA's automation configuration API, backs up the previous record in the private audit directory, updates just this automation and verifies the saved configuration. No Core restart is required. The generated JSON is tracked for review and recovery.

## Validation

The live HA template renderer returned only the configured MA group for both kitchen voice devices and an empty target list for an unknown device with no area. The idle “Stop” pipeline replay returned “Stopped” in 0.09 seconds. Three regression tests cover multiple Echo routes, unresolved companions and conflicting shared-device targets; the complete Python suite has 52 passing tests.

With music actively playing on all three native room players, replaying “Stop” through the Echo Home text stage returned “Stopped” in **0.75 seconds**. The MA group, Kitchen stereo pair, Dining Room and Move all reached idle. The quiet test was stopped and all original 40% volumes were restored. These timings measure processing after transcription; they do not include wake-word detection, microphone recognition or the duration of the spoken reply.
