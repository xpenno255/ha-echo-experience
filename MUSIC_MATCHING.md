# Music matching

Echo Experience 0.3.3 resolves a requested track, artist or album through Music Assistant search before calling play_media with the returned URI. Searches use the originating Echo's Music Assistant config entry; playback still uses its selected, permitted speaker (Kitchen Sonos for the current Echo).

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

## Physical voice failure on 18 September

The 07:53 BST Echo trace transcribed “play Sweet Child of Mine by Guns N’ Roses” correctly. The agent supplied `media_type: artist` instead of `track`, so it searched artists for the song title and failed. The previous read-only search test did not exercise this play-command classification.

The live Echo Home subentry prompt and source `agent.json` now explain the difference with song and artist examples. If an artist request contains a different artist filter, the resolver checks both track and album categories and only accepts a unique match; it does not blindly change every contradictory request into a track. Genuine artist requests with a redundant artist filter also work. The regression suite includes the exact failed tool arguments.

Validation after deploying 0.3.3:

- 49 Python tests passed, including the exact failed play arguments.
- The live read-only action recovered the original contradictory artist-type arguments to `library://track/339` with media type `track`.
- Replayed the exact transcribed sentence through Echo Home with `action: play`: the agent now sent `media_type: track`. Music Assistant and all three native room players (Kitchen stereo pair, Dining Room, Move) reported playing Sweet Child O’ Mine from Appetite for Destruction.
- The brief playback check used 3% volume, stopped afterwards, and restored all rooms to their original 40%. Initial native-player state updates lagged the MA group state; validation waited for every room to report playing.
- Playback was verified from device state and metadata, not by listening to the physical speakers. The initial physical test already confirmed speech recognition; the post-fix request was replayed through the text stage of the same pipeline.
