"""Device-scoped dashboard data, actions and Assist tools."""
import asyncio
import json
import logging
import secrets
import time
from datetime import timedelta
from pathlib import Path
import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.components.intent.const import TIMER_DATA
from homeassistant.core import callback, SupportsResponse
from homeassistant.exceptions import Unauthorized
from homeassistant.helpers import llm, entity_registry as er, issue_registry as ir
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.auth.permissions.const import POLICY_READ, POLICY_CONTROL
from homeassistant.util import dt as dt_util
from .music import resolve_music
from .music_fallback import resolve_with_fallback
from .music_backend import MusicBackend
from .ducking import DuckingManager
from .core import validate_profiles, route_profile, convert, VIEWS, normalize_timer_name
from . import frontend, dashboard
from .stop_route import StopRoute

DOMAIN='echo_experience'
EVENT='echo_experience_update'
# A finished alarm keeps sounding until dismissed; forget it after this long if the display never reports.
RINGING_TTL=3600
_LOGGER=logging.getLogger(__name__)

async def async_setup(hass, config):
    for command in (ws_state, ws_subscribe, ws_action):websocket_api.async_register_command(hass,command)
    return True

def integration_version(hass):
    return json.loads((Path(__file__).parent/'manifest.json').read_text())['version']

async def async_setup_entry(hass, entry):
    def read():
        return validate_profiles(json.loads(Path(hass.config.path('echo_experience.json')).read_text()))
    config=await hass.async_add_executor_job(read)
    runtime=Experience(hass,config)
    hass.data[DOMAIN]=runtime
    version=await hass.async_add_executor_job(integration_version,hass)
    # The card, its resource, the dashboard and the stop route ship with the integration. A failure in one is a
    # visible repair issue and never stops the others; the issue clears when that feature next sets up cleanly.
    async def feature(name,coro):
        try:
            await coro
            ir.async_delete_issue(hass,DOMAIN,'setup_failed_'+name)
        except Exception as err:
            _LOGGER.exception('Echo Experience %s setup failed',name)
            ir.async_create_issue(hass,DOMAIN,'setup_failed_'+name,is_fixable=False,severity=ir.IssueSeverity.ERROR,translation_key='setup_failed_'+name,translation_placeholders={'error':str(err) or type(err).__name__})
    async def card():
        await frontend.async_register_static_path(hass)
        await frontend.async_ensure_resource(hass,version)
    await feature('frontend',card())
    await feature('dashboard',dashboard.async_manage(hass,runtime.profiles,version,entry.options.get('manage_dashboard',True)))
    runtime.stop_route=StopRoute(hass,runtime)
    await feature('stop_route',runtime.stop_route.async_start())
    entry.async_on_unload(runtime.stop_route.stop)
    entry.async_on_unload(entry.add_update_listener(async_options_updated))
    async def reload(call):await hass.config_entries.async_reload(entry.entry_id)
    async_register_admin_service(hass,DOMAIN,'reload',reload)
    entry.async_on_unload(lambda:hass.services.async_remove(DOMAIN,'reload'))
    entry.async_on_unload(llm.async_register_api(hass,ExperienceAPI(hass,runtime)))
    entry.async_on_unload(hass.bus.async_listen('voice_satellite_chat',runtime.chat))
    entry.async_on_unload(hass.bus.async_listen('voice_satellite_timer',runtime.timer_event))
    async def dismiss_timer(call):
        return await dismiss_timer_service(hass,runtime,call)
    hass.services.async_register(DOMAIN,'dismiss_timer',dismiss_timer,schema=vol.Schema({vol.Required('device_id'):str,vol.Optional('name'):str}),supports_response=SupportsResponse.OPTIONAL)
    entry.async_on_unload(lambda:hass.services.async_remove(DOMAIN,'dismiss_timer'))
    runtime.ducking=DuckingManager(hass,runtime.profiles)
    await runtime.ducking.async_start()
    return True

async def dismiss_timer_service(hass,runtime,call):
    """A user context must be allowed to control the target Echo's satellite; automation/system contexts carry no user."""
    p=runtime.profile_for_device(call.data['device_id'])
    if not p:return {'status':'unknown_device'}
    if call.context.user_id:
        user=await hass.auth.async_get_user(call.context.user_id)
        if user is None or not user.permissions.check_entity(p['satellite'],POLICY_CONTROL):
            raise Unauthorized(context=call.context,entity_id=p['satellite'],permission=POLICY_CONTROL)
    return await runtime.dismiss_for_device(call.data['device_id'],call.data.get('name'))

async def async_options_updated(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)

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
        self.music_catalog_cache={}
        self.ringing={}
        self.dismissals={}
        self.dismiss_timeout=4

    def profile(self,slug):
        return next((p for p in self.profiles if p['id']==slug),None)

    def device_of(self,entity_id):
        """Entity registry lookup, kept separate so tests can stand in for it."""
        entry=er.async_get(self.hass).async_get(entity_id)
        return entry.device_id if entry else None

    def profile_for_device(self,device_id):
        """The Echo profile that owns a voice device: its own satellite or one of its ducking companions. No fallback."""
        p=route_profile(self.profiles,device_id=device_id)
        if p or not device_id:return p
        matches=[p for p in self.profiles if any(self.device_of(s)==device_id for s in p.get('ducking',{}).get('additional_satellites',[]))]
        return matches[0] if len(matches)==1 else None

    def forget(self,p,timer_ids):
        """Drop only the named ringing entries; anything that finished later keeps ringing."""
        entries=self.ringing.get(p['id'],{})
        popped=[entries.pop(i,None) for i in timer_ids]
        if not entries:self.ringing.pop(p['id'],None)
        return any(t is not None for t in popped)

    def timers(self,p):
        manager=self.hass.data.get(TIMER_DATA)
        if manager is None:return []
        return [{'id':t.id,'name':t.name or 'Timer','seconds_left':t.seconds_left,
                 'total_seconds':t.created_seconds,'is_active':t.is_active,'sampled_at':time.time()}
                for t in manager.timers.values() if t.device_id==p['device_id']]

    def ringing_timers(self,p):
        """Finished timers whose alarm is sounding; core drops these from manager.timers before the FINISHED event."""
        entries=self.ringing.get(p['id'],{})
        for key in [k for k,t in entries.items() if time.time()-t['finished_at']>RINGING_TTL]:entries.pop(key)
        return sorted(entries.values(),key=lambda t:t['finished_at'])

    def snapshot(self,p):
        return {'profile':p,'timers':self.timers(p),'ringing':self.ringing_timers(p),'result':self.results.get(p['id']),
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
            data=event.data
            if data.get('event_type')=='finished' and data.get('timer_id'):
                self.ringing.setdefault(p['id'],{})[data['timer_id']]={'id':data['timer_id'],'name':data.get('name') or 'Timer','total_seconds':data.get('total_seconds'),'finished_at':time.time()}
            # Native Voice Satellite owns audio and completion/dismissal; no duplicate alarm.
            self.hass.bus.async_fire(EVENT,{'device':p['id'],'timers':self.timers(p),'ringing':self.ringing_timers(p),'timer_event':dict(data)})

    async def dismiss(self,p,ringing):
        """Ask this Echo's dashboard to trigger Voice Satellite's own dismissal and report what happened."""
        token=secrets.token_hex(8)
        ids=[t['id'] for t in ringing]
        future=asyncio.get_running_loop().create_future()
        # Bound to this profile and these timers: a report from another Echo's card, or for another request, is ignored.
        self.dismissals[token]={'future':future,'profile':p['id'],'timers':ids}
        self.hass.bus.async_fire(EVENT,{'device':p['id'],'dismiss':{'request':token,'timers':[{'id':t['id'],'name':t['name']} for t in ringing]}})
        try:
            async with asyncio.timeout(self.dismiss_timeout):report=await future
        except TimeoutError:
            return {'status':'unconfirmed','timers':[t['name'] for t in ringing]}
        finally:self.dismissals.pop(token,None)
        if report.get('dismissed') or not report.get('present'):
            self.forget(p,ids)
            return {'status':'dismissed' if report.get('dismissed') else 'not_ringing','timers':[t['name'] for t in ringing]}
        return {'status':'failed','timers':[t['name'] for t in ringing]}

    async def dismiss_for_device(self,device_id,name=None,profile=None):
        """Silence this device's ringing alarm, never another Echo's. Callers with a validated owner map pass the profile."""
        p=profile or self.profile_for_device(device_id)
        if not p:return {'status':'unknown_device'}
        wanted=normalize_timer_name(name)
        ringing=[t for t in self.ringing_timers(p) if not wanted or normalize_timer_name(t['name'])==wanted]
        if not ringing:return {'status':'not_ringing'}
        result=await self.dismiss(p,ringing)
        if result['status']=='dismissed':await self.publish(p,'timers')
        return result

    def display_report(self,p,args):
        """The Echo's own dashboard reports a dismissal outcome or a device-side silence. Never an LLM-visible operation."""
        token=str(args.get('request') or '')
        ids=[i for i in (args.get('timers') or []) if isinstance(i,str)]
        if token:
            entry=self.dismissals.get(token)
            if not entry or entry['profile']!=p['id']:return {'status':'ignored'}
            if not entry['future'].done():entry['future'].set_result({'dismissed':bool(args.get('dismissed')),'present':bool(args.get('present'))})
            return {'status':'recorded'}
        if not args.get('present') and self.forget(p,ids):
            # Silenced on the device itself (tap or stop word); keep the server's view honest for just those alarms.
            self.hass.bus.async_fire(EVENT,{'device':p['id'],'timers':self.timers(p),'ringing':self.ringing_timers(p)})
        return {'status':'recorded'}

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
        resolution=None
        if action in ('play','search'):
            query=args.get('query','').strip()
            if not query:raise ValueError('A track, artist, playlist or station is required')
            data={'entity_id':player,'media_id':query,'enqueue':'replace'}
            if args.get('media_type'):data['media_type']=args['media_type']
            if args.get('artist'):data['artist']=args['artist']
            if args.get('album'):data['album']=args['album']
            kind=args.get('media_type')
            if kind in ('track','artist','album') or not kind:
                entry=p.get('music_assistant_entry')
                if not entry:raise ValueError('Music Assistant is not configured for this Echo')
                async def search(fields):
                    return await self.hass.services.async_call('music_assistant','search',
                        {'config_entry_id':entry,**fields},blocking=True,return_response=True,context=context)
                backend=MusicBackend(self.hass,entry,p.get('music_resolver_agent'),context,self.music_catalog_cache)
                async with asyncio.timeout(25):
                    if p.get('music_resolver_agent'):
                        resolution=await resolve_with_fallback(search,backend.catalog,backend.advise,query,kind,args.get('artist',''),args.get('album',''),args.get('version',''))
                    else:
                        resolution=await resolve_music(search,query,kind,args.get('artist',''),args.get('album',''),args.get('version',''))
                if action=='search':return resolution
                if resolution['status']!='matched':
                    await self.publish(p,'answer',{'question':query,'speech':resolution.get('question') or resolution.get('message')})
                    return resolution
                data={'entity_id':player,'media_id':resolution['match']['uri'],'enqueue':'replace','media_type':resolution.get('media_type',kind)}
            elif action=='search':
                raise ValueError('Search supports tracks, artists and albums')
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
        return {'match':resolution.get('match') if resolution else None,'status':'request_accepted','player':player,'state':state.state,'title':state.attributes.get('media_title'),'note':'The request was accepted; report playback as started only if state is playing.'}

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
            if op not in ('status','start','pause','resume','cancel','dismiss','add'):raise ValueError('Unsupported timer operation')
            if op=='status':
                return {'timers':self.timers(p),'ringing':self.ringing_timers(p)}
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
                wanted=normalize_timer_name(args.get('name'))
                requested=args.get('timer_id')
                ringing=[t for t in self.ringing_timers(p) if (t['id']==requested if requested else (not wanted or normalize_timer_name(t['name'])==wanted))]
                if ringing and op in ('cancel','dismiss'):
                    result=await self.dismiss(p,ringing)
                    if result['status']=='dismissed':
                        await self.publish(p,'timers')
                        return {'timers':self.timers(p),'ringing':[],'status':'dismissed','dismissed':result['timers'],'note':'The alarm has been silenced. Confirm briefly.'}
                    if result['status']!='not_ringing':raise ValueError('The Echo display did not confirm the alarm was silenced. Tap the alert or say stop again.')
                    if not any(t.device_id==p['device_id'] for t in manager.timers.values()):
                        return {'timers':[],'ringing':[],'status':'already_silenced','note':'That alarm had already been silenced on the Echo; nothing is running.'}
                    ringing=[]
                elif ringing:raise ValueError('The '+ringing[0]['name']+' timer has finished and its alarm is sounding; dismiss it instead')
                if op=='dismiss':
                    others=', '.join(t['name'] for t in self.ringing_timers(p))
                    running=len(self.timers(p))
                    raise ValueError(('No timer alarm is sounding on this Echo' if not others else f'No ringing timer matches; ringing: {others}')+(f'; {running} timer(s) are still running' if running else ''))
                timer=manager.timers.get(requested)
                if timer is None and not requested:
                    matches=[t for t in manager.timers.values() if t.device_id==p['device_id'] and (not wanted or normalize_timer_name(t.name)==wanted)]
                    if not matches:raise ValueError('No timer is running or ringing on this Echo'+(f' named {wanted}' if wanted else ''))
                    if len(matches)>1:raise ValueError('Name the timer to change; there is no unique matching timer on this Echo')
                    timer=matches[0]
                if timer is None or timer.device_id!=p['device_id']:raise ValueError('This timer does not belong to this Echo')
                if op=='cancel':manager.cancel_timer(timer.id)
                elif op=='pause':manager.pause_timer(timer.id)
                elif op=='resume':manager.unpause_timer(timer.id)
                elif op=='add':manager.add_time(timer.id,60)
                else:raise ValueError('Unsupported timer operation')
            await self.publish(p,'timers')
            return {'timers':self.timers(p),'ringing':self.ringing_timers(p),'status':'completed'}
        raise ValueError('Unsupported action')

class ActionTool(llm.Tool):
    def __init__(self,runtime,p,name,description,schema):
        self.runtime,self.profile=runtime,p
        self.name,self.description,self.parameters=name,description,vol.Schema(schema)
    async def async_call(self,hass,tool_input,llm_context):
        try:args=self.parameters(tool_input.tool_args)
        except vol.Invalid as err:return {'error':'Invalid arguments: '+str(err),'retryable':False}
        try:return await self.runtime.execute(self.profile,self.name.removeprefix('echo_'),args,llm_context.context)
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
                ActionTool(self.runtime,p,'echo_timer','Manage native voice timers on THIS Echo only. Start a named timer with a duration in seconds; status lists running timers with remaining seconds plus any ringing (finished) alarms. Pause, resume, cancel or add one minute using its name (omit only if exactly one exists). A finished timer whose alarm is sounding is no longer running: "stop", "stop the timer", "dismiss" or "cancel" while it rings means dismiss. cancel silences a ringing alarm first and otherwise cancels the running timer; dismiss only silences alarms. Never create or guess timer.* entities.',{vol.Required('operation'):vol.In(['start','status','pause','resume','cancel','dismiss','add']),vol.Optional('name'):str,vol.Optional('seconds'):vol.All(vol.Coerce(int),vol.Range(min=1,max=86400))}),
                ActionTool(self.runtime,p,'echo_weather','Get the local forecast and display it on THIS Echo. Use for weather and rain questions. Choose today, tomorrow, next_hours (12 hours), or week.',{vol.Optional('period',default='today'):vol.In(['today','tomorrow','next_hours','week'])}),
                ActionTool(self.runtime,p,'echo_convert','Calculate a unit conversion exactly and display the result. Use for temperatures, weights, volumes and length/distance (millimetres, centimetres, metres, kilometres, inches, feet, yards, miles). Both singular and plural unit names are accepted. Cups/pints need their stated standard; never assume ingredient density.',{vol.Required('value'):vol.Coerce(float),vol.Required('from_unit'):str,vol.Required('to_unit'):str}),
                ActionTool(self.runtime,p,'echo_music','Play music/radio or control playback on this Echo. Default is its selected music speaker. Optional speaker must be one of: '+speakers+'. Always set media_type for play/search: track for a song, album for an album, artist only when query is the band/artist name. The artist field is a separate filter; naming a performer does not make a song an artist request. Put only the title in query and the performer in artist. For album requests use query for the album title and omit the album field; album is only a filter for a track. Only set version if the user explicitly requests one. Standard studio releases are preferred automatically; do not ask about remasters or editions before calling this tool. Search resolves a title without playing. Play resolves tracks/artists/albums before queuing. If status is needs_clarification or not_found, ask a short question using the result; nothing has played. Never guess a URI. volume is 0–100.',{vol.Required('action'):vol.In(['play','search','pause','resume','next','previous','stop','volume']),vol.Optional('query'):str,vol.Optional('media_type'):vol.In(['track','artist','album','playlist','radio','podcast']),vol.Optional('artist'):str,vol.Optional('album'):str,vol.Optional('version'):str,vol.Optional('speaker'):str,vol.Optional('volume'):vol.All(vol.Coerce(float),vol.Range(min=0,max=100))}),
                ActionTool(self.runtime,p,'echo_show','Open a view on THIS Echo when asked to show the home screen, timers, music, weather, guides or home controls.',{vol.Required('view'):vol.In(VIEWS)})])
        return llm.APIInstance(api=self,api_prompt='Use Echo tools for this satellite\'s weather, music and conversions. Use echo_timer for timers and native Assist intents for home commands. A finished timer whose alarm is sounding is listed under ringing, not timers: for stop, dismiss, silence or cancel while it rings use echo_timer operation cancel or dismiss (naming it if given) and confirm only when the result status is dismissed. Use echo_guide for appliance instructions. Never substitute guessed manual instructions or forecast data.',llm_context=context,tools=tools)

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
        if msg['action']=='timer' and msg['args'].get('operation')=='dismissed':result=runtime.display_report(p,msg['args'])
        else:result=await runtime.execute(p,msg['action'],msg['args'],connection.context(msg))
        connection.send_result(msg['id'],result)
    except Exception as err:
        connection.send_error(msg['id'],'echo_error',str(err))
