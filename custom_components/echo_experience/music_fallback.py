"""Catalog-grounded fallback: names from an advisor, playable IDs only from MA."""
import asyncio
import json
import re
from difflib import SequenceMatcher
from .music import (resolve_music, key, canonical, summary, matches, base_title,
                    prefer_editions, RESULT_KEYS, edition_suffix)

SPOKEN_NUMBERS = dict(zip(('zero one two three four five six seven eight nine ten eleven twelve '
                          'thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty thirty '
                          'forty fifty sixty seventy eighty ninety').split(),
                         map(str, [*range(21), 30, 40, 50, 60, 70, 80, 90])))


def ranking_key(text, kind):
    text = canonical(base_title(text, kind), kind)
    tokens = text.split()
    # Numeric titles must reach the shortlist even in a large artist catalog.
    if tokens and all(t in SPOKEN_NUMBERS or t.isdecimal() for t in tokens):
        return ''.join(SPOKEN_NUMBERS.get(t, t) for t in tokens)
    return text.replace(' ', '')


def number_compatible(query, name, kind):
    a = re.findall(r'\b\d+\b', canonical(base_title(query, kind), kind))
    b = re.findall(r'\b\d+\b', canonical(base_title(name, kind), kind))
    return not a or not b or a == b


def similarity(query, name, kind):
    if not number_compatible(query, name, kind):
        return 0.0
    return SequenceMatcher(None, ranking_key(query, kind), ranking_key(name, kind)).ratio()


def phonetic_key(text):
    """Small consonant key used as evidence, never as a global artist alias."""
    text = key(text, 'artist')
    groups = {c: str(n) for n, chars in enumerate(('bfpv', 'cgjkqsxz', 'dt', 'l', 'mn', 'r'), 1)
              for c in chars}
    codes = ''.join(groups.get(c, '') for c in text)
    return re.sub(r'(.)\1+', r'\1', codes)


def plausible_name(query, name, kind):
    """Require independent name evidence before trusting an advisor's choice."""
    if not number_compatible(query, name, kind):
        return False
    a, b = (canonical(base_title(s, kind), kind) for s in (query, name))
    if not a or not b:
        return False
    if key(a, kind) == key(b, kind):
        return True
    # Spoken letters and number components are common in band/track names.
    letters = {'a': 'a', 'ay': 'a', 'bee': 'b', 'be': 'b', 'sea': 'c', 'see': 'c',
               'dee': 'd', 'ee': 'e', 'ef': 'f', 'gee': 'g', 'aitch': 'h',
               'eye': 'i', 'jay': 'j', 'kay': 'k', 'el': 'l', 'em': 'm', 'en': 'n',
               'oh': 'o', 'pee': 'p', 'cue': 'q', 'ar': 'r', 'ess': 's', 'tee': 't',
               'you': 'u', 'vee': 'v', 'ex': 'x', 'why': 'y', 'zed': 'z', 'zee': 'z'}
    for source, target in ((a, b), (b, a)):
        tokens = source.split()
        if all(t in letters or len(t) == 1 for t in tokens):
            if ''.join(letters.get(t, t) for t in tokens) == target.replace(' ', ''):
                return True
        if ''.join(SPOKEN_NUMBERS.get(t, t) for t in tokens) == target.replace(' ', ''):
            return True
    score = similarity(a, b, kind)
    if score >= (.75 if min(len(key(a, kind)), len(key(b, kind))) < 6 else .60):
        return True
    return (score >= .5 and bool(phonetic_key(a)) and phonetic_key(a) == phonetic_key(b)
            and .65 <= len(key(a, kind)) / len(key(b, kind)) <= 1.55)


def eligible(items, kind, artist='', album='', version=''):
    # Reuse metadata constraints while deliberately leaving title comparison to
    # the ranking step. Do not let fuzzy/LLM selection override artist/version.
    return [i for i in items if i.get('name') and matches(i, i['name'], kind, artist, album, version)]


def select(items, query, kind, artist='', album='', version=''):
    pool = eligible(items, kind, artist, album, version or edition_suffix(query, kind))
    exact = [i for i in pool if matches(i, query, kind, artist, album, version)]
    if exact:
        pool = prefer_editions(exact, kind)
        if len(pool) == 1:
            return pool[0], pool
        return None, pool
    pool = [i for i in pool if number_compatible(query, i['name'], kind)]
    pool = prefer_editions(pool, kind)
    pool.sort(key=lambda i: similarity(query, i['name'], kind), reverse=True)
    if kind == 'artist' and 3 <= len(key(query, kind)) <= 5:
        phonetic = [i for i in pool if 3 <= len(key(i['name'], kind)) <= 5
                    and phonetic_key(query) and phonetic_key(query) == phonetic_key(i['name'])
                    and similarity(query, i['name'], kind) >= .6]
        if len(phonetic) == 1:
            return phonetic[0], pool
    if pool and len(key(query, kind)) >= 6:
        score = similarity(query, pool[0]['name'], kind)
        runner_up = similarity(query, pool[1]['name'], kind) if len(pool) > 1 else 0
        if score >= .88 and score - runner_up >= .10:
            return pool[0], pool
    return None, pool[:12]


def matched(item, kind, source):
    return {'status': 'matched', 'match': summary(item), 'media_type': kind, 'resolution': source}


def parse_advice(text):
    """Accept a small JSON object only; never turn model prose into a command."""
    text = text.strip()
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text).strip()
    try:
        value = json.loads(text)
    except (ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) and value.get('confidence') == 'high' else {}


async def resolve_with_fallback(search, catalog, advisor, query, kind, artist='', album='', version=''):
    initial = await resolve_music(search, query, kind, artist, album, version)
    if initial['status'] == 'matched' or kind not in RESULT_KEYS:
        return initial
    # The basic resolver handles contradictory media types without model guesses.
    if kind == 'artist' and artist and key(query, 'artist') != key(artist, 'artist'):
        return initial
    calls = 0

    async def ask(payload):
        nonlocal calls
        if advisor is None or calls >= 2:
            return {}
        calls += 1
        try:
            async with asyncio.timeout(6):
                return parse_advice(await advisor(payload))
        except (TimeoutError, ValueError, TypeError):
            return {}

    async def choose(pool, name, media_type, performer=''):
        if not pool:
            return None
        answer = await ask({'task': 'choose', 'request': {'query': name, 'media_type': media_type, 'artist': performer,
                           'album': album, 'version': version},
                           'candidates': [{'index': n, **summary(i)} for n, i in enumerate(pool[:12])]})
        index = answer.get('index')
        # bool is an int in Python; reject it along with arbitrary/generated IDs.
        if (type(index) is int and 0 <= index < min(len(pool), 12)
                and plausible_name(name, pool[index]['name'], media_type)):
            return pool[index]
        return None

    # Exact-name ambiguity between genuinely different artists remains a model
    # decision only when the request gives no artist; the advisor can decline.
    if initial['status'] == 'needs_clarification' and not artist:
        choices = initial.get('choices', [])
        pool = [{**i, 'artists': [{'name': i['artist']}] if i.get('artist') else [],
                 'album': {'name': i.get('album', '')}} for i in choices]
        if item := await choose(pool, query, kind):
            return matched(item, kind, 'catalog_advisor')
        return initial

    performer = query if kind == 'artist' else artist
    artist_item = None
    if performer:
        artists = await catalog('artist', None)
        artist_item, shortlist = select(artists, performer, 'artist')
        if artist_item is None:
            artist_item = await choose(shortlist, performer, 'artist')
        if artist_item and kind == 'artist':
            return matched(artist_item, kind, 'artist_catalog')
        if artist_item:
            catalog_artist = artist_item['name']
            items = await catalog(kind, artist_item['uri'])
            item, shortlist = select(items, query, kind, catalog_artist, album, version)
            if item is None:
                item = await choose(shortlist, query, kind, catalog_artist)
            if item:
                return matched(item, kind, 'artist_catalog')

    # Similar to the former Gemma music agent: correct a transcription, then
    # verify it against MA. The model cannot supply a URI or perform playback.
    correction = await ask({'task': 'correct', 'request': {'query': query, 'media_type': kind,
                           'artist': artist, 'album': album, 'version': version}})
    title = correction.get('query')
    by = correction.get('artist', artist)
    if not isinstance(title, str) or not isinstance(by, str) or not 0 < len(title) <= 200 or len(by) > 200:
        return initial
    if artist and kind != 'artist' and not by.strip():
        return initial
    if '://' in title + by or not plausible_name(query, title, kind):
        return initial
    if artist and kind != 'artist' and not plausible_name(artist, by, 'artist'):
        return initial
    # An artist already identified in the catalog cannot be changed by a rewrite.
    if artist_item and key(by, 'artist') != key(artist_item['name'], 'artist'):
        return initial
    if title == query and by == artist:
        return initial
    result = await resolve_music(search, title, kind, by, album, version or edition_suffix(query, kind))
    if result['status'] == 'matched':
        result['resolution'] = 'verified_name_correction'
        return result
    return initial
