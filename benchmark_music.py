"""Read-only 20-artist benchmark, with real-advisor and deterministic replay modes.

Fixture mode runs the production resolver against a synthetic catalog, never MA
playback. Library mode calls only echo_music/search and skips unavailable works.
"""
import argparse
import asyncio
import hashlib
import importlib
import json
from pathlib import Path
import re
import sys
import time
import types
import unicodedata

HERE = Path(__file__).resolve().parent
FIXTURE_PATH = HERE / 'tests/fixtures/top20_music.json'
REPLAY_PATH = HERE / 'tests/fixtures/top20_advisor_replay.json'

# Load the actual pure resolver without bootstrapping Home Assistant.
PACKAGE = '_echo_benchmark_production'
if PACKAGE not in sys.modules:
    package = types.ModuleType(PACKAGE)
    package.__path__ = [str(HERE / 'custom_components/echo_experience')]
    sys.modules[PACKAGE] = package
core = importlib.import_module(PACKAGE + '.music')
fallback = importlib.import_module(PACKAGE + '.music_fallback')


def fold(text):
    text = unicodedata.normalize('NFKD', text.casefold())
    return ''.join(c for c in text if c.isalnum() and not unicodedata.combining(c))


def digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class FixtureCatalog:
    """An independent strict text-search adapter; no phonetic aliases or LLM."""
    def __init__(self, items):
        self.items = items
        self.by_uri = {item['uri']: item for item in items}

    async def search(self, fields):
        kind = fields['media_type'][0]
        name, artist = fold(fields['name']), fold(fields.get('artist', ''))
        items = [i for i in self.items if i['media_type'] == kind and name in fold(i['name'])]
        if artist:
            items = [i for i in items if any(artist in fold(a['name']) for a in i.get('artists', []))]
        return {kind + 's': items[:fields.get('limit', 25)]}

    async def catalog(self, kind, artist_uri=None):
        return [i for i in self.items if i['media_type'] == kind and
                (not artist_uri or any(a['uri'] == artist_uri for a in i.get('artists', [])))]


class Advisor:
    def __init__(self, mode, replay, *, agent='conversation.echo_music_resolver'):
        self.mode, self.replay, self.agent = mode, replay, agent
        self.calls = 0

    async def __call__(self, payload):
        key = digest(payload)
        if key in self.replay:
            return self.replay[key]['response']
        if self.mode == 'replay':
            raise LookupError('Missing recorded advisor response: ' + key)
        from ha_client import rest
        self.calls += 1
        result = await asyncio.to_thread(rest, '/api/services/conversation/process?return_response', {
            'agent_id': self.agent, 'text': json.dumps(payload, ensure_ascii=False), 'language': 'en',
        })
        response = result['service_response']['response']['speech']['plain']['speech']
        self.replay[key] = {'request': payload, 'response': response}
        return response


async def run_fixture(case, catalog, advisor):
    request = case['request']
    return await fallback.resolve_with_fallback(catalog.search, catalog.catalog, advisor,
        request['query'], request['media_type'], request.get('artist', ''),
        request.get('album', ''), request.get('version', ''))


def fixture_pass(case, result):
    uri = result.get('match', {}).get('uri') if result.get('status') == 'matched' else None
    if case['expected_uri'] is None:
        return result.get('status') in ('not_found', 'needs_clarification')
    return uri == case['expected_uri']


async def run_library(cases, fixture, device):
    from ha_client import rest, commands
    profile = next(p for p in json.loads((HERE / 'profiles.json').read_text())['devices'] if p['id'] == device)
    actual = []
    for kind in ('artist', 'album', 'track'):
        offset = 0
        while True:
            data = await asyncio.to_thread(rest, '/api/services/music_assistant/get_library?return_response', {
                'config_entry_id': profile['music_assistant_entry'], 'media_type': kind,
                'limit': 500, 'offset': offset,
            })
            items = data['service_response']['items']
            actual.extend(items)
            if len(items) < 500:
                break
            offset += len(items)
    by_uri = {i['uri']: i for i in fixture['items']}
    rows = []
    for case in cases:
        # Synthetic negatives/releases are fixture tests, not claims about NAS content.
        if case['expected_uri'] is None or case['category'] == 'explicit_version':
            rows.append({'id': case['id'], 'status': 'skip', 'reason': 'synthetic_constraint_case'})
            continue
        expected = by_uri[case['expected_uri']]
        kind = expected['media_type']
        by = expected.get('artists', [{}])[0].get('name', '')
        available = [i for i in actual if i['media_type'] == kind and
                     core.matches(i, expected['name'], kind, by)]
        if not available:
            rows.append({'id': case['id'], 'status': 'skip', 'reason': 'not_in_live_library'})
            continue
        started = time.monotonic()
        try:
            result = (await asyncio.to_thread(commands, {'type': 'echo_experience/action', 'device': device,
                      'action': 'music', 'args': {'action': 'search', **case['request']}}))[0]
            passed = result.get('status') == 'matched' and result['match']['uri'] in {i['uri'] for i in available}
            rows.append({'id': case['id'], 'status': 'pass' if passed else 'fail', 'result': result,
                         'seconds': round(time.monotonic() - started, 3)})
        except Exception as err:
            rows.append({'id': case['id'], 'status': 'fail', 'error': str(err)})
    return rows, sorted(i['name'] for i in actual if i['media_type'] == 'artist')


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['replay', 'advisor', 'library'], default='replay')
    parser.add_argument('--record', action='store_true', help='Write actual advisor responses for CI replay')
    parser.add_argument('--fresh', action='store_true', help='Ignore previous advisor recordings')
    parser.add_argument('--filter', default='', help='Restrict to matching case IDs')
    parser.add_argument('--device', default='echo_show_8')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.record and args.mode != 'advisor':
        parser.error('--record requires --mode advisor')
    fixture = json.loads(FIXTURE_PATH.read_text())
    cases = [c for c in fixture['cases'] if args.filter in c['id']]
    if not cases:
        parser.error('No cases matched')
    report = {'schema': 1, 'mode': args.mode, 'case_count': len(cases)}
    if args.mode == 'library':
        rows, artists = await run_library(cases, fixture, args.device)
        report['live_artists'] = artists
    else:
        replay = {} if args.fresh or not REPLAY_PATH.exists() else json.loads(REPLAY_PATH.read_text())['responses']
        advisor = Advisor(args.mode, replay)
        catalog = FixtureCatalog(fixture['items'])
        rows = []
        try:
            for index, case in enumerate(cases):
                started = time.monotonic()
                try:
                    result = await run_fixture(case, catalog, advisor)
                    rows.append({'id': case['id'], 'category': case['category'], 'status': 'pass' if fixture_pass(case, result) else 'fail',
                                 'result': result, 'seconds': round(time.monotonic() - started, 3)})
                except Exception as err:
                    rows.append({'id': case['id'], 'status': 'fail', 'error': str(err)})
                if rows[-1]['status'] == 'fail':
                    print('FAIL', json.dumps(rows[-1], ensure_ascii=False), flush=True)
                if (index + 1) % 25 == 0:
                    print(f'{index + 1}/{len(cases)} cases; {advisor.calls} live advisor calls', flush=True)
        finally:
            if args.record:
                REPLAY_PATH.write_text(json.dumps({'schema': 1, 'agent': advisor.agent,
                    'description': 'Actual music-only agent responses for deterministic regression replay. Fresh model validation uses --mode advisor --fresh.',
                    'responses': replay}, indent=2, ensure_ascii=False) + '\n')
        report['live_advisor_calls'] = advisor.calls
    report['results'] = rows
    report['totals'] = {s: sum(r['status'] == s for r in rows) for s in ('pass', 'fail', 'skip')}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'results'}, ensure_ascii=False), flush=True)
    return 1 if report['totals']['fail'] else 0


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
