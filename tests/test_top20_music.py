"""Replay real advisor responses against the production resolver and strict catalog."""
import json
import unittest

from benchmark_music import Advisor, FixtureCatalog, FIXTURE_PATH, REPLAY_PATH, fixture_pass, run_fixture


class Top20MusicTest(unittest.IsolatedAsyncioTestCase):
    async def test_top20_regression_corpus(self):
        fixture = json.loads(FIXTURE_PATH.read_text())
        replay = json.loads(REPLAY_PATH.read_text())['responses']
        catalog = FixtureCatalog(fixture['items'])
        advisor = Advisor('replay', replay)
        self.assertEqual(len(fixture['cases']), 386)
        for case in fixture['cases']:
            with self.subTest(case=case['id']):
                result = await run_fixture(case, catalog, advisor)
                self.assertTrue(fixture_pass(case, result), result)
        self.assertEqual(advisor.calls, 0)
