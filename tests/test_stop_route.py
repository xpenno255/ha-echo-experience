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
from custom_components.echo_experience.stop_route import StopRoute, COMMANDS, REPLY_TIMER, REPLY_UNCONFIRMED, REPLY_STOPPED, REPLY_NO_TARGET

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
