"""Conservative music resolution before changing a speaker's queue."""
import asyncio
import re
import unicodedata

# Deliberate spoken aliases, not unrestricted fuzzy matching of unrelated names.
ALIASES = {
    'artist': {'guns and roses': 'guns n roses'},
    'track': {'sweet child of mine': 'sweet child o mine'},
}
NUMBERS = {'one': '1', 'i': '1', 'two': '2', 'three': '3', 'four': '4', 'five': '5', 'six': '6', 'seven': '7', 'eight': '8', 'nine': '9', 'ten': '10',
           'ii': '2', 'iii': '3', 'iv': '4', 'v': '5', 'vi': '6',
           'vii': '7', 'viii': '8', 'ix': '9', 'x': '10'}
ROMAN = {str(i): word for i, word in enumerate(
    ('i', 'ii', 'iii', 'iv', 'v', 'vi', 'vii', 'viii', 'ix', 'x'), 1)}
RESULT_KEYS = {'track': 'tracks', 'artist': 'artists', 'album': 'albums'}


def words(text):
    text = unicodedata.normalize('NFKD', text.casefold())
    text = ''.join(c for c in text if not unicodedata.combining(c))
    text = text.replace('&', ' and ').translate(str.maketrans('', '', "'’‘`"))
    return ' '.join(re.sub(r'[^\w]+', ' ', text).split())


def canonical(text, kind):
    text = words(text)
    text = ALIASES.get(kind, {}).get(text, text)
    # A trailing album number may be spoken as a digit or a word.
    if kind == 'album':
        parts = text.split()
        if len(parts) > 1:
            parts[-1] = NUMBERS.get(parts[-1], parts[-1])
        text = ' '.join(parts)
    return text


def key(text, kind):
    return canonical(text, kind).replace(' ', '')


def search_name(text, kind):
    text = canonical(text, kind)
    if kind == 'album':
        parts = text.split()
        if len(parts) > 1:
            parts[-1] = ROMAN.get(parts[-1], parts[-1])
        text = ' '.join(parts)
    return text



EDITION_WORDS = re.compile(r'\b(live|remaster(?:ed)?|deluxe|anniversary|expanded|edition|acoustic|instrumental|karaoke|remix)\b', re.I)


def edition_suffix(name, kind):
    if kind not in ('track', 'album'):
        return ''
    match = re.search(r'(?:\s*[([]([^()\[\]]+)[)\]]|\s+-\s+(.+))$', name)
    suffix = (match.group(1) or match.group(2)) if match else ''
    return suffix if EDITION_WORDS.search(suffix) else ''


def base_title(name, kind):
    suffix = edition_suffix(name, kind)
    if not suffix:
        return name
    return name[:name.rfind(suffix)].rstrip(' ([–-')


def prefer_editions(items, kind):
    """Pick a sensible release of the same work, never merge different artists."""
    groups = {}
    for item in items:
        artists = tuple(sorted(key(a['name'], 'artist') for a in item.get('artists', [])))
        # Artist identities are not deduplicated merely because their names match.
        identity = item['uri'] if kind == 'artist' else (key(base_title(item['name'], kind), kind), artists)
        groups.setdefault(identity, []).append(item)
    def rank(item):
        version = words(item.get('version', '') + ' ' + edition_suffix(item['name'], kind))
        album = item.get('album') or {}
        release = words(album.get('name', ''))
        special = bool(re.search(r'\b(live|acoustic|instrumental|karaoke|remix)\b', version + ' ' + release))
        compilation = bool(re.search(r'\b(greatest hits|best of|compilation)\b', release))
        return (special, bool(version), compilation, not item['uri'].startswith('library://'),
                item.get('year') or 9999, item['uri'])
    return [min(group, key=rank) for group in groups.values()]


def summary(item):
    return {k: v for k, v in {
        'uri': item['uri'], 'name': item['name'],
        'artist': ', '.join(a['name'] for a in item.get('artists', [])),
        'album': (item.get('album') or {}).get('name', ''),
        'version': item.get('version', ''),
    }.items() if v}


def version_matches(wanted, actual):
    wanted, actual = words(wanted), words(actual)
    if wanted in ('studio', 'studio version', 'original', 'original version'):
        return not re.search(r'\b(live|acoustic|instrumental|karaoke|remix)\b', actual)
    return set(wanted.split()).issubset(actual.split())


def matches(item, query, kind, artist='', album='', version=''):
    if not item.get('uri') or key(base_title(item.get('name', ''), kind), kind) != key(base_title(query, kind), kind):
        return False
    if artist and not any(key(a.get('name', ''), 'artist') == key(artist, 'artist')
                          for a in item.get('artists', [])):
        return False
    if album and kind == 'track' and key((item.get('album') or {}).get('name', ''), 'album') != key(album, 'album'):
        return False
    wanted_version = version or edition_suffix(query, kind)
    if wanted_version and not version_matches(wanted_version, item.get('version', '') + ' ' + edition_suffix(item.get('name', ''), kind)):
        return False
    return True


async def resolve_music(search, query, kind, artist='', album='', version=''):
    """Search library first; only unambiguous metadata matches can be played.

    `search` is an async callable accepting Music Assistant search service fields.
    No playback or other mutations happen here. Streaming providers are searched
    only if the local library has no matching result.
    """
    # An artist cannot have a different artist. Some models confuse the
    # requested item's type with the separate artist filter. Resolve both
    # possible title categories; never silently assume track rather than album.
    if kind == 'artist' and artist:
        if key(query, 'artist') == key(artist, 'artist'):
            artist = ''  # Redundant artist filter; artist results have no artists list.
        else:
            results = await asyncio.gather(*(
                resolve_music(search, query, candidate, artist, album, version)
                for candidate in ('track', 'album')
            ))
            choices = []
            for candidate, result in zip(('track', 'album'), results):
                if result['status'] == 'matched':
                    choices.append({**result['match'], 'media_type': candidate})
                elif result['status'] == 'needs_clarification':
                    choices.extend({**item, 'media_type': candidate} for item in result.get('choices', []))
            if len(choices) == 1:
                return {'status': 'matched', 'match': choices[0], 'media_type': choices[0]['media_type']}
            if choices:
                return {'status': 'needs_clarification', 'choices': choices[:5],
                        'question': 'Did you mean the song or album, and which version?',
                        'note': 'Use the returned choices to ask one short clarification. Nothing has been queued.'}
            return {'status': 'not_found',
                    'message': 'No matching song or album by that artist was found. Nothing has been queued.'}
    if kind not in RESULT_KEYS:
        return {'status': 'needs_clarification',
                'question': 'Is that a song, an artist, an album, a playlist or a radio station?'}
    normalized = search_name(query, kind)
    normal_artist = search_name(artist, 'artist') if artist else ''
    attempts = [(query, artist), (normalized, normal_artist), (normalized, '')]
    attempts = list(dict.fromkeys(attempts))
    for library_only in (True, False):
        found = {}
        for name, by in attempts:
            data = {'name': name, 'media_type': [kind], 'limit': 25,
                    'library_only': library_only}
            if by:
                data['artist'] = by
            response = await search(data)
            for item in response.get(RESULT_KEYS[kind], []):
                if matches(item, query, kind, artist, album, version):
                    found[item['uri']] = item
            # The complete result page is evaluated before selecting anything.
            if found:
                choices = [summary(item) for item in prefer_editions(found.values(), kind)]
                if len(choices) == 1:
                    return {'status': 'matched', 'match': choices[0]}
                return {'status': 'needs_clarification', 'choices': choices[:5],
                        'question': 'Which artist, album or version did you mean?',
                        'note': 'Ask one short question using these choices. Nothing has been queued.'}
    return {'status': 'not_found',
            'message': 'No confident match was found. Ask for the artist or the exact title. Nothing has been queued.'}
