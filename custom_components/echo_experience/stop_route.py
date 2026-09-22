"""Fast voice stop route: silence a ringing alarm on the speaking Echo first, otherwise stop its music.

Replaces the generated automation 1757961047860. HA runs every matched sentence trigger and speaks the first
non-None reply, so exactly one handler may own these phrases. Handover is deliberate, not automatic: the route
registers only when Echo Experience loads while that automation is absent or disabled, and every request
re-checks the automation object before doing anything, answering None (letting the automation reply) if it has
been switched back on. Re-enabling the automation later therefore needs an Echo Experience reload to withdraw
the route completely; the repair issue says so.
"""
import logging
import re
from homeassistant.core import callback
from homeassistant.helpers import issue_registry as ir, entity_registry as er, device_registry as dr

DOMAIN='echo_experience'
LEGACY_AUTOMATION_ID='1757961047860'
MUSIC_COMMANDS=['stop music','stop sonos','stop the music','stop the sonos','stop playing music','turn off the music','stop sonos in here']
COMMANDS=['stop',*MUSIC_COMMANDS]
MUSIC_WORDS=re.compile(r'\b(music|sonos)\b',re.I)
REPLY_TIMER='Timer stopped.'
REPLY_UNCONFIRMED="I couldn't confirm the timer alarm stopped. Tap the alert or say stop again."
REPLY_STOPPED='Stopped.'
REPLY_NO_TARGET="I couldn't identify the music speaker for this device."
_LOGGER=logging.getLogger(__name__)

class StopRoute:
    def __init__(self,hass,runtime):
        self.hass,self.runtime=hass,runtime
        self.unregister=None
        self.owners={}

    # ---- ownership -------------------------------------------------------------------------
    def legacy_entity(self):
        """The old automation's live entity object (None when the automation component or entity is absent)."""
        component=self.hass.data.get('automation')
        if component is None or not hasattr(component,'entities'):return None
        return next((e for e in component.entities if getattr(e,'unique_id',None)==LEGACY_AUTOMATION_ID),None)

    def legacy_enabled(self):
        entity=self.legacy_entity()
        return bool(entity is not None and entity.is_on)

    def build_owners(self):
        """Device id -> profile id for every Echo and companion. A device claimed twice is a configuration error."""
        owners={}
        for p in self.runtime.profiles:
            ids=[p['device_id']]+[d for d in (self.runtime.device_of(s) for s in p.get('ducking',{}).get('additional_satellites',[])) if d]
            for device in ids:
                if owners.setdefault(device,p['id'])!=p['id']:
                    raise ValueError(f"voice device {device} belongs to both {owners[device]} and {p['id']}")
        return owners

    async def async_start(self):
        """Called once per (re)load. Registers the route only when it can be the sole owner."""
        try:self.owners=self.build_owners()
        except ValueError as err:
            ir.async_create_issue(self.hass,DOMAIN,'route_conflict',is_fixable=False,severity=ir.IssueSeverity.ERROR,translation_key='route_conflict',translation_placeholders={'detail':str(err)})
            return False
        ir.async_delete_issue(self.hass,DOMAIN,'route_conflict')
        if self.legacy_enabled():
            entity=self.legacy_entity()
            ir.async_create_issue(self.hass,DOMAIN,'legacy_stop_automation',is_fixable=False,severity=ir.IssueSeverity.WARNING,translation_key='legacy_stop_automation',translation_placeholders={'entity_id':entity.entity_id})
            return False
        ir.async_delete_issue(self.hass,DOMAIN,'legacy_stop_automation')
        self.unregister=self.register(COMMANDS,self.handle)
        _LOGGER.info('Echo Experience owns the voice stop phrases')
        return True

    def register(self,sentences,handler):
        from homeassistant.components.conversation import get_agent_manager
        return get_agent_manager(self.hass).register_trigger(sentences=sentences,trigger_callback=handler)

    @callback
    def stop(self):
        if self.unregister:self.unregister();self.unregister=None

    # ---- routing ---------------------------------------------------------------------------
    def origin_device(self,user_input):
        """Same precedence as the conversation trigger platform: the satellite's device, else the request device."""
        satellite=getattr(user_input,'satellite_id',None)
        if satellite:
            entry=er.async_get(self.hass).async_get(satellite)
            if entry and entry.device_id:return entry.device_id
        return getattr(user_input,'device_id',None)

    def area_sonos_players(self,device_id):
        """Unknown origins: a real area is required and only native Sonos media players in it are targets."""
        devices=dr.async_get(self.hass);entities=er.async_get(self.hass)
        device=devices.async_get(device_id) if device_id else None
        if device is None:return []
        area=dr.async_get_effective_area_id(self.hass,device)
        if not area:return []
        players=[]
        for entry in entities.entities.values():
            if entry.platform!='sonos' or entry.domain!='media_player' or entry.disabled:continue
            entry_area=entry.area_id
            if entry_area is None and entry.device_id:
                owner=devices.async_get(entry.device_id)
                entry_area=dr.async_get_effective_area_id(self.hass,owner) if owner else None
            if entry_area==area:players.append(entry.entity_id)
        return sorted(players)

    async def handle(self,user_input,result):
        if self.legacy_enabled():
            # Switched back on without a reload: let the automation answer and do nothing here.
            _LOGGER.warning('Legacy stop automation is enabled again; reload Echo Experience to withdraw its route')
            return None
        text=getattr(user_input,'text','') or ''
        device_id=self.origin_device(user_input)
        profile_id=self.owners.get(device_id) if device_id else None
        p=self.runtime.profile(profile_id) if profile_id else None
        if p is None:
            players=self.area_sonos_players(device_id)
            if not players:return REPLY_NO_TARGET
            return await self.stop_players(players,user_input.context)
        if not MUSIC_WORDS.search(text):
            outcome=await self.runtime.dismiss_for_device(device_id,profile=p)
            status=outcome.get('status')
            if status=='dismissed':return REPLY_TIMER
            if status in ('unconfirmed','failed'):return REPLY_UNCONFIRMED
        # The selected speaker, or the native coordinator when music was started from the Sonos app.
        return await self.stop_players([self.runtime.playback_target(p)],user_input.context,p)

    async def stop_players(self,players,context,p=None):
        try:
            await self.hass.services.async_call('media_player','media_stop',{'entity_id':players},blocking=True,context=context)
        except Exception:
            _LOGGER.exception('Voice stop failed for %s',players)
            name=next((x['name'] for x in (p or {}).get('speakers',[]) if x['entity_id']==players[0]),players[0]) if p else ', '.join(players)
            return f"I couldn't stop the music on {name}."
        return REPLY_STOPPED
