"""The built-in voice stop route must keep every guarantee the retired automation gave, with one owner at a time."""
import asyncio
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock, patch
import unittest

ROOT=Path(__file__).resolve().parents[1]
if 'custom_components.echo_experience' not in sys.modules:
    spec=importlib.util.spec_from_file_location('custom_components.echo_experience',ROOT/'custom_components/echo_experience/__init__.py',submodule_search_locations=[str(ROOT/'custom_components/echo_experience')])
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
from custom_components.echo_experience import Experience
from custom_components.echo_experience.core import validate_profiles
from custom_components.echo_experience import stop_route
from custom_components.echo_experience.stop_route import StopRoute, COMMANDS, REPLY_TIMER, REPLY_UNCONFIRMED, REPLY_STOPPED, REPLY_NO_TARGET, stop_kind
from datetime import timedelta

def profiles():
    return validate_profiles({'devices':[
        {'id':'kitchen','name':'Kitchen','satellite':'assist_satellite.kitchen','device_id':'dev-kitchen','music_player':'media_player.kitchen','weather':'weather.home','dashboard':'echo-home/kitchen',
         'speakers':[{'entity_id':'media_player.kitchen','name':'Kitchen Sonos'}],'ducking':{'players':['media_player.kitchen_a'],'additional_satellites':['assist_satellite.companion']}},
        {'id':'bedroom','name':'Bedroom','satellite':'assist_satellite.bedroom','device_id':'dev-bedroom','music_player':'media_player.bedroom','weather':'weather.home','dashboard':'echo-home/bedroom'}]})['devices']

class Registry:
    """Minimal entity/device registries with the fields the route reads."""
    def __init__(self):
        self.entities={}
        self.devices={}
    def async_get(self,key):return self.entities.get(key) or self.devices.get(key)

class RouteTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.hass=NS(data={},states=NS(get=Mock(return_value=NS(state='idle',attributes={})),is_state=Mock(return_value=False)),bus=NS(async_fire=Mock(),async_listen=Mock(return_value=lambda:None)),services=NS(async_call=AsyncMock()))
        self.runtime=Experience(self.hass,{'devices':profiles()})
        self.runtime.device_of=lambda entity_id:{'assist_satellite.companion':'dev-companion'}.get(entity_id)
        self.route=StopRoute(self.hass,self.runtime)
        self.registered=[]
        self.unregistered=Mock()
        def register(sentences,handler):
            self.registered.append((sentences,handler));return self.unregistered
        self.route.register=register
        self.issues={}
        self.patches=[patch.object(stop_route.ir,'async_create_issue',lambda hass,domain,key,**kw:self.issues.__setitem__(key,kw)),
                      patch.object(stop_route.ir,'async_delete_issue',lambda hass,domain,key:self.issues.pop(key,None))]
        for p in self.patches:p.start();self.addCleanup(p.stop)
        self.registry=Registry()
        self.registry.entities['assist_satellite.kitchen']=self.entity('assist_satellite.kitchen','voice_satellite','dev-kitchen')
        patch.object(stop_route.er,'async_get',lambda hass:self.registry).start();self.addCleanup(patch.stopall)
        patch.object(stop_route.dr,'async_get',lambda hass:self.registry).start()
        patch.object(stop_route.dr,'async_get_effective_area_id',lambda hass,device:device.area_id).start()

    @staticmethod
    def entity(entity_id,platform,device_id=None,area_id=None,disabled=False):
        return NS(entity_id=entity_id,platform=platform,domain=entity_id.split('.')[0],device_id=device_id,area_id=area_id,disabled=disabled)

    def legacy(self,on):
        self.hass.data['automation']=NS(entities=[NS(unique_id='1757961047860',entity_id='automation.stop_sonos',is_on=on)])

    def request(self,text,device_id=None,satellite_id=None):
        return NS(text=text,device_id=device_id,satellite_id=satellite_id,context=NS(user_id=None))

    # ---- ownership
    async def test_registers_once_with_the_legacy_phrase_list_when_no_automation(self):
        self.assertTrue(await self.route.async_start())
        self.assertEqual(self.registered[0][0],COMMANDS)
        self.assertEqual(COMMANDS,['stop','stop music','stop sonos','stop the music','stop the sonos','stop playing music','turn off the music','stop sonos in here'])
        self.assertNotIn('legacy_stop_automation',self.issues)
        self.route.stop();self.unregistered.assert_called_once()
    async def test_waits_while_legacy_automation_enabled(self):
        self.legacy(True)
        self.assertFalse(await self.route.async_start())
        self.assertEqual(self.registered,[])
        self.assertEqual(self.issues['legacy_stop_automation']['translation_placeholders']['entity_id'],'automation.stop_sonos')
    async def test_disabled_legacy_automation_hands_over(self):
        self.legacy(False)
        self.assertTrue(await self.route.async_start());self.assertEqual(len(self.registered),1)
    async def test_re_enabled_automation_makes_route_answer_none(self):
        self.legacy(False);await self.route.async_start()
        self.hass.data['automation'].entities[0].is_on=True
        self.assertIsNone(await self.registered[0][1](self.request('stop',device_id='dev-kitchen'),None))
        self.hass.services.async_call.assert_not_called()
    async def test_conflicting_companion_refuses_to_route(self):
        self.runtime.device_of=lambda entity_id:'dev-bedroom'
        self.assertFalse(await self.route.async_start())
        self.assertIn('route_conflict',self.issues);self.assertEqual(self.registered,[])

    # ---- routing
    async def handle(self,text,**origin):
        await self.route.async_start()
        return await self.registered[0][1](self.request(text,**origin),None)
    async def test_bare_stop_dismisses_ringing_alarm_first_and_leaves_music(self):
        self.runtime.dismiss_for_device=AsyncMock(return_value={'status':'dismissed','timers':['Pasta']})
        self.assertEqual(await self.handle('stop',device_id='dev-kitchen'),REPLY_TIMER)
        self.runtime.dismiss_for_device.assert_awaited_once_with('dev-kitchen',profile=self.runtime.profile('kitchen'))
        self.hass.services.async_call.assert_not_called()
    async def test_unconfirmed_dismissal_never_stops_music_or_claims_success(self):
        self.runtime.dismiss_for_device=AsyncMock(return_value={'status':'unconfirmed'})
        self.assertEqual(await self.handle('stop',device_id='dev-kitchen'),REPLY_UNCONFIRMED)
        self.hass.services.async_call.assert_not_called()
    async def test_nothing_ringing_stops_selected_speaker_not_the_default(self):
        self.runtime.dismiss_for_device=AsyncMock(return_value={'status':'not_ringing'})
        self.runtime.music_players['kitchen']='media_player.kitchen_move'
        self.assertEqual(await self.handle('stop',device_id='dev-kitchen'),REPLY_STOPPED)
        call=self.hass.services.async_call.call_args
        self.assertEqual(call.args[:3],('media_player','media_stop',{'entity_id':['media_player.kitchen_move']}));self.assertTrue(call.kwargs['blocking'])
        self.runtime.music_players.clear();self.hass.services.async_call.reset_mock()
        await self.registered[0][1](self.request('stop music',device_id='dev-kitchen'),None)
        self.assertEqual(self.hass.services.async_call.call_args.args[2]['entity_id'],['media_player.kitchen'],'default when nothing selected')
    async def test_stop_reaches_music_started_from_the_sonos_app(self):
        self.hass.states.get=lambda e:{'media_player.kitchen_a':NS(state='playing',attributes={'group_members':['media_player.kitchen_a']})}.get(e,NS(state='idle',attributes={}))
        self.assertEqual(await self.handle('stop music',device_id='dev-kitchen'),REPLY_STOPPED)
        self.assertEqual(self.hass.services.async_call.call_args.args[2]['entity_id'],['media_player.kitchen_a'])
    async def test_explicit_music_phrase_skips_timer_service(self):
        self.runtime.dismiss_for_device=AsyncMock(side_effect=AssertionError('must not be called'))
        self.assertEqual(await self.handle('stop the music',device_id='dev-kitchen'),REPLY_STOPPED)
    async def test_satellite_id_takes_precedence_and_companion_routes_to_its_echo(self):
        self.runtime.dismiss_for_device=AsyncMock(return_value={'status':'not_ringing'})
        self.registry.entities['assist_satellite.companion']=self.entity('assist_satellite.companion','esphome','dev-companion')
        await self.handle('stop',satellite_id='assist_satellite.companion',device_id='dev-other')
        self.assertEqual(self.hass.services.async_call.call_args.args[2]['entity_id'],['media_player.kitchen'])
    async def test_unknown_device_needs_real_area_and_native_sonos_only(self):
        self.registry.devices['dev-guest']=NS(id='dev-guest',area_id='guest')
        self.registry.devices['dev-noarea']=NS(id='dev-noarea',area_id=None)
        self.registry.devices['sonos-dev']=NS(id='sonos-dev',area_id='guest')
        self.registry.entities.update({
            'media_player.guest_sonos':NS(entity_id='media_player.guest_sonos',platform='sonos',domain='media_player',disabled=False,area_id=None,device_id='sonos-dev'),
            'media_player.guest_tv':NS(entity_id='media_player.guest_tv',platform='samsungtv',domain='media_player',disabled=False,area_id='guest',device_id=None),
            'media_player.hall_sonos':NS(entity_id='media_player.hall_sonos',platform='sonos',domain='media_player',disabled=False,area_id='hall',device_id=None),
            'media_player.guest_ma':NS(entity_id='media_player.guest_ma',platform='music_assistant',domain='media_player',disabled=False,area_id='guest',device_id=None)})
        self.runtime.dismiss_for_device=AsyncMock(side_effect=AssertionError('unknown devices have no timers here'))
        self.assertEqual(await self.handle('stop',device_id='dev-guest'),REPLY_STOPPED)
        self.assertEqual(self.hass.services.async_call.call_args.args[2]['entity_id'],['media_player.guest_sonos'])
        self.hass.services.async_call.reset_mock()
        self.assertEqual(await self.registered[0][1](self.request('stop',device_id='dev-noarea'),None),REPLY_NO_TARGET)
        self.assertEqual(await self.registered[0][1](self.request('stop'),None),REPLY_NO_TARGET)
        self.hass.services.async_call.assert_not_called()
    async def test_service_error_is_reported_with_speaker_name(self):
        self.runtime.dismiss_for_device=AsyncMock(return_value={'status':'not_ringing'})
        self.hass.services.async_call=AsyncMock(side_effect=RuntimeError('boom'))
        self.assertEqual(await self.handle('stop music',device_id='dev-kitchen'),"I couldn't stop the music on Kitchen Sonos.")
    async def test_concurrent_origins_are_independent(self):
        self.runtime.dismiss_for_device=AsyncMock(return_value={'status':'not_ringing'})
        started=[];gate=asyncio.Event()
        async def slow(domain,service,data,**kw):
            started.append(data['entity_id']);await gate.wait()
        self.hass.services.async_call=AsyncMock(side_effect=slow)
        await self.route.async_start();handler=self.registered[0][1]
        tasks=[asyncio.ensure_future(handler(self.request('stop music',device_id='dev-kitchen'),None)),asyncio.ensure_future(handler(self.request('stop music',device_id='dev-bedroom'),None))]
        await asyncio.sleep(0);await asyncio.sleep(0)
        self.assertEqual(sorted(map(tuple,started)),[('media_player.bedroom',),('media_player.kitchen',)])
        gate.set();self.assertEqual(await asyncio.gather(*tasks),[REPLY_STOPPED,REPLY_STOPPED])

class RelayVoiceTest(unittest.IsolatedAsyncioTestCase):
    """A stop said to a relay input satellite is spoken by the Echo it feeds; the input satellite stays silent."""
    async def asyncSetUp(self):
        self.up=True
        self.hass=NS(data={},states=NS(get=lambda e:NS(state='idle' if self.up else 'unavailable')),services=NS(async_call=AsyncMock()))
        cfg={'devices':[{'id':'kitchen','name':'Kitchen','satellite':'assist_satellite.kitchen','device_id':'dev-kitchen','music_player':'media_player.kitchen','weather':'weather.home','dashboard':'echo-home/kitchen',
             'native':{'satellite':'assist_satellite.ks','device_id':'dev-ks'},'input_satellites':['assist_satellite.pe']}]}
        self.runtime=Experience(self.hass,validate_profiles(cfg))
        self.runtime.device_of=lambda e:{'assist_satellite.pe':'dev-pe'}.get(e)
        self.route=StopRoute(self.hass,self.runtime)
        self.route.answer=AsyncMock(return_value=REPLY_TIMER)
        self.route.origin_device=lambda user_input:user_input.device_id
    def request(self,device_id):
        return NS(text='stop',device_id=device_id,satellite_id=None,context=NS(user_id=None))
    async def test_input_satellite_outcome_is_announced_on_the_echo(self):
        self.assertEqual(await self.route.handle(self.request('dev-pe'),None),'')
        self.hass.services.async_call.assert_awaited_once_with('assist_satellite','announce',{'entity_id':'assist_satellite.ks','message':REPLY_TIMER,'preannounce':False},blocking=False,context=unittest.mock.ANY)
    async def test_input_satellite_speaks_itself_when_the_echo_is_down(self):
        self.up=False
        self.assertEqual(await self.route.handle(self.request('dev-pe'),None),REPLY_TIMER)
        self.hass.services.async_call.assert_not_awaited()
    async def test_the_echo_itself_answers_normally(self):
        self.assertEqual(await self.route.handle(self.request('dev-ks'),None),REPLY_TIMER)
        self.hass.services.async_call.assert_not_awaited()

class StopOrderTest(unittest.IsolatedAsyncioTestCase):
    """Stop from a relay input: a sounding alarm first, then the answer the Echo is speaking, then the music."""
    async def asyncSetUp(self):
        self.voice=None
        self.hass=NS(data={},states=NS(get=lambda e:NS(state='playing' if e=='media_player.kitchen' else 'idle',attributes={})),services=NS(async_call=AsyncMock(),has_service=Mock(return_value=True)))
        cfg={'devices':[{'id':'kitchen','name':'Kitchen','satellite':'assist_satellite.kitchen','device_id':'dev-kitchen','music_player':'media_player.kitchen','weather':'weather.home','dashboard':'echo-home/kitchen',
             'native':{'satellite':'assist_satellite.ks','device_id':'dev-ks','node':'ks_echo'},'input_satellites':['assist_satellite.pe']}]}
        self.runtime=Experience(self.hass,validate_profiles(cfg))
        self.runtime.device_of=lambda e:{'assist_satellite.pe':'dev-pe'}.get(e)
        self.runtime.dismiss_for_device=AsyncMock(return_value={'status':'not_ringing'})
        self.route=StopRoute(self.hass,self.runtime)
        self.route.owners=self.route.build_owners()
        self.route.origin_device=lambda user_input:user_input.device_id
        patch.object(stop_route.native,'voice_state',lambda hass,ident:self.voice).start();self.addCleanup(patch.stopall)
    def speaking(self,state='responding',ago=5):
        self.voice=NS(state=state,last_changed=stop_route.dt_util.utcnow()-timedelta(seconds=ago))
    async def stop(self,text='stop',device_id='dev-pe'):
        return await self.route.answer(NS(text=text,device_id=device_id,satellite_id=None,context=NS(user_id=None)))
    def called(self):
        return [c.args[1] for c in self.hass.services.async_call.await_args_list]

    async def test_a_sounding_alarm_wins_over_speech_and_music(self):
        self.speaking();self.runtime.dismiss_for_device.return_value={'status':'dismissed','timers':['Pasta']}
        for text in ('stop','Stop, stop!','stop the timer','stop the pasta timer','stop the alarm'):
            with self.subTest(text=text):self.assertEqual(await self.stop(text),REPLY_TIMER)
        self.assertEqual(self.called(),[])
    async def test_stop_ends_the_answer_being_spoken_and_leaves_the_music(self):
        for state in ('responding','processing'):
            with self.subTest(state=state):
                self.hass.services.async_call.reset_mock();self.speaking(state)
                self.assertEqual(await self.stop('Stop, stop!'),'')
                self.assertEqual(self.called(),['ks_echo_vs_cancel'])
    async def test_stop_just_after_the_answer_ended_leaves_the_music(self):
        self.speaking('idle',ago=1)
        self.assertEqual(await self.stop(),'')
        self.assertEqual(self.called(),[])
    async def test_stop_with_the_echo_quiet_stops_the_music(self):
        for voice in (None,NS(state='idle',last_changed=stop_route.dt_util.utcnow()-timedelta(seconds=30)),NS(state='unavailable',last_changed=stop_route.dt_util.utcnow())):
            with self.subTest(voice=voice):
                self.hass.services.async_call.reset_mock();self.voice=voice
                self.assertEqual(await self.stop('stop it please'),REPLY_STOPPED)
                self.assertEqual(self.called(),['media_stop'])
    async def test_a_music_phrase_stops_the_music_even_while_the_echo_speaks(self):
        self.speaking()
        self.assertEqual(await self.stop('stop the radio'),REPLY_STOPPED)
        self.assertEqual(self.called(),['media_stop']);self.runtime.dismiss_for_device.assert_not_awaited()
    async def test_a_running_timer_is_left_to_the_conversation_agent(self):
        self.speaking()
        for text in ('stop the timer','stop timer','stop the pasta timer'):
            with self.subTest(text=text):self.assertIsNone(await self.stop(text))
        self.assertEqual(self.called(),[])
    async def test_a_stop_the_echo_hears_itself_never_cancels_its_own_turn(self):
        self.speaking('processing')
        self.assertEqual(await self.stop(device_id='dev-ks'),REPLY_STOPPED)
        self.assertEqual(self.called(),['media_stop'])
    async def test_stop_whose_wake_word_already_ended_the_answer_leaves_the_music(self):
        self.voice=NS(state='idle',last_changed=stop_route.dt_util.utcnow()-timedelta(seconds=6))
        request=NS(text='Alexa, stop.',device_id='dev-pe',satellite_id=None,context=NS(user_id=None))
        self.assertEqual(await self.route.answer(request,'Stop.',True),'')
        self.assertEqual(self.called(),[])
        self.assertEqual(await self.route.answer(request,'Stop the music.',True),REPLY_STOPPED,'a music phrase still stops the music')
    async def test_the_relay_cleaned_text_decides_not_the_raw_transcript(self):
        request=NS(text='Computer, stop the timer',device_id='dev-pe',satellite_id=None,context=NS(user_id=None))
        self.assertIsNone(await self.route.answer(request,'Stop the timer'))
        self.assertEqual(self.called(),[])
    async def test_an_answer_that_cannot_be_ended_still_leaves_the_music(self):
        self.speaking();self.hass.services.async_call.side_effect=RuntimeError('gone')
        with self.assertLogs(stop_route._LOGGER,'WARNING'):self.assertEqual(await self.stop(),'')
        self.assertEqual(self.called(),['ks_echo_vs_cancel'])

class StopKindTest(unittest.TestCase):
    def test_phrases(self):
        cases={'plain':('stop','Stop.','Stop, Stop!','stop it','stop that please','So, stop.','I stop','Alexa, stop now','No, stop!','stop talking','okay stop thank you'),
               'music':('stop music','stop the radio','stop playing','Stop the song.','please stop the sonos'),
               'named':('stop the timer','stop timer','Stop Tomer.','stop the pasta timer','stop the alarm','stop the kitchen lights','Stop time, Matt.'),
               None:('','turn off the music','next up stop','what is a bus stop','stop the timer and then set a new one for ten minutes','pause')}
        for kind,phrases in cases.items():
            for text in phrases:
                with self.subTest(text=text):self.assertEqual(stop_kind(text),kind)

class MatcherTest(unittest.TestCase):
    """Drive HA's real trigger sentence matcher so the phrase list is proven against hassil, not assumed.

    requirements-dev.txt pins hassil, so CI always runs this; only an ad-hoc local venv without it skips.
    """
    def test_phrases_match_and_named_timer_phrases_do_not(self):
        import os
        try:from hassil import Intents, recognize_all
        except ImportError:
            if os.environ.get('CI'):raise
            self.skipTest('hassil not installed in this local environment')
        intents=Intents.from_dict({'language':'en','intents':{'route':{'data':[{'sentences':COMMANDS}]}}})
        for text in ['stop','stop music','stop the music','turn off the music','stop sonos in here']:
            self.assertTrue(list(recognize_all(text,intents)),text)
        for text in ['stop the timer','stop the pasta timer','stop the alarm','pause the music','stop']:
            hits=[r.intent_sentence.text for r in recognize_all(text,intents)]
            self.assertEqual(bool(hits),text=='stop',(text,hits))

if __name__=='__main__':unittest.main()
