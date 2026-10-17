"""Live checks for Echo Experience 0.8.0 on one Echo, in the dashboard (A) or native (B) Kiosk runtime.

Usage:
  python scripts/live_native_check.py --phase A    # Echo on the Voice Satellite browser runtime
  python scripts/live_native_check.py --phase B    # Echo on Kiosk Satellite's native runtime
  python scripts/live_native_check.py --runbook    # print the Phase 3 runbook (Kiosk calls are printed, never sent)

Only text pipeline runs with device_id set (weather, time, a conversion), read-only music status, and one timer
cycle (a 2-minute timer named "echo test", cancelled immediately). Nothing plays, stops or changes volume.
The HA token is read from ~/.config/ha/agent-token (or --token-file) and never printed. Steps that change
anything (text runs refresh the Echo's screen; the timer cycle) ask first unless --yes is given. Any satellite of
the Echo that is listening, processing or responding aborts the run before the next step.
Exit code: 0 all pass, 1 a check failed, 2 aborted (pre-flight or someone mid-interaction).
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import websockets

DEFAULTS = {
    'url': 'https://homeassistant.xpennohome.uk',
    'profile': 'echo_show_8',
    'pipeline': 'Echo Home',
    'browser_satellite': 'assist_satellite.echo_show_8',
    'browser_device': '3cbf784cee34a3c4249e1cd03060b6dc',
    'native_satellite': 'assist_satellite.amzn_echo_show_8_assist_satellite',
    'native_device': 'f778d5de1d79969a9248a6d584b08e7f',
    'node': 'ks_amzn_echo_show_8',
    'hacs_repository': '1374903411',
    'branch': 'native-satellite',
    'kiosk': 'http://192.168.1.46:2324',
}
ACTIVE = {'listening', 'processing', 'responding', 'thinking', 'speaking'}
TIMER_NAME = 'echo test'


class Abort(Exception):
    pass


class HA:
    def __init__(self, url, token):
        self.url, self.token, self.next_id = url, token, 0

    async def __aenter__(self):
        self.ws = await websockets.connect(self.url.replace('https://', 'wss://').replace('http://', 'ws://') + '/api/websocket', max_size=None)
        await self.ws.recv()
        await self.ws.send(json.dumps({'type': 'auth', 'access_token': self.token}))
        if json.loads(await self.ws.recv()).get('type') != 'auth_ok':
            raise Abort('Home Assistant rejected the token')
        return self

    async def __aexit__(self, *exc):
        await self.ws.close()

    async def call(self, msg, timeout=30):
        self.next_id += 1
        mid = self.next_id
        await self.ws.send(json.dumps({**msg, 'id': mid}))
        while True:
            reply = json.loads(await asyncio.wait_for(self.ws.recv(), timeout))
            if reply.get('id') == mid and reply.get('type') == 'result':
                if not reply.get('success'):
                    raise RuntimeError((reply.get('error') or {}).get('message') or 'error')
                return reply.get('result')

    async def text_run(self, pipeline, device_id, text, timeout=90):
        """One text-only Assist run with the Echo's device context: tools called, speech, errors."""
        self.next_id += 1
        mid = self.next_id
        await self.ws.send(json.dumps({'id': mid, 'type': 'assist_pipeline/run', 'start_stage': 'intent', 'end_stage': 'intent',
                                       'pipeline': pipeline, 'device_id': device_id, 'input': {'text': text}}))
        tools, speech, kind, error = [], '', None, None
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            reply = json.loads(await asyncio.wait_for(self.ws.recv(), timeout))
            if reply.get('id') != mid:
                continue
            if reply.get('type') == 'result' and not reply.get('success'):
                return {'tools': tools, 'speech': '', 'kind': 'error', 'error': (reply.get('error') or {}).get('message')}
            if reply.get('type') != 'event':
                continue
            event = reply['event']
            if event['type'] == 'intent-progress':
                for call in ((event.get('data') or {}).get('chat_log_delta') or {}).get('tool_calls') or []:
                    tools.append((call.get('tool_name') or '').split('__')[-1])
            elif event['type'] == 'intent-end':
                response = ((event.get('data') or {}).get('intent_output') or {}).get('response') or {}
                kind = response.get('response_type')
                speech = ((response.get('speech') or {}).get('plain') or {}).get('speech') or ''
            elif event['type'] == 'error':
                error = (event.get('data') or {}).get('message')
            if event['type'] in ('run-end', 'error'):
                break
        return {'tools': tools, 'speech': speech, 'kind': kind, 'error': error}


class Checker:
    def __init__(self, ha, cfg, yes):
        self.ha, self.cfg, self.yes = ha, cfg, yes
        self.results = []

    def record(self, name, ok, detail=''):
        self.results.append((name, ok))
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f'  - {detail}' if detail else ''), flush=True)
        return ok

    def confirm(self, what):
        if self.yes:
            return True
        answer = input(f'About to {what}. Continue? [y/N] ').strip().lower()
        if answer != 'y':
            raise Abort('declined: ' + what)
        return True

    async def states(self):
        return {s['entity_id']: s for s in await self.ha.call({'type': 'get_states'})}

    async def guard(self):
        """Abort if anyone is talking to this Echo right now."""
        states = await self.states()
        busy = [e for e in (self.cfg['browser_satellite'], self.cfg['native_satellite']) if (states.get(e) or {}).get('state') in ACTIVE]
        if busy:
            raise Abort('someone is mid-interaction on ' + ', '.join(busy))
        return states

    async def snapshot(self):
        return await self.ha.call({'type': 'echo_experience/state', 'device': self.cfg['profile']})

    async def pipeline_id(self):
        listed = await self.ha.call({'type': 'assist_pipeline/pipeline/list'})
        return next(p['id'] for p in listed['pipelines'] if p['name'] == self.cfg['pipeline'])

    # ---- pre-flight ----------------------------------------------------------------------------
    async def preflight(self, phase):
        states = await self.guard()
        snap = await self.snapshot()
        info = snap.get('runtime')
        self.record('pre-flight: Echo Experience 0.8.0 is loaded', info is not None, 'state has no runtime block: still 0.7.0?' if info is None else '')
        if info is None:
            raise Abort('Echo Experience 0.8.0 is not running')
        self.record('pre-flight: no timers running or ringing', not snap['timers'] and not snap['ringing'],
                    f"{len(snap['timers'])} running, {len(snap['ringing'])} ringing")
        if snap['timers'] or snap['ringing']:
            raise Abort('a timer is running or ringing on this Echo; try again when it is idle')
        native = next((i for i in info['identities'] if i['runtime'] == 'native'), None)
        self.record('pre-flight: native identity derived', bool(native) and native['satellite'] == self.cfg['native_satellite'] and native['device_id'] == self.cfg['native_device'],
                    json.dumps(native))
        browser_state = (states.get(self.cfg['browser_satellite']) or {}).get('state')
        native_state = (states.get(self.cfg['native_satellite']) or {}).get('state')
        expected = 'dashboard' if phase == 'A' else 'native'
        live = {'A': browser_state not in (None, 'unavailable') and native_state in (None, 'unavailable'),
                'B': native_state not in (None, 'unavailable', 'unknown')}[phase]
        self.record(f'pre-flight: Echo is on the {expected} runtime', live, f'browser={browser_state} native={native_state}')
        self.record(f'pre-flight: active identity is {expected}', info['active'] == expected, json.dumps({'mode': info['mode'], 'active': info['active']}))
        if not live:
            raise Abort(f'the Echo is not on the {expected} runtime')
        return snap

    # ---- checks ----------------------------------------------------------------------------
    async def text_checks(self, pipeline):
        """The same questions from both identities: tools must exist for each (the 0.7.0 native failure)."""
        cases = [('weather', "What's the weather forecast today?", 'echo_weather'),
                 ('conversion', 'Convert 5 kilometres to miles.', 'echo_convert'),
                 ('time', 'What time is it?', None)]
        self.confirm('send text questions as the Echo (its screen will show the answers)')
        for identity, device in (('dashboard', self.cfg['browser_device']), ('native', self.cfg['native_device'])):
            for label, text, tool in cases:
                await self.guard()
                run = await self.ha.text_run(pipeline, device, text)
                missing = 'does not exist' in (run['speech'] or '') or 'does not exist' in (run['error'] or '')
                ok = run['kind'] not in (None, 'error') and not missing and (tool is None or tool in run['tools'])
                self.record(f'text {label} as {identity} device', ok, f"tools={run['tools']} speech={run['speech'][:80]!r}" + (f" error={run['error']}" if run['error'] else ''))
                if identity == 'native' and label == 'time' and ok:
                    await asyncio.sleep(1.5)
                    result = (await self.snapshot()).get('result') or {}
                    shown = result.get('view') == 'answer' and result.get('payload', {}).get('speech') == run['speech'] and time.time() - result.get('timestamp', 0) < 60
                    self.record('native answer shown on the dashboard (chat log path)', shown, f"view={result.get('view')}")

    async def music_status(self):
        """Read-only: the profile's selected player and its state. Nothing is sent to any player."""
        snap = await self.snapshot()
        states = await self.states()
        player = snap.get('music_player')
        state = (states.get(player) or {}).get('state')
        self.record('music status readable (no playback change)', bool(player) and state is not None, f'{player}={state}')

    async def timer_cycle(self, phase):
        expected = 'dashboard' if phase == 'A' else 'native'
        await self.guard()
        self.confirm(f'start a 2-minute timer named "{TIMER_NAME}" on the Echo and cancel it immediately')
        created = None
        try:
            started = await self.ha.call({'type': 'echo_experience/action', 'device': self.cfg['profile'], 'action': 'timer',
                                          'args': {'operation': 'start', 'name': TIMER_NAME, 'seconds': 120}})
            created = next((t for t in started.get('timers', []) if t['name'] == TIMER_NAME), None)
            self.record('timer start', created is not None, f"status={started.get('status')}")
            self.record(f'timer lives on the {expected} identity', bool(created) and created.get('runtime') == expected, f"runtime={(created or {}).get('runtime')}")
            listed = await self.ha.call({'type': 'echo_experience/action', 'device': self.cfg['profile'], 'action': 'timer', 'args': {'operation': 'status'}})
            self.record('timer list', any(t['name'] == TIMER_NAME for t in listed.get('timers', [])) and listed.get('ringing') == [])
            if phase == 'B':
                kiosk = await self.ha.call({'type': 'execute_script', 'sequence': [
                    {'action': f"esphome.{self.cfg['node']}_vs_list_timers", 'response_variable': 'r'}, {'stop': 'done', 'response_variable': 'r'}]})
                names = [t.get('name') for t in ((kiosk or {}).get('response') or {}).get('timers', [])]
                self.record('Kiosk lists the timer (vs_list_timers, read-only)', TIMER_NAME in names, f'kiosk timers={names}')
        finally:
            if created:
                cancelled = await self.ha.call({'type': 'echo_experience/action', 'device': self.cfg['profile'], 'action': 'timer',
                                                'args': {'operation': 'cancel', 'timer_id': created['id']}})
                self.record('timer cancel', not any(t['name'] == TIMER_NAME for t in cancelled.get('timers', [])))
        try:
            await self.ha.call({'type': 'echo_experience/action', 'device': self.cfg['profile'], 'action': 'timer', 'args': {'operation': 'dismiss'}})
            self.record('dismiss with nothing ringing is refused', False, 'dismiss unexpectedly succeeded')
        except RuntimeError as err:
            self.record('dismiss with nothing ringing is refused', 'No timer alarm is sounding' in str(err), str(err)[:80])
        device = self.cfg['native_device'] if phase == 'B' else self.cfg['browser_device']
        result = await self.ha.call({'type': 'call_service', 'domain': 'echo_experience', 'service': 'dismiss_timer',
                                     'service_data': {'device_id': device}, 'return_response': True})
        status = ((result or {}).get('response') or {}).get('status')
        self.record('dismiss_timer service: not ringing, nothing touched', status == 'not_ringing', f'status={status}')
        snap = await self.snapshot()
        self.record('post-check: no timers left', not any(t['name'] == TIMER_NAME for t in snap['timers']))

    async def native_services(self):
        services = await self.ha.call({'type': 'get_services'})
        esphome = services.get('esphome', {})
        for name in ('vs_list_timers', 'vs_cancel'):
            self.record(f"esphome.{self.cfg['node']}_{name} available", f"{self.cfg['node']}_{name}" in esphome)


RUNBOOK = """Phase 3 runbook (Echo Experience 0.8.0 on branch {branch}). Run only when no timer is running and nobody is talking.

0. Read-only baseline: get_states for {browser_satellite} and {native_satellite}; HACS repo {hacs_repository} installed_version v0.7.0.
1. Install the branch build through HACS (WebSocket, admin token):
     {{"type":"hacs/repository/download","repository":"{hacs_repository}","version":"{branch}"}}
2. Restart Core while idle:  call_service homeassistant.restart. Wait for the WebSocket to return and
   echo_experience/state {{"device":"{profile}"}} to answer with a "runtime" block.
3. Reload the Kiosk page so it loads the ?v=0.8.0 card:  call_service button.press entity_id button.amzn_echo_show_8_reload_page
4. Check Repairs (repairs/list_issues): no echo_experience setup_failed_* issues.
5. Phase A:  python scripts/live_native_check.py --phase A
   Also by voice (optional, coordinator): "what's the weather" shows the weather view; the existing 0.7.0 behaviour.
6. Switch the Echo to native (Kiosk remote admin, coordinator only; token from POST {kiosk}/api/login):
     POST {kiosk}/api/commands/vsMigrate   {{"satellite":"{browser_satellite}","groups":[]}}
   groups [] carries no settings over and rewrites no Assistant/wake-word selects (they already hold Echo Home / Okay Nabu).
   It stops the page engine, sets voice.enabled=true and voice.runtime=native, waits for HA to hold the satellite, and
   rolls back to the dashboard runtime by itself on failure. Allow ~90 s. Then wait until {native_satellite} is idle.
   If auto-detection is ambiguous mid-switch, pin it (REST, admin token):
     POST /api/config/config_entries/options/flow  {{"handler":"<echo_experience entry_id>"}}
     POST /api/config/config_entries/options/flow/<flow_id>  {{"manage_dashboard":true,"runtime_{profile}":"native"}}
   (Saving reloads Echo Experience; do it only with no timer running.)
7. Phase B:  python scripts/live_native_check.py --phase B
   Voice checks for the coordinator/user: weather, a conversion, "set a 10 second test timer" -> dashboard countdown,
   Kiosk alert pill + dashboard Finished card; "Okay Nabu, stop" -> "Timer stopped." and both alerts clear; repeat and
   tap the pill instead -> dashboard clears. Watch the answer view under the Kiosk overlay (double-render check).
8. Back to the dashboard runtime:
     POST {kiosk}/api/commands/vsRollback  {{}}
   then set the options pin back to auto if it was pinned, wait for {browser_satellite} idle, rerun --phase A.
9. Full rollback of the build (if needed): {{"type":"hacs/repository/download","repository":"{hacs_repository}","version":"v0.7.0"}},
   homeassistant.restart, press button.amzn_echo_show_8_reload_page. If the Echo is still native, run step 8 first.
"""


async def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--phase', choices=['A', 'B'])
    parser.add_argument('--runbook', action='store_true')
    parser.add_argument('--yes', action='store_true', help='do not ask before steps that change anything')
    parser.add_argument('--skip-timer', action='store_true')
    parser.add_argument('--token-file', default='~/.config/ha/agent-token')
    for key, value in DEFAULTS.items():
        parser.add_argument('--' + key.replace('_', '-'), default=value, dest=key)
    args = parser.parse_args()
    cfg = {k: getattr(args, k) for k in DEFAULTS}
    if args.runbook:
        print(RUNBOOK.format(**cfg))
        return 0
    if not args.phase:
        parser.error('--phase A|B or --runbook is required')
    token = Path(args.token_file).expanduser().read_text().strip()
    try:
        async with HA(cfg['url'], token) as ha:
            check = Checker(ha, cfg, args.yes)
            try:
                await check.preflight(args.phase)
                pipeline = await check.pipeline_id()
                await check.text_checks(pipeline)
                await check.music_status()
                if args.phase == 'B':
                    await check.native_services()
                if not args.skip_timer:
                    await check.timer_cycle(args.phase)
            except Abort as err:
                print(f'ABORT {err}')
                return 2
            failed = [n for n, ok in check.results if not ok]
            print(f"\n{len(check.results) - len(failed)}/{len(check.results)} checks passed" + (f"; failed: {', '.join(failed)}" if failed else ''))
            return 1 if failed else 0
    except Abort as err:
        print(f'ABORT {err}')
        return 2


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
