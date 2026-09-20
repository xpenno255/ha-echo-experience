# Fast voice stop

Since 0.5.0 the same automation also owns bare “stop” while a timer alarm is ringing. It first calls `echo_experience.dismiss_timer` for the originating Echo (companion satellites map to their Echo's profile); when that returns `dismissed` it replies “Timer stopped.” and does not touch music. Explicit music phrases (“stop music”, “stop Sonos”, …) skip the timer step entirely. “Stop the timer”, “stop the alarm”, “dismiss the timer/alarm” and “turn off the timer/alarm” are handled here too: with nothing ringing they cancel the single running timer, ask which one if several are running, or say nothing is running. Named dismissals (“stop the pasta timer”) intentionally have no sentence trigger and stay with the LLM's `echo_timer` tool. An unconfirmed dismissal is reported as such rather than claimed. Devices outside the profiles keep the previous area-scoped Sonos behaviour and never call the timer service. The timer step uses `continue_on_error`, but Home Assistant still aborts a script when the service itself is missing, so while the Echo Experience integration is unloaded (reload/upgrade) bare “stop” returns an error instead of stopping music; explicit music phrases are unaffected.


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
