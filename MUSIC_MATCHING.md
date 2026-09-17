# Music matching

Echo Experience 0.3.2 resolves a requested track, artist or album through Music Assistant search before calling play_media with the returned URI. Searches use the originating Echo's Music Assistant config entry; playback still uses its selected, permitted speaker (Kitchen Sonos for the current Echo).

The resolver first searches the library, tries normalized alternatives when needed, then searches connected providers if no library match exists. A 25-second deadline bounds resolution. Each search requests up to 25 candidates. Candidate names must match after normalization, as must any requested artist, album and version. Different tracks, covers or editions are not selected solely because they appear first. Multiple candidates produce a clarification response and leave the queue untouched. Rephrase the request with the artist, album or version to narrow it down.

Normalization handles capitalization, accents, punctuation and spacing. Explicit spoken aliases currently cover **Guns and Roses → Guns N Roses** and **Sweet Child of Mine → Sweet Child O Mine**. Trailing album numbers recognize Roman numerals II–X and spoken numbers two–ten. These are deliberately bounded rules, not a promise to recognize arbitrary misspellings or phonetic names. Additional known spoken aliases can be added to `music.py` with regression tests. Search retrieval still depends on what Music Assistant and each provider return.

The voice tool accepts separate `query`, `media_type`, `artist`, `album` and `version` fields. `action: search` returns a match without playing. `action: play` performs the same resolution and only queues a unique match. Unknown media types need clarification. Radio, playlist and podcast requests keep the previous Music Assistant playback path. The dashboard's optional manual search displays a message when a title needs clarification.

## Validation

On 17 September 2026, the resolver found these in the live library without playback:

| Query | Verified result |
| --- | --- |
| Guns and Roses | Guns N’ Roses |
| Sweet Child of Mine, artist Guns and Roses | Sweet Child O’ Mine / Appetite for Destruction |
| Sweet Child O Mine, artist Guns N Roses | Same original album track |
| Use Your Illusion 2, artist Guns and Roses | Use Your Illusion II |
| Use Your Illusion two, artist Guns N Roses | Use Your Illusion II |

After deployment and the Core restart, all five cases also passed through the live Echo Experience action. The Echo Home text pipeline received “Search for Sweet Child of Mine by Guns and Roses, but do not play anything”, called `echo_music` with `action: search` and the uncorrected words, and reported the correct track. Kitchen Sonos remained idle.

Tests cover rejecting another artist's cover, asking about multiple artists/versions, filtering an explicit album/version, provider fallback, speaker routing, queue preservation on ambiguity and read-only search. Live text/pipeline or API checks do not verify microphone recognition or the acoustic result from the Sonos speakers.
