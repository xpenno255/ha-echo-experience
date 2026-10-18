/* Echo Experience 0.8.3 — redesigned views (dedicated answer, conversion and timer layouts in 0.8.1) with labelled navigation, three music backgrounds (artwork wash, colour atmosphere, full-bleed) over one fixed music layout, direct light and heating controls, device-scoped playback and voice dismissal of ringing timers. */
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icon = name => `<ha-icon icon="mdi:${name}"></ha-icon>`;
const clock = date => date.toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'});
const duration = seconds => {const n=Math.max(0,Math.ceil(seconds));return n>=3600?`${Math.floor(n/3600)}:${String(Math.floor(n%3600/60)).padStart(2,'0')}:${String(n%60).padStart(2,'0')}`:`${Math.floor(n/60)}:${String(n%60).padStart(2,'0')}`;};
const weatherIcon = c => ({sunny:'weather-sunny','clear-night':'weather-night',partlycloudy:'weather-partly-cloudy',cloudy:'weather-cloudy',rainy:'weather-rainy',pouring:'weather-pouring',snowy:'weather-snowy',fog:'weather-fog',windy:'weather-windy','lightning-rainy':'weather-lightning-rainy'}[c]||'weather-cloudy');
const condition = c => ({partlycloudy:'Partly cloudy','clear-night':'Clear tonight','lightning-rainy':'Thundery showers'}[c]||String(c||'Unavailable').replace(/-/g,' '));
// Voice Satellite keeps one browser-wide session at window.__vsSession whose timer manager tracks the ringing state
// (timer.alertActive) and owns dismissal (timer.dismissAlert(): done chime, native Kiosk alert cleared through
// kioskSatellite.setVoiceTimerAlert on 2026.9.10+, DOM alert and blur removed, stop model disarmed). That flag is the
// only truthful source: since Kiosk Satellite gained native timer alerts the .vs-timer-alert element is not rendered at
// all, so a DOM query says "nothing ringing" while the device is sounding. The DOM gesture (Escape, two taps within
// 400 ms) stays as a fallback for builds without the session global.
const alertSelector = '.vs-timer-alert';
const wait = ms => new Promise(r=>setTimeout(r,ms));
const vsTimer = win => { try{return win.__vsSession?.timer||null;}catch(e){return null;} };
// null = unknown (no session to ask), true/false = the session's own answer.
const alertState = doc => { const t=vsTimer(doc.defaultView||window); return t&&'alertActive' in t?!!t.alertActive:(doc.querySelector(alertSelector)?true:null); };
const alertPresent = doc => alertState(doc)===true;
// Which satellite this browser runs. Voice Satellite resolves it the same way (bundle: Ya()/Qa()): the localStorage key
// "vs-satellite-entity" holds the entity it validated against hass.entities, falling back to satellite_entity inside the
// "vs-panel-config" JSON it hydrates from voice_satellite/get_panel_settings. window.__vsExternalSettings.get().satellite
// (its Kiosk-facing API) returns exactly that precedence, so it is tried first.
const browserSatellite = (win) => {
  try{const s=win.__vsExternalSettings?.get?.()?.satellite;if(s)return s;}catch(e){}
  try{const s=win.localStorage?.getItem('vs-satellite-entity');if(s)return s;}catch(e){}
  try{return JSON.parse(win.localStorage?.getItem('vs-panel-config')||'{}').satellite_entity||null;}catch(e){return null;}
};
// Only the browser that hosts this profile's Voice Satellite session may act on or report about its alarms. A second
// dashboard (phone, laptop) subscribed to the same profile has no alert to clear and must stay silent.
const hostsSatellite = (doc,satellite) => !!(satellite&&doc.getElementById?.('voice-satellite-ui')&&browserSatellite(doc.defaultView||window)===satellite);
const dismissNativeAlert = async (doc=document) => {
  if(!alertPresent(doc))return false;
  const win=doc.defaultView||window;
  const t=vsTimer(win);
  if(t&&typeof t.dismissAlert==='function'){
    try{t.dismissAlert();}catch(e){}
    for(let i=0;i<6&&t.alertActive;i++)await wait(150);
    return !t.alertActive;
  }
  doc.dispatchEvent(new win.KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}));
  if(!alertPresent(doc))return true;
  doc.body.dispatchEvent(new win.MouseEvent('click',{bubbles:true,cancelable:true}));
  await wait(60);
  // The first tap may already have cleared it (or the user did); a stray second tap would hit whatever is underneath.
  if(alertPresent(doc))doc.body.dispatchEvent(new win.MouseEvent('click',{bubbles:true,cancelable:true}));
  for(let i=0;i<6&&alertPresent(doc);i++)await wait(150);
  return !alertPresent(doc);
};
const routes = [['home','Home','home-outline'],['music','Music','music'],['weather','Weather','weather-partly-cloudy'],['guide','HomeGuide','book-open-page-variant-outline','Guide'],['controls','Controls','tune-variant']];
const moreRoutes = [['timers','Timers','timer-outline'],['answer','Conversions','calculator-variant-outline']];
const STYLES = ['wash','colour','bleed'];
// Only same-origin paths (HA's media proxy) or https artwork are ever placed in the page.
const safeUrl = u => typeof u==='string'&&((u.startsWith('/')&&!u.startsWith('//'))||u.startsWith('https://'));
// media_player supported_features bits. Only features the player positively reports are offered.
const FEATURE = {pause:1,volume:4,previous:16,next:32,stop:4096,play:16384,shuffle:32768};
const supports = (a,bit) => a.supported_features!=null&&!!(Number(a.supported_features)&bit);
// Positive evidence only: a station channel (Sonos reports this even with media_content_type "music"), an explicit
// radio/channel content type, or a stream URI scheme that only radio uses. A missing duration alone is not radio.
const isRadio = a => !!a.media_channel||['radio','channel'].includes(a.media_content_type)||/^(x-sonosapi-stream|x-sonosapi-hls|x-rincon-mp3radio):/.test(a.media_content_id||'')||/^[a-z0-9_-]+:\/\/radio\//i.test(a.media_content_id||'');
const DEFAULT_PALETTE = ['#2C4B5C','#1E3644','#45405E'];
const hex = (r,g,b) => '#'+[r,g,b].map(v=>Math.round(Math.max(0,Math.min(255,v))).toString(16).padStart(2,'0')).join('');
// Keep sampled colours dark and calm enough for white text over the readability layer.
const tone = ([r,g,b]) => {r/=255;g/=255;b/=255;const max=Math.max(r,g,b),min=Math.min(r,g,b),d=max-min;let h=0,s=0,l=(max+min)/2;
  if(d){s=d/(1-Math.abs(2*l-1));h=max===r?((g-b)/d)%6:max===g?(b-r)/d+2:(r-g)/d+4;h*=60;if(h<0)h+=360;}
  s=Math.min(s,.62);l=Math.min(.42,Math.max(.2,l));const c=(1-Math.abs(2*l-1))*s,x=c*(1-Math.abs((h/60)%2-1)),m=l-c/2;
  const [R,G,B]=h<60?[c,x,0]:h<120?[x,c,0]:h<180?[0,c,x]:h<240?[0,x,c]:h<300?[x,0,c]:[c,0,x];return hex((R+m)*255,(G+m)*255,(B+m)*255);};
// Three saturation-weighted zone colours from a 24px thumbnail. Throws if the canvas is cross-origin tainted.
const artPalette = (img,doc) => {const c=doc.createElement('canvas');c.width=c.height=24;const g=c.getContext('2d',{willReadFrequently:true});g.drawImage(img,0,0,24,24);const d=g.getImageData(0,0,24,24).data;
  return [[0,0,12,14],[12,0,24,14],[0,12,24,24]].map(([x0,y0,x1,y1],z)=>{let r=0,gr=0,b=0,n=0;for(let y=y0;y<y1;y++)for(let x=x0;x<x1;x++){const i=(y*24+x)*4;if(d[i+3]<128)continue;const w=Math.max(d[i],d[i+1],d[i+2])-Math.min(d[i],d[i+1],d[i+2])+16;r+=d[i]*w;gr+=d[i+1]*w;b+=d[i+2]*w;n+=w;}return n?tone([r/n,gr/n,b/n]):DEFAULT_PALETTE[z];});};
const shortName = (name,prefix) => {const rest=prefix&&name.startsWith(prefix+' ')?name.slice(prefix.length+1):name;return rest?rest.charAt(0).toUpperCase()+rest.slice(1):name;};
// The leading word shared by every light name ("Kitchen"), used as the group heading instead of repeating it.
const commonPrefix = names => {if(names.length<2)return '';const first=names[0].split(' ')[0];return names.every(n=>n.split(' ')[0]===first&&n.split(' ').length>1)?first:'';};

class EchoExperienceCard extends HTMLElement {
  constructor(){super();this.attachShadow({mode:'open'});this.view='home';this.data=null;this.error='';this.busy=false;this.touched=0;this._generation=0;this.palettes=new Map();this.failedArt=new Set();}
  setConfig(config){if(!config.device)throw new Error('Echo Experience needs a device profile');this.config=config;this.render();}
  getCardSize(){return 8;}
  set hass(hass){const before=this._hass;this._hass=hass;
    if(this.isConnected && this.config && (!this.connection || this.connection!==hass.connection))this.connect();
    if(this.data){const p=this.data.profile;this.syncPlayback();const watched=[p.satellite,p.weather,p.kiosk_hold,this.player,this.activePlayer,...(p.native_players||[]),...(p.controls||[])];if(watched.some(e=>before?.states[e]!==hass.states[e]))this.render();}
  }
  syncPlayback(){
    if(this.config?.ambient||!this.data)return;
    const active=this.activePlayer,current=this._hass?.states[active]?.state;
    const changed=this._lastPlayer!==active||this._lastPlayback!==current;
    if(changed&&current==='playing'&&['home','music'].includes(this.view)){this.view='music';this.autoMusic=true;}
    if(changed&&['idle','off','standby'].includes(current)&&this.view==='music'&&this.autoMusic){this.view='home';this.autoMusic=false;}
    this._lastPlayer=active;this._lastPlayback=current;
  }
  get player(){return this.data?.music_player||this.data?.profile.music_player;}
  // What is actually carrying this Echo's music: the selected player when active, else a playing (then paused) native
  // member's group coordinator, so the Sonos app or Spotify Connect shows here. Mirrors Experience.playback_target.
  get activePlayer(){const states=this._hass?.states||{},selected=this.player,native=this.data?.profile?.native_players||[];
    for(const wanted of ['playing','paused']){if(states[selected]?.state===wanted)return selected;const hit=native.find(e=>states[e]?.state===wanted),lead=states[hit]?.attributes?.group_members?.[0];if(hit)return states[lead]?.state===wanted?lead:hit;}
    return selected;}
  get musicStyle(){const s=this.data?.profile?.music_style;return STYLES.includes(s)?s:'wash';}
  // The card fills the space below its own top edge; recompute that on resize/rotation without re-rendering, so a
  // focused form keeps its text and the navigation never sits below a stale height.
  fit(){this.style?.setProperty?.('--echo-height',`${Math.max(400,window.innerHeight-this.getBoundingClientRect().top)}px`);}
  connectedCallback(){this._onResize=this._onResize||(()=>this.fit());window.addEventListener?.('resize',this._onResize);this.tickHandle=setInterval(()=>this.tick(),1000);this.refreshHandle=setInterval(()=>this.refresh(),60000);if(this._hass&&this.config)this.connect();}
  disconnectedCallback(){if(this._onResize)window.removeEventListener?.('resize',this._onResize);clearInterval(this.tickHandle);clearInterval(this.refreshHandle);clearTimeout(this.retryHandle);this.watchReady(null);this._generation++;this.drop();this.connection=null;}
  // While Home Assistant starts, the socket is back before this integration registers its commands ("Unknown command"),
  // and the socket library's own resubscribe after a restart can fail the same way. So: retry with backoff, subscribe
  // afresh on every reconnect, and clear the connection error once data arrives again.
  drop(){const u=this.unsubscribe;this.unsubscribe=null;try{Promise.resolve(u?.()).catch(()=>{});}catch(e){}}
  watchReady(conn){if(this._readyConn===conn)return;this._readyConn?.removeEventListener?.('ready',this._onReady);this._readyConn=conn;
    this._onReady=this._onReady||(()=>{this.retries=0;this.connect();});conn?.addEventListener?.('ready',this._onReady);}
  linkFailed(message){this.error=this.linkError=message;this.render();}
  async connect(){
    if(!this._hass||!this.config)return;
    clearTimeout(this.retryHandle);
    const generation=++this._generation;this.drop();this.connection=this._hass.connection;this.watchReady(this.connection);
    try{
      const unsubscribe=this.config.ambient?()=>{}:await this.connection.subscribeMessage(event=>this.receive(event),{type:'echo_experience/subscribe',device:this.config.device});
      if(generation!==this._generation){unsubscribe();return;}this.unsubscribe=unsubscribe;this.retries=0;
      await this.refresh(true);
    }catch(err){if(generation!==this._generation)return;this.linkFailed(err.message||'Unable to connect');
      this.retries=(this.retries||0)+1;this.retryHandle=setTimeout(()=>{if(this.isConnected&&generation===this._generation)this.connect();},Math.min(30000,1000*2**this.retries));}
  }
  async refresh(initial=false){
    if(!this._hass||!this.config||!this.isConnected)return;
    try{
      const data=await this._hass.callWS({type:'echo_experience/state',device:this.config.device,forecast:false});
      this.data=data;if(this.linkError){if(this.error===this.linkError)this.error='';this.linkError='';}
      if(initial && !this.config.ambient && data.result && Date.now()/1000-data.result.timestamp<300){this.view=data.result.view;this.result=data.result;}
      this.syncPlayback();
      this.render();
      if(this.config.ambient)return;
      try{const fresh=await this._hass.callWS({type:'echo_experience/state',device:this.config.device,forecast:true});this.data.forecast=fresh.forecast;this.forecastError='';this.render();}catch(err){this.forecastError=err.message;this.render();}
    }catch(err){this.linkFailed(err.message||'Connection lost');}
  }
  receive(event){
    if(this.config.ambient||event.device!==this.config.device)return;
    if(event.timers && this.data)this.data.timers=event.timers;
    if(event.ringing && this.data)this.data.ringing=event.ringing;
    if(event.dismiss)return this.dismiss(event.dismiss);
    if(event.result){this.result=event.result;this.view=event.result.view;
      if(event.result.payload?.player && this.data)this.data.music_player=event.result.payload.player;
      if(this.view==='music')this.autoMusic=true;
      if(this.view==='weather')this.refresh();
    }
    if(event.timer_event?.event_type==='started' && !['guide','weather'].includes(this.view))this.view='timers';
    if(event.timer_event?.event_type==='finished' && this.view!=='guide')this.view='timers';
    this.render();
  }
  hostsSatellite(){return hostsSatellite(this.ownerDocument||document,this.data?.profile?.satellite);}
  async dismiss(request){
    // Runs only in the Echo's own browser session, then reports the outcome so the voice reply is honest.
    if(!this.hostsSatellite())return;
    const doc=this.ownerDocument||document;const state=alertState(doc);
    // Unknown state (no session to ask and no DOM alert) is reported as such, never as "silenced".
    if(state===null){try{await this._hass.callWS({type:'echo_experience/action',device:this.config.device,action:'timer',args:{operation:'dismissed',request:request.request,timers:[],present:false,dismissed:false,unknown:true}});}catch(err){this.error=err.message;}return;}
    const present=state;const dismissed=present&&await dismissNativeAlert(doc);
    const timers=(request.timers||[]).map(t=>t.id);
    if(this.data&&(dismissed||!present))this.data.ringing=(this.data.ringing||[]).filter(t=>!timers.includes(t.id));
    try{await this._hass.callWS({type:'echo_experience/action',device:this.config.device,action:'timer',args:{operation:'dismissed',request:request.request,timers,present,dismissed}});}
    catch(err){this.error=err.message;}
    this.render();
  }
  checkRinging(){
    // The alarm may be silenced by a tap or the stop word without any server call; report that so stale alarms
    // are not dismissed later. Wait a few seconds because Voice Satellite can defer showing the alert briefly.
    const ringing=this.data?.ringing||[];if(!ringing.length||this.config.ambient||!this._hass||!this.hostsSatellite())return;
    const settled=ringing.every(t=>Date.now()/1000-t.finished_at>5);
    // Only the session's own flag may declare an alarm gone; with no session there is no evidence, so stay quiet.
    this._alertMissing=settled&&alertState(this.ownerDocument||document)===false?(this._alertMissing||0)+1:0;
    if(this._alertMissing<3)return;this._alertMissing=0;const timers=ringing.map(t=>t.id);this.data.ringing=[];
    this._hass.callWS({type:'echo_experience/action',device:this.config.device,action:'timer',args:{operation:'dismissed',timers,present:false,dismissed:false}}).catch(()=>{});
    this.render();
  }
  remaining(t){return t.is_active?Math.max(0,t.seconds_left-(Date.now()/1000-t.sampled_at)):t.seconds_left;}
  tick(){
    const now=new Date();this.shadowRoot.querySelectorAll('[data-clock]').forEach(el=>el.textContent=clock(now));
    this.shadowRoot.querySelectorAll('[data-date]').forEach(el=>el.textContent=this.shortDate(now));
    for(const t of this.data?.timers||[])this.shadowRoot.querySelectorAll(`[data-countdown="${CSS.escape(t.id)}"]`).forEach(el=>el.textContent=duration(this.remaining(t)));
    // Song position advances from HA's own timestamps; nothing is re-rendered or re-sampled here.
    this.shadowRoot.querySelectorAll('[data-progress]').forEach(el=>{const pos=this.position(el.dataset);const bar=el.querySelector('i'),label=el.parentElement?.querySelector('[data-elapsed]');if(bar)bar.style.width=`${pos/Number(el.dataset.dur)*100}%`;if(label)label.textContent=duration(pos);el.setAttribute('aria-valuenow',String(Math.round(pos)));});
    this.checkRinging();
    // Guide stays on screen until Done. Transient answers return to music/home.
    if(['answer','weather','controls'].includes(this.view)&&!this.shadowRoot.activeElement&&Date.now()-Math.max(this.touched,(this.result?.timestamp||0)*1000)>120000){this.view=this._hass?.states[this.activePlayer]?.state==='playing'?'music':'home';this.render();}
  }
  async action(action,args={}){
    if(this.config.ambient||this.busy)return;this.busy=true;this.error='';this.touched=Date.now();this.render();
    try{const result=await this._hass.callWS({type:'echo_experience/action',device:this.config.device,action,args});if(result?.timers)this.data.timers=result.timers;if(['needs_clarification','not_found'].includes(result?.status))this.error=result.question||result.message;}
    catch(err){this.error=err.message||'That action could not be completed';}
    finally{this.busy=false;this.render();}
  }
  // Direct entity services for the Controls view. Only entities assigned to this Echo are ever touched.
  service(domain,service,data){
    if(this.config.ambient||!(this.data?.profile?.controls||[]).includes(data.entity_id)||!data.entity_id.startsWith(domain+'.'))return;
    this.touched=Date.now();this.error='';
    return this._hass.callService(domain,service,data).catch(err=>{this.error=err.message||'That change could not be made';this.render();});
  }
  go(view){if(this.config.ambient)return;if(view!=='guide'&&this.ownsHold){this._hass.callService('switch','turn_off',{entity_id:this.data.profile.kiosk_hold}).catch(err=>{this.error=err.message;this.render();});this.ownsHold=false;}this.menuOpen=false;this.musicControls=false;this.touched=Date.now();this.view=view;this.error='';this.render();if(view==='weather')this.refresh();}
  shortDate(date=new Date()){return date.toLocaleDateString('en-GB',{weekday:'short',day:'numeric',month:'short'}).replace(/,/g,'').toUpperCase();}
  button(label,action,content,cls='',attrs=''){return `<button class="${cls}" data-do="${esc(action)}" aria-label="${esc(label)}"${attrs?' '+attrs:''}>${content||esc(label)}</button>`;}
  head(title,sub='',actions=''){return `<header class="view-head"><div class="titles"><h1>${esc(title)}</h1>${sub?`<p class="sub">${esc(sub)}</p>`:''}</div><div class="head-actions">${actions}<span class="head-clock" data-clock>${clock(new Date())}</span></div></header>`;}
  hint(text){return `<p class="hint">${icon('microphone-outline')}<span>Try “${esc(text)}”</span></p>`;}
  timerStrip(){const timers=this.data.timers;if(!timers.length||this.view==='timers')return '';return `<div class="timer-strip">${timers.map(t=>this.button(`Open ${t.name} timer`,'view:timers',`${icon('timer-outline')}<span>${esc(t.name)}</span><b data-countdown="${esc(t.id)}">${duration(this.remaining(t))}</b>${!t.is_active?'<small>Paused</small>':''}`,'timer-chip')).join('')}</div>`;}
  home(){const s=this._hass.states[this.data.profile.weather];const valid=s&&!['unknown','unavailable'].includes(s.state);const temp=valid?s.attributes.temperature:null;
    return `<section class="quiet-home">${this.config.ambient?`<span class="weather-shortcut decorative" aria-hidden="true">${icon('weather-cloudy')}</span>`:this.button('Open weather forecast','view:weather',`${icon(valid?weatherIcon(s.state):'weather-cloudy')}${temp==null?'':`<span>${Math.round(temp)}°</span>`}`,'weather-shortcut')}<div class="home-clock-block"><div class="home-meta"><span class="home-temperature" aria-label="${esc(valid?condition(s.state):'Weather unavailable')}">${icon(valid?weatherIcon(s.state):'cloud-question')} ${temp==null?'—':Math.round(temp)+'°'}</span><span class="home-divider">|</span><span data-date>${this.shortDate()}</span></div><div class="home-time" data-clock>${clock(new Date())}</div></div></section>`;
  }
  // One card per timer, state spelled out with an icon and a word (never colour alone). Finished alarms come first in
  // the server's order (oldest first), then timers in the server's order, so cards never jump while counting down.
  // A finished card has no dismiss button: Voice Satellite owns the alert and its dismissal (tap or "stop").
  timerCard(t,state){const [glyph,word]={running:['timer-outline','Running'],paused:['pause','Paused'],finished:['alarm-light','Finished']}[state];const live=state!=='finished';
    const actions=live?`${this.button(t.is_active?'Pause':'Resume',`timer:${t.is_active?'pause':'resume'}:${t.id}`,`${icon(t.is_active?'pause':'play')}<span>${t.is_active?'Pause':'Resume'}</span>`)}${this.button('Add one minute',`timer:add:${t.id}`,`${icon('plus')}<span>1 min</span>`)}${this.button('Cancel timer',`timer:cancel:${t.id}`,`${icon('close')}<span>Cancel</span>`,'timer-cancel')}`:`<p class="timer-note">${icon('microphone-outline')}<span>Say “stop” or tap the alert to silence it.</span></p>`;
    return `<article class="timer-card is-${state}"><div class="timer-top"><h2 class="timer-name">${esc(t.name)}</h2><span class="timer-state">${icon(glyph)}<span>${word}</span></span></div><div class="countdown${live&&this.remaining(t)>=3600?' is-long':''}" role="timer"${live?` data-countdown="${esc(t.id)}"`:''}>${live?duration(this.remaining(t)):'0:00'}</div><div class="timer-actions">${actions}</div></article>`;}
  ringingCards(){return (this.data.ringing||[]).map(t=>this.timerCard(t,'finished')).join('');}
  timers(){const timers=this.data.timers||[],ringing=this.data.ringing||[],n=timers.length+ringing.length,running=timers.filter(t=>t.is_active).length;
    const sub=n?[[ringing.length,'finished'],[running,'running'],[timers.length-running,'paused']].filter(([c])=>c).map(([c,w])=>`${c} ${w}`).join(' · '):'Ready when you are';
    const layout=!n?'empty':n===1?'one':n===2?'two':n<=4?'few':'many';
    return `${this.head('Timers',sub)}<div class="view-body timers-body"><div class="timer-grid layout-${layout}">${n?this.ringingCards()+timers.map(t=>this.timerCard(t,t.is_active?'running':'paused')).join(''):`<div class="empty timer-empty"><div class="empty-icon">${icon('timer-sand')}</div><h2>Something on the stove?</h2><p>“Set a pasta timer for twelve minutes”, or start one below.</p><p class="muted">Each Echo keeps its own timers.</p></div>`}</div>
    <form id="timer-form" class="inline-form timer-form" aria-label="Start a timer"><input name="name" aria-label="Timer name" placeholder="Timer name" maxlength="80" value=""><input name="minutes" aria-label="Minutes" type="number" min="0.02" max="1440" step="any" placeholder="Minutes" required><button type="submit" class="primary">${icon('plus')} Start timer</button></form></div>`;}
  // ---- Music -------------------------------------------------------------------------------------------------------
  nowPlaying(){const mp=this._hass.states[this.activePlayer],a=mp?.attributes||{},raw=a.entity_picture_local||a.entity_picture;
    const art=safeUrl(raw)&&!this.failedArt.has(raw)?raw:'';const live=!!mp&&!['unavailable','unknown'].includes(mp.state);return {mp,a:live?a:{},art:live?art:'',live,playing:mp?.state==='playing',radio:live&&isRadio(a)};}
  position(d){const dur=Number(d.dur);let pos=Number(d.pos)||0;const at=Number(d.at);if(d.playing==='1'&&at)pos+=(Date.now()-at)/1000;return Math.min(dur,Math.max(0,pos));}
  // Colour atmosphere: sample each artwork once, in the background, and cache a small bounded set. Failures (CORS,
  // decode) fall back to the theme palette. Results for artwork that is no longer showing are kept but not applied.
  palette(url){
    if(!url)return DEFAULT_PALETTE;const cached=this.palettes.get(url);if(cached!==undefined)return cached||DEFAULT_PALETTE;
    this.palettes.set(url,null);while(this.palettes.size>12)this.palettes.delete(this.palettes.keys().next().value);
    if(typeof Image==='undefined')return DEFAULT_PALETTE;
    const img=new Image();if(url.startsWith('https://'))img.crossOrigin='anonymous';
    img.onload=()=>{if(!this.palettes.has(url))return;let p=null;try{p=artPalette(img,this.ownerDocument||document);}catch(e){}this.palettes.set(url,p);
      const layer=this.shadowRoot.querySelector('.bd-colour');if(p&&layer&&layer.dataset.art===url)p.forEach((c,i)=>layer.style.setProperty(`--c${i+1}`,c));};
    img.src=url;return DEFAULT_PALETTE;}
  musicBackdrop(){const {art}=this.nowPlaying(),style=this.musicStyle;let layer;
    if(art&&style==='wash')layer=`<img class="bd-wash" data-art="${esc(art)}" src="${esc(art)}" alt="">`;
    else if(art&&style==='bleed')layer=`<img class="bd-bleed" data-art="${esc(art)}" src="${esc(art)}" alt="">`;
    else{const p=style==='colour'?this.palette(art):DEFAULT_PALETTE;layer=`<div class="bd-colour" data-art="${esc(art)}" style="--c1:${p[0]};--c2:${p[1]};--c3:${p[2]}"></div>`;}
    return `<div class="backdrop" aria-hidden="true">${layer}<div class="bd-shade"></div></div>`;}
  transport(){const {a,playing,radio}=this.nowPlaying();/* a is empty for a missing or unavailable player, so every slot is disabled */
    const toggle=playing?(supports(a,FEATURE.pause)?'pause':supports(a,FEATURE.stop)?'stop':''):(supports(a,FEATURE.play)?'resume':'');
    const label={pause:'Pause',stop:'Stop',resume:radio?'Play radio':'Play'}[toggle]||(playing?'Pause':'Play');
    const slot=(label,action,name,cls,ok,extra='')=>this.button(label,action,icon(name),cls,`${ok?'':'disabled'} ${extra}`.trim());
    return `<div class="transport">${slot('Previous track','music:previous','skip-previous','round',!radio&&supports(a,FEATURE.previous))}${slot(label,`music:${toggle||'resume'}`,toggle==='pause'?'pause':toggle==='stop'?'stop':'play','round play',!!toggle)}${slot('Next track','music:next','skip-next','round',!radio&&supports(a,FEATURE.next))}${slot(a.shuffle?'Shuffle on':'Shuffle off','music:shuffle',a.shuffle?'shuffle-variant':'shuffle-disabled','round small',!radio&&supports(a,FEATURE.shuffle),`aria-pressed="${!!a.shuffle}"`)}</div>`;}
  music(){const {mp,a,art,live,playing,radio}=this.nowPlaying();const artist=a.media_artist||'',album=a.media_album_name||'',station=a.media_channel||'',title=a.media_title||'';
    const status=!live?'Speaker unavailable':radio?(playing?'Live radio':'Radio paused'):playing?'Now playing':mp?.state==='paused'?'Paused':'Music';
    const speaker=(this.data.profile.speakers||[]).find(s=>s.entity_id===this.activePlayer)?.name||mp?.attributes?.friendly_name||'Speaker';
    const dur=Number(a.media_duration),at=Date.parse(a.media_position_updated_at);let timeline='';
    if(radio)timeline=`<span class="live">${icon('access-point')} Live radio</span>`;
    else if(dur>0){const d={dur,pos:a.media_position,at:isNaN(at)?0:at,playing:playing?'1':'0'},pos=this.position(d);
      timeline=`<span class="time" data-elapsed>${duration(pos)}</span><div class="progress" data-progress data-dur="${dur}" data-pos="${Number(a.media_position)||0}" data-at="${d.at}" data-playing="${d.playing}" role="progressbar" aria-label="Track position" aria-valuemin="0" aria-valuemax="${Math.round(dur)}" aria-valuenow="${Math.round(pos)}"><i style="width:${pos/dur*100}%"></i></div><span class="time">${duration(dur)}</span>`;}
    const canVolume=live&&supports(a,FEATURE.volume)&&a.volume_level!=null,vol=Math.round((a.volume_level??.3)*100);
    return `${this.head(status,'')}<div class="view-body music-body"><section class="music${radio?' is-radio':''}${art?'':' no-art'}">
      <div class="cover">${art?`<img data-art="${esc(art)}" src="${esc(art)}" alt="${radio?'Station artwork':'Album artwork'}">`:`<div class="disc" role="img" aria-label="No artwork"><div>${icon(radio?'radio':'music')}</div></div>`}</div>
      <div class="music-info">${station?`<p class="station">${icon('radio')}<span>${esc(station)}</span></p>`:''}<h2 class="title">${esc(title||(mp&&!['idle','off','standby','unavailable'].includes(mp.state)?'Unknown title':'Ask for music or radio'))}</h2>${artist?`<p class="artist">${esc(artist)}</p>`:''}${album&&album!==artist&&album!==title?`<p class="album">${esc(album)}</p>`:''}<div class="timeline">${timeline}</div></div>
      <div class="music-controls">${this.transport()}<div class="output"><label class="volume">${icon('volume-medium')}<input id="volume" aria-label="Music volume" type="range" min="0" max="100" value="${vol}" style="--fill:${vol}%" ${canVolume?'':'disabled'}><output>${canVolume?vol+'%':'—'}</output></label>${this.button(`Speaker ${speaker}. Change speaker or search music`,'playback',`${icon('speaker')}<span>${esc(speaker)}</span>${icon('chevron-right')}`,'speaker-chip',`aria-expanded="${!!this.musicControls}"`)}</div></div>
    </section></div>${this.musicControls?this.playbackControls():''}`;
  }
  // Secondary panel: speaker choice and search. Transport and volume live in the main view only (no duplicate ids).
  playbackControls(){return `<section class="playback-panel" aria-label="Speaker and search"><div class="panel-title">Speaker and search ${this.button('Close speaker and search','playback',icon('close'),'quiet')}</div><label class="field"><span>Speaker</span><select id="speaker">${(this.data.profile.speakers||[]).map(s=>`<option value="${esc(s.entity_id)}" ${s.entity_id===this.player?'selected':''}>${esc(s.name)}</option>`).join('')}</select></label><form id="music-form" class="inline-form"><input name="query" aria-label="Music search" placeholder="Artist, playlist, song or radio station" required><select name="media_type" aria-label="Music type"><option value="track">Song</option><option value="artist">Artist</option><option value="playlist">Playlist</option><option value="radio">Radio</option><option value="album">Album</option></select><button class="primary" type="submit">Play</button></form></section>`;}
  // ---- Weather -----------------------------------------------------------------------------------------------------
  weather(){const f=this.data.forecast;if(!f)return `${this.head('Weather')}<div class="view-body"><div class="empty">${icon('weather-cloudy')}<p>${esc(this.forecastError||'Loading the local forecast…')}</p></div></div>`;
    const now=Date.now(),unit=f.temperature_unit||'°C',deg=v=>v==null||!Number.isFinite(Number(v))?'—':Math.round(v)+'°';const period=this.result?.view==='weather'?this.result.payload?.period:'today';const tomorrow=new Date();tomorrow.setDate(tomorrow.getDate()+1);
    let hours=(f.hourly||[]).filter(h=>new Date(h.datetime).getTime()>=now-3600000);if(period==='tomorrow')hours=hours.filter(h=>new Date(h.datetime).toDateString()===tomorrow.toDateString());hours=hours.slice(0,8);
    const days=(f.daily||[]).slice(0,5),today=days.find(d=>new Date(d.datetime).toDateString()===new Date().toDateString());
    const rain=p=>p==null||!Number.isFinite(Number(p))?null:Math.min(100,Math.max(0,Math.round(p)));
    const stale=now-f.fetched_at*1000>1800000;
    return `${this.head(period==='tomorrow'?'Tomorrow’s weather':'Weather',`${f.source}, updated ${clock(new Date(f.fetched_at*1000))}${stale?'. May be out of date':''}`)}
    <div class="view-body weather">${this.forecastError?`<div class="error inline">Forecast refresh unavailable. Showing the last forecast.</div>`:''}
      <section class="wx-now" aria-label="Now">${icon(weatherIcon(f.condition))}<p class="wx-temp">${f.temperature==null?'—':Math.round(f.temperature)}<span>${esc(unit)}</span></p><p class="wx-cond">${esc(condition(f.condition))}</p>${today&&(today.temperature!=null||today.templow!=null)?`<p class="wx-range">${today.temperature!=null?`<span>High <b>${deg(today.temperature)}</b></span>`:''}${today.templow!=null?`<span>Low <b>${deg(today.templow)}</b></span>`:''}</p>`:''}</section>
      <section class="wx-hours" aria-labelledby="wx-hours"><div class="wx-label"><h2 id="wx-hours">${period==='tomorrow'?'Tomorrow, hour by hour':'Next few hours'}</h2><p class="wx-key"><i></i>Chance of rain, 0 to 100%</p></div>${hours.length?`<ol class="hour-list">${hours.map(h=>{const r=rain(h.precipitation_probability);return `<li class="hour" title="${esc(`${clock(new Date(h.datetime))}: ${condition(h.condition).replace(/^./,x=>x.toUpperCase())}, ${deg(h.temperature)}, ${r==null?'rain chance unknown':r+'% chance of rain'}`)}"><span class="h-time">${clock(new Date(h.datetime))}</span>${icon(weatherIcon(h.condition))}<span class="visually-hidden">${esc(condition(h.condition))}</span><strong>${deg(h.temperature)}</strong><span class="rain-col" aria-hidden="true"><i style="height:${r??0}%"></i></span><small><span class="visually-hidden">Chance of rain </span>${r==null?'—':r+'%'}</small></li>`;}).join('')}</ol>`:`<p class="muted">${f.hourly_error?'The hourly forecast is unavailable.':'No hourly forecast for this period.'}</p>`}</section>
      <section class="wx-days" aria-labelledby="wx-days"><h2 id="wx-days">Next ${days.length||''} days</h2>${days.length?`<ol class="day-list">${days.map(d=>{const dt=new Date(d.datetime),r=rain(d.precipitation_probability);return `<li class="day"><b class="d-name">${dt.toDateString()===new Date().toDateString()?'Today':dt.toLocaleDateString('en-GB',{weekday:'short'})}</b>${icon(weatherIcon(d.condition))}<span class="d-cond">${esc(condition(d.condition))}</span><span class="d-temps"><strong><span class="visually-hidden">High </span>${deg(d.temperature)}</strong>${d.templow!=null?`<small><span class="visually-hidden">Low </span>${deg(d.templow)}</small>`:''}</span>${r==null?'':`<span class="d-rain">${icon('water-outline')}<span class="visually-hidden">Chance of rain </span>${r}%</span>`}</li>`;}).join('')}</ol>`:`<p class="muted">${f.daily_error?'The daily forecast is unavailable.':'No daily forecast.'}</p>`}</section>
    </div>`;
  }
  // ---- HomeGuide ---------------------------------------------------------------------------------------------------
  guide(){const appliances=this._hass.states['sensor.homeguide_library']?.attributes?.appliances||[];const p=this.result?.view==='guide'?this.result.payload||{}:{};const a=appliances.find(a=>a.id===p.appliance_id);const results=p.guide?.results||[];
    const held=this._hass.states[this.data.profile.kiosk_hold]?.state==='on';
    const actions=`${this.data.profile.kiosk_hold?this.button(held?'Guide kept open':'Keep guide open','hold',`${icon(held?'pin':'pin-outline')}<span>${held?'Kept open':'Keep open'}</span>`,'pill-btn',`aria-pressed="${held}"`):''}${this.button('Done reading','view:home',`${icon('check')}<span>Done</span>`,'pill-btn')}`;
    const sub=a?[a.manufacturer,a.model,a.region].filter(Boolean).join(' '):p.question?'':'Your appliance manuals, ready for questions.';
    if(p.question)return `${this.head(a?.name||'HomeGuide',sub,actions)}<div class="view-body reading"><article class="answer-card"><p class="question">${esc(p.question)}</p><div class="answer">${esc(p.guide?.answer||p.speech||'The assistant is preparing your answer. Source excerpts are below.')}</div></article>${results.length?`<aside class="sources" aria-labelledby="guide-sources"><h2 id="guide-sources">From the manual</h2><ul>${results.map(r=>`<li><b>${esc(r.document||r.document_title||r.title||r.source||r.filename||'Uploaded manual')}${r.page!=null?', page '+esc(r.page):''}</b><p>${esc(r.text||r.content||r.excerpt||r.chunk_text||'')}</p></li>`).join('')}</ul></aside>`:''}</div>`;
    return `${this.head('HomeGuide',sub,actions)}<div class="view-body guide">${appliances.length?`<ul class="appliance-grid" aria-label="Appliances">${appliances.map(a=>`<li class="appliance"><span class="appliance-icon">${icon(({microwave:'microwave',air_fryer:'stove',coffee_machine:'coffee-maker-outline',radiator_valves:'radiator',tumble_dryer:'tumble-dryer'}[a.id]||'book-open-outline'))}</span><h2>${esc(a.name)}</h2><p>${esc([a.manufacturer,a.model].filter(Boolean).join(' '))}</p></li>`).join('')}</ul>`:`<div class="empty"><p>No manuals have been added to HomeGuide yet.</p></div>`}${this.hint('How do I use the defrost setting on my microwave?')}</div>`;
  }
  // Conversions: the original amount is secondary, the converted value and unit primary; the type steps down for long
  // results instead of truncating. Answers: short replies get room, long ones scroll inside the view, never under the nav.
  answer(){const p=this.result?.view==='answer'?this.result.payload||{}:{};
    if(p.equation){const value=Number(p.result).toLocaleString('en-GB',{maximumFractionDigits:4}),unit=String(p.to_unit??''),size=value.length+unit.length*.6;
      return `${this.head('Converted')}<div class="view-body conversion-body"><div class="conversion fit-${size<=8?'l':size<=13?'m':'s'}"><p class="conv-from"><span>${esc(p.value)}</span> <span>${esc(p.from_unit)}</span> <span class="conv-eq" aria-hidden="true">=</span><span class="visually-hidden">is</span></p><p class="conv-to"><strong>${value}</strong> <span class="conv-unit">${esc(unit)}</span></p></div></div>`;}
    if(p.speech){const text=String(p.speech),short=text.length<=160&&text.split('\n').length<=3;
      return `${this.head('Answer')}<div class="view-body answer-body ${short?'is-short':'is-long'}">${p.question?`<p class="answer-q">${esc(p.question)}</p>`:''}<div class="answer-scroll"><p class="answer-text">${esc(text)}</p></div></div>`;}
    return `${this.head('Ask away')}<div class="view-body"><div class="empty compact"><div class="empty-icon">${icon('microphone-outline')}</div><h2>What would you like to know?</h2><p>Ask a question or a unit conversion.</p></div></div>`;
  }
  // ---- Controls ----------------------------------------------------------------------------------------------------
  climateInfo(id){const s=this._hass.states[id],a=s?.attributes||{};const unit=this._hass.config?.unit_system?.temperature||'°C';
    const available=!!s&&!['unavailable','unknown'].includes(s.state);const target=Number(a.temperature),min=Number(a.min_temp),max=Number(a.max_temp);
    const step=Number(a.target_temp_step)>0?Number(a.target_temp_step):unit.includes('F')?1:0.5;
    // Single-setpoint thermostats only; heat_cool ranges and "off" are shown but not adjusted here.
    const adjustable=available&&!['off','heat_cool'].includes(s.state)&&(Number(a.supported_features)&1)===1&&a.temperature!=null&&Number.isFinite(target)&&a.target_temp_low==null&&a.target_temp_high==null&&Number.isFinite(min)&&Number.isFinite(max);
    return {s,a,unit,available,target,min,max,step,adjustable};}
  controls(){const ids=this.data.profile.controls||[],st=this._hass.states,name=id=>st[id]?.attributes?.friendly_name||id;
    const lights=ids.filter(id=>id.startsWith('light.')),climates=ids.filter(id=>id.startsWith('climate.')),other=ids.filter(id=>!lights.includes(id)&&!climates.includes(id));
    const prefix=commonPrefix(lights.map(name));const info=(id,label)=>this.button(`${label} details`,`info:${id}`,icon('dots-vertical'),'tile-info');
    const light=id=>{const s=st[id],known=!!s&&['on','off'].includes(s.state),on=s?.state==='on',label=shortName(name(id),prefix);
      return `<li class="tile light${on?' is-on':''}${known?'':' is-unavailable'}">${known?this.button(`${label}, ${on?'on':'off'}`,`light:${id}`,`${icon(on?'lightbulb':'lightbulb-outline')}<b>${esc(label)}</b><span>${on?'On':'Off'}</span>`,'tile-main',`aria-pressed="${on}"`):this.button(`${label}, unavailable. Show details`,`info:${id}`,`${icon('lightbulb-off-outline')}<b>${esc(label)}</b><span>Unavailable</span>`,'tile-main')}${info(id,label)}</li>`;};
    const heat=id=>{const c=this.climateInfo(id),a=c.a,label=name(id),heating=a.hvac_action==='heating';
      const state=!c.available?'Unavailable':c.s.state==='off'?'Off':heating?'Heating':a.hvac_action==='idle'?'Not heating':a.hvac_action==='off'?'Off':`${condition(c.s.state).replace(/^./,x=>x.toUpperCase())} mode`;
      const cur=Number(a.current_temperature),fmt=v=>Number.isInteger(c.step)?String(Math.round(v)):v.toFixed(1);
      return `<li class="tile heat${heating?' is-heating':''}${c.available?'':' is-unavailable'}"><div class="heat-top"><h3>${esc(label)}</h3>${info(id,label)}</div><p class="heat-state">${icon(heating?'fire':'thermostat')}<span>${esc(state)}</span></p><p class="heat-now"><span class="visually-hidden">Now </span>${a.current_temperature!=null&&Number.isFinite(cur)?`${cur.toFixed(1)}<span>${esc(c.unit)}</span>`:'—'}</p>${c.adjustable?`<div class="heat-set">${this.button(`Lower ${label} target`,`heat:${id}:-1`,icon('minus'),'round small',c.target-c.step<c.min-1e-9?'disabled':'')}<p class="heat-target"><span>Set to</span><b>${fmt(c.target)}${esc(c.unit)}</b></p>${this.button(`Raise ${label} target`,`heat:${id}:1`,icon('plus'),'round small',c.target+c.step>c.max+1e-9?'disabled':'')}</div>`:a.target_temp_low!=null&&a.target_temp_high!=null?`<p class="heat-target"><span>Range</span><b>${esc(a.target_temp_low)}–${esc(a.target_temp_high)}${esc(c.unit)}</b></p>`:''}</li>`;};
    const generic=id=>{const s=st[id];return `<li class="tile">${this.button(`${name(id)}, ${s?.state||'unavailable'}. Show details`,`info:${id}`,`${icon(s?.attributes?.icon?.replace('mdi:','')||'information-outline')}<b>${esc(name(id))}</b><span>${esc(s?.state||'Unavailable')}</span>`,'tile-main')}</li>`;};
    return `${this.head('Controls')}<div class="view-body controls">${!ids.length?'<p class="muted">Room controls can be assigned in this Echo’s profile.</p>':''}${lights.length?`<section class="ctl-group" aria-labelledby="ctl-lights"><h2 id="ctl-lights">${prefix?esc(prefix)+' lights':'Lights'}</h2><ul class="light-grid">${lights.map(light).join('')}</ul></section>`:''}${climates.length?`<section class="ctl-group" aria-labelledby="ctl-heat"><h2 id="ctl-heat">Heating</h2><ul class="heat-grid">${climates.map(heat).join('')}</ul></section>`:''}${other.length?`<section class="ctl-group" aria-labelledby="ctl-other"><h2 id="ctl-other">Other</h2><ul class="light-grid">${other.map(generic).join('')}</ul></section>`:''}${this.hint('Turn on the kitchen lights.')}</div>`;}
  toggleLight(id){const s=this._hass.states[id];if(!s||!['on','off'].includes(s.state))return;return this.service('light',s.state==='on'?'turn_off':'turn_on',{entity_id:id});}
  stepClimate(id,direction){if(!id.startsWith('climate.'))return;const c=this.climateInfo(id);if(!c.adjustable)return;
    const next=Math.round((c.target+Math.sign(direction)*c.step)/c.step)*c.step,value=Number(Math.min(c.max,Math.max(c.min,next)).toFixed(2));
    if(value===c.target)return;return this.service('climate','set_temperature',{entity_id:id,temperature:value});}
  nav(view){return `<nav class="primary-nav" aria-label="Echo views">${routes.map(([v,n,i,short])=>`<button class="nav-item" data-do="view:${v}" aria-label="${n}" ${view===v?'aria-current="page"':''}>${icon(i)}<span${short?' class="long"':''}>${n}</span>${short?`<span class="short" aria-hidden="true">${short}</span>`:''}</button>`).join('')}<button class="nav-item" data-do="menu" aria-expanded="${!!this.menuOpen}" ${moreRoutes.some(([v])=>v===view)?'aria-current="page"':''}>${icon('dots-horizontal')}<span>More</span></button></nav>`;}
  render(){
    if(!this.shadowRoot||!this.config)return;
    this.fit();
    // Never destroy an in-progress form edit on background state updates.
    if(this.shadowRoot.activeElement?.matches('input:not([type=range]),select')&&!this.busy)return;
    // Restore keyboard focus only; a touch tap leaves nothing focused so idle views still return home.
    const fe=this.shadowRoot.activeElement,focused=fe?.matches?.(':focus-visible')?fe.dataset?.do:null;
    const data=this.data;
    const ambient=!!this.config.ambient,view=ambient?'home':this.view;
    const menu=this.menuOpen&&!ambient?`<div class="touch-menu" role="dialog" aria-label="More"><div class="panel-title">More ${this.button('Close','menu',icon('close'),'quiet')}</div>${moreRoutes.map(([v,n,i])=>this.button(n,`view:${v}`,`${icon(i)}<span>${n}</span>`,view===v?'selected':'')).join('')}${view==='music'?this.button('Speaker and search','playback',`${icon('speaker')}<span>Speaker and search</span>`):''}</div>`:'';
    this.shadowRoot.innerHTML=`<style>${styles}</style><ha-card><div class="shell view-${esc(view)} style-${this.musicStyle}${ambient?' ambient':''}">${data&&view==='music'?this.musicBackdrop():''}${this.error?`<div class="error" role="alert">${esc(this.error)} ${this.button('Dismiss error','dismiss-error',icon('close'))}</div>`:''}${data&&!ambient?this.timerStrip():''}<main>${!data?'<div class="empty"><p>Connecting to your Echo…</p></div>':({home:()=>this.home(),timers:()=>this.timers(),music:()=>this.music(),weather:()=>this.weather(),guide:()=>this.guide(),answer:()=>this.answer(),controls:()=>this.controls()}[view]||(()=>this.home()))()}</main>${!ambient?this.nav(view):''}${menu}${this.busy?'<div class="working" role="status">Working…</div>':''}</div></ha-card>`;
    this.shadowRoot.querySelectorAll('[data-do]').forEach(b=>b.onclick=()=>this.click(b.dataset.do));
    // Artwork that fails to load is remembered (bounded) and replaced by the fallback on the next render.
    this.shadowRoot.querySelectorAll('img[data-art]').forEach(img=>img.onerror=()=>{if(this.failedArt.has(img.dataset.art))return;this.failedArt.add(img.dataset.art);if(this.failedArt.size>20)this.failedArt.delete(this.failedArt.values().next().value);this.render();});
    const form=(id,fn)=>{const f=this.shadowRoot.getElementById(id);if(f)f.onsubmit=e=>{e.preventDefault();const values=Object.fromEntries(new FormData(f));f.querySelectorAll('input,select').forEach(el=>el.blur());fn(values);};};
    form('timer-form',v=>this.action('timer',{operation:'start',name:v.name||'Timer',seconds:Math.round(Number(v.minutes)*60)}));
    form('music-form',v=>this.action('music',{action:'play',...v}));
    const speaker=this.shadowRoot.getElementById('speaker');if(speaker)speaker.onchange=()=>{const val=speaker.value;speaker.blur();this.action('music',{action:'select',speaker:val});};
    const volume=this.shadowRoot.getElementById('volume');if(volume){volume.oninput=()=>{volume.style.setProperty('--fill',`${volume.value}%`);const out=volume.parentElement.querySelector('output');if(out)out.textContent=`${volume.value}%`;};volume.onchange=()=>this.action('music',{action:'volume',volume:Number(volume.value)});}
    // Keep keyboard focus on the same control after a re-render.
    if(focused){const again=this.shadowRoot.querySelector(`[data-do="${CSS.escape(focused)}"]`);if(again&&!again.disabled)again.focus();}
  }
  click(value){if(this.config.ambient)return;const [type,action,id]=value.split(':');if(type==='menu'){this.menuOpen=!this.menuOpen;this.render();return;}if(type==='playback'){this.menuOpen=false;this.musicControls=!this.musicControls;this.render();return;}if(type==='view')return this.go(action);
    if(type==='music'){this.touched=Date.now();if(action==='shuffle')return this.action('music',{action:'shuffle',shuffle:!this._hass.states[this.activePlayer]?.attributes?.shuffle});return this.action('music',{action});}
    if(type==='timer')return this.action('timer',{operation:action,timer_id:id});
    if(type==='light')return this.toggleLight(action);
    if(type==='heat')return this.stepClimate(action,Number(id));
    if(type==='info'){if(!(this.data?.profile?.controls||[]).includes(action))return;this.dispatchEvent(new CustomEvent('hass-more-info',{detail:{entityId:action},bubbles:true,composed:true}));return;}
    if(type==='hold'){const on=this._hass.states[this.data.profile.kiosk_hold]?.state==='on';this.ownsHold=!on;this._hass.callService('switch',on?'turn_off':'turn_on',{entity_id:this.data.profile.kiosk_hold}).then(()=>this.render()).catch(err=>{this.error=err.message;this.render();});return;}if(type==='dismiss-error'){this.error='';this.render();}}
}
const styles=`
:host{display:block;--deep:#142C38;--raised:#264654;--tile:#26465480;--ink:#F2F5F7;--muted:#B7CBD7;--amber:#EFBF73;--amber-ink:#2A2112;--cool:#A2D5D0;--rain:#7CC3EE;--line:#B7CBD72e;--focus:#FFE3A8;--accent:var(--cool);font-family:"Avenir Next",Avenir,"Ubuntu Sans","Trebuchet MS","Gill Sans",sans-serif;color:var(--ink);font-size:17px;-webkit-font-smoothing:antialiased}
*{box-sizing:border-box}h1,h2,h3,p{margin:0}ul,ol{margin:0;padding:0;list-style:none}
ha-card{display:block;background:var(--deep);border:0;border-radius:0;color:var(--ink);overflow:hidden;min-height:var(--echo-height,100dvh)}
.shell{position:relative;isolation:isolate;height:var(--echo-height,100dvh);display:flex;flex-direction:column;padding:0 clamp(16px,3vw,40px);background:radial-gradient(120% 90% at 85% 0%,#2B4E5E 0%,transparent 60%),linear-gradient(165deg,#1A3644 0%,var(--deep) 55%,#10232D 100%)}
main{flex:1;min-height:0;display:flex;flex-direction:column;position:relative}
.view-body{flex:1;min-height:0;padding-bottom:14px}
.hour,.day,.tile,.answer-card{position:relative}
.visually-hidden{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);clip-path:inset(50%);white-space:nowrap}
button,input,select{font:inherit;color:inherit}
button{border:0;background:#ffffff14;border-radius:14px;cursor:pointer;min-height:44px;padding:10px 16px}
button:hover{background:#ffffff22}button:disabled{cursor:default;opacity:.35}
button:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid var(--focus);outline-offset:3px}
button ha-icon{--mdc-icon-size:24px}
.quiet{background:transparent;color:var(--muted)}
.primary{background:var(--ink);color:var(--deep);font-weight:600;display:flex;align-items:center;justify-content:center;gap:6px}.primary:hover{background:#fff}
.muted{color:var(--muted)}
/* heading */
.view-head{display:flex;align-items:flex-end;justify-content:space-between;gap:20px;padding:22px 0 16px}
.titles{min-width:0}.view-head h1{font-size:clamp(28px,3.4vw,40px);font-weight:600;letter-spacing:-.015em;line-height:1.1}
.sub{color:var(--muted);font-size:17px;margin-top:4px;overflow-wrap:anywhere}
.head-actions{display:flex;align-items:center;gap:10px;flex:none}
.head-clock{font-size:30px;font-weight:300;letter-spacing:-.02em;margin-left:10px;font-variant-numeric:tabular-nums}
.pill-btn{display:inline-flex;align-items:center;gap:8px;min-height:48px;padding:0 18px;border-radius:999px;background:#ffffff14;border:1px solid var(--line);font-weight:500}
.pill-btn[aria-pressed=true]{background:var(--cool);color:var(--deep);border-color:transparent}
.hint{display:flex;align-items:center;gap:12px;color:var(--muted);font-size:18px;margin-top:16px}.hint ha-icon{--mdc-icon-size:24px;color:var(--cool);flex:none}
/* navigation */
.primary-nav{flex:none;align-self:center;display:flex;gap:4px;padding:6px;margin:0 0 12px;background:#0A181F9e;border:1px solid var(--line);border-radius:999px;backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);position:relative;z-index:3}
.nav-item{display:flex;align-items:center;gap:8px;min-height:54px;padding:0 20px;border-radius:999px;background:transparent;color:var(--muted);font-size:17px;font-weight:500}
.nav-item .short{display:none}.nav-item:hover{background:#ffffff10;color:var(--ink)}.nav-item[aria-current=page]{background:var(--ink);color:var(--deep);font-weight:600}
.touch-menu{position:absolute;z-index:5;bottom:86px;left:50%;transform:translateX(-50%);width:min(560px,calc(100% - 32px));border:1px solid var(--line);border-radius:20px;background:#1D3A48;box-shadow:0 15px 45px #0007;padding:18px;display:grid;grid-template-columns:repeat(2,1fr);gap:10px}
.touch-menu button{display:flex;align-items:center;gap:10px;background:#ffffff0d;font-size:18px;padding:14px;min-height:60px}.touch-menu button.selected{background:#ffffff24}
.panel-title{grid-column:1/-1;display:flex;align-items:center;justify-content:space-between;font-size:21px;font-weight:600;margin-bottom:4px}.panel-title button{min-height:44px;padding:8px}
.error{position:relative;z-index:4;background:#733b31cc;color:#ffd9cc;padding:10px 14px;border-radius:12px;display:flex;justify-content:space-between;align-items:center;gap:10px;font-size:15px;margin-top:12px}.error.inline{grid-column:1/-1;margin:0}
.working{position:absolute;bottom:90px;right:20px;background:var(--ink);color:var(--deep);padding:9px 18px;border-radius:20px;font-size:14px;z-index:6}
.timer-strip{position:relative;z-index:2;display:flex;gap:9px;flex-wrap:wrap;margin-top:14px}.timer-chip{display:flex;gap:9px;align-items:center;font-size:19px;min-height:46px;padding:5px 14px;color:var(--ink);background:#17233299;border:1px solid var(--line);border-radius:999px}.timer-chip b{font-variant-numeric:tabular-nums}.timer-chip small{color:var(--muted)}
.empty{padding:28px 20px;text-align:center;min-height:200px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px}.empty-icon{color:var(--cool)}.empty-icon ha-icon{--mdc-icon-size:50px}.empty h2{font-size:25px;font-weight:500}.empty p{color:var(--muted)}
.inline-form{display:flex;align-items:center;gap:10px;margin-top:18px}.inline-form input{min-width:0;flex:1}.inline-form input[type=number]{max-width:155px}
input,select{border:1px solid #ffffff2a;background:#1B3542;border-radius:12px;padding:12px 14px;min-height:48px;font-size:16px}input::placeholder{color:#9FB2BD}select{max-width:260px}
/* home */
.view-home main{margin:0 calc(-1*clamp(16px,3vw,40px))}
.quiet-home{position:absolute;inset:0}
.view-home .shell,.shell.view-home{background:radial-gradient(90% 70% at 100% 0%,#3A4D72 0%,transparent 65%),radial-gradient(80% 80% at 0% 100%,#3D2C4F 0%,transparent 60%),linear-gradient(160deg,#22394F 0%,#1B2E40 50%,#251F36 100%)}
/* Lower-left clock inset by the shell padding (the same edge as every other view and the mockup), resting just above
   the navigation. Its size is bounded by both width and the card's real height so short landscape screens keep room. */
.home-clock-block{--home-inset:clamp(16px,3vw,40px);--home-clock-size:clamp(90px,min(21vw,calc(var(--echo-height,100dvh)*.32)),250px);position:absolute;left:var(--home-inset);bottom:12px;color:#fff}
.home-meta{display:flex;align-items:center;gap:14px;font-size:clamp(24px,3.8vw,44px);white-space:nowrap}
.home-temperature{display:flex;align-items:center;gap:8px}.home-temperature ha-icon{--mdc-icon-size:1.05em}.home-divider{color:#ffffff8c;font-weight:300}
.home-time{font-size:var(--home-clock-size);font-weight:200;letter-spacing:-.055em;line-height:.95;margin:-4px 0 0 -.04em;font-variant-numeric:tabular-nums}
.weather-shortcut{position:absolute;top:20px;right:clamp(16px,3vw,40px);display:flex;align-items:center;gap:8px;min-height:56px;padding:0 20px;border-radius:999px;background:#ffffff14;border:1px solid var(--line);font-size:22px;color:#fff}.weather-shortcut ha-icon{--mdc-icon-size:28px}
/* Home timer chips are read from across the room: larger name and countdown, sized by width and the card's height.
   The strip stops short of the weather button and is capped above the clock; extra rows scroll inside it. Home only:
   the strip on other views keeps the compact chips. */
.view-home .timer-strip{--chip-name:clamp(19px,min(2.3vw,calc(var(--echo-height,100dvh)*.038)),26px);--chip-count:clamp(24px,min(3.4vw,calc(var(--echo-height,100dvh)*.056)),38px);position:absolute;left:clamp(16px,3vw,40px);right:calc(clamp(16px,3vw,40px) + 150px);top:20px;max-height:calc(var(--echo-height,100dvh)*.38);overflow-y:auto;overscroll-behavior:contain;scrollbar-width:thin;gap:10px;padding:6px;margin:-6px}
.view-home .timer-chip{gap:10px;max-width:100%;min-height:calc(var(--chip-count)*1.75);padding:4px 20px 4px 16px;font-size:var(--chip-name);background:#172332b3}
.view-home .timer-chip ha-icon{--mdc-icon-size:calc(var(--chip-name)*1.2);flex:none;color:var(--cool)}
.view-home .timer-chip span{min-width:0;max-width:10em;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.view-home .timer-chip b{flex:none;font-size:var(--chip-count);font-weight:500;letter-spacing:-.01em;line-height:1}
.view-home .timer-chip small{flex:none;font-size:.78em;padding:2px 9px;border:1px dashed #B7CBD780;border-radius:999px}
.view-home .timer-chip:has(small) b{color:var(--muted)}
.ambient{filter:brightness(.64)}.ambient .decorative{opacity:.7}.ambient .home-clock-block{bottom:6%}
/* music: backdrops */
.backdrop{position:absolute;inset:0;z-index:-1;overflow:hidden;background:#0D1A21}
.bd-wash{position:absolute;inset:-12%;width:124%;height:124%;object-fit:cover;filter:blur(56px) saturate(1.3) brightness(.8);transform:scale(1.08)}
.bd-bleed{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.bd-colour{position:absolute;inset:0;background:radial-gradient(70% 90% at 12% 30%,var(--c1) 0%,transparent 62%),radial-gradient(60% 80% at 92% 18%,var(--c3) 0%,transparent 58%),radial-gradient(80% 90% at 70% 110%,var(--c2) 0%,transparent 65%),#10202A}
.bd-shade{position:absolute;inset:0}
.style-wash .bd-shade{background:linear-gradient(90deg,#08101659 0%,#0810169e 45%,#081016b8 100%),linear-gradient(0deg,#0810168c 0%,transparent 35%)}
.style-colour .bd-shade{background:linear-gradient(90deg,#0A141B26 0%,#0A141B8c 55%,#0A141Bb3 100%)}
.style-bleed .bd-shade{background:linear-gradient(90deg,#060C10c7 0%,#060C10b3 40%,#060C10e0 62%,#060C10eb 100%),linear-gradient(0deg,#060C10b3 0%,transparent 40%)}
/* music: one fixed foreground for every style */
.music-body{display:flex;align-items:center}
.music{width:100%;display:grid;grid-template-columns:auto minmax(0,1fr);grid-template-areas:"cover info" "cover controls";align-items:center;column-gap:clamp(24px,4vw,56px);row-gap:20px}
.cover{grid-area:cover;width:min(calc(var(--echo-height,800px) - 290px),360px,38vw);min-width:150px;aspect-ratio:1;border-radius:20px;overflow:hidden;background:linear-gradient(145deg,#2E6E73,#1B3A4B 70%);box-shadow:0 30px 60px -20px #000b,0 0 0 1px #ffffff1a;display:flex;align-items:center;justify-content:center}
.cover img{width:100%;height:100%;object-fit:cover;display:block}.is-radio .cover img{object-fit:contain;background:#0D1A21}
.disc{border-radius:50%;width:76%;height:76%;background:repeating-radial-gradient(circle,#ffffff00 0 10px,#ffffff12 10px 11px);display:flex;align-items:center;justify-content:center}.disc>div{border-radius:50%;width:40%;height:40%;background:#ffffff1f;display:flex;align-items:center;justify-content:center;color:#F2F5F7d9}.disc ha-icon{--mdc-icon-size:44px}
.music-info{grid-area:info;align-self:end;min-width:0;display:flex;flex-direction:column;gap:6px;max-width:720px}
.station{display:flex;align-items:center;gap:10px;font-size:21px;font-weight:600;color:var(--amber);min-width:0}.station span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.station ha-icon{--mdc-icon-size:24px;flex:none}
.title{font-size:clamp(30px,4.2vw,54px);font-weight:600;letter-spacing:-.02em;line-height:1.08;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere;text-shadow:0 2px 18px #0006}
.artist{font-size:clamp(21px,2.3vw,28px);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.album{font-size:18px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.timeline{display:flex;align-items:center;gap:14px;min-height:36px;margin-top:10px;font-variant-numeric:tabular-nums}
.timeline .time{font-size:16px;color:var(--muted);min-width:3.2em}.timeline .time:last-child{text-align:right}
.progress{flex:1;max-width:520px;height:6px;border-radius:3px;background:#ffffff33;overflow:hidden}.progress i{display:block;height:100%;background:var(--ink);border-radius:3px}
.live{display:inline-flex;align-items:center;gap:8px;padding:6px 14px;border-radius:999px;background:var(--amber);color:var(--amber-ink);font-weight:700;font-size:16px}.live ha-icon{--mdc-icon-size:20px}
.music-controls{grid-area:controls;align-self:start;display:flex;flex-direction:column;gap:16px;min-width:0}
.transport{display:flex;align-items:center;gap:14px}
.round{display:inline-grid;place-items:center;width:64px;height:64px;padding:0;border-radius:50%;border:1px solid #ffffff38;background:#ffffff1a}.round ha-icon{--mdc-icon-size:28px}
.round.small{width:52px;height:52px}.round.small ha-icon{--mdc-icon-size:24px}.round[aria-pressed=true]{background:var(--ink);color:var(--deep)}
.round.play{width:80px;height:80px;background:var(--ink);color:#10202A;border-color:transparent}.round.play ha-icon{--mdc-icon-size:36px}.round.play:hover{background:#fff}
.output{display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.volume{display:flex;align-items:center;gap:12px;flex:1;min-width:200px;max-width:340px;color:var(--muted)}.volume ha-icon{flex:none}.volume output{min-width:3em;font-variant-numeric:tabular-nums}
.volume input{--fill:30%;flex:1;height:44px;margin:0;padding:0;border:0;min-height:0;background:transparent;appearance:none;-webkit-appearance:none}
.volume input::-webkit-slider-runnable-track{height:6px;border-radius:3px;background:linear-gradient(90deg,var(--ink) var(--fill),#ffffff38 var(--fill))}
.volume input::-moz-range-track{height:6px;border-radius:3px;background:#ffffff38}.volume input::-moz-range-progress{height:6px;border-radius:3px;background:var(--ink)}
.volume input::-webkit-slider-thumb{-webkit-appearance:none;width:24px;height:24px;margin-top:-9px;border-radius:50%;background:var(--ink);box-shadow:0 2px 6px #0007}.volume input::-moz-range-thumb{width:24px;height:24px;border:0;border-radius:50%;background:var(--ink)}
.volume input:disabled{opacity:.35}
.speaker-chip{display:inline-flex;align-items:center;gap:8px;min-height:48px;padding:0 10px 0 14px;border-radius:999px;background:#ffffff1a;font-size:16px;max-width:100%}.speaker-chip span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.speaker-chip ha-icon{--mdc-icon-size:20px;flex:none}.speaker-chip ha-icon:first-child{color:var(--cool)}
.playback-panel{position:absolute;z-index:5;left:50%;transform:translateX(-50%);bottom:86px;width:min(760px,calc(100% - 32px));background:#1D3A48;border:1px solid var(--line);border-radius:20px;padding:20px 22px;box-shadow:0 15px 45px #0007;display:flex;flex-direction:column;gap:12px}
.field{display:flex;align-items:center;gap:12px;color:var(--muted)}.field select{flex:1;color:var(--ink)}.playback-panel .inline-form{margin-top:0}
/* weather */
.weather{display:grid;grid-template-columns:minmax(240px,.8fr) minmax(0,2fr);grid-template-rows:minmax(0,1fr) auto;gap:16px 26px}
.wx-now{grid-row:span 2;display:flex;flex-direction:column;justify-content:center;gap:6px;padding:26px;border-radius:22px;background:linear-gradient(160deg,#2C5263 0%,#1F3D4B 100%);min-width:0}
.wx-now>ha-icon{--mdc-icon-size:80px;color:var(--amber)}
.wx-temp{font-size:clamp(84px,9vw,124px);font-weight:200;letter-spacing:-.05em;line-height:1}.wx-temp span{font-size:.36em;letter-spacing:0;vertical-align:.95em;margin-left:4px;color:var(--muted)}
.wx-cond{font-size:28px;font-weight:500;text-transform:capitalize}.wx-range{display:flex;gap:20px;font-size:21px;color:var(--muted);margin-top:4px}.wx-range b{color:var(--ink);font-weight:600}
.wx-hours,.wx-days{min-width:0;min-height:0;display:flex;flex-direction:column;gap:10px}
.weather h2{font-size:20px;font-weight:600}.wx-label{display:flex;align-items:baseline;justify-content:space-between;gap:12px;flex-wrap:wrap}
.wx-key{display:flex;align-items:center;gap:8px;color:var(--muted);font-size:15px}.wx-key i{width:12px;height:12px;border-radius:3px;background:var(--rain)}
.hour-list{flex:1;min-height:0;display:grid;grid-template-columns:repeat(8,minmax(0,1fr));gap:2px;border-radius:16px;overflow:hidden}
.hour{display:grid;grid-template-rows:auto auto auto minmax(30px,1fr) auto;justify-items:center;align-items:center;gap:6px;padding:12px 4px;background:var(--tile)}
.h-time{font-size:16px;color:var(--muted);font-variant-numeric:tabular-nums}.hour ha-icon{--mdc-icon-size:32px}.hour strong{font-size:25px;font-weight:500}
.rain-col{width:14px;height:100%;align-self:stretch;border-radius:4px;background:#7CC3EE24;display:flex;align-items:flex-end;overflow:hidden}.rain-col i{display:block;width:100%;background:var(--rain);border-radius:4px 4px 0 0}
.hour small{font-size:15px;color:var(--muted);font-variant-numeric:tabular-nums}
.day-list{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px}
.day{display:grid;grid-template-columns:auto 1fr;grid-template-areas:"name name" "icon temps" "cond cond" "rain rain";align-items:center;gap:4px 10px;padding:14px 16px;border-radius:16px;background:var(--tile);min-width:0}
.d-name{grid-area:name;font-size:18px}.day>ha-icon{grid-area:icon;--mdc-icon-size:36px}.d-temps{grid-area:temps;display:flex;align-items:baseline;gap:8px;justify-content:flex-end}.d-temps strong{font-size:27px;font-weight:500}.d-temps small{font-size:19px;color:var(--muted)}
.d-cond{grid-area:cond;font-size:15px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-transform:capitalize}.d-rain{grid-area:rain;display:flex;align-items:center;gap:5px;font-size:15px;color:var(--muted)}.d-rain ha-icon{--mdc-icon-size:16px;color:var(--rain)}
/* homeguide */
.guide{display:flex;flex-direction:column}
.appliance-grid{flex:1;min-height:0;display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));grid-auto-rows:minmax(150px,1fr);gap:16px}
.appliance{display:flex;flex-direction:column;justify-content:flex-end;gap:6px;padding:22px;border-radius:22px;border:1px solid var(--line);background:linear-gradient(170deg,#2C5060 0%,#1F3D4B 100%);min-width:0}
.appliance-icon{display:grid;place-items:center;margin-bottom:auto;width:72px;height:72px;border-radius:20px;background:#A2D5D024;color:var(--cool)}.appliance-icon ha-icon{--mdc-icon-size:42px}
.appliance h2{font-size:23px;font-weight:600;line-height:1.15}.appliance p{font-size:16px;color:var(--muted);min-height:1.4em}
.reading{display:grid;grid-template-columns:minmax(0,1.7fr) minmax(240px,1fr);gap:22px}
.answer-card{overflow:auto;padding:26px 30px;border-radius:22px;background:#26465499;display:flex;flex-direction:column;gap:14px}
.question{font-size:20px;color:var(--muted)}.answer{white-space:pre-wrap;font-size:clamp(22px,2.6vw,30px);line-height:1.4;max-width:42ch}
.sources{overflow:auto;padding:20px 22px;border-radius:22px;border:1px solid var(--line)}.sources h2{font-size:19px;font-weight:600;margin-bottom:8px}.sources li{padding:12px 0;border-top:1px solid var(--line)}.sources p{margin-top:4px;color:var(--muted);white-space:pre-wrap;line-height:1.5}
/* answers */
.answer-body{display:flex;flex-direction:column;gap:16px;max-width:min(100%,58rem)}
.answer-q{flex:0 0 auto;max-height:max(2.8em,calc(var(--echo-height,100dvh)*.2));overflow:auto;overscroll-behavior:contain;color:var(--muted);font-size:clamp(20px,2.3vw,26px);line-height:1.35;max-width:46ch;white-space:pre-wrap;overflow-wrap:anywhere}
.answer-scroll{flex:0 1 auto;min-height:min(6em,40%);overflow:auto;overscroll-behavior:contain}
.answer-text{white-space:pre-wrap;overflow-wrap:anywhere;font-weight:400}
.answer-body.is-short{justify-content:center;padding-bottom:calc(14px + 4%)}
.is-short .answer-text{font-size:clamp(30px,min(4.6vw,calc(var(--echo-height,100dvh)*.075)),56px);line-height:1.22;letter-spacing:-.01em;max-width:24ch}
.is-long .answer-scroll{flex:1;padding:22px 28px;border-radius:22px;background:#26465466;border:1px solid var(--line)}
.is-long .answer-text{font-size:clamp(21px,2.4vw,28px);line-height:1.45;max-width:48ch}
/* conversions */
.conversion-body{display:flex;flex-direction:column;justify-content:center;padding-bottom:calc(14px + 4%)}
.conversion{min-width:0;max-width:100%}
.conv-from{color:var(--muted);font-size:clamp(24px,min(3.2vw,calc(var(--echo-height,100dvh)*.055)),40px);line-height:1.2;overflow-wrap:anywhere}.conv-eq{margin-left:.15em;opacity:.8}
.conv-to{display:flex;flex-wrap:wrap;align-items:baseline;column-gap:.18em;margin-top:8px;color:var(--cool);font-weight:200;letter-spacing:-.035em;line-height:1;font-variant-numeric:tabular-nums}
.conv-to strong{font-weight:inherit;min-width:0;overflow-wrap:anywhere}
.conv-unit{font-size:.38em;font-weight:400;letter-spacing:0;color:var(--ink);overflow-wrap:anywhere}
.fit-l .conv-to{font-size:clamp(72px,min(15vw,calc(var(--echo-height,100dvh)*.3)),190px)}
.fit-m .conv-to{font-size:clamp(56px,min(10vw,calc(var(--echo-height,100dvh)*.22)),136px)}
.fit-s .conv-to{font-size:clamp(40px,min(6.6vw,calc(var(--echo-height,100dvh)*.15)),92px)}
/* timers */
.timers-body{display:flex;flex-direction:column;gap:14px}
.timer-grid{flex:1;min-height:0;overflow:auto;display:grid;gap:14px;grid-auto-rows:minmax(min-content,1fr);--count:clamp(52px,min(6.4vw,calc(var(--echo-height,100dvh)*.1)),88px)}
.layout-empty{display:flex;align-items:center;justify-content:center}
.layout-one{grid-template-columns:minmax(0,1fr);--count:clamp(88px,min(17vw,calc(var(--echo-height,100dvh)*.26)),210px)}
.layout-two{grid-template-columns:repeat(2,minmax(0,1fr));--count:clamp(64px,min(9.5vw,calc(var(--echo-height,100dvh)*.17)),132px)}
.layout-few{grid-template-columns:repeat(2,minmax(0,1fr))}.layout-few>:first-child:nth-last-child(odd){grid-column:1/-1}
.layout-many{grid-template-columns:repeat(auto-fill,minmax(300px,1fr));grid-auto-rows:minmax(min-content,auto);--count:clamp(52px,5.4vw,72px)}
.timer-card{min-width:0;display:flex;flex-direction:column;justify-content:space-between;gap:10px;border:1px solid var(--line);background:var(--tile);border-radius:22px;padding:20px 22px}
.timer-top{display:flex;align-items:center;justify-content:space-between;gap:12px;min-width:0}
.timer-name{font-size:21px;font-weight:600;line-height:1.2;min-width:0;overflow-wrap:anywhere}
.timer-state{flex:none;display:inline-flex;align-items:center;gap:6px;padding:5px 12px 5px 9px;border-radius:999px;font-size:15px;font-weight:600;background:#A2D5D024;color:var(--cool)}.timer-state ha-icon{--mdc-icon-size:18px}
.countdown{font-size:var(--count);font-weight:300;letter-spacing:-.04em;line-height:1;font-variant-numeric:tabular-nums;white-space:nowrap}
.countdown.is-long{font-size:max(44px,calc(var(--count)*.7))}
.timer-actions{display:flex;flex-wrap:wrap;align-items:center;gap:8px}.timer-actions button{display:inline-flex;align-items:center;gap:6px;min-height:52px;padding:0 16px;border-radius:999px;font-weight:500}.timer-actions .timer-cancel{margin-left:auto}
.timer-note{display:flex;align-items:center;gap:10px;color:var(--ink);font-size:18px}.timer-note ha-icon{color:var(--amber);flex:none}
.is-paused{border-style:dashed}.is-paused .timer-state{background:#ffffff14;color:var(--muted)}.is-paused .countdown{color:var(--muted)}
.is-finished{border-color:#EFBF73a6;background:linear-gradient(170deg,#5A3A22e6 0%,#3B2A22e6 100%)}.is-finished .timer-state{background:var(--amber);color:var(--amber-ink)}.is-finished .countdown{color:var(--amber)}
@keyframes ring{0%,100%{box-shadow:0 0 0 0 #EFBF7300}50%{box-shadow:0 0 0 6px #EFBF7340}}.is-finished{animation:ring 2s ease-in-out infinite}
.layout-one .timer-card{padding:26px 30px;gap:14px}.layout-one .timer-name{font-size:clamp(24px,2.8vw,34px)}.layout-one .timer-state{font-size:17px;padding:7px 14px 7px 11px}.layout-one .timer-actions button{min-height:60px;padding:0 22px;font-size:18px}
.timer-form{flex:none;margin-top:0}
.timer-empty{min-height:0}
/* controls */
.controls{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.15fr);grid-template-rows:minmax(0,1fr) auto;gap:16px 26px;overflow:auto}
.controls .hint{grid-column:1/-1;margin-top:0}
.ctl-group{min-height:0;display:flex;flex-direction:column;gap:12px}.ctl-group h2{font-size:20px;font-weight:600}
.light-grid{flex:1;display:grid;grid-template-columns:1fr 1fr;grid-auto-rows:minmax(92px,1fr);gap:14px}
.heat-grid{flex:1;display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px}
.tile{position:relative;display:flex;border-radius:22px;border:1px solid var(--line);background:var(--tile);min-width:0}
.tile-main{flex:1;display:grid;grid-template-columns:auto 1fr;grid-template-rows:auto auto;align-content:center;column-gap:14px;padding:16px 52px 16px 20px;text-align:left;background:transparent;border-radius:22px;min-width:0}
.tile-main ha-icon{grid-row:span 2;--mdc-icon-size:38px;color:var(--muted)}.tile-main b{font-size:21px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.tile-main span{font-size:17px;color:var(--muted)}
.tile-info{position:absolute;top:6px;right:6px;width:44px;height:44px;padding:0;display:grid;place-items:center;background:transparent;color:inherit;opacity:.8}
.light.is-on{background:var(--amber);color:var(--amber-ink);border-color:transparent}.light.is-on .tile-main ha-icon,.light.is-on .tile-main span{color:var(--amber-ink)}
.is-unavailable{opacity:.6;border-style:dashed}
.heat{flex-direction:column;justify-content:space-between;gap:6px;padding:18px 20px}
.heat.is-heating{background:linear-gradient(170deg,#5A3A22 0%,#3B2A22 100%);border-color:#EFBF7373}
.heat-top{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}.heat-top h3{font-size:21px;font-weight:600;overflow-wrap:anywhere}.heat .tile-info{position:static;margin:-10px -10px 0 0}
.heat-state{display:flex;align-items:center;gap:6px;font-size:17px;color:var(--muted)}.heat-state ha-icon{--mdc-icon-size:20px}.is-heating .heat-state{color:var(--amber)}
.heat-now{font-size:clamp(56px,6vw,76px);font-weight:200;letter-spacing:-.04em;line-height:1;font-variant-numeric:tabular-nums}.heat-now span{font-size:.4em;vertical-align:.9em;margin-left:2px;color:var(--muted);letter-spacing:0}
.heat-set{display:flex;align-items:center;justify-content:space-between;gap:8px}
.heat-target{display:flex;flex-direction:column;align-items:center;line-height:1.15}.heat-target span{font-size:15px;color:var(--muted)}.heat-target b{font-size:23px;font-weight:600;font-variant-numeric:tabular-nums}
/* short landscape screens */
@media(max-height:650px) and (min-width:761px){.view-head{padding:14px 0 10px}.nav-item{min-height:48px}.round{width:56px;height:56px}.round.play{width:68px;height:68px}.round.small{width:48px;height:48px}.music{row-gap:12px}.wx-temp{font-size:84px}.timer-card{padding:14px 18px;gap:8px}.layout-one .timer-card{padding:20px 26px}.timer-actions button{min-height:48px}.layout-one .timer-actions button{min-height:54px}.timers-body,.timer-grid{gap:10px}}
/* narrow phones */
@media(max-width:760px){
ha-card{overflow:clip}/* clip, unlike hidden, is not a scroll container, so the sticky nav follows the page scroll */
.shell{height:auto;min-height:var(--echo-height,100dvh);padding:0 14px}
.view-head{flex-wrap:wrap;align-items:center;padding-top:16px}.head-clock{display:none}.head-actions{flex-wrap:wrap}
.primary-nav{position:sticky;bottom:0;align-self:stretch;border-radius:22px;margin:0 0 10px;gap:2px}
.nav-item{flex:1;min-width:0;flex-direction:column;gap:2px;padding:6px 2px;min-height:60px;font-size:12px;border-radius:16px}
.nav-item span{max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.nav-item .long{display:none}.nav-item .short{display:inline}
main,.view-body,.weather>*{min-width:0;max-width:100%}
.touch-menu,.playback-panel{position:fixed;bottom:84px}
.view-home main{min-height:70vh}.home-clock-block{--home-clock-size:23vw}.home-meta{font-size:24px;gap:9px}
.music{grid-template-columns:1fr;grid-template-areas:"cover" "info" "controls";row-gap:18px}.cover{width:min(64vw,280px);justify-self:center}
.music-info,.music-controls{align-self:auto}.transport{justify-content:center}.output{justify-content:center}
.weather{grid-template-columns:minmax(0,1fr);grid-template-rows:auto}.wx-now{grid-row:auto}
.hour-list{grid-template-columns:repeat(8,72px);overflow-x:auto;min-height:210px;contain:inline-size;max-width:100%}
.day-list{grid-template-columns:minmax(0,1fr);contain:inline-size}.day{grid-template-columns:3.4em 30px minmax(0,1fr) auto auto;grid-template-areas:"name icon cond temps rain";gap:4px 8px;padding:12px}.day>ha-icon{--mdc-icon-size:28px}.d-temps strong{font-size:23px}.d-temps small{font-size:17px}
.appliance-grid{grid-template-columns:repeat(2,minmax(0,1fr));grid-auto-rows:minmax(150px,auto)}.appliance{padding:16px}.appliance h2{font-size:19px}
.reading{grid-template-columns:minmax(0,1fr)}
.controls{grid-template-columns:minmax(0,1fr);overflow:visible}.light-grid{grid-template-columns:minmax(0,1fr)}
.inline-form{flex-wrap:wrap}.inline-form input{flex-basis:130px}.inline-form select{max-width:130px}
.timer-chip{font-size:16px}
.view-home .timer-strip{--chip-name:17px;--chip-count:24px;left:14px;right:14px;top:88px;max-height:calc(var(--echo-height,100dvh)*.3)}.view-home .timer-chip{min-height:48px;padding:4px 14px 4px 12px}.view-home .timer-chip span{max-width:8em}
.timer-grid{overflow:visible;grid-template-columns:minmax(0,1fr);grid-auto-rows:auto;--count:clamp(52px,16vw,72px)}.layout-one{--count:clamp(64px,22vw,110px)}.layout-empty{display:flex}.timer-actions .timer-cancel{margin-left:0}
.timer-top{flex-wrap:wrap;align-items:flex-start;gap:6px 10px}.timer-name{flex:1 1 100%}
.conversion-body,.answer-body.is-short{justify-content:flex-start;padding-top:12px}}
@media(prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
`;
if(!customElements.get('echo-experience-card'))customElements.define('echo-experience-card',EchoExperienceCard);
window.customCards=window.customCards||[];window.customCards.push({type:'echo-experience-card',name:'Echo Experience',description:'A device-scoped home, timers, music, weather and HomeGuide dashboard.'});
