/* Echo Experience redesign mockup.
 * Standalone and offline: no network calls, no Home Assistant, no audio.
 * All text is inserted with textContent; no innerHTML is used anywhere. */
'use strict';

const SVG_NS = 'http://www.w3.org/2000/svg';

/* ---------- Sample data (fixed, fictional) ---------- */

const SPEAKER = 'Kitchen Sonos';

const SAMPLES = {
  photo: {
    kind: 'song',
    title: 'Heather Light',
    artist: 'The Moorland Quartet',
    album: 'Late Afternoon',
    art: '../assets/heather-landscape.jpg',
    artAlt: 'Demo artwork: heather moorland at sunset',
    focus: '22% 70%',
    palette: ['#6A3F8C', '#2F5878', '#C89B62'],
    duration: 252,
    elapsed: 98,
  },
  busy: {
    kind: 'song',
    title: 'Paper Suns',
    artist: 'Kite Parade',
    album: 'Bright Things, Loudly',
    art: 'assets/sample-illustration.svg',
    artAlt: 'Demo artwork: bright patterned illustration',
    focus: '60% 40%',
    palette: ['#F2542D', '#540D6E', '#0E7C7B'],
    duration: 201,
    elapsed: 47,
  },
  radio: {
    kind: 'radio',
    title: 'Mid-morning with Priya',
    artist: '',
    album: '',
    station: 'Canalside Radio 94.6',
    art: 'assets/sample-radio-logo.svg',
    artAlt: 'Demo station logo: Canalside Radio',
    focus: '50% 40%',
    palette: ['#E0A82E', '#13315C', '#2A6F97'],
  },
  none: {
    kind: 'song',
    title: 'An Unusually Long Song Title That Keeps Going Past the Edge of the Screen (Extended Live Version)',
    artist: 'The Northern Lights Collective featuring Members of the City Philharmonic Orchestra',
    album: 'Recorded Live at the Town Hall: Winter Sessions, Volume Two (Deluxe Edition)',
    art: '',
    artAlt: '',
    palette: ['#2E6E73', '#1B3A4B', '#7A8F5A'],
    duration: 734,
    elapsed: 312,
  },
};

const WEATHER = {
  place: 'Weoley Castle',
  source: 'Met Office',
  temp: 14,
  condition: 'partly',
  high: 16,
  low: 8,
  hourly: [
    ['partly', 14, 10], ['partly', 15, 10], ['cloud', 15, 20], ['cloud', 16, 35],
    ['rain', 14, 70], ['rain', 13, 85], ['cloud', 12, 40], ['partly', 11, 15],
  ],
  daily: [
    ['partly', 16, 8, 30], ['rain', 13, 7, 80], ['cloud', 14, 9, 45],
    ['sun', 17, 8, 5], ['partly', 15, 10, 20],
  ],
};

const CONDITIONS = {
  sun: ['i-sun', 'Sunny'],
  partly: ['i-partly', 'Partly cloudy'],
  cloud: ['i-cloud', 'Cloudy'],
  rain: ['i-rain', 'Rain'],
};

const APPLIANCES = [
  { id: 'air_fryer', name: 'Air fryer', maker: 'Ninja', model: 'AF500UK', region: 'UK', icon: 'i-airfryer' },
  { id: 'coffee_machine', name: 'Coffee machine', maker: 'Sage', model: '', region: '', icon: 'i-coffee' },
  { id: 'microwave', name: 'Microwave', maker: 'Panasonic', model: 'NN-ST46KB', region: 'UK', icon: 'i-microwave' },
  { id: 'radiator_valves', name: 'Radiator valves', maker: 'Honeywell', model: 'HR92', region: '', icon: 'i-radiator' },
  { id: 'tumble_dryer', name: 'Tumble dryer', maker: 'LG', model: '', region: '', icon: 'i-dryer' },
];

const VIEWS = [
  ['home', 'Home', 'i-home'],
  ['music', 'Music', 'i-music'],
  ['weather', 'Weather', 'i-weather'],
  ['guide', 'HomeGuide', 'i-book'],
  ['controls', 'Controls', 'i-sliders'],
];

/* ---------- Mock state ---------- */

const params = new URLSearchParams(location.search);
const pick = (value, allowed, fallback) => (allowed.includes(value) ? value : fallback);

const state = {
  view: pick(params.get('view'), VIEWS.map((v) => v[0]), 'home'),
  concept: pick(params.get('concept'), ['wash', 'colour', 'bleed'], 'wash'),
  sample: pick(params.get('sample'), Object.keys(SAMPLES), 'photo'),
  playing: true,
  shuffle: false,
  volume: 35,
  elapsed: {},
  appliance: pick(params.get('appliance'), APPLIANCES.map((a) => a.id), null),
  pinned: false,
  lights: [
    { id: 'all', name: 'All lights', on: true },
    { id: 'spots', name: 'Spotlights', on: true },
    { id: 'lamps', name: 'Lamps', on: false },
    { id: 'wall', name: 'Wall lights', on: false },
  ],
  heating: [
    { id: 'kitchen', name: 'Kitchen', current: 18.4, target: 20 },
    { id: 'living', name: 'Living room', current: 21.6, target: 19 },
  ],
};
for (const [key, s] of Object.entries(SAMPLES)) if (s.kind === 'song') state.elapsed[key] = s.elapsed;

/* ---------- DOM helpers ---------- */

function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  if (attrs) {
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === 'class') el.className = v;
      else if (k === 'text') el.textContent = v;
      else if (k === 'style') for (const [p, val] of Object.entries(v)) el.style.setProperty(p, val);
      else el.setAttribute(k, v === true ? '' : String(v));
    }
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

function icon(id, cls = 'icon') {
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('class', cls);
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('focusable', 'false');
  const use = document.createElementNS(SVG_NS, 'use');
  use.setAttribute('href', `#${id}`);
  svg.append(use);
  return svg;
}

function btn(label, action, content, cls = '', extra = {}) {
  return h('button', { type: 'button', class: cls, 'data-action': action, 'aria-label': label, ...extra }, content ?? label);
}

const pad = (n) => String(n).padStart(2, '0');
const clock = (d) => `${d.getHours()}:${pad(d.getMinutes())}`;
const mmss = (s) => `${Math.floor(s / 60)}:${pad(Math.floor(s % 60))}`;
const shortDate = (d) => d.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' }).replace(/,/g, '');

/* ---------- Elements ---------- */

const stage = document.getElementById('stage');
const backdrop = document.getElementById('backdrop');
const head = document.getElementById('screen-head');
const body = document.getElementById('screen-body');
const navList = document.getElementById('nav-list');
const sampleSwitch = document.getElementById('sample-switch');
const conceptInputs = document.querySelectorAll('input[name="concept"]');

/* ---------- Shared pieces ---------- */

function headClock() {
  return h('time', { class: 'head-clock', 'data-clock': '' }, clock(new Date()));
}

function setHead(title, sub, actions) {
  head.replaceChildren(
    h('div', { class: 'head-titles' }, h('h1', { text: title }), sub ? h('p', { class: 'head-sub', text: sub }) : null),
    h('div', { class: 'head-actions' }, actions || [], headClock()),
  );
}

function renderNav() {
  navList.replaceChildren(...VIEWS.map(([id, label, ic]) => h('li', null,
    h('button', {
      type: 'button',
      class: 'nav-item',
      'data-action': `view:${id}`,
      'aria-current': state.view === id ? 'page' : null,
    }, icon(ic), h('span', { text: label })))));
}

/* ---------- Home ---------- */

function renderHome() {
  head.replaceChildren();
  backdrop.replaceChildren();
  const now = new Date();
  const cond = CONDITIONS[WEATHER.condition];
  body.replaceChildren(h('section', { class: 'home', 'aria-label': 'Clock' },
    h('button', { type: 'button', class: 'weather-shortcut', 'data-action': 'view:weather', 'aria-label': `Open forecast. ${cond[1]}, ${WEATHER.temp} degrees` },
      icon(cond[0]), h('span', { text: `${WEATHER.temp}°` })),
    h('div', { class: 'home-clock' },
      h('p', { class: 'home-meta' },
        h('span', { class: 'home-temp' }, icon(cond[0]), `${WEATHER.temp}°`),
        h('span', { class: 'home-divider', 'aria-hidden': 'true', text: '|' }),
        h('span', { 'data-date': '', text: shortDate(now) })),
      h('p', { class: 'home-time', 'data-clock': '', text: clock(now) }))));
}

/* ---------- Music ---------- */

function coverEl(s, cls) {
  if (s.art) return h('img', { class: cls, src: s.art, alt: s.artAlt, style: { 'object-position': s.focus || '50% 50%' } });
  return h('div', { class: `${cls} cover-fallback`, role: 'img', 'aria-label': 'No artwork for this track' },
    h('span', { class: 'fallback-rings', 'aria-hidden': 'true' }), icon('i-music', 'fallback-icon'));
}

function musicBackdrop(s) {
  const [c1, c2, c3] = s.palette;
  backdrop.style.setProperty('--c1', c1);
  backdrop.style.setProperty('--c2', c2);
  backdrop.style.setProperty('--c3', c3);
  const layers = [];
  if (state.concept === 'wash' && s.art) layers.push(h('img', { class: 'bd-wash', src: s.art, alt: '' }));
  else if (state.concept === 'bleed' && s.art) layers.push(h('img', { class: 'bd-bleed', src: s.art, alt: '', style: { 'object-position': s.focus || '50% 50%' } }));
  else layers.push(h('div', { class: 'bd-colour' }));
  layers.push(h('div', { class: 'bd-shade' }), h('div', { class: 'bd-grain' }));
  backdrop.replaceChildren(...layers);
}

function renderMusic() {
  const s = SAMPLES[state.sample];
  const isRadio = s.kind === 'radio';
  musicBackdrop(s);

  const status = isRadio ? (state.playing ? 'Live radio' : 'Radio stopped') : (state.playing ? 'Now playing' : 'Paused');
  setHead(status, null);

  const meta = h('div', { class: 'music-meta' },
    isRadio ? h('p', { class: 'music-station' }, icon('i-radio'), h('span', { text: s.station })) : null,
    h('h2', { class: 'music-title', text: s.title }),
    s.artist ? h('p', { class: 'music-artist', text: s.artist }) : null,
    s.album && s.album !== s.artist && s.album !== s.title ? h('p', { class: 'music-album', text: s.album }) : null);

  let timeline;
  if (isRadio) {
    timeline = h('div', { class: 'music-timeline is-live' },
      h('span', { class: 'live-badge' }, h('span', { class: 'live-dot', 'aria-hidden': 'true' }), 'Live'),
      h('span', { class: 'live-note', text: 'Broadcasting now. No track length.' }));
  } else {
    const el = state.elapsed[state.sample];
    const pct = Math.min(100, (el / s.duration) * 100);
    timeline = h('div', { class: 'music-timeline' },
      h('span', { class: 'time', 'data-elapsed': '', text: mmss(el) }),
      h('div', { class: 'progress', role: 'progressbar', 'aria-label': 'Track position', 'aria-valuemin': 0, 'aria-valuemax': s.duration, 'aria-valuenow': Math.round(el), 'aria-valuetext': `${mmss(el)} of ${mmss(s.duration)}` },
        h('span', { class: 'progress-fill', style: { width: `${pct}%` } })),
      h('span', { class: 'time', text: mmss(s.duration) }));
  }

  const playLabel = isRadio ? (state.playing ? 'Stop radio' : 'Play radio') : (state.playing ? 'Pause' : 'Play');
  const playIcon = state.playing ? (isRadio ? 'i-stop' : 'i-pause') : 'i-play';
  const transport = h('div', { class: 'transport' },
    btn('Previous track', 'music:prev', icon('i-prev'), 'round', { disabled: isRadio, hidden: isRadio ? null : false, 'aria-hidden': isRadio ? 'true' : null, tabindex: isRadio ? '-1' : null }),
    btn(playLabel, 'music:play', icon(playIcon), 'round play'),
    btn('Next track', 'music:next', icon('i-next'), 'round', { disabled: isRadio, 'aria-hidden': isRadio ? 'true' : null, tabindex: isRadio ? '-1' : null }),
    isRadio ? h('span', { class: 'round-spacer', 'aria-hidden': 'true' })
      : btn('Shuffle', 'music:shuffle', icon('i-shuffle'), 'round small', { 'aria-pressed': String(state.shuffle) }));

  const volume = h('label', { class: 'volume' },
    icon('i-volume'),
    h('span', { class: 'sr-only', text: 'Volume' }),
    h('input', { type: 'range', min: 0, max: 100, step: 1, value: state.volume, 'data-input': 'volume', style: { '--fill': `${state.volume}%` } }),
    h('output', { class: 'volume-value', text: `${state.volume}%` }));

  const speaker = h('p', { class: 'speaker' }, icon('i-speaker'), h('span', { class: 'sr-only', text: 'Playing on ' }), SPEAKER);

  body.replaceChildren(h('section', { class: `music concept-${state.concept}${isRadio ? ' is-radio' : ''}${s.art ? '' : ' no-art'}`, 'aria-label': 'Music' },
    h('div', { class: 'music-art' }, state.concept === 'bleed' ? null : coverEl(s, 'cover')),
    h('div', { class: 'music-main' },
      meta,
      timeline,
      h('div', { class: 'music-controls' }, transport, h('div', { class: 'music-output' }, volume, speaker)))));
}

/* ---------- Weather ---------- */

function renderWeather() {
  backdrop.replaceChildren();
  const now = new Date();
  setHead('Weather', `${WEATHER.place}. ${WEATHER.source}, updated ${clock(new Date(now.getTime() - 14 * 60000))}`);
  const cond = CONDITIONS[WEATHER.condition];

  const current = h('section', { class: 'wx-now', 'aria-label': 'Now' },
    h('div', { class: 'wx-now-main' },
      icon(cond[0], 'icon wx-now-icon'),
      h('p', { class: 'wx-now-temp' }, String(WEATHER.temp), h('span', { class: 'deg', text: '°C' }))),
    h('p', { class: 'wx-now-cond', text: cond[1] }),
    h('p', { class: 'wx-now-range' },
      h('span', null, 'High ', h('b', { text: `${WEATHER.high}°` })),
      h('span', null, 'Low ', h('b', { text: `${WEATHER.low}°` }))));

  const start = now.getHours() + 1;
  const hours = WEATHER.hourly.map(([c, t, rain], i) => {
    const label = `${(start + i) % 24}:00`;
    const ci = CONDITIONS[c];
    return h('li', { class: 'wx-hour', title: `${label}: ${ci[1]}, ${t}°, ${rain}% chance of rain` },
      h('span', { class: 'wx-hour-time', text: label }),
      icon(ci[0], 'icon wx-hour-icon'),
      h('span', { class: 'sr-only', text: ci[1] }),
      h('span', { class: 'wx-hour-temp', text: `${t}°` }),
      h('span', { class: 'rain-col', 'aria-hidden': 'true' }, h('span', { class: 'rain-fill', style: { height: `${rain}%` } })),
      h('span', { class: 'wx-hour-rain' }, h('span', { class: 'sr-only', text: 'Chance of rain ' }), `${rain}%`));
  });

  const days = WEATHER.daily.map(([c, hi, lo, rain], i) => {
    const d = new Date(now); d.setDate(d.getDate() + i);
    const name = i === 0 ? 'Today' : d.toLocaleDateString('en-GB', { weekday: 'short' });
    const ci = CONDITIONS[c];
    return h('li', { class: 'wx-day' },
      h('span', { class: 'wx-day-name', text: name }),
      icon(ci[0], 'icon wx-day-icon'),
      h('span', { class: 'wx-day-cond', text: ci[1] }),
      h('span', { class: 'wx-day-temps' },
        h('b', null, h('span', { class: 'sr-only', text: 'High ' }), `${hi}°`),
        h('span', { class: 'wx-day-low' }, h('span', { class: 'sr-only', text: 'Low ' }), `${lo}°`)),
      h('span', { class: 'wx-day-rain' }, icon('i-drop', 'icon tiny'), h('span', { class: 'sr-only', text: 'Chance of rain ' }), `${rain}%`));
  });

  body.replaceChildren(h('div', { class: 'weather' },
    current,
    h('section', { class: 'wx-hours', 'aria-labelledby': 'wx-hours-h' },
      h('div', { class: 'wx-section-head' },
        h('h2', { id: 'wx-hours-h', text: 'Next 8 hours' }),
        h('p', { class: 'wx-key' }, h('span', { class: 'rain-swatch', 'aria-hidden': 'true' }), 'Chance of rain, 0 to 100%')),
      h('ol', { class: 'wx-hour-list' }, hours)),
    h('section', { class: 'wx-days', 'aria-labelledby': 'wx-days-h' },
      h('h2', { id: 'wx-days-h', text: 'Next 5 days' }),
      h('ol', { class: 'wx-day-list' }, days))));
}

/* ---------- HomeGuide ---------- */

function guideActions() {
  return [
    h('button', { type: 'button', class: 'pill-btn', 'data-action': 'guide:pin', 'aria-pressed': String(state.pinned) },
      icon(state.pinned ? 'i-check' : 'i-pin'), state.pinned ? 'Kept open' : 'Keep open'),
    h('button', { type: 'button', class: 'pill-btn', 'data-action': 'view:home' }, 'Done'),
  ];
}

function renderGuide() {
  backdrop.replaceChildren();
  const a = APPLIANCES.find((x) => x.id === state.appliance);
  if (a) return renderGuideReading(a);

  setHead('HomeGuide', 'Choose an appliance, or just ask.', guideActions());
  body.replaceChildren(h('div', { class: 'guide' },
    h('ul', { class: 'guide-grid', 'aria-label': 'Appliances' }, APPLIANCES.map((x) => h('li', null,
      h('button', { type: 'button', class: 'appliance', 'data-action': `guide:open:${x.id}` },
        h('span', { class: 'appliance-icon' }, icon(x.icon)),
        h('span', { class: 'appliance-name', text: x.name }),
        h('span', { class: 'appliance-model', text: [x.maker, x.model].filter(Boolean).join(' ') }))))),
    h('p', { class: 'ask-hint' }, icon('i-mic'),
      h('span', null, 'Try ', h('q', { text: 'How do I use the defrost setting on my microwave?' })))));
}

function renderGuideReading(a) {
  setHead(a.name, [a.maker, a.model, a.region].filter(Boolean).join(' '), [
    h('button', { type: 'button', class: 'pill-btn', 'data-action': 'guide:back' }, icon('i-back'), 'All appliances'),
    ...guideActions(),
  ]);
  body.replaceChildren(h('div', { class: 'reading' },
    h('article', { class: 'reading-answer' },
      h('p', { class: 'sample-tag', text: 'Sample layout, not real guidance' }),
      h('p', { class: 'reading-question', text: `Your question about the ${a.maker} ${a.name.toLowerCase()} appears here.` }),
      h('p', { class: 'reading-text', text: `The answer from the ${a.maker} manual is shown here in large type, so it can be read from across the kitchen.` }),
      h('p', { class: 'reading-text muted', text: 'Long answers continue below and can be scrolled.' })),
    h('aside', { class: 'reading-sources', 'aria-label': 'Manual excerpts' },
      h('h2', { text: 'From the manual' }),
      h('ul', null,
        h('li', null, h('b', { text: `${a.maker} manual, page 12` }), h('span', { text: 'Excerpt text appears here.' })),
        h('li', null, h('b', { text: `${a.maker} manual, page 18` }), h('span', { text: 'Excerpt text appears here.' }))))));
}

/* ---------- Controls ---------- */

function renderControls() {
  backdrop.replaceChildren();
  setHead('Controls', 'Kitchen', [h('span', { class: 'demo-chip', text: 'Demo: changes stay in this mockup' })]);

  const lights = state.lights.map((l) => h('li', null,
    h('button', { type: 'button', class: `light${l.on ? ' is-on' : ''}`, 'data-action': `light:${l.id}`, 'aria-pressed': String(l.on) },
      icon(l.on ? 'i-bulb-on' : 'i-bulb', 'icon light-icon'),
      h('span', { class: 'light-name', text: l.name }),
      h('span', { class: 'light-state', text: l.on ? 'On' : 'Off' }))));

  const heat = state.heating.map((r) => {
    const heating = r.target > r.current;
    return h('li', { class: `heat${heating ? ' is-heating' : ''}` },
      h('div', { class: 'heat-top' },
        h('h3', { class: 'heat-name', text: r.name }),
        h('p', { class: 'heat-state' }, icon(heating ? 'i-flame' : 'i-thermo'), heating ? 'Heating' : 'Not heating')),
      h('p', { class: 'heat-current' }, h('span', { class: 'sr-only', text: 'Now ' }), r.current.toFixed(1), h('span', { class: 'deg', text: '°' })),
      h('div', { class: 'heat-set' },
        btn(`Lower ${r.name} target`, `heat:${r.id}:-0.5`, icon('i-minus'), 'round small'),
        h('p', { class: 'heat-target', 'aria-live': 'polite' }, h('span', { text: 'Set to' }), h('b', { text: `${r.target.toFixed(1)}°` })),
        btn(`Raise ${r.name} target`, `heat:${r.id}:0.5`, icon('i-plus'), 'round small')));
  });

  body.replaceChildren(h('div', { class: 'controls' },
    h('section', { class: 'ctl-group', 'aria-labelledby': 'ctl-lights' },
      h('h2', { id: 'ctl-lights' }, 'Kitchen lights'),
      h('ul', { class: 'light-grid' }, lights)),
    h('section', { class: 'ctl-group', 'aria-labelledby': 'ctl-heat' },
      h('h2', { id: 'ctl-heat' }, 'Heating'),
      h('ul', { class: 'heat-grid' }, heat)),
    h('p', { class: 'ask-hint' }, icon('i-mic'), h('span', null, 'Try ', h('q', { text: 'Turn on the kitchen lights.' })))));
}

/* ---------- Render ---------- */

const RENDER = { home: renderHome, music: renderMusic, weather: renderWeather, guide: renderGuide, controls: renderControls };

function syncUrl() {
  const p = new URLSearchParams();
  p.set('view', state.view);
  p.set('concept', state.concept);
  p.set('sample', state.sample);
  if (state.view === 'guide' && state.appliance) p.set('appliance', state.appliance);
  history.replaceState(null, '', `?${p}`);
}

function render(focusSelector) {
  stage.dataset.view = state.view;
  stage.dataset.concept = state.concept;
  backdrop.removeAttribute('style');
  RENDER[state.view]();
  renderNav();
  for (const input of conceptInputs) input.checked = input.value === state.concept;
  sampleSwitch.value = state.sample;
  syncUrl();
  if (focusSelector) {
    const el = stage.querySelector(focusSelector);
    if (el) el.focus();
  }
}

/* ---------- Events ---------- */

stage.addEventListener('click', (e) => {
  const b = e.target.closest('[data-action]');
  if (!b || b.disabled) return;
  const [kind, a, c] = b.dataset.action.split(':');
  const keep = `[data-action="${b.dataset.action}"]`;
  switch (kind) {
    case 'view':
      state.view = a;
      if (a !== 'guide') state.appliance = null;
      render(`.nav-item[data-action="view:${a}"]`);
      return;
    case 'music': {
      const s = SAMPLES[state.sample];
      if (a === 'play') state.playing = !state.playing;
      if (a === 'shuffle') state.shuffle = !state.shuffle;
      if (a === 'prev' && s.kind === 'song') state.elapsed[state.sample] = 0;
      if (a === 'next' && s.kind === 'song') state.elapsed[state.sample] = 0;
      render(keep);
      return;
    }
    case 'guide':
      if (a === 'open') { state.appliance = c; render('[data-action="guide:back"]'); return; }
      if (a === 'back') { const prev = state.appliance; state.appliance = null; render(`[data-action="guide:open:${prev}"]`); return; }
      if (a === 'pin') state.pinned = !state.pinned;
      render(keep);
      return;
    case 'light': {
      const l = state.lights.find((x) => x.id === a);
      if (a === 'all') {
        const on = !l.on;
        for (const x of state.lights) x.on = on;
      } else {
        l.on = !l.on;
        state.lights[0].on = state.lights.slice(1).some((x) => x.on);
      }
      render(keep);
      return;
    }
    case 'heat': {
      const r = state.heating.find((x) => x.id === a);
      r.target = Math.min(28, Math.max(7, r.target + Number(c)));
      render(keep);
      return;
    }
    default:
  }
});

stage.addEventListener('input', (e) => {
  if (e.target.dataset.input !== 'volume') return;
  state.volume = Number(e.target.value);
  const out = e.target.parentElement.querySelector('.volume-value');
  if (out) out.textContent = `${state.volume}%`;
  e.target.style.setProperty('--fill', `${state.volume}%`);
});

for (const input of conceptInputs) {
  input.addEventListener('change', () => {
    state.concept = input.value;
    if (state.view !== 'music') state.view = 'music';
    render();
  });
}

sampleSwitch.addEventListener('change', () => {
  state.sample = pick(sampleSwitch.value, Object.keys(SAMPLES), 'photo');
  state.playing = true;
  if (state.view !== 'music') state.view = 'music';
  render();
});

/* Clock and track position tick locally. Text only, no animation. */
setInterval(() => {
  const now = new Date();
  for (const el of document.querySelectorAll('[data-clock]')) el.textContent = clock(now);
  for (const el of document.querySelectorAll('[data-date]')) el.textContent = shortDate(now);
  const s = SAMPLES[state.sample];
  if (state.playing && s.kind === 'song') {
    const next = state.elapsed[state.sample] + 1;
    state.elapsed[state.sample] = next >= s.duration ? 0 : next;
    if (state.view === 'music') {
      const el = state.elapsed[state.sample];
      const t = stage.querySelector('[data-elapsed]');
      const bar = stage.querySelector('.progress');
      if (t) t.textContent = mmss(el);
      if (bar) {
        bar.setAttribute('aria-valuenow', String(el));
        bar.setAttribute('aria-valuetext', `${mmss(el)} of ${mmss(s.duration)}`);
        bar.firstElementChild.style.width = `${(el / s.duration) * 100}%`;
      }
    }
  }
}, 1000);

render();
