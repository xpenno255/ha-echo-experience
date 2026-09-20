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

    def test_bare_stop_dismisses_ringing_timer_before_music_and_explicit_music_skips_timers(self):
        config=module.build([{'device_id':'kitchen','music_player':'media_player.kitchen'}],[])
        commands=config['triggers'][0]['command']
        self.assertEqual(commands,['stop',*module.MUSIC_COMMANDS])
        self.assertFalse(any('timer' in c or 'alarm' in c or '{' in c for c in commands),'timer phrases stay with the LLM tool')
        dismiss,choose=config['actions']
        self.assertEqual(dismiss['then'][0]['action'],'echo_experience.dismiss_timer')
        self.assertIn('not music_phrase',dismiss['if'][0]['value_template'])
        self.assertTrue(dismiss['then'][0]['continue_on_error'])
        self.assertEqual(dismiss['then'][0]['data'],{'device_id':'{{ origin_device }}'})
        self.assertNotIn('timer_phrase',config['variables'])
        outcomes=[c['conditions'][0]['value_template'] for c in choose['choose']]
        self.assertEqual(outcomes,["{{ dismissal.status == 'dismissed' }}","{{ dismissal.status in ['unconfirmed', 'failed'] }}",'{{ stop_players | length > 0 }}'])
        self.assertEqual(choose['choose'][0]['sequence'],[{'set_conversation_response':'Timer stopped.'}])
        self.assertEqual(choose['choose'][1]['sequence'][0]['set_conversation_response'],"I couldn't confirm the timer alarm stopped. Tap the alert or say stop again.")
        self.assertEqual(config['variables']['dismissal'],{'status':'skipped'})

    def test_tracked_automation_matches_generator(self):
        import json
        root=Path(__file__).resolve().parents[1]
        tracked=json.loads((root/'automations/voice_music_stop.json').read_text())
        profiles=json.loads((root/'profiles.json').read_text())['devices']
        own={p['device_id'] for p in profiles}
        companions=[d for d in tracked['variables']['device_players'] if d not in own]
        registry=[{'entity_id':s,'device_id':d} for p in profiles for s,d in zip(p.get('ducking',{}).get('additional_satellites',[]),companions)]
        self.assertEqual(module.build(profiles,registry),tracked)

    def test_shared_device_with_conflicting_targets_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'conflicting'):
            module.build([{'device_id':'shared','music_player':'media_player.kitchen'},
                          {'device_id':'shared','music_player':'media_player.bedroom'}],[])
