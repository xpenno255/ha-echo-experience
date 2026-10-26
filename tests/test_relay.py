"""Echo Relay: a listen-only satellite's turn runs on the Echo through vs_show; stop, fallback, cue and validation."""
import asyncio
import copy
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
from custom_components.echo_experience import Experience, relay as relay_module
from custom_components.echo_experience.core import validate_profiles
from custom_components.echo_experience.ducking import DuckingManager
from custom_components.echo_experience.relay import Relay, WakeCue

PE='assist_satellite.pe'
def config(**extra):
    return {'devices':[{'id':'kitchen','name':'Kitchen','satellite':'assist_satellite.kitchen','device_id':'dev-kitchen','music_player':'media_player.kitchen','weather':'weather.home','dashboard':'echo-home/kitchen',
        'native':{'satellite':'assist_satellite.ks','device_id':'dev-ks','node':'ks_echo'},'input_satellites':[PE],
        'ducking':{'players':['media_player.kitchen_a'],'additional_satellites':[PE]},**extra}]}

class RelayTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.states={'assist_satellite.ks':NS(state='idle')}
        self.hass=NS(data={},states=NS(get=lambda e:self.states.get(e)),services=NS(async_call=AsyncMock(),has_service=Mock(return_value=True)),
                     bus=NS(async_fire=Mock(),async_listen=Mock(return_value=lambda:None)),async_create_task=lambda coro,name=None:asyncio.ensure_future(coro))
        self.runtime=Experience(self.hass,validate_profiles(config()))
        self.runtime.device_of=lambda e:{PE:'dev-pe'}.get(e)
        self.runtime.stop_route=NS(handle=AsyncMock(return_value='Stopped.'))
        self.relay=Relay(self.hass,self.runtime)
        relay_module.native._warned.clear()
    def turn(self,text,device_id='dev-pe'):
        return NS(text=text,device_id=device_id,satellite_id=None,language='en',conversation_id='c1',context=NS(user_id=None),extra_system_prompt=None)

    async def test_forwards_to_vs_show_with_empty_speech_and_no_follow_up(self):
        result=await self.relay.process(self.turn('what is the weather'))
        self.hass.services.async_call.assert_awaited_once_with('esphome','ks_echo_vs_show',{'prompt':'what is the weather','speak':True,'pipeline':1,'duration':15},blocking=False,context=unittest.mock.ANY)
        self.assertEqual(result.response.speech['plain']['speech'],'')
        self.assertFalse(result.continue_conversation)
    async def test_relay_settings_are_used(self):
        self.runtime=Experience(self.hass,validate_profiles(config(relay={'pipeline':2,'duration':30})));self.runtime.device_of=lambda e:{PE:'dev-pe'}.get(e)
        await Relay(self.hass,self.runtime).process(self.turn('hi'))
        data=self.hass.services.async_call.await_args.args[2]
        self.assertEqual((data['pipeline'],data['duration']),(2,30))
    async def test_unknown_device_is_not_relayed(self):
        result=await self.relay.process(self.turn('hi',device_id='dev-other'))
        self.hass.services.async_call.assert_not_awaited()
        self.assertFalse(result.continue_conversation)
    async def test_ducking_only_satellite_is_not_an_input(self):
        cfg=config();cfg['devices'][0]['input_satellites']=[]
        self.runtime=Experience(self.hass,validate_profiles(cfg));self.runtime.device_of=lambda e:{PE:'dev-pe'}.get(e)
        self.assertIsNone(self.runtime.profile_for_input('dev-pe'))
    async def test_stop_phrase_is_answered_by_the_stop_route_not_forwarded(self):
        result=await Relay.process(self.relay,self.turn('Stop.'))
        self.runtime.stop_route.handle.assert_awaited_once()
        self.hass.services.async_call.assert_not_awaited()
        self.assertEqual(result.response.speech['plain']['speech'],'Stopped.')
    async def test_stop_route_declining_forwards_the_phrase(self):
        self.runtime.stop_route.handle=AsyncMock(return_value=None)
        await self.relay.process(self.turn('stop'))
        self.assertEqual(self.hass.services.async_call.await_args.args[2]['prompt'],'stop')
    async def test_echo_unavailable_delegates_to_fallback_agent_once_warned(self):
        self.states['assist_satellite.ks']=NS(state='unavailable')
        sentinel=object()
        with patch('homeassistant.components.conversation.async_converse',AsyncMock(return_value=sentinel)) as conv,self.assertLogs(relay_module.native._LOGGER,'WARNING') as logs:
            self.assertIs(await self.relay.process(self.turn('hi')),sentinel)
            await self.relay.process(self.turn('hi again'))
        self.assertEqual(conv.await_args.kwargs['agent_id'],'conversation.home_assistant')
        self.assertEqual(len(logs.records),1)
        self.hass.services.async_call.assert_not_awaited()
    async def test_missing_vs_show_service_falls_back(self):
        self.hass.services.has_service.return_value=False
        with patch('homeassistant.components.conversation.async_converse',AsyncMock(return_value='x')) as conv:
            await self.relay.process(self.turn('hi'))
        conv.assert_awaited_once()

    # ---- wake cue
    def changed(self,cue,old,new,entity=PE):
        cue.changed(NS(data={'entity_id':entity,'old_state':NS(state=old),'new_state':NS(state=new)}))
        return asyncio.sleep(0)
    async def test_listening_gives_a_chime_toast_once(self):
        cue=WakeCue(self.hass,self.runtime)
        await self.changed(cue,'idle','listening');await asyncio.sleep(0)
        service,data=self.hass.services.async_call.await_args.args[1:3]
        self.assertEqual(service,'ks_echo_notification');self.assertTrue(data['chime']);self.assertEqual(data['icon'],'mdi:microphone')
        self.hass.services.async_call.reset_mock()
        await self.changed(cue,'listening','listening');await self.changed(cue,'listening','idle');await asyncio.sleep(0)
        self.hass.services.async_call.assert_not_awaited()
    async def test_cue_can_be_disabled_and_fails_soft(self):
        cue=WakeCue(self.hass,Experience(self.hass,validate_profiles(config(relay={'wake_cue':False}))))
        self.assertEqual(cue.owners,{})
        cue=WakeCue(self.hass,self.runtime)
        self.hass.services.async_call.side_effect=RuntimeError('boom')
        await cue.cue(self.runtime.profiles[0])
    async def test_cue_skipped_when_echo_is_down(self):
        self.states['assist_satellite.ks']=NS(state='unavailable')
        await WakeCue(self.hass,self.runtime).cue(self.runtime.profiles[0])
        self.hass.services.async_call.assert_not_awaited()

    # ---- validation and ducking
    def test_defaults_and_validation(self):
        p=validate_profiles({'devices':[{k:v for k,v in config()['devices'][0].items() if k!='input_satellites'}]})['devices'][0]
        self.assertEqual((p['input_satellites'],p['relay']),([],{'pipeline':1,'duration':15,'wake_cue':True,'fallback_agent':'conversation.home_assistant'}))
        for bad in ({'input_satellites':['light.x']},{'input_satellites':'x'},{'input_satellites':['assist_satellite.kitchen']},{'input_satellites':[PE,PE]},
                    {'relay':{'pipeline':True}},{'relay':{'duration':-1}},{'relay':{'wake_cue':'yes'}},{'relay':{'fallback_agent':'x'}},{'relay':[]}):
            with self.assertRaises(ValueError,msg=bad):validate_profiles(config(**bad))
    def test_input_satellite_cannot_belong_to_two_profiles(self):
        cfg=config();other=copy.deepcopy(cfg['devices'][0]);other.update(id='bed',satellite='assist_satellite.bed',device_id='dev-bed');other.pop('native');other.pop('ducking');cfg['devices'].append(other)
        with self.assertRaises(ValueError):validate_profiles(cfg)
    def test_input_satellite_is_a_ducking_source_once(self):
        manager=DuckingManager(self.hass,self.runtime.profiles,store=NS())
        self.assertEqual(len(manager.sources[PE]),1)
        cfg=config();cfg['devices'][0]['ducking']['additional_satellites']=[]
        self.assertIn(PE,DuckingManager(self.hass,validate_profiles(cfg)['devices'],store=NS()).sources)

if __name__=='__main__':unittest.main()
