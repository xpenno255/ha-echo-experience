"""Kiosk Satellite's native Voice Satellite runtime (an ESPHome Assist satellite) for the same physical Echo.

Everything here is optional and fails soft: a missing private Home Assistant API, an absent ESPHome device or a
Kiosk running the dashboard runtime only disables the native path (logged once) and never touches the browser
(Voice Satellite) path, which keeps its 0.7.0 behaviour.
"""
import asyncio
import inspect
import logging
import time

from .core import identities, identity, check_identities

_LOGGER = logging.getLogger(__name__)
TIMER_EVENT = 'esphome.kiosk_satellite_timer'
KIOSK_KEYS = ('kiosk_navigation', 'kiosk_screensaver', 'kiosk_now_playing', 'kiosk_hold')
UNAVAILABLE = (None, 'unavailable', 'unknown')
# A conversation turn is followed for at most this long; LLM turns are bounded well below it.
TURN_DEADLINE = 120
TURN_POLL = 0.25
_warned = set()


def warn_once(key, message, *args):
    if key in _warned:
        return
    _warned.add(key)
    _LOGGER.warning(message, *args)


# ---- identity -------------------------------------------------------------------------------

def derive_identities(hass, profiles):
    """Fill profile['native'] from the Kiosk ESPHome device that already owns the profile's kiosk_* entities.

    Explicit configuration always wins. Ambiguity or a conflict with another identity leaves the profile
    dashboard-only. Returns {profile_id: reason} for the profiles left without a native identity.
    """
    try:
        from homeassistant.helpers import entity_registry as er
        entities = er.async_get(hass)
    except Exception as err:  # noqa: BLE001 - registries missing means no native support, not a failed setup
        warn_once('registry', 'Echo Experience: native runtime detection unavailable (%s)', err)
        return {p['id']: 'registry unavailable' for p in profiles if not p.get('native')}
    skipped = {}
    for p in profiles:
        if p.get('native'):
            continue
        try:
            found, reason = _derive_one(entities, p)
        except Exception as err:  # noqa: BLE001
            found, reason = None, f'detection failed: {err}'
        if not found:
            skipped[p['id']] = reason
            continue
        p['native'] = {**found, 'derived': True}
        try:
            check_identities(profiles)
        except ValueError as err:
            p.pop('native')
            skipped[p['id']] = str(err)
    for pid, reason in skipped.items():
        _LOGGER.info('Echo Experience: profile %s runs the dashboard runtime only (%s)', pid, reason)
    return skipped


def _derive_one(entities, p):
    device_id = None
    for key in KIOSK_KEYS:
        entry = entities.async_get(p[key]) if p.get(key) else None
        if entry is not None and entry.platform == 'esphome' and entry.device_id:
            device_id = entry.device_id
            break
    if not device_id:
        return None, 'no Kiosk ESPHome entity in the profile'
    satellites = [e for e in entities.entities.values()
                  if e.device_id == device_id and e.domain == 'assist_satellite' and e.platform == 'esphome'
                  and not e.disabled_by]
    if len(satellites) != 1:
        return None, f'{len(satellites)} ESPHome satellites on the Kiosk device'
    return {'satellite': satellites[0].entity_id, 'device_id': device_id}, None


def node_name(hass, ident):
    """The ESPHome service prefix of a native identity, built the way Home Assistant builds it."""
    if not ident:
        return None
    if ident.get('node'):
        return ident['node']
    try:
        from homeassistant.helpers import device_registry as dr
        device = dr.async_get(hass).async_get(ident['device_id'])
        for entry_id in getattr(device, 'config_entries', ()) or ():
            entry = hass.config_entries.async_get_entry(entry_id)
            if entry is None or entry.domain != 'esphome':
                continue
            info = getattr(getattr(entry, 'runtime_data', None), 'device_info', None)
            name = getattr(info, 'name', None) or (entry.data or {}).get('device_name')
            if name:
                ident['node'] = name.replace('-', '_')
                return ident['node']
    except Exception as err:  # noqa: BLE001
        warn_once('node', 'Echo Experience: could not resolve the Kiosk ESPHome node name (%s)', err)
    return None


def satellite_up(hass, ident):
    state = hass.states.get(ident['satellite']) if ident else None
    return getattr(state, 'state', None) not in UNAVAILABLE


def timer_device(manager, device_id):
    check = getattr(manager, 'is_timer_device', None)
    if callable(check):
        try:
            return bool(check(device_id))
        except Exception:  # noqa: BLE001
            return False
    return device_id in (getattr(manager, 'handlers', None) or {})


def mode(p, overrides):
    """An explicit pin (options flow) beats the profile file, which beats auto."""
    pinned = (overrides or {}).get(p['id'])
    if pinned in ('dashboard', 'native'):
        return pinned
    return p.get('runtime') if p.get('runtime') in ('dashboard', 'native') else 'auto'


def active_identity(hass, p, overrides, manager=None):
    """The identity new timers belong to. auto: native while its satellite is up and holds a timer handler."""
    wanted = mode(p, overrides)
    native = identity(p, 'native')
    if wanted == 'native':
        return native or identity(p, 'dashboard')
    if wanted == 'dashboard' or native is None:
        return identity(p, 'dashboard')
    if satellite_up(hass, native) and (manager is None or timer_device(manager, native['device_id'])):
        return native
    return identity(p, 'dashboard')


# ---- timers ---------------------------------------------------------------------------------

def _start_supported(manager):
    start = getattr(manager, 'start_timer', None)
    if not callable(start):
        return False
    try:
        params = inspect.signature(start).parameters
    except (TypeError, ValueError):
        return True
    return all(k in params for k in ('device_id', 'hours', 'minutes', 'seconds', 'language', 'name'))


def start_timer(hass, manager, device_id, hours, minutes, seconds, name):
    """Start a native Assist timer on the Kiosk's ESPHome device through core's timer manager."""
    if not _start_supported(manager):
        warn_once('start_timer', 'Echo Experience: this Home Assistant timer manager cannot start native timers')
        raise ValueError('Native timers are not supported by this Home Assistant version')
    if not timer_device(manager, device_id):
        raise ValueError("The Echo's native voice satellite is not connected; Home Assistant cannot start a timer on it")
    language = getattr(getattr(hass, 'config', None), 'language', None) or 'en'
    try:
        return manager.start_timer(device_id=device_id, hours=hours, minutes=minutes, seconds=seconds,
                                   language=language, name=name)
    except Exception as err:  # noqa: BLE001 - TimersNotSupportedError and friends become a tool error
        raise ValueError(f'Home Assistant could not start the timer: {err}') from err


async def list_ringing(hass, ident, timeout):
    """Timer ids the Kiosk says are ringing, or None when that cannot be known."""
    node = node_name(hass, ident)
    service = f'{node}_vs_list_timers' if node else None
    if not service or not hass.services.has_service('esphome', service):
        warn_once('vs_list_timers', 'Echo Experience: esphome.%s is not available; native timer alerts cannot be checked', service)
        return None
    try:
        async with asyncio.timeout(timeout):
            response = await hass.services.async_call('esphome', service, {}, blocking=True, return_response=True)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning('Echo Experience: %s failed: %s', service, err)
        return None
    timers = (response or {}).get('timers') if isinstance(response, dict) else None
    if not isinstance(timers, list):
        return None
    return {str(t.get('timer_id')) for t in timers if isinstance(t, dict) and t.get('finished')}


async def cancel_alert(hass, ident):
    """vs_cancel silences every ringing timer on the Kiosk (and only that while one rings)."""
    node = node_name(hass, ident)
    service = f'{node}_vs_cancel' if node else None
    if not service or not hass.services.has_service('esphome', service):
        return False
    try:
        await hass.services.async_call('esphome', service, {}, blocking=True)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning('Echo Experience: %s failed: %s', service, err)
        return False
    return True


# ---- conversation display ---------------------------------------------------------------------

def current_chat_log():
    """The chat log of the conversation being processed, through core's private context variable."""
    try:
        from homeassistant.components.conversation import chat_log
    except Exception as err:  # noqa: BLE001
        warn_once('chat_log', 'Echo Experience: conversation chat log unavailable (%s); native answers are not shown', err)
        return None
    var = getattr(chat_log, 'current_chat_log', None)
    if var is None or not hasattr(var, 'get'):
        warn_once('chat_log', 'Echo Experience: conversation chat log context unavailable; native answers are not shown')
        return None
    try:
        return var.get()
    except Exception:  # noqa: BLE001
        return None


def _role(content):
    return getattr(content, 'role', None)


def _tool_names(content):
    names = []
    for call in getattr(content, 'tool_calls', None) or []:
        name = getattr(call, 'tool_name', None) or (call.get('tool_name') if isinstance(call, dict) else None)
        if name:
            names.append(name)
    return names


def digest(contents, start):
    """(question, answer, tool names) of the turn whose user message is at index start; answer None until final."""
    question = (getattr(contents[start], 'content', '') or '') if start < len(contents) else ''
    names, answer = [], None
    for content in contents[start + 1:]:
        role = _role(content)
        if role == 'user':
            break
        if role != 'assistant':
            continue
        calls = _tool_names(content)
        names.extend(calls)
        text = getattr(content, 'content', None)
        if not calls and isinstance(text, str) and text.strip():
            answer = text
            break
    return question, answer, names


class TurnWatcher:
    """Shows the spoken answer of native turns, which no Voice Satellite chat event describes.

    The Echo Experience API instance is created inside the agent's chat log context, so the conversation is tied
    to the asking device there. Only native-origin turns are followed; browser turns keep voice_satellite_chat.
    """

    def __init__(self, hass, show):
        self.hass, self.show = hass, show
        self.turns = {}
        self.closed = False

    def track(self, p, ident):
        if self.closed or not ident or ident['runtime'] != 'native':
            return False
        log = current_chat_log()
        contents = getattr(log, 'content', None)
        conversation_id = getattr(log, 'conversation_id', None)
        if log is None or not isinstance(contents, list) or not conversation_id:
            return False
        start = next((i for i in range(len(contents) - 1, -1, -1) if _role(contents[i]) == 'user'), None)
        if start is None:
            return False
        current = self.turns.get(conversation_id)
        if current and current['start'] == start and not current['task'].done():
            return True  # same turn asked for the API again
        if current:
            current['task'].cancel()
        task = self.hass.async_create_background_task(self._follow(conversation_id, log, start, p), f'Echo Experience turn {conversation_id}') \
            if hasattr(self.hass, 'async_create_background_task') else self.hass.async_create_task(self._follow(conversation_id, log, start, p))
        self.turns[conversation_id] = {'start': start, 'task': task, 'profile': p['id']}
        return True

    async def _follow(self, conversation_id, log, start, p):
        deadline = time.monotonic() + TURN_DEADLINE
        try:
            while time.monotonic() < deadline:
                question, answer, names = digest(log.content, start)
                if answer is not None:
                    self.show(p, question, answer, names)
                    return
                await asyncio.sleep(TURN_POLL)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            _LOGGER.exception('Echo Experience: could not follow a native conversation turn')
        finally:
            entry = self.turns.get(conversation_id)
            if entry and entry['start'] == start:
                self.turns.pop(conversation_id, None)

    def close(self):
        self.closed = True
        for entry in list(self.turns.values()):
            entry['task'].cancel()
        self.turns.clear()
