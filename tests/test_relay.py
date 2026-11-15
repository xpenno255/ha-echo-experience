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
        self.hass.services.async_call.assert_awaited_once_with('esphome','ks_echo_vs_show',{'prompt':'what is the weather','speak':True,'pipeline':1,'duration':15},blocking=True,context=unittest.mock.ANY)
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

    # ---- misheard "stop timer"
    def with_timer(self,running=True,ringing=False):
        self.runtime.timers=Mock(return_value=[{'id':'t1','name':'Timer'}] if running else [])
        self.runtime.ringing_timers=Mock(return_value=[{'id':'t2','name':'Pasta'}] if ringing else [])
    async def test_misheard_timer_stop_is_sent_plainly_while_a_timer_runs(self):
        self.with_timer()
        for heard in ('Stop time, Matt.','Stop Tomer.','Stop, Toma.','stop the tima','stop tim','stop the time','stop timer','stop timer now please'):
            with self.subTest(heard=heard):
                self.hass.services.async_call.reset_mock()
                await self.relay.process(self.turn(heard))
                self.assertEqual(self.hass.services.async_call.await_args.args[2]['prompt'],'Stop the timer.')
        self.runtime.stop_route.handle.assert_not_awaited()
    async def test_any_stop_goes_to_the_stop_route_while_an_alarm_sounds(self):
        self.with_timer(running=True,ringing=True)
        for heard in ('Stop Tomer.','stop the timer','stop the pasta timer','stop the alarm','Stop, Matt.'):
            with self.subTest(heard=heard):
                self.runtime.stop_route.handle.reset_mock()
                result=await self.relay.process(self.turn(heard))
                self.runtime.stop_route.handle.assert_awaited_once()
                self.assertEqual(result.response.speech['plain']['speech'],'Stopped.')
        self.hass.services.async_call.assert_not_awaited()
    async def test_misheard_timer_stop_is_sent_plainly_when_the_route_finds_nothing_sounding(self):
        self.with_timer(running=False,ringing=True)
        self.runtime.stop_route.handle=AsyncMock(return_value=None)
        await self.relay.process(self.turn('Stop Tomer.'))
        self.assertEqual(self.hass.services.async_call.await_args.args[2]['prompt'],'Stop the timer.')
    async def test_plain_and_music_stops_never_reach_the_model(self):
        self.with_timer()
        for heard in ('Stop, Stop!','So, stop.','stop it','stop that','Stop it please.','Alexa, stop','No, stop!','stop talking','stop the radio','stop playing','Stop the song.'):
            with self.subTest(heard=heard):
                self.runtime.stop_route.handle.reset_mock()
                await self.relay.process(self.turn(heard))
                self.runtime.stop_route.handle.assert_awaited_once()
        self.hass.services.async_call.assert_not_awaited()
    async def test_misheard_timer_stop_is_left_alone_without_a_timer(self):
        self.with_timer(running=False)
        await self.relay.process(self.turn('Stop time, Matt.'))
        self.assertEqual(self.hass.services.async_call.await_args.args[2]['prompt'],'Stop time, Matt.')
    async def test_other_stop_phrases_are_not_taken_for_the_timer(self):
        self.with_timer()
        for heard in ('stop mama','stop tuna','stop to','stop the musik','stop the alarm','stop the kitchen lights','next up stop'):
            with self.subTest(heard=heard):
                self.assertFalse(relay_module.sounds_like_timer_stop(heard))
                self.hass.services.async_call.reset_mock()
                await self.relay.process(self.turn(heard))
                self.assertEqual(self.hass.services.async_call.await_args.args[2]['prompt'],heard)
    async def test_fallback_agent_gets_the_plain_timer_stop(self):
        self.with_timer();self.states['assist_satellite.ks']=NS(state='unavailable')
        with patch('homeassistant.components.conversation.async_converse',AsyncMock(return_value='x')) as conv:
            await self.relay.process(self.turn('Stop Tomer.'))
        self.assertEqual(conv.await_args.args[1],'Stop the timer.')

    # ---- the wake word sent with the request
    async def test_wake_word_in_front_is_taken_off_before_the_echo_gets_the_request(self):
        for heard,sent in (('Alexa, set a 2 minute timer.','Set a 2 minute timer.'),(' Alexa set a 2 minute timer','Set a 2 minute timer'),('ALEXA! What is the weather?','What is the weather?'),
                           ('Alexa. Alexa, play the radio','Alexa, play the radio'),('Is Alexa listening?','Is Alexa listening?'),('Alexander the Great','Alexander the Great'),("Let's set a timer","Let's set a timer")):
            with self.subTest(heard=heard):
                self.hass.services.async_call.reset_mock()
                await self.relay.process(self.turn(heard))
                self.assertEqual(self.hass.services.async_call.await_args.args[2]['prompt'],sent)
    async def test_wake_word_then_stop_is_a_stop(self):
        for heard in ('Alexa, stop.','Alexa stop the music','Alexa. Stop, stop!'):
            with self.subTest(heard=heard):
                self.runtime.stop_route.handle.reset_mock()
                await self.relay.process(self.turn(heard))
                self.assertEqual(self.runtime.stop_route.handle.await_args.kwargs['text'].casefold()[:4],'stop')
        self.hass.services.async_call.assert_not_awaited()
    async def test_wake_word_then_misheard_timer_stop_is_sent_plainly(self):
        self.with_timer()
        await self.relay.process(self.turn('Alexa, stop Tomer.'))
        self.assertEqual(self.hass.services.async_call.await_args.args[2]['prompt'],'Stop the timer.')
    async def test_the_wake_word_alone_ends_quietly(self):
        for heard in ('Alexa.','Alexa?',' alexa '):
            with self.subTest(heard=heard):
                result=await self.relay.process(self.turn(heard))
                self.assertEqual(result.response.speech['plain']['speech'],'')
        self.hass.services.async_call.assert_not_awaited();self.runtime.stop_route.handle.assert_not_awaited()
    async def test_wake_words_come_from_the_profile(self):
        self.runtime=Experience(self.hass,validate_profiles(config(relay={'wake_words':['computer','hey jarvis']})));self.runtime.device_of=lambda e:{PE:'dev-pe'}.get(e)
        relay=Relay(self.hass,self.runtime)
        for heard,sent in (('Computer, lights on','Lights on'),('Hey Jarvis, lights on','Lights on'),('Alexa, lights on','Alexa, lights on')):
            with self.subTest(heard=heard):
                await relay.process(self.turn(heard))
                self.assertEqual(self.hass.services.async_call.await_args.args[2]['prompt'],sent)

    # ---- hand-off
    def services(self,show):
        """vs_show answers from the given list in turn (an exception is raised); every other service succeeds."""
        calls=[]
        async def call(domain,service,data,**kw):
            calls.append(service)
            if service.endswith('vs_show'):
                outcome=show.pop(0)
                if isinstance(outcome,Exception):raise outcome
                if outcome=='hang':await asyncio.sleep(60)
        self.hass.services.async_call=AsyncMock(side_effect=call)
        return calls
    async def test_no_answer_from_the_echo_is_said_on_the_input_satellite(self):
        calls=self.services(['hang'])
        with patch.object(relay_module,'HANDOFF_TIMEOUT',0.01),self.assertLogs(relay_module._LOGGER,'WARNING'):
            result=await self.relay.process(self.turn('set a timer for five minutes'))
        self.assertEqual(result.response.speech['plain']['speech'],"Sorry, I couldn't reach the Kitchen. Please try again.")
        self.assertEqual(calls,['ks_echo_vs_show'],'a request that may have arrived is not offered twice')
    async def test_a_turn_on_screen_is_interrupted_for_the_new_request(self):
        calls=self.services([RuntimeError('a turn is on screen'),RuntimeError('a turn is on screen'),None])
        with patch.object(relay_module,'INTERRUPT_PAUSE',0):
            result=await self.relay.process(self.turn('what is the weather'))
        self.assertEqual(calls,['ks_echo_vs_show','ks_echo_vs_cancel','ks_echo_vs_show','ks_echo_vs_show'])
        self.assertEqual(result.response.speech['plain']['speech'],'')
    async def test_an_echo_that_keeps_refusing_is_said_on_the_input_satellite(self):
        calls=self.services([RuntimeError('Voice Satellite is off')]*4)
        with patch.object(relay_module,'INTERRUPT_PAUSE',0),self.assertLogs(relay_module._LOGGER,'WARNING'):
            result=await self.relay.process(self.turn('what is the weather'))
        self.assertEqual(calls.count('ks_echo_vs_show'),4);self.assertEqual(calls.count('ks_echo_vs_cancel'),1)
        self.assertIn("couldn't reach the Kitchen",result.response.speech['plain']['speech'])

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

    # ---- the wake word quietens the Echo
    def voice(self,state):
        return patch.object(relay_module.native,'voice_state',lambda hass,ident:NS(state=state) if state else None)
    async def test_wake_word_ends_the_answer_the_echo_is_speaking(self):
        cue=WakeCue(self.hass,Experience(self.hass,validate_profiles(config(relay={'wake_cue':False}))))
        for state in ('responding','processing'):
            with self.subTest(state=state),self.voice(state):
                self.hass.services.async_call.reset_mock();cue.runtime.hushed.clear()
                await self.changed(cue,'idle','listening');await asyncio.sleep(0)
                self.hass.services.async_call.assert_awaited_once_with('esphome','ks_echo_vs_cancel',{},blocking=True)
                self.assertIn('kitchen',cue.runtime.hushed)
    async def test_wake_word_leaves_a_quiet_echo_and_a_sounding_alarm_alone(self):
        cue=WakeCue(self.hass,Experience(self.hass,validate_profiles(config(relay={'wake_cue':False}))))
        for state in ('idle',None,'unavailable'):
            with self.subTest(state=state),self.voice(state):
                await self.changed(cue,'idle','listening');await asyncio.sleep(0)
        cue.runtime.ringing_timers=Mock(return_value=[{'id':'t','name':'Pasta'}])
        with self.voice('responding'):
            await self.changed(cue,'idle','listening');await asyncio.sleep(0)
        self.hass.services.async_call.assert_not_awaited();self.assertEqual(cue.runtime.hushed,{})
    async def test_only_input_satellites_quieten_the_echo(self):
        cue=WakeCue(self.hass,self.runtime)
        with self.voice('responding'):
            await self.changed(cue,'idle','listening',entity='assist_satellite.other');await asyncio.sleep(0)
        self.hass.services.async_call.assert_not_awaited()
    async def test_stop_after_a_hush_is_told_to_the_stop_route_once(self):
        self.runtime.hushed['kitchen']=relay_module.time.monotonic()
        await self.relay.process(self.turn('Alexa, stop.'))
        self.assertTrue(self.runtime.stop_route.handle.await_args.kwargs['hushed'])
        await self.relay.process(self.turn('stop'))
        self.assertFalse(self.runtime.stop_route.handle.await_args.kwargs['hushed'],'the next turn starts clean')
    async def test_an_old_hush_or_one_used_by_another_request_does_not_count(self):
        self.runtime.hushed['kitchen']=relay_module.time.monotonic()-relay_module.HUSH_WINDOW-1
        await self.relay.process(self.turn('stop'))
        self.assertFalse(self.runtime.stop_route.handle.await_args.kwargs['hushed'])
        self.runtime.hushed['kitchen']=relay_module.time.monotonic()
        await self.relay.process(self.turn('what is the weather'))
        self.assertEqual(self.runtime.hushed,{})

    # ---- validation and ducking
    def test_defaults_and_validation(self):
        p=validate_profiles({'devices':[{k:v for k,v in config()['devices'][0].items() if k!='input_satellites'}]})['devices'][0]
        self.assertEqual((p['input_satellites'],p['relay']),([],{'pipeline':1,'duration':15,'wake_cue':True,'wake_words':['alexa'],'fallback_agent':'conversation.home_assistant'}))
        for bad in ({'input_satellites':['light.x']},{'input_satellites':'x'},{'input_satellites':['assist_satellite.kitchen']},{'input_satellites':[PE,PE]},
                    {'relay':{'pipeline':True}},{'relay':{'duration':-1}},{'relay':{'wake_cue':'yes'}},{'relay':{'fallback_agent':'x'}},{'relay':[]},{'relay':{'wake_words':'alexa'}},{'relay':{'wake_words':['']}}):
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
