"""Resolution must tolerate speech formatting without silently playing a cover."""
import unittest
from unittest.mock import AsyncMock
import test_experience
from custom_components.echo_experience.music import resolve_music, key


def track(uri='library://track/339', artist='Guns N’ Roses', album='Appetite for Destruction', version=''):
    return {'uri':uri, 'name':'Sweet Child O’ Mine', 'artists':[{'name':artist}],
            'album':{'name':album}, 'version':version}


class ResolverTest(unittest.IsolatedAsyncioTestCase):
    async def test_punctuation_case_and_spoken_alias(self):
        for title, artist in [('sweet child o mine','Guns N Roses'),
                              ("Sweet Child O' Mine", "Guns N' Roses"),
                              ('Sweet Child of Mine','Guns and Roses')]:
            with self.subTest(title=title):
                search=AsyncMock(return_value={'tracks':[track()]})
                result=await resolve_music(search,title,'track',artist)
                self.assertEqual(result['match']['uri'],'library://track/339')

    async def test_alias_retries_normalized_search(self):
        search=AsyncMock(side_effect=[{'tracks':[]},{'tracks':[track()]}])
        result=await resolve_music(search,'Sweet Child of Mine','track','Guns and Roses')
        self.assertEqual(result['status'],'matched')
        data=search.call_args.args[0]
        self.assertEqual((data['name'],data['artist']),('sweet child o mine','guns n roses'))

    async def test_album_number(self):
        item={'uri':'library://album/25','name':'Use Your Illusion II','artists':[{'name':'Guns N’ Roses'}]}
        search=AsyncMock(side_effect=[{'albums':[]},{'albums':[item]}])
        result=await resolve_music(search,'Use Your Illusion two','album','Guns and Roses')
        self.assertEqual(result['match']['uri'],'library://album/25')
        self.assertEqual(search.call_args.args[0]['name'],'use your illusion ii')

    async def test_cover_rejected_when_artist_specified(self):
        search=AsyncMock(return_value={'tracks':[track(artist='Another Band')]})
        result=await resolve_music(search,'Sweet Child O Mine','track','Guns N Roses')
        self.assertEqual(result['status'],'not_found')

    async def test_two_artists_require_clarification(self):
        search=AsyncMock(return_value={'tracks':[track(),track('library://track/2',artist='Another Band')]})
        result=await resolve_music(search,'Sweet Child O Mine','track')
        self.assertEqual(result['status'],'needs_clarification')
        self.assertEqual(len(result['choices']),2)

    async def test_album_and_version_are_respected(self):
        search=AsyncMock(return_value={'tracks':[track(),track('library://track/2',album='Live Era',version='Live')]})
        result=await resolve_music(search,'Sweet Child O Mine','track','Guns N Roses')
        self.assertEqual(result['match']['uri'],'library://track/339')
        result=await resolve_music(search,'Sweet Child O Mine','track','Guns N Roses','Live Era','live')
        self.assertEqual(result['match']['uri'],'library://track/2')

    async def test_provider_fallback_only_after_library(self):
        async def search(data):
            return {'tracks':[] if data['library_only'] else [track()]}
        result=await resolve_music(search,'Sweet Child O Mine','track','Guns N Roses')
        self.assertEqual(result['status'],'matched')

    async def test_artist_type_with_song_and_performer_recovers(self):
        async def search(data):
            return {'tracks': [track()]} if data['media_type'] == ['track'] else {'albums': []}
        result=await resolve_music(search,'Sweet Child of Mine','artist',"Guns N' Roses")
        self.assertEqual(result['status'],'matched')
        self.assertEqual(result['media_type'],'track')
        self.assertEqual(result['match']['uri'],'library://track/339')

    async def test_conflicting_type_does_not_choose_song_over_album(self):
        async def search(data):
            if data['media_type'] == ['track']:return {'tracks':[track()]}
            return {'albums':[{'uri':'library://album/other','name':'Sweet Child O Mine','artists':[{'name':'Guns N Roses'}]}]}
        result=await resolve_music(search,'Sweet Child O Mine','artist','Guns N Roses')
        self.assertEqual(result['status'],'needs_clarification')
        self.assertEqual({c['media_type'] for c in result['choices']},{'track','album'})

    async def test_artist_with_redundant_filter_is_valid(self):
        search=AsyncMock(return_value={'artists':[{'uri':'library://artist/3','name':'Guns N’ Roses'}]})
        result=await resolve_music(search,'Guns and Roses','artist','Guns N Roses')
        self.assertEqual(result['status'],'matched')
        self.assertNotIn('artist',search.call_args.args[0])

    async def test_unknown_type_does_not_guess(self):
        search=AsyncMock()
        self.assertEqual((await resolve_music(search,'Something',None))['status'],'needs_clarification')
        search.assert_not_called()

    def test_no_substring_or_unsafe_fuzzy_matching(self):
        self.assertNotEqual(key('Hello','track'),key('Hello Again','track'))
        self.assertEqual(key('AC/DC','artist'),key('AC DC','artist'))
        self.assertEqual(key('Beyoncé','artist'),key('Beyonce','artist'))
        self.assertNotEqual(key('Guns','artist'),key('Guns N Roses','artist'))


class PlaybackTest(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_experience.RuntimeTest.asyncSetUp
    async def test_resolved_uri_used_on_correct_speaker(self):
        p=self.profiles[1];p['music_assistant_entry']='bedroom-ma'
        self.hass.services.async_call.return_value={'tracks':[track()]}
        result=await self.runtime.music(p,{'action':'play','query':'Sweet Child of Mine','artist':'Guns and Roses','media_type':'track'})
        calls=self.hass.services.async_call.call_args_list
        search=next(c for c in calls if c.args[:2]==('music_assistant','search'))
        play=next(c for c in calls if c.args[:2]==('music_assistant','play_media'))
        self.assertEqual(search.args[2]['config_entry_id'],'bedroom-ma')
        self.assertEqual(play.args[2]['entity_id'],'media_player.bedroom')
        self.assertEqual(play.args[2]['media_id'],'library://track/339')
        self.assertEqual(result['status'],'request_accepted')

    async def test_ambiguous_play_does_not_change_queue(self):
        p=self.profiles[0];p['music_assistant_entry']='kitchen-ma'
        self.hass.services.async_call.return_value={'tracks':[track(),track('library://track/2',artist='Another Artist')]}
        result=await self.runtime.music(p,{'action':'play','query':'Sweet Child O Mine','media_type':'track'})
        self.assertEqual(result['status'],'needs_clarification')
        self.assertFalse(any(c.args[:2]==('music_assistant','play_media') for c in self.hass.services.async_call.call_args_list))

    async def test_search_never_plays(self):
        p=self.profiles[0];p['music_assistant_entry']='kitchen-ma'
        self.hass.services.async_call.return_value={'tracks':[track()]}
        result=await self.runtime.music(p,{'action':'search','query':'Sweet Child O Mine','media_type':'track'})
        self.assertEqual(result['status'],'matched')
        self.assertTrue(all(c.args[:2]==('music_assistant','search') for c in self.hass.services.async_call.call_args_list))

    async def test_actual_failed_play_arguments_recover_correct_type(self):
        p=self.profiles[0];p['music_assistant_entry']='kitchen-ma'
        async def service(domain, action, data, **kwargs):
            if action=='search':
                return {'tracks':[track()]} if data['media_type']==['track'] else {'albums':[]}
        self.hass.services.async_call.side_effect=service
        await self.runtime.music(p,{'action':'play','artist':"Guns N' Roses",'media_type':'artist','query':'Sweet Child of Mine'})
        call=next(c for c in self.hass.services.async_call.call_args_list if c.args[:2]==('music_assistant','play_media'))
        self.assertEqual(call.args[2]['media_id'],'library://track/339')
        self.assertEqual(call.args[2]['media_type'],'track')
        self.assertEqual(call.args[2]['entity_id'],'media_player.kitchen')

    async def test_radio_path_preserved(self):
        await self.runtime.music(self.profiles[0],{'action':'play','query':'BBC Radio 2','media_type':'radio'})
        call=next(c for c in self.hass.services.async_call.call_args_list if c.args[:2]==('music_assistant','play_media'))
        self.assertEqual(call.args[2]['media_id'],'BBC Radio 2')
