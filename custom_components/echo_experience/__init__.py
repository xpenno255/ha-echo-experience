"""Device-scoped dashboard data, actions and Assist tools."""
import asyncio
import json
import logging
import time
from datetime import timedelta
from pathlib import Path
import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.components.intent.const import TIMER_DATA
from homeassistant.core import callback
from homeassistant.helpers import llm
from homeassistant.auth.permissions.const import POLICY_READ, POLICY_CONTROL
from homeassistant.util import dt as dt_util
from .ducking import DuckingManager
from .core import validate_profiles, route_profile, convert, VIEWS, normalize_timer_name

DOMAIN='echo_experience'
EVENT='echo_experience_update'
_LOGGER=logging.getLogger(__name__)

async def async_setup(hass, config):
    for command in (ws_state, ws_subscribe, ws_action):websocket_api.async_register_command(hass,command)
    return True

async def async_setup_entry(hass, entry):
    def read():
        return validate_profiles(json.loads(Path(hass.config.path('echo_experience.json')).read_text()))
    config=await hass.async_add_executor_job(read)
    runtime=Experience(hass,config)
    hass.data[DOMAIN]=runtime
    entry.async_on_unload(llm.async_register_api(hass,ExperienceAPI(hass,runtime)))
    entry.async_on_unload(hass.bus.async_listen('voice_satellite_chat',runtime.chat))
    entry.async_on_unload(hass.bus.async_listen('voice_satellite_timer',runtime.timer_event))
    runtime.ducking=DuckingManager(hass,runtime.profiles)
    await runtime.ducking.async_start()
    return True

async def async_unload_entry(hass, entry):
    runtime=hass.data.pop(DOMAIN,None)
    if runtime and getattr(runtime,'ducking',None):await runtime.ducking.async_close()
    return True

class Experience:
    def __init__(self,hass,config):
        self.hass=hass
        self.profiles=config['devices']
        self.results={}
        self.forecasts={}
        self.locks={}
        self.music_players={}

    def profile(self,slug):
        return next((p for p in self.profiles if p['id']==slug),None)

    def timers(self,p):
        manager=self.hass.data.get(TIMER_DATA)
        if manager is None:return []
        return [{'id':t.id,'name':t.name or 'Timer','seconds_left':t.seconds_left,
                 'total_seconds':t.created_seconds,'is_active':t.is_active,'sampled_at':time.time()}
                for t in manager.timers.values() if t.device_id==p['device_id']]

    def snapshot(self,p):
        return {'profile':p,'timers':self.timers(p),'result':self.results.get(p['id']),
                'music_player':self.music_players.get(p['id'],p['music_player']),
                'forecast':self.forecasts.get(p['weather'])}

    async def publish(self,p,view,payload=None,wake=True):
        result={'view':view,'payload':payload or {},'timestamp':time.time()}
        self.results[p['id']]=result
        # Store first so a new/reloaded dashboard can recover the requested view.
        self.hass.bus.async_fire(EVENT,{'device':p['id'],'result':result})
        if wake:
            for key in ('kiosk_now_playing','kiosk_screensaver'):
                eid=p.get(key)
                if eid and self.hass.states.is_state(eid,'on'):
                    await self.hass.services.async_call('switch','turn_off',{'entity_id':eid},blocking=True)
            nav=p.get('kiosk_navigation')
            if nav and not self.hass.states.is_state(nav,p['dashboard']):
                try:
                    await self.hass.services.async_call('select','select_option',{'entity_id':nav,'option':p['dashboard']},blocking=True)
                except Exception: _LOGGER.warning('Could not navigate %s to its dashboard',p['id'],exc_info=True)
        return result

    @callback
    def timer_event(self,event):
        p=route_profile(self.profiles,satellite=event.data.get('entity_id'))
        if p:
            # Native Voice Satellite owns audio and completion/dismissal; no duplicate alarm.
            self.hass.bus.async_fire(EVENT,{'device':p['id'],'timers':self.timers(p),'timer_event':dict(event.data)})

    @callback
    def chat(self,event):
        p=route_profile(self.profiles,satellite=event.data.get('entity_id'))
        if not p:return
        data=event.data
        names={(t.get('name') or '').split('__')[-1] for t in data.get('tool_calls',[])}
        recent=self.results.get(p['id'])
        if recent and time.time()-recent['timestamp']<90 and names.intersection({'query_home_documents','echo_guide','echo_convert','echo_weather','echo_music','echo_show','echo_timer'}):
            updated={**recent,'payload':{**recent['payload'],'speech':data.get('tts_text',''),'question':data.get('stt_text','')}}
            self.results[p['id']]=updated
            self.hass.bus.async_fire(EVENT,{'device':p['id'],'result':updated})
        elif data.get('tts_text') and not any('timer' in (n or '').lower() for n in names):
            # Display the actual answer. Never execute actions by matching spoken prose.
            self.hass.async_create_task(self.publish(p,'answer',{'speech':data['tts_text'],'question':data.get('stt_text','')}))

    async def forecast(self,p):
        entity=p['weather']
        async with self.locks.setdefault(entity,asyncio.Lock()):
            cached=self.forecasts.get(entity)
            if cached and time.time()-cached['fetched_at']<600:return cached
            state=self.hass.states.get(entity)
            if not state or state.state in ('unavailable','unknown'):raise ValueError('The weather provider is unavailable')
            result={'entity_id':entity,'source':state.attributes.get('friendly_name',entity),'fetched_at':time.time(),
                    'condition':state.state,'temperature':state.attributes.get('temperature'),
                    'temperature_unit':state.attributes.get('temperature_unit','°C'),'hourly':[],'daily':[]}
            for kind in ('hourly','daily'):
                try:
                    response=await self.hass.services.async_call('weather','get_forecasts',{'entity_id':entity,'type':kind},blocking=True,return_response=True)
                    result[kind]=(response or {}).get(entity,{}).get('forecast',[])[:72 if kind=='hourly' else 7]
                except Exception:
                    result[kind+'_error']='Forecast unavailable'
            if not result['hourly'] and not result['daily']:raise ValueError('No forecast is available from this provider')
            self.forecasts[entity]=result
            return result

    async def weather(self,p,args):
        forecast=await self.forecast(p)
        period=args.get('period','today')
        now=dt_util.now()
        chosen=[]
        source=forecast['daily'] if period=='week' else forecast['hourly']
        for item in source:
            stamp=dt_util.parse_datetime(item.get('datetime',''))
            if not stamp:continue
            local=dt_util.as_local(stamp)
            if period=='week' or (period=='today' and local.date()==now.date() and local>=now-timedelta(hours=1)) or (period=='tomorrow' and local.date()==(now+timedelta(days=1)).date()) or (period=='next_hours' and now-timedelta(hours=1)<=local<=now+timedelta(hours=12)):
                chosen.append(item)
        answer={**forecast,'period':period,'requested_forecast':chosen}
        await self.publish(p,'weather',{'period':period})
        return {'source':forecast['source'],'temperature_unit':forecast['temperature_unit'],'current_temperature':forecast['temperature'],'period':period,'forecast':chosen,'note':'Summarise only the requested period. Missing precipitation is unknown, not zero.'}

    def speaker(self,p,args):
        requested=args.get('speaker')
        if requested:
            match=[x['entity_id'] for x in p['speakers'] if requested.casefold() in (x['entity_id'].casefold(),x['name'].casefold())]
            if len(match)!=1:raise ValueError('Choose a configured speaker: '+', '.join(x['name'] for x in p['speakers']))
            return match[0]
        return self.music_players.get(p['id'],p['music_player'])

    async def music(self,p,args,context=None):
        player=self.speaker(p,args)
        if not self.hass.states.get(player) or self.hass.states.is_state(player,'unavailable'):raise ValueError('That speaker is unavailable')
        action=args.get('action','play')
        if action=='select':
            self.music_players[p['id']]=player
            return await self.publish(p,'music',{'player':player})
        if action=='play':
            query=args.get('query','').strip()
            if not query:raise ValueError('A track, artist, playlist or station is required')
            data={'entity_id':player,'media_id':query,'enqueue':'replace'}
            if args.get('media_type'):data['media_type']=args['media_type']
            if args.get('artist'):data['artist']=args['artist']
            domain,service='music_assistant','play_media'
        elif action=='volume':
            data={'entity_id':player,'volume_level':float(args['volume'])/100}
            if not 0<=data['volume_level']<=1:raise ValueError('Volume must be between 0 and 100')
            domain,service='media_player','volume_set'
        else:
            service={'pause':'media_pause','resume':'media_play','next':'media_next_track','previous':'media_previous_track','stop':'media_stop'}.get(action)
            if not service:raise ValueError('Unsupported music action')
            domain,data='media_player',{'entity_id':player}
        await self.hass.services.async_call(domain,service,data,blocking=True,context=context)
        self.music_players[p['id']]=player
        await self.publish(p,'music',{'player':player})
        state=self.hass.states.get(player)
        return {'status':'request_accepted','player':player,'state':state.state,'title':state.attributes.get('media_title'),'note':'The request was accepted; report playback as started only if state is playing.'}

    async def execute(self,p,action,args,context=None):
        if action=='weather':return await self.weather(p,args)
        if action=='music':return await self.music(p,args,context)
        if action=='convert':
            result=convert(args['value'],args['from_unit'],args['to_unit'])
            await self.publish(p,'answer',result)
            return result
        if action=='show':
            if args.get('view') not in VIEWS:raise ValueError('Unknown view')
            return await self.publish(p,args['view'])
        if action=='timer':
            manager=self.hass.data.get(TIMER_DATA)
            if not manager:raise ValueError('Timer manager unavailable')
            op=args.get('operation','start')
            if op=='status':
                return {'timers':self.timers(p)}
            if op=='start':
                seconds=int(args.get('seconds',0))
                if not 1<=seconds<=86400:raise ValueError('Choose 1 second to 24 hours')
                before=set(manager.timers)
                hours,remainder=divmod(seconds,3600)
                minutes,secs=divmod(remainder,60)
                await self.hass.services.async_call('voice_satellite','start_timer',{'entity_id':p['satellite'],'name':(normalize_timer_name(args.get('name')) or 'Timer')[:80],'hours':hours,'minutes':minutes,'seconds':secs},blocking=True,context=context)
                if not any(key not in before and timer.device_id==p['device_id'] for key,timer in manager.timers.items()):
                    raise ValueError('Home Assistant did not create the timer. Check the satellite connection.')
            else:
                timer=manager.timers.get(args.get('timer_id'))
                if timer is None and not args.get('timer_id'):
                    name=str(args.get('name','')).casefold().strip()
                    matches=[t for t in manager.timers.values() if t.device_id==p['device_id'] and (not name or normalize_timer_name(t.name)==normalize_timer_name(name))]
                    if len(matches)!=1:raise ValueError('Name the timer to change; there is no unique matching timer on this Echo')
                    timer=matches[0]
                if timer is None or timer.device_id!=p['device_id']:raise ValueError('This timer does not belong to this Echo')
                if op=='cancel':manager.cancel_timer(timer.id)
                elif op=='pause':manager.pause_timer(timer.id)
                elif op=='resume':manager.unpause_timer(timer.id)
                elif op=='add':manager.add_time(timer.id,60)
                else:raise ValueError('Unsupported timer operation')
            await self.publish(p,'timers')
            return {'timers':self.timers(p),'status':'completed'}
        raise ValueError('Unsupported action')

class ActionTool(llm.Tool):
    def __init__(self,runtime,p,name,description,schema):
        self.runtime,self.profile=runtime,p
        self.name,self.description,self.parameters=name,description,vol.Schema(schema)
    async def async_call(self,hass,tool_input,llm_context):
        try:return await self.runtime.execute(self.profile,self.name.removeprefix('echo_'),tool_input.tool_args,llm_context.context)
        except (ValueError,KeyError) as err:return {'error':str(err),'retryable':False}
        except Exception:
            _LOGGER.exception('Echo tool failed: %s',self.name)
            return {'error':'The requested action could not be completed. Do not claim success.','retryable':False}

class GuideTool(llm.Tool):
    def __init__(self,original,runtime,p):
        self.original,self.runtime,self.profile=original,runtime,p
        self.name,self.description,self.parameters='echo_guide',original.description,original.parameters
    async def async_call(self,hass,tool_input,llm_context):
        result=await self.original.async_call(hass,tool_input,llm_context)
        if self.profile:
            await self.runtime.publish(self.profile,'guide',{'appliance_id':tool_input.tool_args['appliance_id'],'question':tool_input.tool_args['query'],'guide':result})
        return result

class ExperienceAPI(llm.API):
    def __init__(self,hass,runtime):
        super().__init__(hass=hass,id=DOMAIN,name='Echo Experience')
        self.runtime=runtime
    async def async_get_api_instance(self,context):
        p=route_profile(self.runtime.profiles,device_id=context.device_id)
        tools=[]
        for entry in self.hass.config_entries.async_entries('homeguide'):
            from custom_components.homeguide.api import HomeGuideAPI
            original=await HomeGuideAPI(self.hass,entry).async_get_api_instance(context)
            tools.extend(GuideTool(t,self.runtime,p) for t in original.tools)
        if p:
            speakers=', '.join(x['name'] for x in p['speakers'])
            tools.extend([
                ActionTool(self.runtime,p,'echo_timer','Manage native voice timers on THIS Echo only. Start a named timer with a duration in seconds; status lists remaining seconds. Pause, resume, cancel or add one minute using its name (omit only if exactly one exists). Never create or guess timer.* entities.',{vol.Required('operation'):vol.In(['start','status','pause','resume','cancel','add']),vol.Optional('name'):str,vol.Optional('seconds'):vol.All(vol.Coerce(int),vol.Range(min=1,max=86400))}),
                ActionTool(self.runtime,p,'echo_weather','Get the local forecast and display it on THIS Echo. Use for weather and rain questions. Choose today, tomorrow, next_hours (12 hours), or week.',{vol.Optional('period',default='today'):vol.In(['today','tomorrow','next_hours','week'])}),
                ActionTool(self.runtime,p,'echo_convert','Calculate a unit conversion exactly and display the result. Use for temperatures, weights, volumes and lengths. Cups/pints need their stated standard; never assume ingredient density.',{vol.Required('value'):vol.Coerce(float),vol.Required('from_unit'):str,vol.Required('to_unit'):str}),
                ActionTool(self.runtime,p,'echo_music','Play music/radio or control playback on this Echo. Default is its selected music speaker. Optional speaker must be one of: '+speakers+'. query can be a track, artist, album, playlist or radio station; media_type disambiguates. volume is 0–100.',{vol.Required('action'):vol.In(['play','pause','resume','next','previous','stop','volume']),vol.Optional('query'):str,vol.Optional('media_type'):vol.In(['track','artist','album','playlist','radio','podcast']),vol.Optional('artist'):str,vol.Optional('speaker'):str,vol.Optional('volume'):vol.All(vol.Coerce(float),vol.Range(min=0,max=100))}),
                ActionTool(self.runtime,p,'echo_show','Open a view on THIS Echo when asked to show the home screen, timers, music, weather, guides or home controls.',{vol.Required('view'):vol.In(VIEWS)})])
        return llm.APIInstance(api=self,api_prompt='Use Echo tools for this satellite\'s weather, music and conversions. Use echo_timer for timers and native Assist intents for home commands. Use echo_guide for appliance instructions. Never substitute guessed manual instructions or forecast data.',llm_context=context,tools=tools)

def access(hass,connection,slug,policy):
    runtime=hass.data.get(DOMAIN)
    p=runtime.profile(slug) if runtime else None
    if not p:raise ValueError('Unknown Echo profile')
    if not connection.user.permissions.check_entity(p['satellite'],policy):raise ValueError('Access denied')
    return runtime,p

@websocket_api.websocket_command({vol.Required('type'):'echo_experience/state',vol.Required('device'):str,vol.Optional('forecast',default=False):bool})
@websocket_api.async_response
async def ws_state(hass,connection,msg):
    try:
        runtime,p=access(hass,connection,msg['device'],POLICY_READ)
        if msg['forecast']:await runtime.forecast(p)
        connection.send_result(msg['id'],runtime.snapshot(p))
    except Exception as err:connection.send_error(msg['id'],'echo_error',str(err))

@websocket_api.websocket_command({vol.Required('type'):'echo_experience/subscribe',vol.Required('device'):str})
@websocket_api.async_response
async def ws_subscribe(hass,connection,msg):
    try:runtime,p=access(hass,connection,msg['device'],POLICY_READ)
    except ValueError as err:
        connection.send_error(msg['id'],'echo_error',str(err));return
    @callback
    def event(ev):
        if ev.data.get('device')==p['id']:connection.send_event(msg['id'],dict(ev.data))
    connection.subscriptions[msg['id']]=hass.bus.async_listen(EVENT,event)
    connection.send_result(msg['id'])

@websocket_api.websocket_command({vol.Required('type'):'echo_experience/action',vol.Required('device'):str,vol.Required('action'):vol.In(['weather','music','convert','show','timer']),vol.Optional('args',default={}):dict})
@websocket_api.async_response
async def ws_action(hass,connection,msg):
    try:
        runtime,p=access(hass,connection,msg['device'],POLICY_CONTROL)
        result=await runtime.execute(p,msg['action'],msg['args'],connection.context(msg))
        connection.send_result(msg['id'],result)
    except Exception as err:
        connection.send_error(msg['id'],'echo_error',str(err))
