"""Keep an Echo awake on its dashboard while one of its timers runs or rings.

Kiosk's Hold mode switch (profile `kiosk_hold`) pins the dashboard and blocks the screensaver. The integration turns
it on while a profile has a running timer or a ringing alarm and off again once neither is left, but only when it
turned it on itself: a hold set by someone else (a pinned guide) is left alone, and taken over only if that owner
releases it while a timer still runs. Paused timers do not hold the screen. Ownership is stored, so a hold left on
across a restart (timers do not survive one) is released at the next start.
"""
import asyncio
import logging
from datetime import timedelta
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store

STORE_KEY='echo_experience.screen_hold'
# Catches ringing alarms that expire unreported and switches that were unavailable when a timer changed.
RECHECK=timedelta(minutes=1)
_LOGGER=logging.getLogger(__name__)

class ScreenHold:
    def __init__(self,hass,runtime,store=None):
        self.hass,self.runtime=hass,runtime
        self.store=store if store is not None else Store(hass,1,STORE_KEY)
        self.owned=set()
        self.lock=asyncio.Lock()
        self.unsubscribers=[]

    def profiles(self):
        return [p for p in self.runtime.profiles if p.get('kiosk_hold')]

    def wanted(self,p):
        return any(t['is_active'] for t in self.runtime.timers(p)) or bool(self.runtime.ringing_timers(p))

    async def async_start(self):
        self.owned=set((await self.store.async_load() or {}).get('owned',[]))
        holds=[p['kiosk_hold'] for p in self.profiles()]
        if holds:
            self.unsubscribers.append(async_track_state_change_event(self.hass,holds,self.hold_changed))
            self.unsubscribers.append(async_track_time_interval(self.hass,self.recheck,RECHECK))
        await self.sync_all()

    def stop(self):
        for unsubscribe in self.unsubscribers:unsubscribe()
        self.unsubscribers=[]

    @callback
    def schedule(self,p):
        """Timer events arrive as callbacks; sync once the timer manager has settled."""
        if p.get('kiosk_hold'):self.hass.async_create_task(self.sync(p))

    @callback
    def hold_changed(self,event):
        # Someone released the hold (a guide's Done, a manual toggle); take it back if a timer still needs it.
        if getattr(event.data.get('new_state'),'state',None)!='off':return
        p=next((p for p in self.profiles() if p['kiosk_hold']==event.data.get('entity_id')),None)
        if p:self.schedule(p)

    async def recheck(self,_now=None):
        await self.sync_all()

    async def sync_all(self):
        for p in self.profiles():await self.sync(p)

    async def sync(self,p):
        async with self.lock:
            eid=p['kiosk_hold'];state=getattr(self.hass.states.get(eid),'state',None)
            if state not in ('on','off'):return
            owned=set(self.owned)
            if self.wanted(p):
                if state=='off' and await self.switch(eid,'turn_on'):owned.add(p['id'])
            elif p['id'] in owned:
                if state=='off' or await self.switch(eid,'turn_off'):owned.discard(p['id'])
            if owned!=self.owned:
                self.owned=owned
                await self.store.async_save({'owned':sorted(owned)})

    async def switch(self,eid,service):
        try:
            await self.hass.services.async_call('switch',service,{'entity_id':eid},blocking=True)
            return True
        except Exception:
            _LOGGER.warning('Could not %s %s for a timer',service.replace('_',' '),eid,exc_info=True)
            return False
