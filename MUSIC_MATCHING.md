# Music matching — 0.4.1

The Echo keeps simple music requests on a fast path and uses the Music Assistant catalog plus a dedicated name resolver when a transcription needs help. A selected URI always comes from Music Assistant. The voice model cannot invent a playable ID or change the originating Echo's permitted speaker.

## Resolution order

1. Search the library, trying punctuation, accents, known spoken aliases and album numbers (digits, words, Roman numerals). Try connected providers if the library has no exact match.
2. Prefer a standard studio release of the same work and artist. Ordinary/remastered/deluxe duplicates do not cause a question. Respect an explicitly requested album or version. Different artists are kept separate.
3. If needed, resolve the artist against the actual library artist list. Close spelling errors with a clear ranking margin resolve directly. For tracks/albums, fetch that artist's actual library tracks/albums using the installed Music Assistant client's `get_artist_tracks` / `get_artist_albums` methods.
4. Rank the real titles and give a shortlist to **Echo Music Resolver** when phonetic or musical knowledge is needed. The agent must return an existing candidate index with high confidence. If a catalog match is not available, it can suggest a canonical name; that name must pass another Music Assistant lookup before playback.
5. Ask a short question only when the request still lacks a convincing match. An explicit artist cannot be dropped, an identified artist cannot be swapped, and an album number or requested live/version constraint cannot be discarded by a correction.

The advisor has no Home Assistant APIs or function tools. Its output is parsed as JSON, and generated URIs, invalid indices, low confidence and malformed replies are rejected. It receives no playback controls. Calls use fresh conversation sessions so requests from different Echos do not share conversational history.

Advisor choices and corrected names must also pass an independent spelling/phonetic plausibility check. A confident model answer cannot substitute an unrelated title merely because it belongs to the requested artist. Short artist names can resolve through a unique close phonetic catalog match; ambiguous identities remain unresolved. Spoken letters and number components provide additional evidence for names such as AC/DC and 30/30-150.

The artist catalog is limited to 1,000 entries and each artist's title catalog to 2,000 items, cached for five minutes per Music Assistant entry/artist/type. Shortlists contain at most 12 items. Exact matches need no model call. Each fallback permits at most two model calls of six seconds each, within the overall 25-second resolution deadline. Catalog failures and advisor failures fall back to the unresolved result. Retrieval quality still depends on Music Assistant/provider metadata; this is not a guarantee of arbitrary speech recognition.

## Why the old flow felt easier

The disabled `automation.view_assist_play_music_with_music_assistant_enhanced` uses `xpenno255/blueprint-playmusicwithmusicassistant-sw.yaml`. Its configured fallback was `conversation.gemma4_music_agent`, using `gemma-4-26b-a4b`. It corrected names then retried Music Assistant. Both extended search and smart selection were disabled, so it requested one result and chose the first match.

The new implementation retains name correction, adds catalog-grounded selection and default release preferences, and continues playing the verified URI on the Echo's configured speaker. The older automation and its agent are unchanged.

The 19 September “Play the album Mammoth 2 by Mammoth” trace exposed another bug: the main agent passed `query: Mammoth 2` and `album: Mammoth 2`. Album search results have no parent album, so the duplicate filter wrongly rejected a valid result. `album` now filters tracks only. The main prompt/tool description also tells the agent to omit it for album requests.

## Configuration and deployment

`music_agent.json` contains the dedicated resolver's settings and prompt. Create a conversation subentry called **Echo Music Resolver** on the same Extended OpenAI provider as the previous music agent (currently Gemma). Keep `functions: '[]'` and `llm_hass_api: []`; do not enable device-control tools. The current entity is `conversation.echo_music_resolver`. The existing agent `conversation.gemma4_music_agent` is not modified.

Add `music_resolver_agent: conversation.echo_music_resolver` alongside `music_assistant_entry` in each participating Echo's profile. The same tool-free agent may serve multiple Echos; speaker routing remains profile-specific. Omitting the field retains the basic resolver without the advisor/catalog fallback. `agent.json` records the main Echo Home prompt; update that subentry's prompt as well when installing.

Python changes require a Core restart. Back up the current owned files and agent settings first and avoid active voice timers. Deploy profiles and source with `deploy.py`. The lookup-only `echo_music` action `search` exercises the same matching path as `play` without touching playback or the dashboard. The installed HA Music Assistant integration supplies the client dependency (1.5.1 on HA 2026.9.2); no additional credentials or Python requirements are added.

## Validation

76 Python tests include a 386-case favourite-artist regression corpus, as well as number/alias handling, the exact duplicate-album bug, studio/default editions, explicit live and album filters, rejected covers, catalog spelling/phonetic recovery, actual-candidate selection, invalid/low-confidence model output, invented names, timeouts, two-call budget, artist/version preservation and fallback routing to the originating Echo's speaker. Earlier regression cases for misclassified artist requests and scoped voice stopping remain covered. See [TOP20_TESTS.md](TOP20_TESTS.md) for corpus provenance, fresh-advisor results and repeatable commands.

Read-only live checks on 19 September:

| Request | Verified result | Approx. time |
| --- | --- | --- |
| Mammoth 2 by Mammoth, with duplicate album field | Mammoth II | 1.68 s |
| Blackburd by Altar Bridge | Blackbird by Alter Bridge | 0.74 s |
| black birch by Alter Bridge | Blackbird by Alter Bridge | 1.00 s |
| alter brij | Alter Bridge | 1.45 s |
| sweet childe of mine by Guns and Roses | Sweet Child O’ Mine, Appetite for Destruction | 0.78 s |
| Use Your Illusion two by Guns N Roses | Use Your Illusion II | 0.28 s |
| xqzpkflm unknown band | No match, no playback | 0.84 s |

The resolver agent separately corrected “motley crew” to “Mötley Crüe” and declined an unrelated name despite being offered a candidate. That artist was not asserted to exist in the local library. Music remained playing throughout the read-only validation. These are backend/text-stage checks, not microphone or acoustic playback tests.

Final deployed Echo Home pipeline checks also succeeded: “Search for the album Mammoth 2 by Mammoth without playing anything” returned Mammoth II in 1.05 s, and “Search for the album Black Birch by Altar Bridge without playing anything” returned Blackbird by Alter Bridge in 1.69 s. The agent still redundantly supplied the album field, demonstrating why the backend fix is required rather than relying on prompt wording alone. Deployed Python files were compared byte-for-byte with the repository; the Sonos group remained playing.
