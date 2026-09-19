"""Read-only Music Assistant catalog and a tool-free music advisor."""
import asyncio
import json
import logging
import time

_LOGGER = logging.getLogger(__name__)


class MusicBackend:
    def __init__(self, hass, entry_id, agent_id, context, cache):
        self.hass, self.entry_id, self.agent_id = hass, entry_id, agent_id
        self.context, self.cache = context, cache

    async def catalog(self, kind, artist_uri=None):
        cache_key = (self.entry_id, kind, artist_uri)
        cached = self.cache.get(cache_key)
        if cached and time.monotonic() - cached[0] < 300:
            return cached[1]
        try:
            async with asyncio.timeout(4):
                from homeassistant.components.music_assistant.helpers import get_music_assistant_client
                client = get_music_assistant_client(self.hass, self.entry_id)
                if kind == 'artist':
                    result = await client.music.get_library_artists(limit=1000)
                else:
                    artist = await client.music.get_item_by_uri(artist_uri)
                    method = client.music.get_artist_albums if kind == 'album' else client.music.get_artist_tracks
                    result = await method(artist.item_id, artist.provider, in_library_only=True)
                items = [item.to_dict() for item in result[:2000]]
                self.cache[cache_key] = (time.monotonic(), items)
                return items
        except Exception:
            _LOGGER.warning('Music catalog lookup unavailable for %s', kind, exc_info=True)
            return []

    async def advise(self, payload):
        if not self.agent_id:
            return ''
        try:
            result = await self.hass.services.async_call('conversation', 'process', {
                'agent_id': self.agent_id, 'text': json.dumps(payload, ensure_ascii=False),
                'language': 'en',
            }, blocking=True, return_response=True, context=self.context)
            return result.get('response', {}).get('speech', {}).get('plain', {}).get('speech', '')
        except Exception:
            _LOGGER.warning('Music name advisor unavailable', exc_info=True)
            return ''
