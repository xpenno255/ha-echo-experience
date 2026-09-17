"""Restore-safe, shared-speaker ducking for configured Assist satellites."""
import asyncio
import logging
import math
import time
from datetime import timedelta

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store

_LOGGER = logging.getLogger(__name__)
ACTIVE_STATES = {'listening', 'processing', 'responding', 'thinking', 'speaking'}


class DuckingManager:
    """One volume lease per speaker, shared by all active voice devices.

    Originals are journalled before changing volume. Restoration only changes a
    speaker still at our ducked level, preserving intentional volume adjustments.
    """

    def __init__(self, hass, profiles, *, store=None, clock=time.monotonic):
        self.hass = hass
        self.clock = clock
        self.store = store if store is not None else Store(hass, 1, 'echo_experience.ducking')
        self.sources = {}
        for p in profiles:
            cfg = p.get('ducking', {})
            if not cfg.get('enabled', False):
                continue
            for satellite in [p['satellite'], *cfg.get('additional_satellites', [])]:
                self.sources.setdefault(satellite, []).append(cfg)
        self.players = {e for configs in self.sources.values() for c in configs for e in c['players']}
        self.leases = {}
        self.started = {}
        self.last_active = {}
        self.lock = asyncio.Lock()
        self.unsubscribers = []
        self.task = None
        self.dirty = False
        self.closed = False

    async def async_start(self):
        saved = await self.store.async_load()
        self.leases = (saved or {}).get('volumes', {})
        # Recover an interrupted session before starting fresh voice ownership.
        for player in list(self.leases):
            await self._restore(player)
        watched = self.players | set(self.sources) | set(self.leases)
        if watched:
            self.unsubscribers.append(async_track_state_change_event(self.hass, watched, self._changed))
            self.unsubscribers.append(async_track_time_interval(self.hass, self._changed, timedelta(seconds=1)))
        self.unsubscribers.append(self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self._stopping))
        await self.async_reconcile()

    @callback
    def _changed(self, _event):
        if self.closed:
            return
        self.dirty = True
        if self.task is None or self.task.done():
            self.task = self.hass.async_create_task(self._drain(), 'Echo Experience music ducking')

    async def _drain(self):
        while self.dirty and not self.closed:
            self.dirty = False
            try:
                await self.async_reconcile()
            except Exception:
                _LOGGER.exception('Could not update music ducking; volume journal retained')

    async def _stopping(self, _event):
        await self.async_close()

    async def _save(self):
        await self.store.async_save({'volumes': self.leases})

    def _volume(self, player):
        state = self.hass.states.get(player)
        if state is None or state.state in {'unknown', 'unavailable'}:
            return None
        value = state.attributes.get('volume_level')
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
            return None
        return float(value)

    async def _set_volume(self, player, volume):
        async with asyncio.timeout(10):
            await self.hass.services.async_call(
                'media_player', 'volume_set', {'entity_id': player, 'volume_level': volume}, blocking=True
            )

    async def _restore(self, player):
        lease = self.leases[player]
        current = self._volume(player)
        if current is None:
            return  # Keep the recovery journal until this player returns.
        if abs(current - lease['ducked']) < 0.0001:
            lease['restoring'] = True
            await self._save()
            try:
                await self._set_volume(player, lease['original'])
            except Exception:
                _LOGGER.warning('Could not restore volume on %s; will retry', player, exc_info=True)
                return
            observed = self._volume(player)
            if observed is None or abs(observed - lease['ducked']) < 0.0001:
                return  # Wait for the actual state acknowledgement before releasing.
        # A different level means another controller/user changed the volume.
        del self.leases[player]
        await self._save()

    async def async_reconcile(self):
        async with self.lock:
            if self.closed:
                return
            now = self.clock()
            desired = {}
            for satellite, configs in self.sources.items():
                state = self.hass.states.get(satellite)
                active = state is not None and state.state in ACTIVE_STATES
                if active:
                    self.started.setdefault(satellite, now)
                    self.last_active[satellite] = now
                else:
                    started = self.started.pop(satellite, None)
                    if started is not None and now - started >= min(c['max_duration'] for c in configs):
                        self.last_active.pop(satellite, None)
                for cfg in configs:
                    within_limit = not active or now - self.started[satellite] < cfg['max_duration']
                    cooling = (state is not None and state.state == 'idle'
                               and now - self.last_active.get(satellite, -math.inf) < cfg['restore_delay'])
                    if within_limit and (active or cooling):
                        for player in cfg['players']:
                            desired[player] = min(desired.get(player, 1), cfg['volume_factor'])
            for player in list(self.leases):
                if player not in desired or self.leases[player].get('restoring'):
                    await self._restore(player)
            for player, factor in desired.items():
                if player in self.leases:
                    continue  # Never multiply an already-ducked volume again.
                state = self.hass.states.get(player)
                current = self._volume(player)
                if state is None or state.state != 'playing' or current is None or current == 0:
                    continue
                target = min(current, round(current * factor, 2))
                if target == current:
                    continue
                self.leases[player] = {'original': current, 'ducked': target}
                await self._save()  # Recovery must be durable before the volume change.
                try:
                    await self._set_volume(player, target)
                except Exception:
                    _LOGGER.warning('Could not duck %s; recovery record retained', player, exc_info=True)

    async def async_close(self):
        self.closed = True
        for unsubscribe in self.unsubscribers:
            unsubscribe()
        self.unsubscribers.clear()
        if self.task is not None and not self.task.done():
            await self.task
        async with self.lock:
            for player in list(self.leases):
                await self._restore(player)
