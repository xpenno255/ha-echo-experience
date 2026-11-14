"""A running or ringing timer keeps the Echo's dashboard awake; the integration only ever releases its own hold."""
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
from custom_components.echo_experience import Experience, TIMER_DATA
from custom_components.echo_experience.core import validate_profiles
from custom_components.echo_experience import screen_hold
from custom_components.echo_experience.screen_hold import ScreenHold

HOLD='switch.kitchen_hold'

def profiles():
    base={'weather':'weather.home','speakers':[]}
    return validate_profiles({'devices':[
        {**base,'id':'kitchen','name':'Kitchen','satellite':'assist_satellite.kitchen','device_id':'dev-kitchen','music_player':'media_player.kitchen','dashboard':'echo-home/kitchen','kiosk_hold':HOLD,'speakers':[{'entity_id':'media_player.kitchen','name':'Kitchen'}]},
        {**base,'id':'bedroom','name':'Bedroom','satellite':'assist_satellite.bedroom','device_id':'dev-bedroom','music_player':'media_player.bedroom','dashboard':'echo-home/bedroom','speakers':[{'entity_id':'media_player.bedroom','name':'Bedroom'}]}]})['devices']

class Store:
    def __init__(self,data=None):self.data=data;self.saved=[]
    async def async_load(self):return self.data
    async def async_save(self,data):self.data=data;self.saved.append(data)

class ScreenHoldTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.switch={'state':'off'}
        async def call(domain,service,data,blocking=False):
            self.calls.append((domain,service,data['entity_id']))
            self.switch['state']='on' if service=='turn_on' else 'off'
        self.calls=[]
        self.timers={}
        self.players={}
        self.hass=NS(data={TIMER_DATA:NS(timers=self.timers)},states=NS(get=lambda e:NS(state=self.switch['state']) if e==HOLD else (NS(state=self.players[e],attributes={}) if e in self.players else None)),
                     services=NS(async_call=AsyncMock(side_effect=call)),bus=NS(async_fire=Mock()),async_create_task=asyncio.ensure_future)
        self.runtime=Experience(self.hass,{'devices':profiles()})
        self.kitchen=self.runtime.profiles[0]
        self.store=Store()
        self.hold=ScreenHold(self.hass,self.runtime,store=self.store)
        self.runtime.screen_hold=self.hold

    def timer(self,active=True,device='dev-kitchen'):
        self.timers['t1']=NS(id='t1',name='Pasta',device_id=device,seconds_left=300,created_seconds=600,is_active=active)

    async def settle(self):
        for _ in range(3):await asyncio.sleep(0)

    async def test_running_timer_holds_and_release_follows(self):
        self.timer();self.runtime.timer_event(NS(data={'entity_id':'assist_satellite.kitchen','event_type':'started'}));await self.settle()
        self.assertEqual(self.calls,[('switch','turn_on',HOLD)]);self.assertEqual(self.store.data,{'owned':['kitchen']})
        del self.timers['t1'];self.runtime.timer_event(NS(data={'entity_id':'assist_satellite.kitchen','event_type':'cancelled'}));await self.settle()
        self.assertEqual(self.calls[-1],('switch','turn_off',HOLD));self.assertEqual(self.store.data,{'owned':[]})

    async def test_ringing_alarm_keeps_the_hold_until_dismissed(self):
        self.timer();await self.hold.sync(self.kitchen)
        del self.timers['t1'];self.runtime.timer_event(NS(data={'entity_id':'assist_satellite.kitchen','event_type':'finished','timer_id':'t1','name':'Pasta'}));await self.settle()
        self.assertEqual(self.switch['state'],'on','a finished alarm is still sounding')
        self.runtime.display_report(self.kitchen,{'present':False,'timers':['t1']});await self.settle()
        self.assertEqual(self.switch['state'],'off')

    async def test_paused_and_foreign_timers_do_not_hold(self):
        self.timer(active=False);await self.hold.sync(self.kitchen)
        self.timer(device='dev-bedroom');await self.hold.sync(self.kitchen)
        self.assertEqual(self.calls,[])

    async def test_someone_elses_hold_is_left_alone(self):
        self.switch['state']='on';self.timer();await self.hold.sync(self.kitchen)
        del self.timers['t1'];await self.hold.sync(self.kitchen)
        self.assertEqual(self.calls,[],'a pinned guide keeps its hold');self.assertEqual(self.store.saved,[])

    async def test_hold_released_by_another_owner_is_taken_back_while_a_timer_runs(self):
        self.switch['state']='on';self.timer();await self.hold.sync(self.kitchen)
        self.switch['state']='off';self.hold.hold_changed(NS(data={'entity_id':HOLD,'new_state':NS(state='off')}));await self.settle()
        self.assertEqual(self.calls,[('switch','turn_on',HOLD)])
        del self.timers['t1'];await self.hold.sync(self.kitchen);self.assertEqual(self.switch['state'],'off')

    async def test_stale_hold_from_before_a_restart_is_released(self):
        self.switch['state']='on';self.store.data={'owned':['kitchen']}
        unsubscribe=Mock()
        with patch.object(screen_hold,'async_track_state_change_event',return_value=unsubscribe) as track,patch.object(screen_hold,'async_track_time_interval',return_value=unsubscribe):
            await self.hold.async_start()
        self.assertEqual(track.call_args_list[0].args[1],[HOLD],'only Echoes with a hold switch are watched')
        self.assertEqual(track.call_args_list[1].args[1],['media_player.kitchen'],'and only their speakers')
        self.assertEqual(self.calls,[('switch','turn_off',HOLD)]);self.assertEqual(self.store.data,{'owned':[]})
        self.hold.stop();self.assertEqual(unsubscribe.call_count,3)

    # ---- music
    def music(self,state,entity='media_player.kitchen'):
        self.players[entity]=state
        self.hold.music_changed(NS(data={'entity_id':entity}))

    async def test_playing_music_holds_and_stopping_releases_after_the_grace(self):
        fired=[]
        with patch.object(screen_hold,'async_call_later',side_effect=lambda hass,delay,action:(fired.append(action),Mock())[1]) as later:
            self.music('playing');await self.settle()
            self.assertEqual(self.calls,[('switch','turn_on',HOLD)]);later.assert_not_called()
            self.music('paused');await self.settle()
            self.assertEqual(self.switch['state'],'on','a pause waits for the grace period')
            self.assertEqual(later.call_args.args[1],screen_hold.MUSIC_RELEASE)
            from homeassistant.core import HassJobType, get_hassjob_callable_job_type
            self.assertEqual(get_hassjob_callable_job_type(later.call_args.args[2]),HassJobType.Callback,'the release must run in the event loop, not an executor thread')
            fired[-1](None);await self.settle()
        self.assertEqual(self.calls[-1],('switch','turn_off',HOLD));self.assertEqual(self.store.data,{'owned':[]})

    async def test_track_change_within_the_grace_keeps_the_hold(self):
        cancels=[]
        def later(hass,delay,action):
            cancels.append(Mock());return cancels[-1]
        with patch.object(screen_hold,'async_call_later',side_effect=later):
            self.music('playing');await self.settle()
            self.music('idle');self.music('playing');await self.settle()
        cancels[0].assert_called_once_with()
        self.assertEqual(self.calls,[('switch','turn_on',HOLD)],'no off and on between tracks')

    async def test_music_started_from_another_app_on_a_native_speaker_holds(self):
        self.kitchen['native_players']=['media_player.kitchen_sonos']
        self.players.update({'media_player.kitchen':'idle','media_player.kitchen_sonos':'playing'})
        self.hold.music_changed(NS(data={'entity_id':'media_player.kitchen_sonos'}));await self.settle()
        self.assertEqual(self.calls,[('switch','turn_on',HOLD)])

    async def test_other_rooms_music_and_the_option_off_do_not_hold(self):
        self.players['media_player.bedroom']='playing'
        self.hold.music_changed(NS(data={'entity_id':'media_player.bedroom'}));await self.settle()
        self.kitchen['hold_while_music']=False;self.players['media_player.kitchen']='playing'
        self.hold.music_changed(NS(data={'entity_id':'media_player.kitchen'}));await self.hold.sync(self.kitchen)
        self.assertEqual(self.calls,[])

    async def test_a_guide_pin_survives_the_music_ending(self):
        self.switch['state']='on';self.players['media_player.kitchen']='playing';await self.hold.sync(self.kitchen)
        self.players['media_player.kitchen']='idle';await self.hold.sync(self.kitchen)
        self.assertEqual(self.calls,[],'the integration never owned this hold')

    async def test_unavailable_switch_keeps_ownership_for_a_retry(self):
        self.switch['state']='on';self.timer();self.hold.owned={'kitchen'};del self.timers['t1']
        self.switch['state']='unavailable';await self.hold.sync(self.kitchen)
        self.assertEqual((self.calls,self.hold.owned),([],{'kitchen'}))
        self.switch['state']='on';await self.hold.recheck();self.assertEqual(self.hold.owned,set())

    async def test_failed_switch_call_does_not_claim_the_hold(self):
        self.hass.services.async_call.side_effect=RuntimeError('offline')
        self.timer();await self.hold.sync(self.kitchen)
        self.assertEqual(self.hold.owned,set());self.assertEqual(self.store.saved,[])

if __name__=='__main__':unittest.main()
