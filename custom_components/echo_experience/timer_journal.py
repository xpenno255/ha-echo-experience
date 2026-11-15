"""Keep an Echo's timers across a Home Assistant restart.

Home Assistant holds voice timers in memory only, and a Kiosk rings when Home Assistant tells it a timer finished,
so a Core restart used to lose every running timer without a word. The journal writes each profile's timers (name,
end time, paused or not) to storage whenever they change. At the next start the timers Home Assistant no longer
has are started again with the time they have left, once the Echo's voice device is back. One that ran out while
Home Assistant was down is announced on the Echo instead of being dropped. Either way the Echo is first told the
old timer is gone, because a Kiosk keeps its own copy until Home Assistant says so.

A reload of the integration restores nothing: the timers are still in Home Assistant then.
"""
import asyncio
import logging
import time
from datetime import timedelta

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import CoreState, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store

from . import native
from .core import identities, match_identity

STORE_KEY = 'echo_experience.timers'
# Timer events drive the journal; this catches a change no event reported.
RECHECK = timedelta(seconds=30)
# After a start the Echo's voice device takes a while to reconnect; timers wait this long for it.
RESTORE_WAIT = 600
RESTORE_POLL = 5
# An alarm missed by more than this is old news and is not announced.
MISSED_MAX = 3600
# Two samples of the same running timer differ by rounding; a real change (added time) is larger.
END_TOLERANCE = 3
_LOGGER = logging.getLogger(__name__)


def ago(seconds):
    minutes = int(round(seconds / 60))
    return 'less than a minute ago' if minutes < 1 else 'a minute ago' if minutes == 1 else f'{minutes} minutes ago'


class TimerJournal:
    def __init__(self, hass, runtime, store=None, clock=time.time, sleep=asyncio.sleep):
        self.hass, self.runtime, self.clock, self.sleep = hass, runtime, clock, sleep
        self.store = store if store is not None else Store(hass, 1, STORE_KEY)
        self.saved = None
        self.pending = []
        self.frozen = False
        self.closed = False
        self.lock = asyncio.Lock()
        self.unsubscribers = []
        self.restoring = None

    # ---- what is running now ----------------------------------------------------------------
    def live(self):
        """One record per timer of a profile, or None while Home Assistant's timer manager is not there."""
        manager = self.runtime.timer_manager()
        if manager is None:
            return None
        owners = {i['device_id']: p['id'] for p in self.runtime.profiles for i in identities(p)}
        now = self.clock()
        records = []
        for timer in manager.timers.values():
            if timer.device_id not in owners:
                continue
            left = timer.seconds_left
            active = bool(timer.is_active)
            records.append({'id': timer.id, 'profile': owners[timer.device_id], 'device_id': timer.device_id,
                            'name': timer.name, 'is_active': active, 'seconds_left': left,
                            'ends_at': now + left if active else None, 'created_seconds': timer.created_seconds})
        return records

    @staticmethod
    def same(a, b):
        if a is None or b is None or len(a) != len(b):
            return False
        for x, y in zip(sorted(a, key=lambda r: r['id']), sorted(b, key=lambda r: r['id'])):
            if (x['id'], x['name'], x['is_active']) != (y['id'], y['name'], y['is_active']):
                return False
            if x['is_active'] and abs(x['ends_at'] - y['ends_at']) > END_TOLERANCE:
                return False
            if not x['is_active'] and x['seconds_left'] != y['seconds_left']:
                return False
        return True

    async def save(self, force=False):
        async with self.lock:
            if self.frozen or self.closed and not force:
                return
            records = self.live()
            if records is None:
                return
            # Timers still waiting to be restored are kept until they are, so a second restart cannot lose them.
            wanted = [*records, *self.pending]
            if not force and self.same(wanted, self.saved):
                return
            await self.store.async_save({'timers': wanted})
            self.saved = wanted

    @callback
    def schedule(self, *_):
        if self.frozen or self.closed:
            return
        self.hass.async_create_task(self.save(), 'Echo Experience timer journal')

    # ---- lifecycle --------------------------------------------------------------------------
    async def async_start(self):
        saved = ((await self.store.async_load()) or {}).get('timers') or []
        manager = self.runtime.timer_manager()
        known = set(manager.timers) if manager is not None else set()
        # Only a start of Home Assistant loses timers; on a reload they are all still there.
        if getattr(self.hass, 'state', None) is not CoreState.running:
            self.pending = [r for r in saved if isinstance(r, dict) and r.get('id') not in known and r.get('device_id')]
        self.unsubscribers.append(async_track_time_interval(self.hass, self.schedule, RECHECK))
        self.unsubscribers.append(self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self.stopping))
        if self.pending:
            _LOGGER.info('Echo Experience: %d timer(s) to bring back after the restart', len(self.pending))
            self.restoring = self.hass.async_create_task(self.restore(), 'Echo Experience timer restore')
        else:
            await self.save()

    async def stopping(self, _event=None):
        """Home Assistant is going down: write what runs now and touch nothing after, whatever shutdown does to it."""
        await self.save(force=True)
        self.frozen = True

    @callback
    def stop(self):
        self.closed = True
        for unsubscribe in self.unsubscribers:
            try:
                unsubscribe()
            except Exception:  # noqa: BLE001 - the once-only stop listener may already have gone
                pass
        self.unsubscribers.clear()
        if self.restoring is not None and not self.restoring.done():
            self.restoring.cancel()

    # ---- after a restart --------------------------------------------------------------------
    async def restore(self):
        waited = 0
        try:
            while self.pending and not self.closed:
                manager = self.runtime.timer_manager()
                for record in list(self.pending):
                    if manager is not None and native.timer_device(manager, record['device_id']):
                        self.pending.remove(record)
                        await self.restore_one(manager, record)
                if not self.pending:
                    break
                if waited >= RESTORE_WAIT:
                    _LOGGER.warning('Echo Experience: gave up bringing back %d timer(s); the Echo did not return within %d s: %s',
                                    len(self.pending), RESTORE_WAIT, ', '.join(str(r.get('name') or 'timer') for r in self.pending))
                    self.pending.clear()
                    break
                await self.sleep(RESTORE_POLL)
                waited += RESTORE_POLL
        finally:
            if not self.closed:
                await self.save(force=True)

    async def restore_one(self, manager, record):
        name = record.get('name')
        # The Echo still shows its own copy of the timer Home Assistant forgot; without this there would be two.
        native.forget_timer(manager, record['device_id'], record.get('id'), name, record.get('created_seconds'))
        try:
            if record.get('is_active'):
                left = int(round(record['ends_at'] - self.clock()))
                if left <= 0:
                    await self.missed(record, -left)
                    return
            else:
                left = int(record.get('seconds_left') or 0)
                if left <= 0:
                    return
            timer_id = native.start_timer(self.hass, manager, record['device_id'], left // 3600, left % 3600 // 60, left % 60, name)
            if not record.get('is_active'):
                manager.pause_timer(timer_id)
            _LOGGER.info('Echo Experience: brought back the %s with %d s left%s', f'{name} timer' if name else 'timer', left,
                         '' if record.get('is_active') else ' (paused)')
        except Exception as err:  # noqa: BLE001 - one timer that cannot come back must not stop the others
            _LOGGER.warning('Echo Experience: could not bring back the %s: %s', f'{name} timer' if name else 'timer', err)

    async def missed(self, record, late):
        """It ran out while Home Assistant was down. Its alarm never sounded, so say so on the Echo."""
        name = record.get('name')
        _LOGGER.warning('Echo Experience: the %s finished %d s ago, while Home Assistant was down', f'{name} timer' if name else 'timer', late)
        if late > MISSED_MAX:
            return
        p = self.runtime.profile(record.get('profile'))
        ident = match_identity(p, device_id=record['device_id']) if p else None
        if not native.satellite_up(self.hass, ident):
            return
        message = f"Your {name + ' ' if name else ''}timer finished {ago(late)}, while Home Assistant was restarting."
        await self.hass.services.async_call('assist_satellite', 'announce', {'entity_id': ident['satellite'], 'message': message}, blocking=False)
