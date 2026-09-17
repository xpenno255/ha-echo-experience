"""Behavioural checks for volume ownership, failure recovery and isolation."""
import copy
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
import unittest

# Bootstrap the installed HA imports in the same way as the existing tests.
import test_experience
from custom_components.echo_experience.ducking import DuckingManager
from custom_components.echo_experience.core import validate_profiles


class DuckingTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.now = 0
        self.states = {}
        self.calls = []
        self.fail = set()
        self.persisted = None
        self.set('assist_satellite.kitchen', 'idle')
        self.set('assist_satellite.second', 'idle')
        self.set('media_player.left', 'playing', .74)
        self.set('media_player.right', 'playing', .09)
        self.set('media_player.other_room', 'playing', .5)
        self.store = NS(async_load=AsyncMock(return_value=None), async_save=AsyncMock(side_effect=self.save))
        self.hass = NS(states=NS(get=self.states.get), services=NS(async_call=AsyncMock(side_effect=self.call)))
        self.cfg = {'enabled': True, 'players': ['media_player.left', 'media_player.right'],
                    'additional_satellites': ['assist_satellite.second'], 'volume_factor': .1,
                    'restore_delay': 1, 'max_duration': 120}
        self.manager = DuckingManager(self.hass, [{'satellite': 'assist_satellite.kitchen', 'ducking': self.cfg}], store=self.store, clock=lambda: self.now)

    def set(self, entity, state, volume=None):
        self.states[entity] = NS(state=state, attributes={} if volume is None else {'volume_level': volume})

    async def save(self, data):
        self.persisted = copy.deepcopy(data)

    async def call(self, domain, service, data, **kwargs):
        player = data['entity_id']
        self.calls.append((player, data['volume_level']))
        # Journal must already exist when any volume command leaves the integration.
        if data['volume_level'] < self.states[player].attributes.get('volume_level', 0):
            self.assertIn(player, self.persisted['volumes'])
        if player in self.fail:
            raise RuntimeError('Speaker temporarily disconnected')
        self.states[player].attributes['volume_level'] = data['volume_level']

    async def active(self, entity='assist_satellite.kitchen', state='listening'):
        self.set(entity, state)
        await self.manager.async_reconcile()

    async def idle(self, entity='assist_satellite.kitchen'):
        self.set(entity, 'idle')
        self.now += 2
        await self.manager.async_reconcile()

    async def test_ducks_once_across_voice_phases_and_restores_individual_levels(self):
        await self.active()
        self.assertEqual(self.calls, [('media_player.left', .07), ('media_player.right', .01)])
        for phase in ['processing', 'responding', 'listening', 'thinking', 'speaking']:
            await self.active(state=phase)
        self.assertEqual(len(self.calls), 2)
        await self.idle()
        self.assertEqual(self.calls[-2:], [('media_player.left', .74), ('media_player.right', .09)])
        self.assertEqual(self.manager.leases, {})
        self.assertEqual(self.states['media_player.other_room'].attributes['volume_level'], .5)

    async def test_shared_speakers_wait_until_both_satellites_finish(self):
        await self.active()
        await self.active('assist_satellite.second')
        await self.idle()
        self.assertEqual(len(self.calls), 2)
        await self.idle('assist_satellite.second')
        self.assertEqual(len(self.calls), 4)

    async def test_user_volume_change_is_preserved(self):
        await self.active()
        self.states['media_player.left'].attributes['volume_level'] = .3
        await self.idle()
        self.assertEqual(self.states['media_player.left'].attributes['volume_level'], .3)
        self.assertNotIn(('media_player.left', .74), self.calls)

    async def test_music_started_during_request_is_ducked(self):
        self.set('media_player.left', 'idle', .74)
        await self.active()
        self.assertNotIn('media_player.left', self.manager.leases)
        self.set('media_player.left', 'playing', .74)
        await self.manager.async_reconcile()
        self.assertEqual(self.states['media_player.left'].attributes['volume_level'], .07)

    async def test_idle_delay_avoids_restore_between_followups(self):
        await self.active()
        self.set('assist_satellite.kitchen', 'idle')
        self.now = .5
        await self.manager.async_reconcile()
        self.assertEqual(len(self.calls), 2)
        await self.active()
        await self.idle()
        self.assertEqual(len(self.calls), 4)

    async def test_disconnected_satellite_releases_volumes(self):
        await self.active()
        self.set('assist_satellite.kitchen', 'unavailable')
        await self.manager.async_reconcile()
        self.assertFalse(self.manager.leases)

    async def test_stuck_satellite_timeout_and_next_session(self):
        await self.active()
        self.now = 121
        await self.manager.async_reconcile()
        self.assertFalse(self.manager.leases)
        self.now = 130
        await self.manager.async_reconcile()
        self.assertEqual(len(self.calls), 4)
        await self.idle()
        await self.active()
        self.assertEqual(len(self.calls), 6)

    async def test_timeout_does_not_duck_again_on_immediate_idle(self):
        await self.active()
        self.now = 121
        await self.manager.async_reconcile()
        self.set('assist_satellite.kitchen', 'idle')
        self.now += .1
        await self.manager.async_reconcile()
        self.assertFalse(self.manager.leases)
        self.assertEqual(len(self.calls), 4)

    async def test_delayed_restore_ack_keeps_recovery_record(self):
        await self.active()
        self.hass.services.async_call = AsyncMock()  # Accepted, state not yet updated.
        await self.idle()
        self.assertTrue(self.manager.leases['media_player.left']['restoring'])
        self.set('media_player.left', 'playing', .74)
        self.set('media_player.right', 'playing', .09)
        await self.manager.async_reconcile()
        self.assertFalse(self.manager.leases)

    async def test_offline_speaker_retries_restore_when_it_returns(self):
        await self.active()
        self.set('media_player.left', 'unavailable')
        await self.idle()
        self.assertIn('media_player.left', self.manager.leases)
        self.set('media_player.left', 'idle', .07)
        await self.manager.async_reconcile()
        self.assertEqual(self.states['media_player.left'].attributes['volume_level'], .74)
        self.assertFalse(self.manager.leases)

    async def test_failed_duck_does_not_leave_other_speakers_down(self):
        self.fail.add('media_player.left')
        await self.active()
        self.fail.clear()
        await self.idle()
        self.assertEqual(self.states['media_player.left'].attributes['volume_level'], .74)
        self.assertEqual(self.states['media_player.right'].attributes['volume_level'], .09)

    async def test_unload_restores_and_preserves_recovery_for_offline_player(self):
        await self.active()
        self.set('media_player.right', 'unavailable')
        await self.manager.async_close()
        self.assertEqual(self.states['media_player.left'].attributes['volume_level'], .74)
        self.assertIn('media_player.right', self.persisted['volumes'])

    async def test_recovery_journal_restores_interrupted_session(self):
        self.manager.leases = {'media_player.left': {'original': .74, 'ducked': .07}}
        self.set('media_player.left', 'playing', .07)
        await self.manager.async_reconcile()
        self.assertEqual(self.states['media_player.left'].attributes['volume_level'], .74)
        self.assertFalse(self.manager.leases)

    async def test_muted_zero_volume_not_raised_and_paused_not_ducked(self):
        self.set('media_player.left', 'playing', 0)
        self.set('media_player.right', 'paused', .09)
        await self.active()
        self.assertFalse(self.calls)

    async def test_unconfigured_satellite_cannot_duck(self):
        self.set('assist_satellite.other_room', 'listening')
        await self.manager.async_reconcile()
        self.assertFalse(self.calls)

    def test_bad_profile_rejected(self):
        for key, value in [('volume_factor', float('nan')), ('volume_factor', 2), ('players', ['light.kitchen']), ('max_duration', 0), ('additional_satellites', ['media_player.left'])]:
            profiles = test_experience.profiles()
            profiles[0]['ducking'] = {**self.cfg, key: value}
            with self.assertRaises(ValueError):
                validate_profiles({'devices': profiles})


if __name__ == '__main__':
    unittest.main()
