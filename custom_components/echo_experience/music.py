"""Conservative music resolution before changing a speaker's queue."""
import re
import unicodedata

# Deliberate spoken aliases, not unrestricted fuzzy matching of unrelated names.
ALIASES = {
    'artist': {'guns and roses': 'guns n roses'},
    'track': {'sweet child of mine': 'sweet child o mine'},
}
NUMBERS = {'two': '2', 'three': '3', 'four': '4', 'five': '5', 'six': '6', 'seven': '7', 'eight': '8', 'nine': '9', 'ten': '10',
           'ii': '2', 'iii': '3', 'iv': '4', 'v': '5', 'vi': '6',
           'vii': '7', 'viii': '8', 'ix': '9', 'x': '10'}
ROMAN = {str(i): word for i, word in enumerate(
    ('ii', 'iii', 'iv', 'v', 'vi', 'vii', 'viii', 'ix', 'x'), 2)}
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


def summary(item):
    return {k: v for k, v in {
        'uri': item['uri'], 'name': item['name'],
        'artist': ', '.join(a['name'] for a in item.get('artists', [])),
        'album': (item.get('album') or {}).get('name', ''),
        'version': item.get('version', ''),
    }.items() if v}


def matches(item, query, kind, artist='', album='', version=''):
    if not item.get('uri') or key(item.get('name', ''), kind) != key(query, kind):
        return False
    if artist and not any(key(a.get('name', ''), 'artist') == key(artist, 'artist')
                          for a in item.get('artists', [])):
        return False
    if album and key((item.get('album') or {}).get('name', ''), 'album') != key(album, 'album'):
        return False
    if version and key(item.get('version', ''), 'version') != key(version, 'version'):
        return False
    return True


async def resolve_music(search, query, kind, artist='', album='', version=''):
    """Search library first; only unambiguous metadata matches can be played.

    `search` is an async callable accepting Music Assistant search service fields.
    No playback or other mutations happen here. Streaming providers are searched
    only if the local library has no matching result.
    """
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
                choices = [summary(item) for item in found.values()]
                if len(choices) == 1:
                    return {'status': 'matched', 'match': choices[0]}
                return {'status': 'needs_clarification', 'choices': choices[:5],
                        'question': 'Which artist, album or version did you mean?',
                        'note': 'Ask one short question using these choices. Nothing has been queued.'}
    return {'status': 'not_found',
            'message': 'No confident match was found. Ask for the artist or the exact title. Nothing has been queued.'}
