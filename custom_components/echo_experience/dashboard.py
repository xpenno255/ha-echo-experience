"""Keep the Echo Home dashboard in step with the profiles without ever overwriting hand-edited work.

Lovelace keeps its dashboards collection private to its own setup, and every collection save rewrites the whole
storage file, so the integration never instantiates a second collection. It only saves into a dashboard that
already exists in storage mode and that it can prove it generated. Creating the dashboard on a fresh install is
left to an admin through Settings → Dashboards (the only writer of that collection); a reload then adopts the
empty dashboard and fills it.
"""
import logging
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store

DOMAIN='echo_experience'
URL_PATH='echo-home'
MARKER='echo_experience_generated'
STORE_KEY='echo_experience.dashboard'
BACKUPS_KEY='echo_experience.dashboard_backups'
KEEP=5
ISSUES=('dashboard_missing','dashboard_hand_edited','dashboard_yaml','dashboard_write_failed','dashboard_read_failed')
EMPTY_KEYS={'title','views','echo_experience_generated'}
_LOGGER=logging.getLogger(__name__)

def build_views(profiles):
    views=[]
    for p in profiles:
        views.append({'title':p['name'],'path':p['id'],'type':'panel','cards':[{'type':'custom:echo-experience-card','device':p['id']}]})
        views.append({'title':p['name']+' Screensaver','path':p['id']+'-screensaver','type':'panel','subview':True,'cards':[{'type':'custom:echo-experience-card','device':p['id'],'ambient':True}]})
    return views

def legacy_config(profiles):
    """Exactly what the retired deploy.py saved, so a 0.5.1 dashboard can be adopted by equality."""
    return {'title':'Echo Home','views':build_views(profiles)}

def build_config(profiles,version):
    return {'title':'Echo Home',MARKER:version,'views':build_views(profiles)}

def is_empty(config):
    """A dashboard freshly created in the UI (or emptied on purpose): no views, no cards, no user keys."""
    return isinstance(config,dict) and set(config)<=EMPTY_KEYS and not config.get('views')

def generated_by_us(current,profiles,snapshot):
    """Only full equality with something this integration wrote counts; the marker alone proves nothing after an edit."""
    if current is None or is_empty(current):return True
    if current==legacy_config(profiles):return True
    if snapshot is not None and current==snapshot:return True
    if isinstance(current,dict) and MARKER in current:
        # Our marker but different content: compare ignoring the version stamp so a version bump alone still adopts.
        stripped={k:v for k,v in current.items() if k!=MARKER}
        if snapshot is not None and stripped=={k:v for k,v in snapshot.items() if k!=MARKER}:return True
    return False

def issue(hass,key,**placeholders):
    ir.async_create_issue(hass,DOMAIN,key,is_fixable=False,severity=ir.IssueSeverity.WARNING,translation_key=key,translation_placeholders={'url':URL_PATH,**placeholders})

async def async_manage(hass,profiles,version,enabled=True):
    """Returns one of: disabled, unavailable, missing, yaml, hand_edited, unchanged, saved, failed."""
    for key in ISSUES:ir.async_delete_issue(hass,DOMAIN,key)
    if not enabled:return 'disabled'
    lovelace=hass.data.get('lovelace')
    if lovelace is None or not hasattr(lovelace,'dashboards'):return 'unavailable'
    existing=lovelace.dashboards.get(URL_PATH)
    if existing is None:
        issue(hass,'dashboard_missing')
        return 'missing'
    if getattr(existing,'mode',None)!='storage' or not hasattr(existing,'async_save'):
        issue(hass,'dashboard_yaml')
        return 'yaml'
    store=Store(hass,1,STORE_KEY)
    snapshot=(await store.async_load() or {}).get('config')
    wanted=build_config(profiles,version)
    try:current=await existing.async_load(False)
    except Exception as err:
        # Only "nothing saved yet" is uninitialised. Any other read failure must never authorise an unbacked overwrite.
        if type(err).__name__!='ConfigNotFound':
            _LOGGER.exception('Could not read the Echo Home dashboard')
            issue(hass,'dashboard_read_failed')
            return 'read_failed'
        current=None
    if not generated_by_us(current,profiles,snapshot):
        issue(hass,'dashboard_hand_edited')
        return 'hand_edited'
    if current==wanted:
        if snapshot!=wanted:await store.async_save({'config':wanted})
        return 'unchanged'
    try:
        if current is not None:
            backups=Store(hass,1,BACKUPS_KEY)
            history=(await backups.async_load() or {}).get('backups',[])
            await backups.async_save({'backups':([current]+history)[:KEEP]})
        await existing.async_save(wanted)
        await store.async_save({'config':wanted})
    except Exception:
        _LOGGER.exception('Could not save the Echo Home dashboard')
        issue(hass,'dashboard_write_failed')
        return 'failed'
    return 'saved'
