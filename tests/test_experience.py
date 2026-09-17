import asyncio
import copy
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('custom_components.echo_experience',ROOT/'custom_components/echo_experience/__init__.py',submodule_search_locations=[str(ROOT/'custom_components/echo_experience')])
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
from custom_components.echo_experience.core import convert,route_profile,validate_profiles,normalize_timer_name
from custom_components.echo_experience import Experience, TIMER_DATA

def profiles():
 return [{'id':name,'name':name,'satellite':'assist_satellite.'+name,'device_id':'device-'+name,'music_player':'media_player.'+name,'weather':'weather.home','dashboard':'echo-home/'+name} for name in ['kitchen','bedroom']]

class CoreTest(unittest.TestCase):
 def test_profiles_are_independent(self):
  p=validate_profiles({'devices':profiles()})['devices']
  self.assertEqual(route_profile(p,device_id='device-bedroom')['id'],'bedroom')
  self.assertIsNone(route_profile(p,device_id='unknown'))
  self.assertIsNone(route_profile(p))
  self.assertIsNone(route_profile(p,device_id='device-bedroom',satellite='assist_satellite.kitchen'))
 def test_timer_name_suffix(self):
  self.assertEqual(normalize_timer_name(' Check Timer '),normalize_timer_name('check'))
  self.assertNotEqual(normalize_timer_name('tea'),normalize_timer_name('steak'))
 def test_duplicate_device_rejected(self):
  p=profiles();p[1]['device_id']=p[0]['device_id']
  with self.assertRaises(ValueError):validate_profiles({'devices':p})
 def test_conversions(self):
  self.assertAlmostEqual(convert(350,'fahrenheit','celsius')['result'],176.6666667,places=5)
  self.assertEqual(convert(.5,'l','ml')['result'],500)
  self.assertAlmostEqual(convert(250,'g','oz')['result'],8.81849,places=4)
  self.assertNotEqual(convert(1,'uk pint','ml')['result'],convert(1,'us pint','ml')['result'])
 def test_ambiguous_unsafe_conversions(self):
  for args in [(1,'cup','g'),(1,'ml','g'),(float('nan'),'g','oz'),(-274,'c','f')]:
   with self.assertRaises(ValueError):convert(*args)

class RuntimeTest(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.profiles=validate_profiles({'devices':profiles()})['devices']
  self.hass=NS(data={},states=NS(get=Mock(return_value=NS(state='idle',attributes={})),is_state=Mock(return_value=False)),bus=NS(async_fire=Mock()),services=NS(async_call=AsyncMock()))
  self.runtime=Experience(self.hass,{'devices':self.profiles})
 async def test_display_event_is_scoped(self):
  await self.runtime.publish(self.profiles[1],'answer',{'equation':'2+2=4'},wake=False)
  self.assertNotIn('kitchen',self.runtime.results)
  self.assertEqual(self.hass.bus.async_fire.call_args.args[1]['device'],'bedroom')
 async def test_foreign_timer_cannot_be_cancelled(self):
  manager=NS(timers={'timer-bedroom':NS(device_id='device-bedroom')},cancel_timer=Mock())
  self.hass.data[TIMER_DATA]=manager
  with self.assertRaises(ValueError):await self.runtime.execute(self.profiles[0],'timer',{'operation':'cancel','timer_id':'timer-bedroom'})
  manager.cancel_timer.assert_not_called()
 async def test_timer_snapshot_uses_actual_paused_state(self):
  def timer(dev,active,sec):return NS(id=dev,name='Pasta',device_id=dev,seconds_left=sec,created_seconds=600,is_active=active)
  self.hass.data[TIMER_DATA]=NS(timers={'a':timer('device-kitchen',False,417),'b':timer('device-bedroom',True,10)})
  result=self.runtime.timers(self.profiles[0])
  self.assertEqual(len(result),1);self.assertEqual(result[0]['seconds_left'],417);self.assertFalse(result[0]['is_active'])
 async def test_timer_duration_uses_service_units_and_checks_creation(self):
  manager=NS(timers={})
  self.hass.data[TIMER_DATA]=manager
  with self.assertRaisesRegex(ValueError,'did not create'):
   await self.runtime.execute(self.profiles[0],'timer',{'operation':'start','name':'Pasta','seconds':3723})
  data=self.hass.services.async_call.call_args.args[2]
  self.assertEqual((data['hours'],data['minutes'],data['seconds']),(1,2,3))
 async def test_namespaced_tool_keeps_guide_view(self):
  import time
  self.runtime.results['kitchen']={'view':'guide','payload':{'appliance_id':'microwave'},'timestamp':time.time()}
  self.runtime.chat(NS(data={'entity_id':'assist_satellite.kitchen','tts_text':'Verified answer','tool_calls':[{'name':'echo-experience__query_home_documents'}]}))
  self.assertEqual(self.runtime.results['kitchen']['view'],'guide')
  self.assertEqual(self.runtime.results['kitchen']['payload']['speech'],'Verified answer')
 async def test_music_speaker_whitelist(self):
  with self.assertRaises(ValueError):await self.runtime.music(self.profiles[0],{'action':'pause','speaker':'media_player.bedroom'})
  self.hass.services.async_call.assert_not_called()
 async def test_foreign_chat_ignored(self):
  self.runtime.chat(NS(data={'entity_id':'assist_satellite.unknown','tts_text':'hello'}))
  self.hass.bus.async_fire.assert_not_called()
 async def test_conversion_event_does_not_leak(self):
  await self.runtime.execute(self.profiles[0],'convert',{'value':1,'from_unit':'kg','to_unit':'g'})
  self.assertNotIn('bedroom',self.runtime.results)
  self.assertEqual(self.runtime.results['kitchen']['payload']['result'],1000)
 async def test_music_request_targets_selected_device(self):
  await self.runtime.music(self.profiles[1],{'action':'pause'})
  call=self.hass.services.async_call.call_args
  self.assertEqual(call.args[:2],('media_player','media_pause'))
  self.assertEqual(call.args[2]['entity_id'],'media_player.bedroom')

if __name__=='__main__':unittest.main()
