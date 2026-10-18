"""Kiosk Satellite native runtime: a second (ESPHome) voice identity for the same Echo, next to the browser one.

The browser (Voice Satellite) path must behave exactly as in 0.7.0; every native path fails soft.
"""
import asyncio
import copy
import time
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock, patch

import test_experience  # noqa: F401 - bootstraps the package exactly like the existing suites
from test_experience import module
from custom_components.echo_experience import Experience, TIMER_DATA, native
from custom_components.echo_experience.core import validate_profiles, route_profile, runtime_overrides, identities
from custom_components.echo_experience.ducking import DuckingManager
from custom_components.echo_experience.stop_route import StopRoute, REPLY_TIMER, REPLY_UNCONFIRMED, REPLY_STOPPED
from custom_components.echo_experience import stop_route
from homeassistant.components.conversation import chat_log as ha_chat_log


def raw_profiles(native_ids=True):
    out = []
    for name in ['kitchen', 'bedroom']:
        p = {'id': name, 'name': name, 'satellite': 'assist_satellite.' + name, 'device_id': 'device-' + name,
             'music_player': 'media_player.' + name, 'weather': 'weather.home', 'dashboard': 'echo-home/' + name}
        if native_ids:
            p['native'] = {'satellite': f'assist_satellite.ks_{name}', 'device_id': f'esp-{name}', 'node': f'ks_{name}'}
        out.append(p)
    return out


class Timers:
    """Stand-in for core's TimerManager with the methods Echo Experience uses."""

    def __init__(self, devices=()):
        self.timers = {}
        self.handlers = {d: object() for d in devices}
        self.started = []
        self.cancel_timer = Mock(side_effect=lambda i: self.timers.pop(i))

    def is_timer_device(self, device_id):
        return device_id in self.handlers

    def start_timer(self, device_id, hours, minutes, seconds, language, name=None, conversation_command=None, conversation_agent_id=None):
        timer_id = f't{len(self.started) + 1}'
        self.started.append({'device_id': device_id, 'hours': hours, 'minutes': minutes, 'seconds': seconds, 'language': language, 'name': name})
        self.timers[timer_id] = NS(id=timer_id, name=name, device_id=device_id, seconds_left=hours * 3600 + minutes * 60 + seconds,
                                   created_seconds=hours * 3600 + minutes * 60 + seconds, is_active=True)
        return timer_id


class Base(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.profiles = validate_profiles({'devices': raw_profiles()})['devices']
        self.states = {'assist_satellite.ks_kitchen': NS(state='idle', attributes={}), 'assist_satellite.ks_bedroom': NS(state='idle', attributes={}),
                       'assist_satellite.kitchen': NS(state='unavailable', attributes={}), 'assist_satellite.bedroom': NS(state='unavailable', attributes={})}
        self.esphome = {}
        self.service_calls = []

        async def call(domain, service, data, **kw):
            self.service_calls.append((domain, service, data))
            if domain == 'esphome':
                return await self.esphome[service](data)
            return None
        self.hass = NS(data={}, config=NS(language='en'),
                       states=NS(get=lambda e: self.states.get(e), is_state=lambda e, v: getattr(self.states.get(e), 'state', None) == v),
                       bus=NS(async_fire=Mock()), services=NS(async_call=AsyncMock(side_effect=call), has_service=lambda d, s: d == 'esphome' and s in self.esphome),
                       async_create_task=asyncio.ensure_future, async_create_background_task=lambda coro, name=None: asyncio.ensure_future(coro))
        self.manager = Timers(['esp-kitchen', 'esp-bedroom', 'device-kitchen', 'device-bedroom'])
        self.hass.data[TIMER_DATA] = self.manager
        self.runtime = Experience(self.hass, {'devices': self.profiles})
        self.kitchen, self.bedroom = self.profiles

    def fired(self, key):
        return [c.args[1] for c in self.hass.bus.async_fire.call_args_list if key in c.args[1]]

    def kiosk(self, device='esp-kitchen', **data):
        self.runtime.native_timer_event(NS(data={'device_id': device, 'timer_id': 't1', 'name': 'pasta', 'total_seconds': 60, 'seconds_left': 0, 'is_active': False, **data}))


class ProfileTest(unittest.TestCase):
    def test_existing_profile_file_validates_unchanged(self):
        import json
        from pathlib import Path
        config = json.loads((Path(__file__).resolve().parents[1] / 'profiles.json').read_text())
        p = validate_profiles(config)['devices'][0]
        self.assertEqual(p['runtime'], 'auto')
        self.assertEqual([i['runtime'] for i in identities(p)], ['dashboard'], 'no native identity until derived')

    def test_both_identities_route_to_the_same_profile_and_nothing_else(self):
        p = validate_profiles({'devices': raw_profiles()})['devices']
        for key in ('device-kitchen', 'esp-kitchen'):
            self.assertEqual(route_profile(p, device_id=key)['id'], 'kitchen')
        self.assertEqual(route_profile(p, satellite='assist_satellite.ks_kitchen')['id'], 'kitchen')
        self.assertIsNone(route_profile(p, device_id='esp-stranger'))
        self.assertIsNone(route_profile(p, device_id='esp-bedroom', satellite='assist_satellite.kitchen'))

    def test_identities_must_be_unique_across_profiles(self):
        for key, value in [('satellite', 'assist_satellite.bedroom'), ('device_id', 'device-bedroom'), ('device_id', 'esp-bedroom')]:
            raw = raw_profiles()
            raw[0]['native'][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validate_profiles({'devices': raw})

    def test_invalid_native_and_runtime_rejected(self):
        for bad in [{'satellite': 'media_player.x', 'device_id': 'd'}, {'satellite': 'assist_satellite.x'}, 'native', {'satellite': 'assist_satellite.x', 'device_id': 'd', 'node': 'Bad-Name'}]:
            raw = raw_profiles();raw[0]['native'] = bad
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_profiles({'devices': raw})
        raw = raw_profiles();raw[0]['runtime'] = 'browser'
        with self.assertRaises(ValueError):validate_profiles({'devices': raw})

    def test_runtime_overrides_come_only_from_valid_option_keys(self):
        self.assertEqual(runtime_overrides({'manage_dashboard': True, 'runtime_kitchen': 'native', 'runtime_bedroom': 'nonsense', 'other': 'native'}), {'kitchen': 'native'})
        self.assertEqual(runtime_overrides(None), {})


class Registry:
    def __init__(self, entries):
        self.entities = {e.entity_id: e for e in entries}

    def async_get(self, entity_id):
        return self.entities.get(entity_id)


def entry(entity_id, platform, device_id, disabled_by=None):
    return NS(entity_id=entity_id, platform=platform, device_id=device_id, domain=entity_id.split('.')[0], disabled_by=disabled_by)


class DeriveTest(unittest.TestCase):
    def profiles(self):
        raw = raw_profiles(native_ids=False)
        raw[0]['kiosk_navigation'] = 'select.ks_kitchen_dashboard_view'
        return validate_profiles({'devices': raw})['devices']

    def derive(self, entries, profiles=None):
        profiles = profiles or self.profiles()
        with patch('homeassistant.helpers.entity_registry.async_get', lambda hass: Registry(entries)):
            skipped = native.derive_identities(NS(), profiles)
        return profiles, skipped

    def test_native_identity_comes_from_the_kiosk_device(self):
        profiles, skipped = self.derive([entry('select.ks_kitchen_dashboard_view', 'esphome', 'esp-kitchen'),
                                         entry('assist_satellite.ks_kitchen', 'esphome', 'esp-kitchen'),
                                         entry('assist_satellite.kitchen', 'voice_satellite', 'device-kitchen'),
                                         entry('assist_satellite.other', 'esphome', 'esp-other')])
        self.assertEqual(profiles[0]['native'], {'satellite': 'assist_satellite.ks_kitchen', 'device_id': 'esp-kitchen', 'derived': True})
        self.assertEqual(set(skipped), {'bedroom'}, 'a profile without Kiosk entities stays dashboard-only')

    def test_ambiguous_or_foreign_devices_stay_dashboard_only(self):
        cases = {
            'two satellites': [entry('select.ks_kitchen_dashboard_view', 'esphome', 'esp-kitchen'), entry('assist_satellite.a', 'esphome', 'esp-kitchen'), entry('assist_satellite.b', 'esphome', 'esp-kitchen')],
            'disabled': [entry('select.ks_kitchen_dashboard_view', 'esphome', 'esp-kitchen'), entry('assist_satellite.a', 'esphome', 'esp-kitchen', disabled_by='user')],
            'not esphome': [entry('select.ks_kitchen_dashboard_view', 'template', 'esp-kitchen'), entry('assist_satellite.a', 'esphome', 'esp-kitchen')],
            'none': [entry('select.ks_kitchen_dashboard_view', 'esphome', 'esp-kitchen')],
        }
        for label, entries in cases.items():
            with self.subTest(label):
                profiles, skipped = self.derive(entries)
                self.assertNotIn('native', profiles[0]);self.assertIn('kitchen', skipped)

    def test_conflicting_derivation_is_dropped(self):
        profiles = self.profiles()
        profiles[1]['native'] = {'satellite': 'assist_satellite.ks_kitchen', 'device_id': 'esp-elsewhere'}
        profiles, skipped = self.derive([entry('select.ks_kitchen_dashboard_view', 'esphome', 'esp-kitchen'), entry('assist_satellite.ks_kitchen', 'esphome', 'esp-kitchen')], profiles)
        self.assertNotIn('native', profiles[0]);self.assertIn('Duplicate', skipped['kitchen'])

    def test_explicit_identity_is_kept_and_missing_registry_fails_soft(self):
        raw = raw_profiles()
        profiles = validate_profiles({'devices': raw})['devices']
        with patch('homeassistant.helpers.entity_registry.async_get', side_effect=KeyError('entity_registry')):
            native.derive_identities(NS(), profiles)
        self.assertEqual(profiles[0]['native']['device_id'], 'esp-kitchen')
        profiles = self.profiles()
        with patch('homeassistant.helpers.entity_registry.async_get', side_effect=KeyError('entity_registry')):
            self.assertEqual(set(native.derive_identities(NS(), profiles)), {'kitchen', 'bedroom'})


class GatingTest(Base):
    async def instance(self, device_id):
        self.hass.config_entries = NS(async_entries=Mock(return_value=[]))
        return await module.ExperienceAPI(self.hass, self.runtime).async_get_api_instance(NS(device_id=device_id))

    async def test_tools_for_both_identities_of_an_echo_only(self):
        for device in ('device-kitchen', 'esp-kitchen', 'esp-bedroom'):
            with self.subTest(device=device):
                self.assertIn('echo_weather', {t.name for t in (await self.instance(device)).tools})
        self.assertEqual((await self.instance('esp-stranger')).tools, [])
        self.assertEqual((await self.instance(None)).tools, [])

    async def test_weather_tool_publishes_to_the_asking_echo(self):
        tools = (await self.instance('esp-bedroom')).tools
        tool = next(t for t in tools if t.name == 'echo_show')
        await tool.async_call(self.hass, NS(tool_name='echo_show', tool_args={'view': 'timers'}), NS(context=None, device_id='esp-bedroom'))
        self.assertEqual(self.hass.bus.async_fire.call_args.args[1]['device'], 'bedroom')


class TimerStartTest(Base):
    async def start(self, origin=None, profile=None):
        return await self.runtime.execute(profile or self.kitchen, 'timer', {'operation': 'start', 'name': 'Echo test timer', 'seconds': 120}, origin=origin)

    def voice_satellite_calls(self):
        return [c for c in self.service_calls if c[0] == 'voice_satellite']

    async def test_native_origin_starts_on_the_kiosk_through_core(self):
        result = await self.start(origin='esp-kitchen')
        self.assertEqual(self.manager.started, [{'device_id': 'esp-kitchen', 'hours': 0, 'minutes': 2, 'seconds': 0, 'language': 'en', 'name': 'echo test'}])
        self.assertEqual(self.voice_satellite_calls(), [])
        self.assertEqual([t['name'] for t in result['timers']], ['echo test'])

    async def test_dashboard_origin_uses_voice_satellite_exactly_as_before(self):
        async def vs(domain, service, data, **kw):
            self.service_calls.append((domain, service, data))
            self.manager.timers['b1'] = NS(id='b1', name=data['name'], device_id='device-kitchen', seconds_left=120, created_seconds=120, is_active=True)
        self.hass.services.async_call.side_effect = vs
        await self.start(origin='device-kitchen')
        self.assertEqual(self.service_calls, [('voice_satellite', 'start_timer', {'entity_id': 'assist_satellite.kitchen', 'name': 'echo test', 'hours': 0, 'minutes': 2, 'seconds': 0})])
        self.assertEqual(self.manager.started, [])

    async def test_card_start_follows_the_active_identity(self):
        # auto: native while its satellite is up and holds a timer handler
        await self.start()
        self.assertEqual(self.manager.started[-1]['device_id'], 'esp-kitchen')
        # native satellite unavailable: the browser identity
        self.states['assist_satellite.ks_kitchen'].state = 'unavailable'
        self.assertEqual(self.runtime.active_identity(self.kitchen)['runtime'], 'dashboard')
        self.states['assist_satellite.ks_kitchen'].state = 'idle';del self.manager.handlers['esp-kitchen']
        self.assertEqual(self.runtime.active_identity(self.kitchen)['runtime'], 'dashboard', 'no timer handler yet: not native')

    async def test_override_beats_profile_file_beats_auto(self):
        self.assertEqual(self.runtime.timer_identity(self.kitchen, 'device-kitchen')['runtime'], 'dashboard', 'auto follows the asking satellite')
        self.runtime.overrides = {'kitchen': 'native'}
        self.states['assist_satellite.ks_kitchen'].state = 'unavailable'
        self.assertEqual(self.runtime.timer_identity(self.kitchen, 'device-kitchen')['runtime'], 'native', 'a pin overrides origin and availability')
        self.kitchen['runtime'] = 'native';self.runtime.overrides = {'kitchen': 'dashboard'}
        self.states['assist_satellite.ks_kitchen'].state = 'idle'
        self.assertEqual(self.runtime.timer_identity(self.kitchen, 'esp-kitchen')['runtime'], 'dashboard', 'the options pin beats the file')
        self.runtime.overrides = {'kitchen': 'auto'}
        self.assertEqual(self.runtime.timer_identity(self.kitchen)['runtime'], 'native', 'auto in options defers to the file')
        self.assertEqual(self.runtime.snapshot(self.kitchen)['runtime']['mode'], 'native')

    async def test_native_failures_are_tool_errors_not_crashes(self):
        self.manager.handlers.pop('esp-kitchen')
        self.runtime.overrides = {'kitchen': 'native'}
        with self.assertRaisesRegex(ValueError, 'not connected'):await self.start()
        self.hass.data[TIMER_DATA] = NS(timers={}, handlers={'esp-kitchen': 1})
        with self.assertRaisesRegex(ValueError, 'not supported'):await self.start()
        tool = module.ActionTool(self.runtime, self.kitchen, 'echo_timer', '', {'operation': str, 'seconds': int, 'name': str})
        result = (await tool.async_call(self.hass, NS(tool_args={'operation': 'start', 'seconds': 60, 'name': 'x'}), NS(context=None, device_id='esp-kitchen'))).data
        self.assertFalse(result['retryable']);self.assertIn('not supported', result['error'])

    async def test_list_and_cancel_span_both_identities(self):
        await self.start(origin='esp-kitchen')
        self.manager.timers['b1'] = NS(id='b1', name='roast', device_id='device-kitchen', seconds_left=50, created_seconds=60, is_active=True)
        self.manager.timers['x1'] = NS(id='x1', name='bed', device_id='esp-bedroom', seconds_left=50, created_seconds=60, is_active=True)
        status = await self.runtime.execute(self.kitchen, 'timer', {'operation': 'status'})
        self.assertEqual(sorted(t['name'] for t in status['timers']), ['echo test', 'roast'])
        await self.runtime.execute(self.kitchen, 'timer', {'operation': 'cancel', 'name': 'echo test'})
        self.assertEqual(sorted(self.manager.timers), ['b1', 'x1'])
        with self.assertRaisesRegex(ValueError, 'does not belong'):await self.runtime.execute(self.kitchen, 'timer', {'operation': 'cancel', 'timer_id': 'x1'})


class KioskTimerEventTest(Base):
    async def test_native_timer_events_drive_the_screen_hold(self):
        self.runtime.screen_hold = NS(schedule=Mock())
        self.kiosk(event_type='started', seconds_left=60, is_active=True)
        self.kiosk(event_type='dismissed')
        self.assertEqual([c.args[0]['id'] for c in self.runtime.screen_hold.schedule.call_args_list], ['kitchen'] * 3, 'start, then dismissal (forget and the event)')
        self.runtime.screen_hold.schedule.reset_mock();self.kiosk(device='esp-unknown', event_type='started')
        self.runtime.screen_hold.schedule.assert_not_called()

    async def test_events_become_dashboard_updates_for_their_echo_only(self):
        self.kiosk(event_type='started', seconds_left=60, is_active=True)
        event = self.hass.bus.async_fire.call_args.args[1]
        self.assertEqual((event['device'], event['timer_event']['event_type']), ('kitchen', 'started'))
        self.kiosk(event_type='finished')
        self.assertEqual([(t['id'], t['runtime']) for t in self.runtime.ringing_timers(self.kitchen)], [('t1', 'native')])
        self.assertEqual(self.runtime.ringing_timers(self.bedroom), [])
        self.kiosk(event_type='dismissed')
        self.assertEqual(self.runtime.ringing_timers(self.kitchen), [])
        self.assertEqual(self.hass.bus.async_fire.call_args.args[1]['ringing'], [])

    async def test_foreign_and_browser_device_ids_are_ignored(self):
        self.kiosk(device='esp-stranger', event_type='finished')
        self.kiosk(device='device-kitchen', event_type='finished')
        self.kiosk(device=None, event_type='finished')
        self.hass.bus.async_fire.assert_not_called()
        self.assertEqual(self.runtime.ringing_timers(self.kitchen), [])

    async def test_browser_timer_event_still_records_dashboard_ringing(self):
        self.runtime.timer_event(NS(data={'entity_id': 'assist_satellite.kitchen', 'event_type': 'finished', 'timer_id': 'b1', 'name': 'Pasta', 'total_seconds': 60}))
        self.assertEqual(self.runtime.ringing_timers(self.kitchen)[0]['runtime'], 'dashboard')


class NativeDismissTest(Base):
    def kiosk_services(self, ringing=('t1',), dismiss=True, list_fails=False):
        self.listed = 0
        async def list_timers(data):
            self.listed += 1
            if list_fails:raise RuntimeError('kiosk offline')
            return {'timers': [{'timer_id': t, 'name': 'pasta', 'finished': True} for t in self.ringing_now] + [{'timer_id': 'r9', 'finished': False}]}
        async def cancel(data):
            if dismiss:
                for t in list(self.ringing_now):
                    self.kiosk(event_type='dismissed', timer_id=t)
                self.ringing_now = []
        self.ringing_now = list(ringing)
        self.esphome.update({'ks_kitchen_vs_list_timers': list_timers, 'ks_kitchen_vs_cancel': cancel})

    def cancels(self):
        return [c for c in self.service_calls if c[1] == 'ks_kitchen_vs_cancel']

    async def test_stop_while_ringing_silences_through_the_kiosk(self):
        self.kiosk_services();self.kiosk(event_type='finished')
        result = await self.runtime.execute(self.kitchen, 'timer', {'operation': 'cancel'})
        self.assertEqual((result['status'], result['dismissed']), ('dismissed', ['pasta']))
        self.assertEqual(len(self.cancels()), 1);self.assertEqual(self.runtime.ringing_timers(self.kitchen), [])
        self.assertEqual(self.fired('dismiss'), [], 'no browser dismissal request for a native alarm')

    async def test_kiosk_silences_every_ringing_timer_and_says_so(self):
        self.kiosk_services(ringing=('t1', 't2'))
        self.kiosk(event_type='finished');self.kiosk(event_type='finished', timer_id='t2', name='eggs')
        result = await self.runtime.execute(self.kitchen, 'timer', {'operation': 'dismiss', 'name': 'pasta', 'timer_id': 't1'})
        self.assertEqual(result['also_silenced'], ['eggs']);self.assertEqual(self.runtime.ringing_timers(self.kitchen), [])

    async def test_nothing_ringing_on_the_kiosk_never_calls_vs_cancel(self):
        # vs_cancel without a ringing alert would end the very turn that asked to stop.
        self.kiosk_services(ringing=());self.kiosk(event_type='finished')
        self.assertEqual(await self.runtime.dismiss_for_device('esp-kitchen'), {'status': 'not_ringing', 'timers': ['pasta']})
        self.assertEqual(self.cancels(), []);self.assertEqual(self.runtime.ringing_timers(self.kitchen), [])

    async def test_unconfirmed_outcomes_keep_the_alarm(self):
        self.runtime.dismiss_timeout = 0.05
        for label, kwargs in [('no event, still ringing', {'dismiss': False}), ('list fails', {'list_fails': True})]:
            with self.subTest(label):
                self.runtime.ringing.clear();self.kiosk_services(**kwargs);self.kiosk(event_type='finished')
                self.assertEqual((await self.runtime.dismiss_for_device('esp-kitchen'))['status'], 'unconfirmed')
                self.assertEqual([t['id'] for t in self.runtime.ringing_timers(self.kitchen)], ['t1'])
        self.esphome.clear()
        self.assertEqual((await self.runtime.dismiss_for_device('esp-kitchen'))['status'], 'unconfirmed', 'native runtime not running')
        self.assertEqual(self.runtime.native_waiters, [])

    async def test_missed_event_is_confirmed_by_the_kiosk_list(self):
        self.runtime.dismiss_timeout = 0.05
        self.kiosk_services(dismiss=False);self.kiosk(event_type='finished')
        async def cancel(data):self.ringing_now = []
        self.esphome['ks_kitchen_vs_cancel'] = cancel
        self.assertEqual((await self.runtime.dismiss_for_device('esp-kitchen'))['status'], 'dismissed')

    async def test_bare_stop_from_the_native_satellite(self):
        self.kiosk_services();self.kiosk(event_type='finished')
        registry = NS(async_get=lambda key: {'assist_satellite.ks_kitchen': NS(device_id='esp-kitchen')}.get(key))
        route = StopRoute(self.hass, self.runtime)
        handlers = []
        route.register = lambda sentences, handler: handlers.append(handler) or (lambda: None)
        with patch.object(stop_route.er, 'async_get', lambda hass: registry), patch.object(stop_route.ir, 'async_delete_issue', lambda *a: None):
            self.runtime.device_of = lambda e: None
            self.assertTrue(await route.async_start())
            self.assertEqual(route.owners['esp-kitchen'], 'kitchen')
            reply = await handlers[0](NS(text='stop', satellite_id='assist_satellite.ks_kitchen', device_id=None, context=NS(user_id=None)), None)
        self.assertEqual(reply, REPLY_TIMER);self.assertEqual(len(self.cancels()), 1)


    async def test_browser_ringing_still_uses_the_card_protocol(self):
        self.kiosk_services()
        self.runtime.timer_event(NS(data={'entity_id': 'assist_satellite.kitchen', 'event_type': 'finished', 'timer_id': 'b1', 'name': 'Roast'}))
        async def card():
            for _ in range(50):
                await asyncio.sleep(0)
                if self.fired('dismiss'):
                    request = self.fired('dismiss')[-1]['dismiss']
                    self.assertEqual(request['timers'], [{'id': 'b1', 'name': 'Roast'}])
                    self.runtime.display_report(self.kitchen, {'request': request['request'], 'timers': ['b1'], 'present': True, 'dismissed': True});return
            raise AssertionError('no card request')
        reporter = asyncio.ensure_future(card())
        self.assertEqual(await self.runtime.dismiss_for_device('device-kitchen'), {'status': 'dismissed', 'timers': ['Roast']})
        await reporter
        self.assertEqual(self.cancels(), [], 'a browser alarm never reaches the Kiosk services')

    async def test_mixed_runtimes_are_each_silenced_where_they_ring(self):
        self.runtime.dismiss_timeout = 0.05
        self.kiosk_services();self.kiosk(event_type='finished')
        self.runtime.timer_event(NS(data={'entity_id': 'assist_satellite.kitchen', 'event_type': 'finished', 'timer_id': 'b1', 'name': 'Roast'}))
        result = await self.runtime.dismiss_for_device('device-kitchen')
        self.assertEqual(result['status'], 'unconfirmed', 'the browser card never answered')
        self.assertEqual(len(self.cancels()), 1)
        self.assertEqual([t['id'] for t in self.runtime.ringing_timers(self.kitchen)], ['b1'])


class SetupWiringTest(unittest.IsolatedAsyncioTestCase):
    """async_setup_entry with no registries or chat log available still loads and listens for Kiosk events."""
    asyncSetUp = test_experience.SetupTest.asyncSetUp

    async def test_native_wiring_is_soft(self):
        self.entry.options = {'manage_dashboard': False, 'runtime_echo_show_8': 'native'}
        self.assertTrue(await module.async_setup_entry(self.hass, self.entry))
        listened = [c.args[0] for c in self.hass.bus.async_listen.call_args_list]
        self.assertEqual(listened, ['voice_satellite_chat', 'voice_satellite_timer', native.TIMER_EVENT])
        runtime = self.hass.data[module.DOMAIN]
        self.assertEqual(runtime.overrides, {'echo_show_8': 'native'})
        self.assertIsInstance(runtime.turns, native.TurnWatcher)
        self.assertEqual([i['runtime'] for i in identities(runtime.profiles[0])], ['dashboard'], 'no registry: dashboard only')
        self.assertEqual(self.issues, {})
        for unload in self.unloads:unload()
        self.assertTrue(runtime.turns.closed)


class ConvertAliasTest(Base):
    """Models copying basic_utilities.unit_convert send amount instead of value (seen live, about 1 in 5 runs)."""

    async def convert(self, args):
        self.hass.config_entries = NS(async_entries=Mock(return_value=[]))
        tools = (await module.ExperienceAPI(self.hass, self.runtime).async_get_api_instance(NS(device_id='esp-kitchen'))).tools
        tool = next(t for t in tools if t.name == 'echo_convert')
        return tool, (await tool.async_call(self.hass, NS(tool_name='echo_convert', tool_args=args), NS(context=None, device_id='esp-kitchen'))).data

    async def test_amount_is_accepted_as_value_with_the_same_coercion(self):
        for amount in (5, 5.0, '5', ' 5 '):
            with self.subTest(amount=amount):
                tool, result = await self.convert({'amount': amount, 'from_unit': 'km', 'to_unit': 'miles'})
                self.assertAlmostEqual(result['result'], 3.1068559612, places=8)
                self.assertEqual(result['value'], 5.0)

    async def test_value_wins_and_bad_amounts_still_fail_validation(self):
        tool, result = await self.convert({'value': 2, 'amount': 9, 'from_unit': 'kg', 'to_unit': 'g'})
        self.assertEqual(result['result'], 2000, 'the declared name wins')
        tool, result = await self.convert({'amount': 'lots', 'from_unit': 'kg', 'to_unit': 'g'})
        self.assertIn('Invalid arguments', result['error']);self.assertFalse(result['retryable'])
        tool, result = await self.convert({'from_unit': 'kg', 'to_unit': 'g'})
        self.assertIn('Invalid arguments', result['error'])
        self.assertNotIn('amount', str(tool.parameters.schema), 'the alias is accepted, never advertised')
        self.assertIn('value (the number to convert)', tool.description)
        self.assertEqual(module.ActionTool(self.runtime, self.kitchen, 'echo_show', '', {'view': str}).unalias({'amount': 1}), {'amount': 1}, 'only tools that declare aliases map them')


class ChatLogTest(Base):
    """Native turns: the answer comes from the conversation's chat log, tied to the Echo when its tools are built."""

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.hass.config_entries = NS(async_entries=Mock(return_value=[]))
        self.runtime.turns = native.TurnWatcher(self.hass, self.runtime.show_reply)
        patcher = patch.object(native, 'TURN_POLL', 0.001);patcher.start();self.addCleanup(patcher.stop)
        self.addCleanup(self.runtime.turns.close)

    async def ask(self, device_id, conversation_id, question='what is the weather'):
        log = NS(conversation_id=conversation_id, content=[NS(role='system', content=''), NS(role='user', content=question)])
        token = ha_chat_log.current_chat_log.set(log)
        try:
            await module.ExperienceAPI(self.hass, self.runtime).async_get_api_instance(NS(device_id=device_id))
        finally:
            ha_chat_log.current_chat_log.reset(token)
        return log

    async def settle(self):
        for _ in range(20):
            await asyncio.sleep(0.002)

    def answers(self):
        return [(e['device'], e['result']['view'], e['result']['payload']) for e in self.fired('result')]

    async def test_native_answer_is_shown_on_its_echo(self):
        log = await self.ask('esp-kitchen', 'c1', 'what time is it')
        log.content.append(NS(role='assistant', content='It is ten past two.', tool_calls=None))
        await self.settle()
        self.assertEqual(self.answers(), [('kitchen', 'answer', {'speech': 'It is ten past two.', 'question': 'what time is it'})])
        self.assertEqual(self.runtime.turns.turns, {}, 'the turn is forgotten once shown')

    async def test_tool_turn_adds_speech_to_the_tool_view(self):
        log = await self.ask('esp-kitchen', 'c1')
        log.content.append(NS(role='assistant', content=None, tool_calls=[NS(tool_name='echo-experience__echo_weather')]))
        await self.runtime.publish(self.kitchen, 'weather', {'period': 'today'}, wake=False)
        log.content.append(NS(role='tool_result', tool_name='echo-experience__echo_weather', content=None))
        log.content.append(NS(role='assistant', content='Sunny, 12 degrees.', tool_calls=None))
        await self.settle()
        self.assertEqual(self.answers()[-1], ('kitchen', 'weather', {'period': 'today', 'speech': 'Sunny, 12 degrees.', 'question': 'what is the weather'}))

    async def test_timer_replies_are_not_shown_as_answers(self):
        log = await self.ask('esp-kitchen', 'c1', 'set a pasta timer')
        log.content.append(NS(role='assistant', content=None, tool_calls=[NS(tool_name='echo-experience__echo_timer')]))
        log.content.append(NS(role='assistant', content='Pasta timer set.', tool_calls=None))
        await self.settle()
        self.assertEqual(self.answers(), [])

    async def test_browser_and_foreign_conversations_are_ignored(self):
        for device, conversation in [('device-kitchen', 'browser'), ('esp-stranger', 'foreign'), (None, 'none')]:
            log = await self.ask(device, conversation)
            log.content.append(NS(role='assistant', content='Hello', tool_calls=None))
        await self.settle()
        self.assertEqual(self.answers(), [], 'browser turns keep voice_satellite_chat; others are not ours')
        self.assertEqual(self.runtime.turns.turns, {})

    async def test_two_concurrent_satellites_stay_separate(self):
        kitchen = await self.ask('esp-kitchen', 'ck', 'kitchen question')
        bedroom = await self.ask('esp-bedroom', 'cb', 'bedroom question')
        bedroom.content.append(NS(role='assistant', content='Bedroom answer', tool_calls=None))
        await self.settle()
        kitchen.content.append(NS(role='assistant', content='Kitchen answer', tool_calls=None))
        await self.settle()
        self.assertEqual([(d, p['speech'], p['question']) for d, v, p in self.answers()],
                         [('bedroom', 'Bedroom answer', 'bedroom question'), ('kitchen', 'Kitchen answer', 'kitchen question')])

    async def test_follow_up_turn_replaces_the_previous_one(self):
        log = await self.ask('esp-kitchen', 'c1', 'first')
        log.content.append(NS(role='user', content='second'))
        token = ha_chat_log.current_chat_log.set(log)
        try:await module.ExperienceAPI(self.hass, self.runtime).async_get_api_instance(NS(device_id='esp-kitchen'))
        finally:ha_chat_log.current_chat_log.reset(token)
        log.content.append(NS(role='assistant', content='Second answer', tool_calls=None))
        await self.settle()
        self.assertEqual([p['question'] for d, v, p in self.answers()], ['second'])

    async def test_no_chat_log_context_or_module_fails_soft(self):
        await module.ExperienceAPI(self.hass, self.runtime).async_get_api_instance(NS(device_id='esp-kitchen'))
        self.assertEqual(self.runtime.turns.turns, {})
        with patch.object(native, 'current_chat_log', side_effect=RuntimeError('moved')):
            tools = (await module.ExperienceAPI(self.hass, self.runtime).async_get_api_instance(NS(device_id='esp-kitchen'))).tools
        self.assertIn('echo_weather', {t.name for t in tools}, 'tools still offered')

    async def test_browser_chat_event_path_is_unchanged(self):
        self.runtime.chat(NS(data={'entity_id': 'assist_satellite.kitchen', 'tts_text': 'Hi there', 'stt_text': 'hello'}))
        await self.settle()
        self.assertEqual(self.answers(), [('kitchen', 'answer', {'speech': 'Hi there', 'question': 'hello'})])


class CompanionsTest(Base):
    async def test_ducking_watches_both_identities(self):
        self.kitchen['ducking'] = {'enabled': True, 'players': ['media_player.sonos'], 'additional_satellites': ['assist_satellite.voice_pe'],
                                   'volume_factor': .1, 'restore_delay': 1, 'max_duration': 120}
        manager = DuckingManager(self.hass, [self.kitchen], store=NS())
        self.assertEqual(set(manager.sources), {'assist_satellite.kitchen', 'assist_satellite.ks_kitchen', 'assist_satellite.voice_pe'})

    async def test_websocket_access_accepts_either_satellite(self):
        self.hass.data[module.DOMAIN] = self.runtime
        allowed = {'assist_satellite.ks_kitchen'}
        connection = NS(user=NS(permissions=NS(check_entity=lambda e, policy: e in allowed)))
        self.assertIs(module.access(self.hass, connection, 'kitchen', module.POLICY_READ)[1], self.kitchen)
        allowed.clear()
        with self.assertRaisesRegex(ValueError, 'Access denied'):module.access(self.hass, connection, 'kitchen', module.POLICY_READ)

    async def test_dismiss_service_checks_the_calling_identity(self):
        user = NS(permissions=NS(check_entity=Mock(return_value=True)))
        self.hass.auth = NS(async_get_user=AsyncMock(return_value=user))
        await module.dismiss_timer_service(self.hass, self.runtime, NS(data={'device_id': 'esp-kitchen'}, context=NS(user_id='u1')))
        user.permissions.check_entity.assert_called_once_with('assist_satellite.ks_kitchen', module.POLICY_CONTROL)

    async def test_options_flow_offers_one_runtime_pin_per_profile(self):
        from custom_components.echo_experience.config_flow import EchoExperienceOptions
        flow = EchoExperienceOptions()
        flow.hass = NS(data={'echo_experience': self.runtime})
        with patch.object(EchoExperienceOptions, 'config_entry', NS(options={'manage_dashboard': False, 'runtime_kitchen': 'native'}), create=True):
            form = await flow.async_step_init()
        schema = form['data_schema']
        self.assertEqual(schema({}), {'manage_dashboard': False, 'runtime_kitchen': 'native', 'runtime_bedroom': 'auto'})
        import voluptuous as vol
        with self.assertRaises(vol.Invalid):schema({'runtime_kitchen': 'browser'})


if __name__ == '__main__':
    unittest.main()
