"""Serve the dashboard card from the integration and keep its Lovelace resource current."""
import logging
from pathlib import Path
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.helpers import issue_registry as ir

DOMAIN='echo_experience'
URL_BASE='/echo_experience'
CARD='echo-experience.js'
LEGACY_PATH='/local/echo-experience/echo-experience.js'
CARD_DIR=str(Path(__file__).parent/'www')
_LOGGER=logging.getLogger(__name__)

def card_url(version):
    return f'{URL_BASE}/{CARD}?v={version}'

async def async_register_static_path(hass):
    """Register once per runtime; a reload must not raise on the duplicate."""
    if hass.data.get(DOMAIN+'_static'):return
    try:
        await hass.http.async_register_static_paths([StaticPathConfig(URL_BASE,CARD_DIR,False)])
    except RuntimeError:
        _LOGGER.debug('Static path %s already registered',URL_BASE)
    hass.data[DOMAIN+'_static']=True

def resources_of(hass):
    lovelace=hass.data.get('lovelace')
    return getattr(lovelace,'resources',None) if lovelace is not None else None

async def async_ensure_resource(hass,version):
    """Create or update the module resource; remove the legacy /local copy so one card class loads."""
    resources=resources_of(hass)
    url=card_url(version)
    if resources is None or not hasattr(resources,'async_create_item'):
        # YAML resources cannot be edited; load the new file and ask for the old entry to go.
        add_extra_js_url(hass,url)
        if resources is not None and any(LEGACY_PATH in (item.get('url') or '') for item in resources.async_items()):
            ir.async_create_issue(hass,DOMAIN,'resources_yaml',is_fixable=False,severity=ir.IssueSeverity.WARNING,translation_key='resources_yaml',translation_placeholders={'legacy':LEGACY_PATH})
        else:ir.async_delete_issue(hass,DOMAIN,'resources_yaml')
        return url
    await resources.async_get_info()
    ir.async_delete_issue(hass,DOMAIN,'resources_yaml')
    current=None;legacy=[]
    for item in list(resources.async_items()):
        item_url=(item.get('url') or '').split('?')[0]
        if item_url==LEGACY_PATH:legacy.append(item)
        elif item_url==f'{URL_BASE}/{CARD}':current=item
    # The new resource must exist before the old one goes, so a failure here never leaves the card unregistered.
    if current is None:
        await resources.async_create_item({'res_type':'module','url':url})
    elif current.get('url')!=url:
        await resources.async_update_item(current['id'],{'res_type':'module','url':url})
    for item in legacy:
        _LOGGER.info('Removing legacy Echo Experience resource %s',item.get('url'))
        await resources.async_delete_item(item['id'])
    return url
