"""Fewer questions, with catalog-verified names and explicit preferences retained."""
import json
import unittest
from unittest.mock import AsyncMock
import test_experience
from test_music import track
from custom_components.echo_experience.music import resolve_music
from custom_components.echo_experience.music_fallback import resolve_with_fallback, parse_advice, select, plausible_name

ARTIST={'name':'Alter Bridge','uri':'library://artist/1'}
ALBUM={'name':'Blackbird','uri':'library://album/1','artists':[ARTIST]}
EMPTY=AsyncMock(return_value={})

class FallbackTest(unittest.IsolatedAsyncioTestCase):
    async def test_spoken_numeric_title_survives_large_artist_catalog(self):
        performer = {'name': 'Stone Sour', 'uri': 'stone-sour'}
        wanted = {'name': '30/30-150', 'uri': 'numeric-track', 'artists': [performer]}
        distractors = [{'name': name, 'uri': str(n), 'artists': [performer]} for n, name in enumerate([
            'Through Glass', 'Come Whatever May', 'Made of Scars', 'Reborn', 'Your God',
            'Sillyworld', 'Socio', '1st Person', 'Cardiff', 'Zzyzx Rd', 'Hell and Consequences',
            'Bother', 'Get Inside', 'Inhale', 'Blue Study', 'Orchids'])]
        async def catalog(kind, uri):
            return [performer] if kind == 'artist' else [*distractors, wanted]
        advisor = AsyncMock(return_value='{"index":0,"confidence":"high"}')
        result = await resolve_with_fallback(EMPTY, catalog, advisor,
            'thirty thirty one fifty', 'track', 'stone sower')
        self.assertEqual(result['match']['uri'], wanted['uri'])
        advisor.assert_called_once()
        self.assertEqual(advisor.call_args.args[0]['request']['media_type'], 'artist')

    def test_short_phonetic_artist_requires_unique_catalog_identity(self):
        reef = {'name': 'Reef', 'uri': 'reef'}
        item, _ = select([reef], 'reeve', 'artist')
        self.assertEqual(item, reef)
        for other in ({'name': 'Reeve', 'uri': 'reeve'}, {'name': 'Reef', 'uri': 'another-reef'}):
            item, _ = select([reef, other], 'reev', 'artist')
            self.assertIsNone(item)
        item, _ = select([{'name': "Slash's Snakepit", 'uri': 'snakepit'}], 'Slash', 'artist')
        self.assertIsNone(item)

    def test_advisor_plausibility_preserves_spoken_letters_numbers_and_titles(self):
        for query, name, kind in [('a sea dee sea', 'AC/DC', 'artist'),
                                 ('thirty thirty one fifty', '30/30-150', 'track'),
                                 ('mews', 'Muse', 'artist'), ('doo ality', 'Duality', 'track'),
                                 ('threw glass', 'Through Glass', 'track')]:
            with self.subTest(query=query):
                self.assertTrue(plausible_name(query, name, kind))

    async def test_confident_advisor_cannot_substitute_unrelated_work(self):
        for query, name, artist, kind in [('Year of the Tiger', 'Vulgar Display of Power', 'Pantera', 'album'),
                                         ('Slash', "It's Five O'Clock Somewhere", "Slash's Snakepit", 'album'),
                                         ('Beggars and Hangers On', 'Back from Cali', 'Slash', 'track')]:
            with self.subTest(query=query):
                performer = {'name': artist, 'uri': 'artist'}
                item = {'name': name, 'uri': 'unrelated', 'artists': [performer]}
                async def catalog(k, uri):
                    return [performer] if k == 'artist' else [item]
                async def search(data):
                    return {kind + 's': [item]} if data['name'] == name else {}
                advisor = AsyncMock(side_effect=[json.dumps({'index': 0, 'confidence': 'high'}),
                    json.dumps({'query': name, 'artist': artist, 'confidence': 'high'})])
                result = await resolve_with_fallback(search, catalog, advisor, query, kind, artist)
                self.assertEqual(result['status'], 'not_found')

    async def test_correction_cannot_replace_unresolved_performer(self):
        advisor = AsyncMock(return_value=json.dumps({'query': 'Sweet Child O Mine',
            'artist': 'Guns N Roses', 'confidence': 'high'}))
        result = await resolve_with_fallback(AsyncMock(return_value={'tracks': [track()]}),
            AsyncMock(return_value=[]), advisor, 'Sweet Child O Mine', 'track', 'Unknown Performer')
        self.assertEqual(result['status'], 'not_found')

    async def test_exact_match_never_calls_advisor_or_catalog(self):
        search=AsyncMock(return_value={'tracks':[track()]});catalog=AsyncMock();advisor=AsyncMock()
        result=await resolve_with_fallback(search,catalog,advisor,'Sweet Child O Mine','track','Guns N Roses')
        self.assertEqual(result['status'],'matched');catalog.assert_not_called();advisor.assert_not_called()

    async def test_actual_mammoth_album_request_with_duplicate_filter(self):
        item={'name':'Mammoth II','uri':'library://album/20','artists':[{'name':'Mammoth'}]}
        result=await resolve_music(AsyncMock(return_value={'albums':[item]}),'Mammoth 2','album','Mammoth','Mammoth 2')
        self.assertEqual(result['match']['uri'],item['uri'])

    async def test_artist_catalog_recovers_typo_without_advisor(self):
        async def catalog(kind,uri):return [ARTIST] if kind=='artist' else [ALBUM]
        advisor=AsyncMock()
        result=await resolve_with_fallback(EMPTY,catalog,advisor,'Blackburd','album','Altar Bridge')
        self.assertEqual(result['match']['uri'],ALBUM['uri']);advisor.assert_not_called()

    async def test_advisor_selects_only_actual_catalog_entry(self):
        async def catalog(kind,uri):return [ARTIST] if kind=='artist' else [ALBUM]
        advisor=AsyncMock(return_value='{"index":0,"confidence":"high"}')
        result=await resolve_with_fallback(EMPTY,catalog,advisor,'Black Bird','album','Alter Bridge')
        self.assertEqual(result['match']['uri'],ALBUM['uri'])
        # A genuinely phonetic title needs the advisor; whitespace itself does not.
        result=await resolve_with_fallback(EMPTY,catalog,advisor,'black birch','album','Alter Bridge')
        self.assertEqual(result['match']['uri'],ALBUM['uri']);advisor.assert_called_once()

    async def test_bad_or_unconfident_agent_output_does_not_play(self):
        async def catalog(kind,uri):return [ARTIST] if kind=='artist' else [ALBUM]
        for output in ['{"index":99,"confidence":"high"}', '{"index":true,"confidence":"high"}',
                       '{"index":0,"confidence":"low"}', '{"uri":"fake://track/1","confidence":"high"}', 'Playing it now']:
            result=await resolve_with_fallback(EMPTY,catalog,AsyncMock(return_value=output),'nothing similar','album','Alter Bridge')
            self.assertEqual(result['status'],'not_found')

    async def test_corrected_name_is_researched_not_played_directly(self):
        async def search(data):return {'artists':[ARTIST]} if data['name']=='Alter Bridge' else {}
        result=await resolve_with_fallback(search,AsyncMock(return_value=[]),
            AsyncMock(return_value='{"query":"Alter Bridge","artist":"","confidence":"high"}'),'altar brij','artist')
        self.assertEqual(result['match']['uri'],ARTIST['uri'])
        self.assertEqual(result['resolution'],'verified_name_correction')

    async def test_invented_corrected_name_fails_validation(self):
        result=await resolve_with_fallback(EMPTY,AsyncMock(return_value=[]),
            AsyncMock(return_value='{"query":"Invented Band","artist":"","confidence":"high"}'),'unknown band','artist')
        self.assertEqual(result['status'],'not_found')

    async def test_artist_already_matched_cannot_be_swapped(self):
        advisor=AsyncMock(return_value='{"query":"Hello","artist":"Unrelated","confidence":"high"}')
        async def catalog(kind,uri):return [ARTIST] if kind=='artist' else []
        result=await resolve_with_fallback(EMPTY,catalog,advisor,'missing','track','Alter Bridge')
        self.assertEqual(result['status'],'not_found')

    async def test_correction_cannot_drop_requested_performer(self):
        async def search(data):return {'tracks':[track()]} if data['name']=='Sweet Child O Mine' else {}
        result=await resolve_with_fallback(search,AsyncMock(return_value=[]),
            AsyncMock(return_value='{"query":"Sweet Child O Mine","artist":"","confidence":"high"}'),
            'swit child','track','Some Other Band')
        self.assertEqual(result['status'],'not_found')

    async def test_correction_cannot_drop_explicit_live_suffix(self):
        async def search(data):return {'tracks':[track()]} if data['name']=='Sweet Child O Mine' else {}
        result=await resolve_with_fallback(search,AsyncMock(return_value=[]),
            AsyncMock(return_value='{"query":"Sweet Child O Mine","artist":"Guns N Roses","confidence":"high"}'),
            'swit child (Live)','track','Guns N Roses')
        self.assertEqual(result['status'],'not_found')

    async def test_two_call_budget(self):
        async def catalog(kind,uri):return [ARTIST] if kind=='artist' else [ALBUM]
        advisor=AsyncMock(return_value='{"confidence":"low"}')
        await resolve_with_fallback(EMPTY,catalog,advisor,'unknown album','album','unknown artist')
        self.assertLessEqual(advisor.call_count,2)

    async def test_timeout_degrades_to_clarification(self):
        advisor=AsyncMock(side_effect=TimeoutError)
        result=await resolve_with_fallback(EMPTY,AsyncMock(return_value=[]),advisor,'unknown','artist')
        self.assertEqual(result['status'],'not_found')

    async def test_standard_edition_and_explicit_live(self):
        search=AsyncMock(return_value={'tracks':[track('live',version='Live'),track('remaster',version='2011 Remaster'),track('original')]})
        result=await resolve_music(search,'Sweet Child O Mine','track','Guns N Roses')
        self.assertEqual(result['match']['uri'],'original')
        result=await resolve_music(search,'Sweet Child O Mine','track','Guns N Roses',version='Live')
        self.assertEqual(result['match']['uri'],'live')

    async def test_deluxe_album_no_question_and_explicit_choice(self):
        deluxe={**ALBUM,'name':'Blackbird (Deluxe Edition)','uri':'deluxe'}
        search=AsyncMock(return_value={'albums':[deluxe,ALBUM]})
        result=await resolve_music(search,'Blackbird','album','Alter Bridge')
        self.assertEqual(result['match']['uri'],ALBUM['uri'])
        result=await resolve_music(search,'Blackbird (Deluxe Edition)','album','Alter Bridge')
        self.assertEqual(result['match']['uri'],'deluxe')

    def test_album_numbers_never_fuzzy_match_other_numbers(self):
        items=[{'name':'Mammoth III','uri':'third','artists':[{'name':'Mammoth'}]}]
        item,pool=select(items,'Mammoth 2','album','Mammoth')
        self.assertIsNone(item);self.assertEqual(pool,[])

    async def test_album_filter_on_track_still_enforced(self):
        result=await resolve_music(AsyncMock(return_value={'tracks':[track()]}),'Sweet Child O Mine','track','Guns N Roses','Wrong Album')
        self.assertEqual(result['status'],'not_found')

    def test_advice_parser_rejects_prose_and_non_object(self):
        self.assertEqual(parse_advice('[]'),{})
        self.assertEqual(parse_advice('Sure! {"index":0,"confidence":"high"}'),{})

class FallbackRoutingTest(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_experience.RuntimeTest.asyncSetUp

    async def test_catalog_fallback_keeps_originating_echo_player(self):
        from unittest.mock import patch
        p=self.profiles[1]
        p.update(music_assistant_entry='bedroom-ma',music_resolver_agent='conversation.resolver')
        self.hass.services.async_call.return_value={}
        with patch.object(test_experience.module, 'MusicBackend') as backend:
            backend.return_value.catalog=AsyncMock(side_effect=[[ARTIST],[ALBUM]])
            backend.return_value.advise=AsyncMock()
            result=await self.runtime.music(p,{'action':'play','query':'Blackburd','media_type':'album','artist':'Altar Bridge'})
            self.assertEqual(backend.call_args.args[1:3],('bedroom-ma','conversation.resolver'))
        play=next(c for c in self.hass.services.async_call.call_args_list if c.args[:2]==('music_assistant','play_media'))
        self.assertEqual(play.args[2]['entity_id'],'media_player.bedroom')
        self.assertEqual(play.args[2]['media_id'],ALBUM['uri'])
        self.assertEqual(result['status'],'request_accepted')
