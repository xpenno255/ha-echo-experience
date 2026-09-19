# Favourite-artist music tests

The suite exercises the production artist/album/track resolver with the 20 artists supplied on 19 September 2026. It contains 386 cases, one canonical album and two canonical songs per artist. Canonical work metadata was checked against Apple Search API results, with MusicBrainz recording checks for Stone Sour's 30/30-150 and Pearl Jam's Even Flow. Source references are embedded in `tests/fixtures/top20_music.json`.

The fixture has 160 items: 20 artists, 20 albums, 40 tracks and 80 deliberately synthetic live/remastered variants. All fixture URIs use `fixture://`; none are playable IDs. These are authored text requests, not recorded microphone transcripts, and the fixture is not an inventory of the NAS.

## Coverage

- Canonical artists, album titles and songs, punctuation, apostrophes, accents and spoken spellings.
- Combined errors in the artist and title, spoken letters (AC/DC), numbered albums and numeric track titles.
- Standard releases, explicit live versions, invalid versions and duplicate album fields.
- Conflicting performers, unknown artists and distinct identities such as Slash versus Slash's Snakepit.
- Existing integration tests separately cover per-Echo output routing, so resolution cannot redirect playback to a different device's speaker.

## Results

The first fresh real-advisor run passed 379/386 cases. Four failures involved Reeve/Reef. Three involved confident but unrelated replacements: Year of the Tiger became Pantera's Vulgar Display of Power; Slash became Slash's Snakepit's It's Five O'Clock Somewhere; Beggars and Hangers On became Slash's Back from Cali.

After the resolver fixes, a fresh run passed **386/386**, making **104 actual requests** to `conversation.echo_music_resolver`. Exact and sufficiently close matches resolve without the model. The original and final reports are retained in `benchmarks/top20_baseline_report.json` and `benchmarks/top20_advisor_report.json`.

Offline CI runs all 386 cases using recorded responses from that actual advisor run. It does not call a model or Home Assistant. This verifies resolver regressions reproducibly; it does not guarantee a future model will answer identically. The fixture's search adapter is independent strict text search, without the resolver's aliases or phonetic logic. Missing recorded requests fail the test rather than silently fabricating advice.

The normal suite passes 76 Python tests (including the 386-case replay) and 11 frontend assertions. All benchmark modes perform lookups only; none queue music, stop playback or set volume.

The first installed-library run passed 55/56 applicable requests and exposed a gap hidden by the smaller fixture: "thirty thirty one fifty by stone sower" did not find 30/30-150 in Stone Sour's larger catalog. Numeric title components now participate in ranking before shortlist selection, and a separate regression uses more than 12 competing tracks. The updated local resolver successfully selected the real library track from a snapshot of all 530 tracks using the actual advisor.

After deployment and restart, the final installed-library run passed **56/56 applicable requests**, including the numeric Stone Sour request in 0.44 seconds. Of the remaining 330 cases, 225 were skipped because the expected work was absent and 105 were synthetic version/negative constraints reserved for fixture testing. The library contains five artists, 30 albums and 530 tracks; four artists are from the user's list (Alter Bridge, Black Stone Cherry, Guns N' Roses and Stone Sour), plus Mammoth. The other 16 favourites have fixture coverage only. Private library reports stay outside Git. Deployed Python source was byte-verified, Core returned to RUNNING and Sonos remained in the playing state; no benchmark sent playback commands.

## Run again

Run from the repository root with the development dependencies installed:

```sh
# Deterministic offline replay, also included in normal unittest discovery.
python benchmark_music.py --mode replay
python -m unittest discover -s tests -q

# Fresh requests to the configured music-only advisor, using the synthetic catalog.
python benchmark_music.py --mode advisor --fresh --record --output benchmarks/top20_advisor_report.json

# Read-only searches against the installed integration and actual library.
python benchmark_music.py --mode library --output .backups/top20_library.private.json
```

Live modes require the ignored local `.env` setup used by `ha_client.py`. Library mode skips works absent from the actual library and skips synthetic constraint/version cases. A fixture pass is not evidence that a provider or NAS contains that work. NAS validation can be extended once the music share is connected to Music Assistant; no direct NAS credentials are needed by this test suite.

Remaining limits: speech recognition, the main conversation agent's interpretation of a full utterance, speaker grouping and audible playback need separate end-to-end checks. The advisor's plausibility guard reduces unrelated selections but is deliberately conservative and cannot prove intent for every ambiguous phrase. Add actual failed transcripts to the corpus as they occur.
