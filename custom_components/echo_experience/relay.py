"""Echo Relay: a listen-only satellite (wake word + speech-to-text) hands its turn to an Echo.

The Echo runs the turn natively through the Kiosk's vs_show service, so tools, timers, display and speech all
belong to the Echo. The relay agent answers the input satellite with empty speech: the pipeline skips TTS and the
satellite returns to idle without speaking or re-listening. When the Echo is down the turn is delegated to a
configured agent and answered on the input satellite instead. A turn the Echo does not take (no answer in time, or
still refused after the turn on its screen was interrupted) is said so on the input satellite.
"""
import asyncio
import difflib
import logging
import re
import time

from homeassistant.core import callback
from homeassistant.helpers.event import async_track_state_change_event

from . import native
from .core import identity, input_satellites
from .stop_route import COMMANDS, normalise, stop_kind

_LOGGER = logging.getLogger(__name__)
STOP_PHRASES = {c.casefold() for c in COMMANDS}
CUE_TITLE = 'Listening'
CUE_DURATION = 4
# Misheard "stop timer" ("Stop time, Matt.", "Stop Tomer.") is sent on as this phrase while the Echo has a timer.
TIMER_STOP = 'Stop the timer.'
TIMER_STOP_FORMS = ('stop timer', 'stop the timer')
TIMER_STOP_SIMILARITY = 0.75
MUSIC_WORDS = re.compile(r'\b(music|sonos|song|radio|playing)\b')
# The Echo acknowledges vs_show in milliseconds; no answer in this time means the turn did not reach it.
HANDOFF_TIMEOUT = 4
# After interrupting the turn on the Echo's screen it needs a moment before it takes another.
INTERRUPT_RETRIES = 3
INTERRUPT_PAUSE = 0.4
REPLY_UNREACHABLE = "Sorry, I couldn't reach the {name}. Please try again."
# A stop within this long of its wake word ending the Echo's answer was for that answer.
HUSH_WINDOW = 30


def strip_wake_word(text, words):
    """The request without the wake word an input satellite sent with it: "Alexa, set a timer." -> "Set a timer."

    An Echo Dot can start its audio at the wake word instead of guessing where the word ends, which otherwise
    leaves the word's tail in ("Let's set a timer") or cuts the first word of the request.
    """
    text = text or ''
    if not words:
        return text
    rest = re.sub(r'^\W*(?:' + '|'.join(re.escape(w.strip()) for w in words) + r')\b\W*', '', text, count=1, flags=re.I)
    return text if rest == text else rest[:1].upper() + rest[1:]


def sounds_like_timer(word):
    """Speech-to-text spells "timer" as toma, tomer, tima, time...: a t-m consonant start is the stable part."""
    return re.sub(r'[aeiouy]', '', word).startswith('tm')


def sounds_like_timer_stop(text):
    """A short "stop ..." phrase close to "stop (the) timer". Music phrases and bare/known stop phrases never match."""
    phrase = normalise(text)
    words = phrase.split()
    if len(words) < 2 or len(words) > 4 or words[0] != 'stop' or phrase in STOP_PHRASES or MUSIC_WORDS.search(phrase):
        return False
    rest = words[2:] if words[1] == 'the' else words[1:]
    if rest and sounds_like_timer(rest[0]):
        return True
    return max(difflib.SequenceMatcher(None, phrase, form).ratio() for form in TIMER_STOP_FORMS) >= TIMER_STOP_SIMILARITY


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
        relay = p['relay']
        hushed = time.monotonic() - self.runtime.hushed.pop(p['id'], float('-inf')) < HUSH_WINDOW
        text = strip_wake_word(user_input.text, relay['wake_words'])
        if not normalise(text):
            return self.reply(user_input)  # the wake word and nothing after it
        # Sentence triggers only run for the default agent, so stop is answered here directly: every plain or
        # music stop, and any other "stop ..." while an alarm is sounding (it silences the alarm).
        kind = stop_kind(text)
        is_stop = kind in ('plain', 'music') or normalise(text) in STOP_PHRASES \
            or (kind == 'named' and bool(self.runtime.ringing_timers(p)))
        if is_stop and self.runtime.stop_route:
            speech = await self.runtime.stop_route.handle(user_input, None, text=text, hushed=hushed)
            if speech is not None:
                # The stop route has already given the outcome to the Echo when it is up (speech is then empty).
                return self.reply(user_input, speech)
        if sounds_like_timer_stop(text) and (self.runtime.timers(p) or self.runtime.ringing_timers(p)):
            # Speech-to-text mangles "stop timer" into names and words the model then chases. With a timer on
            # this Echo the intent is clear enough to say it plainly; without one the words go on unchanged.
            _LOGGER.info('Echo Experience relay: %r taken as %r for %s', text, TIMER_STOP, p['id'])
            text = TIMER_STOP
        service = vs_service(self.hass, p, 'vs_show')
        if service:
            data = {'prompt': text, 'speak': True, 'pipeline': relay['pipeline'], 'duration': relay['duration']}
            if await self.hand_off(p, service, data, user_input.context):
                return self.reply(user_input)
            return self.reply(user_input, REPLY_UNREACHABLE.format(name=p['name']))
        native.warn_once('relay_fallback_' + p['id'], 'Echo Experience relay: %s is unavailable; answering on the input satellite with %s', p['id'], relay['fallback_agent'])
        from homeassistant.components import conversation
        return await conversation.async_converse(
            self.hass, text, user_input.conversation_id, user_input.context, language=user_input.language,
            agent_id=relay['fallback_agent'], device_id=user_input.device_id, satellite_id=getattr(user_input, 'satellite_id', None),
            extra_system_prompt=getattr(user_input, 'extra_system_prompt', None))

    async def hand_off(self, p, service, data, context):
        """True once the Echo has taken the turn.

        The Kiosk answers vs_show as soon as the turn is on its screen, so a wait is cheap and tells a lost request
        from a delivered one. It refuses while another turn is on screen: that turn is interrupted (as a new wake
        word would) and the request is offered again.
        """
        async def offer():
            async with asyncio.timeout(HANDOFF_TIMEOUT):
                await self.hass.services.async_call('esphome', service, data, blocking=True, context=context)

        try:
            await offer()
            return True
        except TimeoutError:
            _LOGGER.warning('Echo Experience relay: %s did not answer within %s s; the request was not delivered', p['id'], HANDOFF_TIMEOUT)
            return False
        except Exception as err:  # noqa: BLE001 - refused (a turn is on screen) or the connection failed
            refusal = err
        if not await native.end_turn(self.hass, identity(p, 'native'), HANDOFF_TIMEOUT):
            _LOGGER.warning('Echo Experience relay: %s did not take the request (%s)', p['id'], refusal)
            return False
        for _ in range(INTERRUPT_RETRIES):
            await asyncio.sleep(INTERRUPT_PAUSE)
            try:
                await offer()
                _LOGGER.info('Echo Experience relay: interrupted the turn on %s for a new request', p['id'])
                return True
            except TimeoutError:
                break
            except Exception as err:  # noqa: BLE001
                refusal = err
        _LOGGER.warning('Echo Experience relay: %s did not take the request (%s)', p['id'], refusal)
        return False


class WakeCue:
    """When one of an Echo's input satellites starts listening: the Echo stops talking, and (wake_cue) gives a
    chime and toast. Cheap, fail-soft."""

    def __init__(self, hass, runtime):
        self.hass, self.runtime = hass, runtime
        self.unsubscribe = None
        self.inputs = {s: p for p in runtime.profiles for s in input_satellites(p)}
        self.owners = {s: p for s, p in self.inputs.items() if p['relay']['wake_cue']}

    def start(self):
        if self.inputs:
            self.unsubscribe = async_track_state_change_event(self.hass, list(self.inputs), self.changed)

    def stop(self):
        if self.unsubscribe:
            self.unsubscribe()
            self.unsubscribe = None

    @callback
    def changed(self, event):
        new, old = event.data.get('new_state'), event.data.get('old_state')
        if getattr(new, 'state', None) != 'listening' or getattr(old, 'state', None) == 'listening':
            return
        entity = event.data.get('entity_id')
        if entity in self.inputs:
            self.hass.async_create_task(self.hush(self.inputs[entity]), 'Echo Experience wake hush')
        if entity in self.owners:
            self.hass.async_create_task(self.cue(self.owners[entity]), 'Echo Experience wake cue')

    async def hush(self, p):
        """The wake word ends the answer the Echo is working out or speaking, as it does on an Echo itself.

        Otherwise the input satellite hears the Echo's voice along with the request ("Alexa, stop. Expect rain to
        continue...") and keeps listening until the Echo has finished. A sounding alarm is left alone: vs_cancel
        would silence it, and that is for the request to decide.
        """
        try:
            ident = identity(p, 'native')
            state = getattr(native.voice_state(self.hass, ident), 'state', None)
            if state not in native.TURN_STATES or self.runtime.ringing_timers(p):
                return
            self.runtime.hushed[p['id']] = time.monotonic()
            await native.end_turn(self.hass, ident, HANDOFF_TIMEOUT)
        except Exception as err:  # noqa: BLE001
            native.warn_once('wake_hush', 'Echo Experience: could not quieten the Echo on a wake word (%s)', err)

    async def cue(self, p):
        service = vs_service(self.hass, p, 'notification')
        if not service:
            return
        try:
            # Duration, scale and volume units are the Kiosk's; the toast closes itself after CUE_DURATION.
            await self.hass.services.async_call('esphome', service, {'message': '', 'title': CUE_TITLE, 'duration': CUE_DURATION, 'type': 'info', 'chime': True, 'scale': 1, 'icon': 'mdi:microphone', 'chime_file': '', 'volume': 0.5, 'image': ''}, blocking=False)
        except Exception as err:  # noqa: BLE001
            native.warn_once('wake_cue', 'Echo Experience: wake cue failed (%s)', err)
