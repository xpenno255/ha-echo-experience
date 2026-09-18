"""Stop routes must not cross Echo profiles or guess an unknown origin."""
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('stop_automation',Path(__file__).resolve().parents[1]/'stop_automation.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class StopRoutingTest(unittest.TestCase):
    def test_two_echoes_and_companion_use_their_own_groups(self):
        config=module.build([
            {'device_id':'kitchen','music_player':'media_player.kitchen','ducking':{'additional_satellites':['assist_satellite.companion']}},
            {'device_id':'bedroom','music_player':'media_player.bedroom'},
        ],[{'entity_id':'assist_satellite.companion','device_id':'companion'}])
        self.assertEqual(config['variables']['device_players'],{
            'kitchen':'media_player.kitchen','companion':'media_player.kitchen','bedroom':'media_player.bedroom'})
        self.assertEqual(config['mode'],'parallel')

    def test_unknown_companion_is_not_guessed(self):
        config=module.build([{'device_id':'kitchen','music_player':'media_player.kitchen',
                             'ducking':{'additional_satellites':['assist_satellite.missing']}}],[])
        self.assertEqual(config['variables']['device_players'],{'kitchen':'media_player.kitchen'})

    def test_shared_device_with_conflicting_targets_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'conflicting'):
            module.build([{'device_id':'shared','music_player':'media_player.kitchen'},
                          {'device_id':'shared','music_player':'media_player.bedroom'}],[])
