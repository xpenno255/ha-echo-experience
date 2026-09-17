# Kitchen Sonos routing — 17 September 2026

Kitchen Echo now uses `media_player.kitchen_sonos_group_ma` as both its default and sole allowed Echo Experience music output. Speech and native voice timer alarms remain on the Echo. Profile deployed and integration reloaded without restarting Home Assistant.

The existing Music Assistant Sync Group Player (`syncgroup_zrcqrbxb`) has fixed members Dining Room Sonos, Kitchen Sonos and Move Sonos, using native Sonos players. Live Sonos topology confirms Kitchen Sonos is a bonded left/right Play:5 pair, so these three players represent four physical speakers. No group membership changes were needed.

Music Assistant also has duplicate Home Assistant MediaPlayers entries for Sonos. These were left unchanged; their presence alone does not establish a cause of failures.

Validation: resumed the existing group queue at 15% volume. Kitchen, Dining Room and Move all reported playing Resolve with the same group membership; the Echo music player remained idle. Physical Echo screenshot confirmed artwork, title and artist. Stopped playback and restored individual Sonos volumes. This verifies reported playback and display, not acoustic synchronisation.

The user reports intermittent failures to start or playback on only some speakers, possibly after Alexa use. This was not reproduced. MA documents that a sync group may fail to power on if a child belongs to another group: https://www.music-assistant.io/faq/groups/ . Alexa causation remains unconfirmed. If it recurs, capture MA group/member state and native Sonos topology before regrouping.

Audit: `profiles.pre_sonos.json`, `sonos.pre_playback_test.private.json`, `sonos-music-live.jpg` under the existing 20260917T142647Z review directory.
