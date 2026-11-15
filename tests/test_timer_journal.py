"""Timers are written down as they change and started again after a Home Assistant restart."""
import asyncio
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock, patch
import unittest

import test_experience  # noqa: F401 - bootstraps the package like the other suites
from homeassistant.core import CoreState
from custom_components.echo_experience import Experience, timer_journal
from custom_components.echo_experience.core import validate_profiles
from custom_components.echo_experience.timer_journal import TimerJournal, ago

def config():
    return {'devices':[{'id':'kitchen','name':'Kitchen','satellite':'assist_satellite.kitchen','device_id':'dev-kitchen','music_player':'media_player.kitchen','weather':'weather.home','dashboard':'echo-home/kitchen',
        'native':{'satellite':'assist_satellite.ks','device_id':'dev-ks','node':'ks_echo'}}]}

class Manager:
    """The parts of Home Assistant's timer manager the journal and native.start_timer use."""
    def __init__(self):
        self.timers={};self.handlers={'dev-ks':object()};self.started=[];self.paused=[]
    def add(self,id,seconds,name=None,active=True,device='dev-ks'):
        self.timers[id]=NS(id=id,name=name,device_id=device,seconds_left=seconds,is_active=active,created_seconds=seconds)
    def is_timer_device(self,device_id):return device_id in self.handlers
    def start_timer(self,device_id,hours,minutes,seconds,language,name=None):
        total=hours*3600+minutes*60+seconds;new='new%d'%(len(self.started)+1)
        self.started.append((device_id,total,name));self.add(new,total,name,device=device_id);return new
    def pause_timer(self,timer_id):
        self.paused.append(timer_id);self.timers[timer_id].is_active=False

class JournalTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.now=1000.0;self.stored=None;self.manager=Manager();self.tasks=[]
        def task(coro,name=None):
            t=asyncio.ensure_future(coro);self.tasks.append(t);return t
        self.hass=NS(data={},state=CoreState.starting,states=NS(get=lambda e:NS(state='idle')),services=NS(async_call=AsyncMock()),
                     bus=NS(async_listen_once=Mock(return_value=lambda:None)),async_create_task=task,config=NS(language='en'))
        self.runtime=Experience(self.hass,validate_profiles(config()))
        self.runtime.timer_manager=lambda:self.manager
        self.store=NS(async_load=AsyncMock(side_effect=lambda:self.stored),async_save=AsyncMock(side_effect=self.save))
        patch.object(timer_journal,'async_track_time_interval',Mock(return_value=lambda:None)).start();self.addCleanup(patch.stopall)
        self.sleeps=0
    async def save(self,data):self.stored={'timers':[dict(r) for r in data['timers']]}
    async def nap(self,seconds):
        self.sleeps+=1;self.now+=seconds;await asyncio.sleep(0)
    def journal(self):
        return TimerJournal(self.hass,self.runtime,store=self.store,clock=lambda:self.now,sleep=self.nap)
    async def settle(self):
        for t in list(self.tasks):await t

    async def test_running_timers_are_written_down_as_they_change(self):
        j=self.journal();await j.async_start()
        self.assertEqual(self.stored,{'timers':[]})
        self.manager.add('a',600,'pasta');self.manager.add('x',60,device='dev-elsewhere')
        await j.save()
        self.assertEqual(self.stored['timers'],[{'id':'a','profile':'kitchen','device_id':'dev-ks','name':'pasta','is_active':True,'seconds_left':600,'ends_at':1600.0,'created_seconds':600}])
        saves=self.store.async_save.await_count
        self.now=1100;self.manager.timers['a'].seconds_left=500;await j.save()
        self.assertEqual(self.store.async_save.await_count,saves,'the same timer a little later is not a change')
        self.manager.timers['a'].seconds_left=560;await j.save()
        self.assertEqual(self.stored['timers'][0]['ends_at'],1660.0,'a minute added is')
        self.manager.timers['a'].is_active=False;await j.save()
        self.assertEqual((self.stored['timers'][0]['is_active'],self.stored['timers'][0]['ends_at']),(False,None))
        del self.manager.timers['a'];await j.save()
        self.assertEqual(self.stored['timers'],[])

    async def test_a_restart_brings_running_and_paused_timers_back_with_the_time_left(self):
        self.stored={'timers':[{'id':'a','profile':'kitchen','device_id':'dev-ks','name':'pasta','is_active':True,'seconds_left':600,'ends_at':1000.0+3725,'created_seconds':3900},
                               {'id':'b','profile':'kitchen','device_id':'dev-ks','name':None,'is_active':False,'seconds_left':90,'ends_at':None,'created_seconds':120}]}
        self.now=1100.0
        j=self.journal();await j.async_start();await self.settle()
        self.assertEqual(self.manager.started,[('dev-ks',3625,'pasta'),('dev-ks',90,None)])
        self.assertEqual(self.manager.paused,['new2'])
        self.assertEqual(sorted(r['id'] for r in self.stored['timers']),['new1','new2'],'the journal now holds the new timers')
        self.hass.services.async_call.assert_not_awaited()

    async def test_timers_wait_for_the_echo_to_come_back(self):
        self.stored={'timers':[{'id':'a','profile':'kitchen','device_id':'dev-ks','name':'pasta','is_active':True,'seconds_left':600,'ends_at':2000.0,'created_seconds':600}]}
        self.manager.handlers.clear()
        async def nap(seconds):
            self.sleeps+=1;self.now+=seconds
            if self.sleeps==3:self.manager.handlers['dev-ks']=object()
            await asyncio.sleep(0)
        j=TimerJournal(self.hass,self.runtime,store=self.store,clock=lambda:self.now,sleep=nap)
        await j.async_start();await asyncio.sleep(0)
        self.assertEqual(self.stored['timers'][0]['id'],'a','still journalled while it waits') if self.stored else None
        await self.settle()
        self.assertEqual(self.manager.started,[('dev-ks',985,'pasta')],'fifteen seconds were spent waiting')

    async def test_gives_up_when_the_echo_never_returns(self):
        self.stored={'timers':[{'id':'a','profile':'kitchen','device_id':'dev-ks','name':'pasta','is_active':True,'seconds_left':600,'ends_at':9000.0,'created_seconds':600}]}
        self.manager.handlers.clear()
        j=self.journal()
        with self.assertLogs(timer_journal._LOGGER,'WARNING') as logs:
            await j.async_start();await self.settle()
        self.assertEqual(self.manager.started,[]);self.assertEqual(self.stored,{'timers':[]})
        self.assertIn('pasta',logs.output[-1])

    async def test_a_timer_that_ran_out_while_down_is_announced_not_restarted(self):
        self.stored={'timers':[{'id':'a','profile':'kitchen','device_id':'dev-ks','name':'pasta','is_active':True,'seconds_left':60,'ends_at':1000.0,'created_seconds':600},
                               {'id':'old','profile':'kitchen','device_id':'dev-ks','name':'eggs','is_active':True,'seconds_left':60,'ends_at':1000.0-7200,'created_seconds':600}]}
        self.now=1000.0+185
        j=self.journal()
        with self.assertLogs(timer_journal._LOGGER,'WARNING'):
            await j.async_start();await self.settle()
        self.assertEqual(self.manager.started,[])
        self.hass.services.async_call.assert_awaited_once_with('assist_satellite','announce',{'entity_id':'assist_satellite.ks','message':'Your pasta timer finished 3 minutes ago, while Home Assistant was restarting.'},blocking=False)

    async def test_a_reload_restores_nothing(self):
        self.stored={'timers':[{'id':'gone','profile':'kitchen','device_id':'dev-ks','name':'pasta','is_active':True,'seconds_left':600,'ends_at':5000.0,'created_seconds':600}]}
        self.hass.state=CoreState.running
        self.manager.add('a',300,'tea')
        j=self.journal();await j.async_start();await self.settle()
        self.assertEqual(self.manager.started,[])
        self.assertEqual([r['id'] for r in self.stored['timers']],['a'])

    async def test_shutdown_writes_once_more_and_then_leaves_the_journal_alone(self):
        j=self.journal();await j.async_start()
        self.manager.add('a',600,'pasta')
        await j.stopping()
        self.assertEqual([r['id'] for r in self.stored['timers']],['a'])
        self.manager.timers.clear();await j.save();j.schedule()
        self.assertEqual([r['id'] for r in self.stored['timers']],['a'],'whatever shutdown does to the timers is not written')

    async def test_one_timer_that_cannot_come_back_does_not_stop_the_others(self):
        self.stored={'timers':[{'id':'a','profile':'kitchen','device_id':'dev-ks','name':'bad','is_active':True,'seconds_left':600,'ends_at':5000.0,'created_seconds':600},
                               {'id':'b','profile':'kitchen','device_id':'dev-ks','name':'good','is_active':True,'seconds_left':600,'ends_at':5000.0,'created_seconds':600}]}
        real=self.manager.start_timer
        def start(device_id,hours,minutes,seconds,language,name=None):
            if name=='bad':raise RuntimeError('no')
            return real(device_id,hours,minutes,seconds,language,name)
        self.manager.start_timer=start
        j=self.journal()
        with self.assertLogs(timer_journal._LOGGER,'WARNING'):
            await j.async_start();await self.settle()
        self.assertEqual([s[2] for s in self.manager.started],['good'])

    def test_ago(self):
        self.assertEqual([ago(s) for s in (5,60,95,185,3000)],['less than a minute ago','a minute ago','2 minutes ago','3 minutes ago','50 minutes ago'])

if __name__=='__main__':unittest.main()
