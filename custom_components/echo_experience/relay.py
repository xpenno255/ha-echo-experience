"""Echo Relay: a listen-only satellite (wake word + speech-to-text) hands its turn to an Echo.

The Echo runs the turn natively through the Kiosk's vs_show service, so tools, timers, display and speech all
belong to the Echo. The relay agent answers the input satellite with empty speech: the pipeline skips TTS and the
satellite returns to idle without speaking or re-listening. When the Echo is down the turn is delegated to a
configured agent and answered on the input satellite instead.
"""
import logging
import re

from homeassistant.core import callback
from homeassistant.helpers.event import async_track_state_change_event

from . import native
from .core import identity, input_satellites
from .stop_route import COMMANDS

_LOGGER = logging.getLogger(__name__)
STOP_PHRASES = {c.casefold() for c in COMMANDS}
CUE_TITLE = 'Listening'
CUE_DURATION = 4


def normalise(text):
    return ' '.join(re.sub(r'[^\w\s]', ' ', (text or '').casefold()).split())


def vs_service(hass, p, suffix):
    """esphome service name for the profile's native Echo when it is up, else None."""
    ident = identity(p, 'native')
    node = native.node_name(hass, ident)
    if not ident or not node or not native.satellite_up(hass, ident):
        return None
    name = f'{node}_{suffix}'
    return name if hass.services.has_service('esphome', name) else None


class Relay:
    def __init__(self, hass, runtime):
        self.hass, self.runtime = hass, runtime

    @staticmethod
    def reply(user_input, speech=''):
        from homeassistant.components.conversation import ConversationResult
        from homeassistant.helpers import intent
        response = intent.IntentResponse(language=user_input.language)
        response.async_set_speech(speech)
        return ConversationResult(response=response, conversation_id=user_input.conversation_id, continue_conversation=False)

    async def process(self, user_input):
        p = self.runtime.profile_for_input(user_input.device_id, getattr(user_input, 'satellite_id', None))
        if p is None:
            native.warn_once('relay_unknown', 'Echo Experience relay: device %s is not in any profile input_satellites', user_input.device_id)
            return self.reply(user_input, "This device isn't set up to relay to an Echo.")
        # Sentence triggers only run for the default agent, so the stop phrases are answered here directly.
        if normalise(user_input.text) in STOP_PHRASES and self.runtime.stop_route:
            speech = await self.runtime.stop_route.handle(user_input, None)
            if speech is not None:
                return self.reply(user_input, speech)
        relay = p['relay']
        service = vs_service(self.hass, p, 'vs_show')
        if service:
            await self.hass.services.async_call('esphome', service, {'prompt': user_input.text, 'speak': True, 'pipeline': relay['pipeline'], 'duration': relay['duration']}, blocking=False, context=user_input.context)
            return self.reply(user_input)
        native.warn_once('relay_fallback_' + p['id'], 'Echo Experience relay: %s is unavailable; answering on the input satellite with %s', p['id'], relay['fallback_agent'])
        from homeassistant.components import conversation
        return await conversation.async_converse(
            self.hass, user_input.text, user_input.conversation_id, user_input.context, language=user_input.language,
            agent_id=relay['fallback_agent'], device_id=user_input.device_id, satellite_id=getattr(user_input, 'satellite_id', None),
            extra_system_prompt=getattr(user_input, 'extra_system_prompt', None))


class WakeCue:
    """Chime and toast on the Echo when one of its input satellites starts listening. Cheap, fail-soft."""

    def __init__(self, hass, runtime):
        self.hass, self.runtime = hass, runtime
        self.unsubscribe = None
        self.owners = {s: p for p in runtime.profiles if p['relay']['wake_cue'] for s in input_satellites(p)}

    def start(self):
        if self.owners:
            self.unsubscribe = async_track_state_change_event(self.hass, list(self.owners), self.changed)

    def stop(self):
        if self.unsubscribe:
            self.unsubscribe()
            self.unsubscribe = None

    @callback
    def changed(self, event):
        new, old = event.data.get('new_state'), event.data.get('old_state')
        if getattr(new, 'state', None) != 'listening' or getattr(old, 'state', None) == 'listening':
            return
        p = self.owners.get(event.data.get('entity_id'))
        if p:
            self.hass.async_create_task(self.cue(p), 'Echo Experience wake cue')

    async def cue(self, p):
        service = vs_service(self.hass, p, 'notification')
        if not service:
            return
        try:
            # Duration, scale and volume units are the Kiosk's; the toast closes itself after CUE_DURATION.
            await self.hass.services.async_call('esphome', service, {'message': '', 'title': CUE_TITLE, 'duration': CUE_DURATION, 'type': 'info', 'chime': True, 'scale': 1, 'icon': 'mdi:microphone', 'chime_file': '', 'volume': 0.5, 'image': ''}, blocking=False)
        except Exception as err:  # noqa: BLE001
            native.warn_once('wake_cue', 'Echo Experience: wake cue failed (%s)', err)
