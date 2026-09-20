"""The integration may only write a dashboard it can prove it generated, and never through a second collection."""
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch
import unittest

ROOT=Path(__file__).resolve().parents[1]
if 'custom_components.echo_experience' not in sys.modules:
    spec=importlib.util.spec_from_file_location('custom_components.echo_experience',ROOT/'custom_components/echo_experience/__init__.py',submodule_search_locations=[str(ROOT/'custom_components/echo_experience')])
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
from custom_components.echo_experience import dashboard, frontend
import json

PROFILES=[{'id':'echo_show_8','name':'Kitchen Echo'}]
LEGACY=json.loads('''{"title": "Echo Home","views": [{"title": "Kitchen Echo","path": "echo_show_8","type": "panel","cards": [{"type": "custom:echo-experience-card","device": "echo_show_8"}]},{"title": "Kitchen Echo Screensaver","path": "echo_show_8-screensaver","type": "panel","subview": true,"cards": [{"type": "custom:echo-experience-card","device": "echo_show_8","ambient": true}]}]}''')

class FakeStore:
    data={}
    def __init__(self,hass,version,key):self.key=key
    async def async_load(self):return FakeStore.data.get(self.key)
    async def async_save(self,value):FakeStore.data[self.key]=value

class Dash:
    def __init__(self,config,mode='storage'):
        self.config=config;self.mode=mode;self.saved=[]
    async def async_load(self,force):return self.config
    async def async_save(self,config):self.saved.append(config);self.config=config

class DashboardTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        FakeStore.data={}
        self.issues={}
        patch.object(dashboard,'Store',FakeStore).start();self.addCleanup(patch.stopall)
        patch.object(dashboard.ir,'async_create_issue',lambda hass,domain,key,**kw:self.issues.__setitem__(key,kw)).start()
        patch.object(dashboard.ir,'async_delete_issue',lambda hass,domain,key:self.issues.pop(key,None)).start()
    def hass(self,dash):
        return NS(data={'lovelace':NS(dashboards={'echo-home':dash} if dash else {})})
    async def test_generated_config_matches_the_retired_deploy_script_plus_marker(self):
        self.assertEqual(dashboard.legacy_config(PROFILES),LEGACY)
        built=dashboard.build_config(PROFILES,'0.6.0')
        self.assertEqual({k:v for k,v in built.items() if k!=dashboard.MARKER},LEGACY);self.assertEqual(built[dashboard.MARKER],'0.6.0')
    async def test_adopts_a_0_5_1_dashboard_by_exact_equality_and_backs_it_up(self):
        dash=Dash(json.loads(json.dumps(LEGACY)))
        self.assertEqual(await dashboard.async_manage(self.hass(dash),PROFILES,'0.6.0'),'saved')
        self.assertEqual(dash.saved[0][dashboard.MARKER],'0.6.0')
        self.assertEqual(FakeStore.data[dashboard.BACKUPS_KEY]['backups'],[LEGACY])
        self.assertEqual(FakeStore.data[dashboard.STORE_KEY]['config'],dash.config)
    async def test_hand_edited_dashboard_is_left_alone_even_with_marker(self):
        edited=dashboard.build_config(PROFILES,'0.6.0');edited['views'].append({'title':'Mine','path':'mine','cards':[]})
        dash=Dash(edited)
        self.assertEqual(await dashboard.async_manage(self.hass(dash),PROFILES,'0.6.1'),'hand_edited')
        self.assertEqual(dash.saved,[]);self.assertIn('dashboard_hand_edited',self.issues)
        unrelated=Dash({'title':'Other','views':[{'title':'Heating','cards':[]}]})
        self.assertEqual(await dashboard.async_manage(self.hass(unrelated),PROFILES,'0.6.0'),'hand_edited')
    async def test_version_bump_alone_rewrites_and_rotates_backups(self):
        dash=Dash(json.loads(json.dumps(LEGACY)))
        h=self.hass(dash)
        await dashboard.async_manage(h,PROFILES,'0.6.0')
        for v in ['0.6.1','0.6.2','0.6.3','0.6.4','0.6.5','0.6.6']:
            self.assertEqual(await dashboard.async_manage(h,PROFILES,v),'saved')
        self.assertEqual(len(FakeStore.data[dashboard.BACKUPS_KEY]['backups']),dashboard.KEEP)
        self.assertEqual(await dashboard.async_manage(h,PROFILES,'0.6.6'),'unchanged')
    async def test_missing_yaml_and_disabled_cases_never_write(self):
        self.assertEqual(await dashboard.async_manage(self.hass(None),PROFILES,'0.6.0'),'missing');self.assertIn('dashboard_missing',self.issues)
        yaml=Dash(LEGACY,mode='yaml')
        self.assertEqual(await dashboard.async_manage(self.hass(yaml),PROFILES,'0.6.0'),'yaml');self.assertEqual(yaml.saved,[])
        dash=Dash({'title':'Other','views':[]})
        self.assertEqual(await dashboard.async_manage(self.hass(dash),PROFILES,'0.6.0',enabled=False),'disabled');self.assertEqual(self.issues,{})
    async def test_no_dashboards_collection_is_ever_instantiated(self):
        src=(ROOT/'custom_components/echo_experience/dashboard.py').read_text()
        self.assertNotIn('DashboardsCollection(',src)
    async def test_read_failure_fails_closed_without_writing(self):
        dash=Dash(LEGACY);dash.async_load=AsyncMock(side_effect=OSError('disk'))
        self.assertEqual(await dashboard.async_manage(self.hass(dash),PROFILES,'0.6.0'),'read_failed')
        self.assertEqual(dash.saved,[]);self.assertIn('dashboard_read_failed',self.issues);self.assertEqual(FakeStore.data,{})
    async def test_uninitialised_storage_is_adopted_but_only_config_not_found(self):
        class ConfigNotFound(Exception):pass
        dash=Dash(None);dash.async_load=AsyncMock(side_effect=ConfigNotFound())
        self.assertEqual(await dashboard.async_manage(self.hass(dash),PROFILES,'0.6.0'),'saved')
        self.assertEqual(dash.saved[0]['views'],LEGACY['views']);self.assertNotIn(dashboard.BACKUPS_KEY,FakeStore.data)
    async def test_saved_empty_dashboard_is_adopted_and_user_content_is_not(self):
        for empty in ({'views':[]},{'title':'Echo Home','views':[]},{}):
            FakeStore.data={};dash=Dash(dict(empty))
            self.assertEqual(await dashboard.async_manage(self.hass(dash),PROFILES,'0.6.0'),'saved',empty)
            self.assertEqual(FakeStore.data[dashboard.BACKUPS_KEY]['backups'],[empty])
        for user in ({'views':[{'title':'Mine'}]},{'title':'Echo Home','views':[],'badges':[]},{'strategy':{'type':'map'}}):
            dash=Dash(dict(user))
            self.assertEqual(await dashboard.async_manage(self.hass(dash),PROFILES,'0.6.0'),'hand_edited',user);self.assertEqual(dash.saved,[])
    async def test_write_failure_keeps_snapshot_and_raises_issue(self):
        dash=Dash(json.loads(json.dumps(LEGACY)));dash.async_save=AsyncMock(side_effect=OSError('disk'))
        self.assertEqual(await dashboard.async_manage(self.hass(dash),PROFILES,'0.6.0'),'failed')
        self.assertNotIn(dashboard.STORE_KEY,FakeStore.data);self.assertIn('dashboard_write_failed',self.issues)

class Resources:
    def __init__(self,items):self.items=items;self.created=[];self.updated=[];self.deleted=[]
    async def async_get_info(self):return {}
    def async_items(self):return list(self.items)
    async def async_create_item(self,data):self.created.append(data);self.items.append({'id':'new',**data})
    async def async_update_item(self,item_id,data):self.updated.append((item_id,data))
    async def async_delete_item(self,item_id):self.deleted.append(item_id);self.items=[i for i in self.items if i['id']!=item_id]

class ResourceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.issues={}
        patch.object(frontend.ir,'async_create_issue',lambda hass,domain,key,**kw:self.issues.__setitem__(key,kw)).start();self.addCleanup(patch.stopall)
        patch.object(frontend.ir,'async_delete_issue',lambda hass,domain,key:self.issues.pop(key,None)).start()
    async def test_replaces_legacy_local_resource_and_versions_the_new_one(self):
        res=Resources([{'id':'old','url':'/local/echo-experience/echo-experience.js?v=abc123','res_type':'module'},{'id':'x','url':'/hacsfiles/other.js'}])
        url=await frontend.async_ensure_resource(NS(data={'lovelace':NS(resources=res)}),'0.6.0')
        self.assertEqual(url,'/echo_experience/echo-experience.js?v=0.6.0')
        self.assertEqual(res.deleted,['old']);self.assertEqual(res.created,[{'res_type':'module','url':url}])
    async def test_legacy_resource_survives_when_new_one_cannot_be_created(self):
        res=Resources([{'id':'old','url':'/local/echo-experience/echo-experience.js','res_type':'module'}])
        res.async_create_item=AsyncMock(side_effect=RuntimeError('storage locked'))
        with self.assertRaises(RuntimeError):await frontend.async_ensure_resource(NS(data={'lovelace':NS(resources=res)}),'0.6.0')
        self.assertEqual(res.deleted,[])
    async def test_version_change_updates_in_place_and_same_version_is_idempotent(self):
        res=Resources([{'id':'ours','url':'/echo_experience/echo-experience.js?v=0.5.1'}])
        hass=NS(data={'lovelace':NS(resources=res)})
        await frontend.async_ensure_resource(hass,'0.6.0')
        self.assertEqual(res.updated,[('ours',{'res_type':'module','url':'/echo_experience/echo-experience.js?v=0.6.0'})]);self.assertEqual(res.created,[])
        res.items=[{'id':'ours','url':'/echo_experience/echo-experience.js?v=0.6.0'}];res.updated=[]
        await frontend.async_ensure_resource(hass,'0.6.0');self.assertEqual(res.updated,[])
    async def test_yaml_resources_use_extra_js_and_raise_issue_for_legacy_entry(self):
        yaml=NS(async_items=lambda:[{'url':'/local/echo-experience/echo-experience.js'}])
        with patch.object(frontend,'add_extra_js_url') as extra:
            await frontend.async_ensure_resource(NS(data={'lovelace':NS(resources=yaml)}),'0.6.0')
        extra.assert_called_once();self.assertIn('resources_yaml',self.issues)
    async def test_translations_cover_every_issue_key_in_code(self):
        import re
        keys=set()
        for f in (ROOT/'custom_components/echo_experience').glob('*.py'):
            keys.update(re.findall(r"async_create_issue\(hass,DOMAIN,'([a-z_]+)'",f.read_text()))
            keys.update(re.findall(r"issue\(hass,'([a-z_]+)'",f.read_text()))
            keys.update(re.findall(r"async_create_issue\(self\.hass,DOMAIN,'([a-z_]+)'",f.read_text()))
        keys.update(dashboard.ISSUES)
        setup=(ROOT/'custom_components/echo_experience/__init__.py').read_text()
        features=re.findall(r"await feature\('([a-z_]+)'",setup);self.assertEqual(sorted(features),['dashboard','frontend','stop_route'])
        keys.discard('setup_failed_');keys.update('setup_failed_'+name for name in features)
        translations=json.loads((ROOT/'custom_components/echo_experience/translations/en.json').read_text())['issues']
        self.assertTrue(keys);self.assertEqual(keys-set(translations),set())
        self.assertEqual((ROOT/'custom_components/echo_experience/strings.json').read_text(),(ROOT/'custom_components/echo_experience/translations/en.json').read_text())

if __name__=='__main__':unittest.main()
