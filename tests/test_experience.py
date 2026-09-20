import asyncio
import copy
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock, patch
from homeassistant.exceptions import Unauthorized
import time
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
 def test_distance_voice_aliases(self):
  self.assertAlmostEqual(convert(5.5,'km','mile')['result'],3.4175415573,places=9)
  for a,b in [('millimetre','millimeters'),('centimetre','centimeters'),('metre','meters'),('kilometre','kilometers'),('inch','inches'),('foot','feet'),('yard','yards'),('mile','miles')]:
   with self.subTest(unit=a):self.assertEqual(convert(1,a,b)['result'],1)
  self.assertEqual(convert(1,' Metre ','cm')['result'],100)
  self.assertAlmostEqual(convert(1,'us_cup','ml')['result'],236.5882365)
 def test_unknown_unit_error_identifies_missing_unit(self):
  with self.assertRaisesRegex(ValueError,'Unsupported or ambiguous unit: furlong'):
   convert(1,'furlong','mile')
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
 def finish(self,name='Pasta',timer_id='t1',device='kitchen'):
  # Core pops the timer from manager.timers before Voice Satellite fires its FINISHED bus event.
  self.hass.data.setdefault(TIMER_DATA,NS(timers={},cancel_timer=Mock()))
  self.runtime.timer_event(NS(data={'entity_id':'assist_satellite.'+device,'event_type':'finished','timer_id':timer_id,'name':name,'total_seconds':60,'seconds_left':0,'is_active':True}))
 def report(self,dismissed,present=True,profile=0):
  # Stand in for the Echo's dashboard: answer the dismissal request once it appears on the event bus.
  async def answer():
   for _ in range(50):
    await asyncio.sleep(0)
    requests=[c.args[1]['dismiss']['request'] for c in self.hass.bus.async_fire.call_args_list if 'dismiss' in c.args[1]]
    if requests:
     self.runtime.display_report(self.profiles[profile],{'operation':'dismissed','request':requests[-1],'present':present,'dismissed':dismissed});return
   raise AssertionError('no dismissal request was published')
  self.reporter=asyncio.ensure_future(answer())
 async def test_finished_timer_is_tracked_as_ringing_per_echo(self):
  self.finish()
  self.assertEqual([t['name'] for t in self.runtime.ringing_timers(self.profiles[0])],['Pasta'])
  self.assertEqual(self.runtime.ringing_timers(self.profiles[1]),[])
  self.assertEqual(self.hass.bus.async_fire.call_args.args[1]['ringing'][0]['id'],'t1')
  status=await self.runtime.execute(self.profiles[0],'timer',{'operation':'status'})
  self.assertEqual(status['ringing'][0]['name'],'Pasta');self.assertEqual(status['timers'],[])
 async def test_cancel_while_ringing_dismisses_via_display(self):
  self.finish();self.report(dismissed=True)
  result=await self.runtime.execute(self.profiles[0],'timer',{'operation':'cancel','name':'pasta timer'})
  self.assertEqual(result['status'],'dismissed');self.assertEqual(result['dismissed'],['Pasta'])
  self.assertEqual(self.runtime.ringing_timers(self.profiles[0]),[])
  self.hass.data[TIMER_DATA].cancel_timer.assert_not_called()
  self.assertEqual(self.hass.bus.async_fire.call_args_list[1].args[1]['dismiss']['timers'],[{'id':'t1','name':'Pasta'}])
 async def test_bare_dismiss_without_name_covers_all_ringing_on_this_echo_only(self):
  self.finish('Pasta','t1');self.finish('Eggs','t2');self.finish('Bedroom','t3',device='bedroom');self.report(dismissed=True)
  result=await self.runtime.execute(self.profiles[0],'timer',{'operation':'dismiss'})
  self.assertEqual(sorted(result['dismissed']),['Eggs','Pasta'])
  self.assertEqual([t['name'] for t in self.runtime.ringing_timers(self.profiles[1])],['Bedroom'])
 async def test_unconfirmed_dismissal_is_reported_not_claimed(self):
  self.runtime.dismiss_timeout=0.05
  self.finish()
  with self.assertRaisesRegex(ValueError,'did not confirm'):await self.runtime.execute(self.profiles[0],'timer',{'operation':'cancel'})
  self.assertEqual([t['id'] for t in self.runtime.ringing_timers(self.profiles[0])],['t1'])
  self.assertEqual(self.runtime.dismissals,{})
 async def test_alert_already_gone_clears_ringing_state(self):
  self.finish();self.report(dismissed=False,present=False)
  result=await self.runtime.execute(self.profiles[0],'timer',{'operation':'cancel'})
  self.assertEqual(result['status'],'already_silenced');self.assertEqual(self.runtime.ringing_timers(self.profiles[0]),[])
 async def test_device_side_silence_report_clears_only_listed_ringing(self):
  self.finish('Pasta','t1');self.finish('Eggs','t2')
  self.runtime.display_report(self.profiles[0],{'operation':'dismissed','timers':['t1'],'present':False,'dismissed':False})
  self.assertEqual([t['id'] for t in self.runtime.ringing_timers(self.profiles[0])],['t2'])
  self.assertEqual([t['id'] for t in self.hass.bus.async_fire.call_args.args[1]['ringing']],['t2'])
  fired=self.hass.bus.async_fire.call_count
  self.runtime.display_report(self.profiles[0],{'operation':'dismissed','timers':['t1'],'present':False,'dismissed':False})
  self.assertEqual(self.hass.bus.async_fire.call_count,fired,'an already-forgotten id changes nothing')
 async def test_cross_profile_and_unknown_tokens_are_ignored(self):
  self.runtime.dismiss_timeout=0.05
  self.finish();self.report(dismissed=True,profile=1)
  with self.assertRaisesRegex(ValueError,'did not confirm'):await self.runtime.execute(self.profiles[0],'timer',{'operation':'cancel'})
  self.assertEqual([t['id'] for t in self.runtime.ringing_timers(self.profiles[0])],['t1'],'the bedroom card cannot confirm a kitchen dismissal')
  self.assertEqual(self.runtime.display_report(self.profiles[0],{'operation':'dismissed','request':'nope','present':False,'dismissed':True}),{'status':'ignored'})
  self.assertEqual([t['id'] for t in self.runtime.ringing_timers(self.profiles[0])],['t1'])
 async def test_acknowledgment_clears_only_requested_ids(self):
  self.finish('Pasta','t1')
  async def answer():
   for _ in range(50):
    await asyncio.sleep(0)
    requests=[c.args[1]['dismiss'] for c in self.hass.bus.async_fire.call_args_list if 'dismiss' in c.args[1]]
    if requests:
     self.finish('Eggs','t2')  # finished after the request went out
     self.assertEqual([t['id'] for t in requests[-1]['timers']],['t1'])
     self.runtime.display_report(self.profiles[0],{'operation':'dismissed','request':requests[-1]['request'],'timers':['t1'],'present':True,'dismissed':True});return
   raise AssertionError('no dismissal request was published')
  reporter=asyncio.ensure_future(answer())
  result=await self.runtime.execute(self.profiles[0],'timer',{'operation':'dismiss'})
  await reporter
  self.assertEqual(result['dismissed'],['Pasta'])
  self.assertEqual([t['id'] for t in self.runtime.ringing_timers(self.profiles[0])],['t2'])
 async def test_dismissed_is_not_an_llm_operation(self):
  self.finish()
  with self.assertRaisesRegex(ValueError,'Unsupported timer operation'):await self.runtime.execute(self.profiles[0],'timer',{'operation':'dismissed','present':False,'dismissed':True})
  tool=next(t for t in await self.tools() if t.name=='echo_timer')
  result=await tool.async_call(self.hass,NS(tool_name='echo_timer',tool_args={'operation':'dismissed','present':False,'dismissed':True}),NS(context=None))
  self.assertIn('Invalid arguments',result['error']);self.assertFalse(result['retryable'])
  result=await tool.async_call(self.hass,NS(tool_name='echo_timer',tool_args={'operation':'start','seconds':'soon'}),NS(context=None))
  self.assertIn('Invalid arguments',result['error']);self.hass.services.async_call.assert_not_called()
  self.assertEqual([t['id'] for t in self.runtime.ringing_timers(self.profiles[0])],['t1'])
 async def tools(self):
  self.hass.config_entries=NS(async_entries=Mock(return_value=[]))
  api=module.ExperienceAPI(self.hass,self.runtime)
  return (await api.async_get_api_instance(NS(device_id='device-kitchen'))).tools
 async def test_service_requires_control_of_the_target_satellite(self):
  allowed=NS(permissions=NS(check_entity=Mock(return_value=True)));denied=NS(permissions=NS(check_entity=Mock(return_value=False)))
  self.hass.auth=NS(async_get_user=AsyncMock(return_value=denied))
  with self.assertRaises(Unauthorized):
   await module.dismiss_timer_service(self.hass,self.runtime,NS(data={'device_id':'device-kitchen'},context=NS(user_id='u1')))
  denied.permissions.check_entity.assert_called_once_with('assist_satellite.kitchen',module.POLICY_CONTROL)
  self.hass.auth.async_get_user.return_value=allowed
  self.assertEqual(await module.dismiss_timer_service(self.hass,self.runtime,NS(data={'device_id':'device-kitchen'},context=NS(user_id='u1'))),{'status':'not_ringing'})
  self.hass.auth.async_get_user.return_value=None
  with self.assertRaises(Unauthorized):
   await module.dismiss_timer_service(self.hass,self.runtime,NS(data={'device_id':'device-kitchen'},context=NS(user_id='ghost')))
  self.hass.auth.async_get_user=AsyncMock(side_effect=AssertionError('no lookup without a user'))
  self.assertEqual(await module.dismiss_timer_service(self.hass,self.runtime,NS(data={'device_id':'device-kitchen'},context=NS(user_id=None))),{'status':'not_ringing'})
  self.assertEqual(await module.dismiss_timer_service(self.hass,self.runtime,NS(data={'device_id':'nobody'},context=NS(user_id='u1'))),{'status':'unknown_device'})
 async def test_companion_satellite_routes_to_its_echo(self):
  self.profiles[0]['ducking']={'enabled':True,'players':['media_player.kitchen'],'additional_satellites':['assist_satellite.companion']}
  self.finish('Pasta','t1');self.report(dismissed=True)
  with patch.object(Experience,'device_of',lambda self,e:{'assist_satellite.companion':'device-companion'}.get(e)):
   self.assertEqual(self.runtime.profile_for_device('device-companion')['id'],'kitchen')
   self.assertIsNone(self.runtime.profile_for_device('device-stranger'))
   self.assertEqual(await self.runtime.dismiss_for_device('device-stranger'),{'status':'unknown_device'})
   self.assertEqual(await self.runtime.dismiss_for_device('device-companion'),{'status':'dismissed','timers':['Pasta']})
 async def test_running_timer_cancel_still_works_and_named_ringing_is_separate(self):
  running=NS(id='r1',name='Roast',device_id='device-kitchen',seconds_left=100,created_seconds=600,is_active=True)
  self.hass.data[TIMER_DATA]=NS(timers={'r1':running},cancel_timer=Mock())
  self.finish('Pasta','t1')
  result=await self.runtime.execute(self.profiles[0],'timer',{'operation':'cancel','name':'roast'})
  self.hass.data[TIMER_DATA].cancel_timer.assert_called_once_with('r1');self.assertEqual(result['ringing'][0]['name'],'Pasta')
  with self.assertRaisesRegex(ValueError,'alarm is sounding'):await self.runtime.execute(self.profiles[0],'timer',{'operation':'pause','name':'pasta'})
  with self.assertRaisesRegex(ValueError,'No ringing timer matches'):await self.runtime.execute(self.profiles[0],'timer',{'operation':'dismiss','name':'roast'})
 async def test_dismiss_service_scopes_to_origin_device_and_never_cancels_running(self):
  self.assertEqual(await self.runtime.dismiss_for_device('unknown'),{'status':'unknown_device'})
  self.assertEqual(await self.runtime.dismiss_for_device('device-kitchen'),{'status':'not_ringing'})
  running=NS(id='r1',name='Roast',device_id='device-kitchen',seconds_left=100,created_seconds=600,is_active=True)
  self.hass.data[TIMER_DATA]=NS(timers={'r1':running},cancel_timer=Mock())
  self.assertEqual(await self.runtime.dismiss_for_device('device-kitchen'),{'status':'not_ringing'})
  self.hass.data[TIMER_DATA].cancel_timer.assert_not_called()
  self.finish('Bedroom','t3',device='bedroom');self.finish('Pasta','t1');self.report(dismissed=True)
  result=await self.runtime.dismiss_for_device('device-kitchen')
  self.assertEqual(result,{'status':'dismissed','timers':['Pasta']})
  self.assertEqual([t['name'] for t in self.runtime.ringing_timers(self.profiles[1])],['Bedroom'])
 async def test_stale_ringing_entries_expire(self):
  self.finish()
  self.runtime.ringing['kitchen']['t1']['finished_at']=time.time()-module.RINGING_TTL-1
  self.assertEqual(self.runtime.ringing_timers(self.profiles[0]),[])
 async def test_music_request_targets_selected_device(self):
  await self.runtime.music(self.profiles[1],{'action':'pause'})
  call=self.hass.services.async_call.call_args
  self.assertEqual(call.args[:2],('media_player','media_pause'))
  self.assertEqual(call.args[2]['entity_id'],'media_player.bedroom')

if __name__=='__main__':unittest.main()
