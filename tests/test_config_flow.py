import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

ROOT=Path(__file__).resolve().parents[1]
if 'custom_components.echo_experience' not in sys.modules:
    spec=importlib.util.spec_from_file_location('custom_components.echo_experience',ROOT/'custom_components/echo_experience/__init__.py',submodule_search_locations=[str(ROOT/'custom_components/echo_experience')])
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
from custom_components.echo_experience.config_flow import EchoExperienceOptions
from custom_components.echo_experience.core import apply_profile_options

def devices():
    return [{'id':n,'name':n.title(),'satellite':'assist_satellite.'+n,'device_id':'device-'+n,'music_player':'media_player.'+n,'weather':'weather.home'} for n in ['kitchen','bedroom']]

class OptionsFlowTest(unittest.IsolatedAsyncioTestCase):
    """Options pick an Echo, then its music background, and keep every other stored option."""
    def setUp(self):
        self.dir=tempfile.TemporaryDirectory();self.addCleanup(self.dir.cleanup)
        self.path=Path(self.dir.name)/'echo_experience.json'
        self.path.write_text(json.dumps({'devices':devices()}))
        self.entry=NS(options={'manage_dashboard':False,'music_styles':{'kitchen':'colour'},'future_option':7})
    def flow(self):
        f=EchoExperienceOptions()
        f.hass=NS(config=NS(path=lambda name:str(Path(self.dir.name)/name)),async_add_executor_job=AsyncMock(side_effect=lambda fn,*a:fn(*a)),
                  config_entries=NS(async_get_known_entry=lambda entry_id:self.entry))
        f.handler='e1';f.flow_id='f1';f.context={}
        return f
    async def test_select_echo_then_style_preserves_dashboard_unknown_and_other_devices(self):
        f=self.flow()
        form=await f.async_step_init()
        self.assertEqual(form['step_id'],'init');self.assertFalse(form['errors'])
        schema=form['data_schema']({})
        self.assertEqual(schema,{'manage_dashboard':False,'device':'kitchen'})
        form=await f.async_step_init({'manage_dashboard':True,'device':'bedroom'})
        self.assertEqual(form['step_id'],'music_style');self.assertEqual(form['description_placeholders'],{'device':'Bedroom'})
        self.assertEqual(form['data_schema']({}),{'music_style':'wash'},'unset Echo defaults to wash')
        done=await f.async_step_music_style({'music_style':'bleed'})
        self.assertEqual(done['type'],'create_entry')
        self.assertEqual(done['data'],{'manage_dashboard':True,'music_styles':{'kitchen':'colour','bedroom':'bleed'},'future_option':7})
        self.assertEqual(self.entry.options['music_styles'],{'kitchen':'colour'},'stored options are not mutated in place')
        # Reload path: setup applies the saved options to freshly read profiles.
        p=apply_profile_options(devices(),done['data'])
        self.assertEqual({x['id']:x['music_style'] for x in p},{'kitchen':'colour','bedroom':'bleed'})
    async def test_current_style_is_the_default_and_invalid_values_are_rejected(self):
        f=self.flow()
        form=await f.async_step_init({'manage_dashboard':False,'device':'kitchen'})
        self.assertEqual(form['data_schema']({}),{'music_style':'colour'})
        self.assertEqual(sorted(form['data_schema'].schema[next(iter(form['data_schema'].schema))].config['options']),['bleed','colour','wash'])
        form=await f.async_step_music_style({'music_style':'neon'})
        self.assertEqual(form['type'],'form');self.assertEqual(form['errors'],{'music_style':'invalid_style'})
    async def test_unknown_device_is_rejected(self):
        form=await self.flow().async_step_init({'manage_dashboard':False,'device':'garage'})
        self.assertEqual((form['step_id'],form['errors']),('init',{'device':'unknown_device'}))
    async def test_malformed_stored_styles_read_as_default(self):
        self.entry.options={'music_styles':['bad']}
        f=self.flow()
        form=await f.async_step_init({'manage_dashboard':True,'device':'kitchen'})
        self.assertEqual(form['data_schema']({}),{'music_style':'wash'})
        done=await f.async_step_music_style({'music_style':'wash'})
        self.assertEqual(done['data'],{'manage_dashboard':True,'music_styles':{'kitchen':'wash'}})
    async def test_unreadable_profiles_still_allow_dashboard_toggle(self):
        self.path.write_text('not json')
        f=self.flow()
        form=await f.async_step_init()
        self.assertEqual(form['errors'],{'base':'invalid_profiles'});self.assertEqual(form['data_schema']({}),{'manage_dashboard':False})
        done=await f.async_step_init({'manage_dashboard':True})
        self.assertEqual(done['data'],{'manage_dashboard':True,'music_styles':{'kitchen':'colour'},'future_option':7})

if __name__=='__main__':unittest.main()
