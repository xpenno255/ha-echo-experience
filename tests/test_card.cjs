const fs=require('node:fs');const vm=require('node:vm');const assert=require('node:assert/strict');
const sandbox={HTMLElement:class{attachShadow(){this.shadowRoot={querySelectorAll:()=>[],activeElement:null};}},customElements:{get:()=>false,define(){}},window:{},console,Date,Math,String,Number,Set,Map,CSS:{escape:x=>x},setInterval,clearInterval,setTimeout,clearTimeout,Promise};
vm.createContext(sandbox);vm.runInContext(fs.readFileSync(process.argv[2],'utf8')+'\nthis.Card=EchoExperienceCard;this.escapeText=esc;',sandbox);
let a=new sandbox.Card();a.config={device:'kitchen'};a.data={timers:[]};a.render=()=>{};a.refresh=()=>{};
a.receive({device:'bedroom',result:{view:'guide',payload:{speech:'Private bedroom reply'}}});assert.equal(a.view,'home');assert.equal(a.result,undefined);
a.receive({device:'kitchen',result:{view:'answer',payload:{equation:'1 kg = 1000 g'}}});assert.equal(a.view,'answer');
assert.equal(a.remaining({is_active:false,seconds_left:417,sampled_at:0}),417);
assert.equal(sandbox.escapeText('<img src=x onerror=alert(1)>'),'&lt;img src=x onerror=alert(1)&gt;');
a.receive({device:'kitchen',timers:[{id:'one'}]});assert.equal(a.data.timers.length,1);
let playback=new sandbox.Card();playback.config={device:'kitchen'};playback.data={profile:{music_player:'media_player.kitchen'},timers:[]};playback._hass={states:{'media_player.kitchen':{state:'idle'},'media_player.bedroom':{state:'playing'}}};
playback.syncPlayback();assert.equal(playback.view,'home','Other rooms must not open music');
playback._hass.states['media_player.kitchen'].state='playing';playback.syncPlayback();assert.equal(playback.view,'music');
playback._hass.states['media_player.kitchen'].state='paused';playback.syncPlayback();assert.equal(playback.view,'music','Pause retains artwork');
playback._hass.states['media_player.kitchen'].state='idle';playback.syncPlayback();assert.equal(playback.view,'home');
playback.view='guide';playback._hass.states['media_player.kitchen'].state='playing';playback.syncPlayback();assert.equal(playback.view,'guide','Playback must not cover a guide');
// Music started from the Sonos app drives the native players while the Music Assistant entity stays idle.
const native=new sandbox.Card();native.config={device:'kitchen'};native.data={profile:{music_player:'media_player.kitchen_ma',native_players:['media_player.kitchen_sonos','media_player.dining_sonos']},timers:[]};
const group={group_members:['media_player.kitchen_sonos','media_player.dining_sonos']};
native._hass={states:{'media_player.kitchen_ma':{state:'idle'},'media_player.kitchen_sonos':{state:'idle',attributes:group},'media_player.dining_sonos':{state:'idle',attributes:group},'media_player.living_sonos':{state:'playing'}}};
native.syncPlayback();assert.equal(native.view,'home','another room playing natively stays out');
native._hass.states['media_player.dining_sonos'].state='playing';assert.equal(native.activePlayer,'media_player.dining_sonos','an idle coordinator is not trusted');native._hass.states['media_player.kitchen_sonos'].state='playing';native.syncPlayback();assert.equal(native.view,'music','native playback opens music');
assert.equal(native.activePlayer,'media_player.kitchen_sonos','controls go to the group coordinator');
native._hass.states['media_player.kitchen_ma'].state='playing';assert.equal(native.activePlayer,'media_player.kitchen_ma','Music Assistant wins when both play');
native._hass.states['media_player.kitchen_ma'].state='idle';native._hass.states['media_player.dining_sonos'].state='idle';native._hass.states['media_player.kitchen_sonos'].state='idle';native.syncPlayback();assert.equal(native.view,'home','stopping returns an auto-opened view');
native.view='timers';native._hass.states['media_player.kitchen_sonos'].state='playing';native.syncPlayback();assert.equal(native.view,'timers','timers keep precedence');
// ---- 0.8.0 redesign: fixed music foreground, three backgrounds, radio detection, transport, controls ----
let added=0;const ok=(v,m)=>{assert.ok(v,m);added++;},eq=(a,b,m)=>{assert.equal(a,b,m);added++;};
const P='media_player.kitchen';
const song={state:'playing',attributes:{media_title:'Song <b>x</b>',media_artist:'Artist',media_album_name:'Album',media_content_type:'music',media_duration:200,media_position:50,media_position_updated_at:new Date(Date.now()-10000).toISOString(),entity_picture:'/api/media_player_proxy/media_player.kitchen?token=abc',volume_level:.4,shuffle:false,supported_features:1|4|16|32|16384|32768}};
const musicCard=(attrs,style)=>{const c=new sandbox.Card();c.config={device:'kitchen'};c.data={profile:{music_player:P,speakers:[{entity_id:P,name:'Kitchen Sonos'}],music_style:style,controls:[]},timers:[]};c._hass={states:{[P]:{...song,attributes:{...song.attributes,...attrs}}}};c.render=()=>{};return c;};
eq(musicCard({},undefined).musicStyle,'wash','missing style defaults to wash');eq(musicCard({},'neon').musicStyle,'wash','unknown style falls back to wash');
const layers={wash:'bd-wash',colour:'bd-colour',bleed:'bd-bleed'};const fg=new Set();
for(const style of ['wash','colour','bleed']){const c=musicCard({},style);ok(c.musicBackdrop().includes(layers[style]),style+' background layer');fg.add(c.music().replace(/width:[\d.]+%|data-clock>[^<]*|data-elapsed>[^<]*|aria-valuenow="\d+"/g,''));}
eq(fg.size,1,'foreground markup is identical for every style');
const songHtml=musicCard({},'wash').music();
ok(/class="cover"><img data-art="\/api\/media_player_proxy/.test(songHtml),'cover stays on the left in every style');ok(songHtml.includes('Song &lt;b&gt;x&lt;/b&gt;'),'metadata is escaped');
ok(songHtml.includes('data-progress')&&!songHtml.includes('Live radio'),'songs show progress');
ok(/aria-valuenow="(5[89]|60)"/.test(songHtml),'progress advances from HA timestamps');
const c0=musicCard({},'wash');eq(c0.position({dur:'200',pos:'190',at:String(Date.now()-60000),playing:'1'}),200,'position never passes the end');eq(c0.position({dur:'200',pos:'50',at:String(Date.now()-60000),playing:'0'}),50,'paused position holds');
// Sonos radio: media_channel present even though content type says music (study_sonos); dining_sonos has no channel.
const radio=musicCard({media_channel:'Absolute Radio',media_title:'Absolute Radio',media_artist:undefined,media_album_name:undefined,media_duration:undefined,media_content_id:'aac://http://stream',supported_features:4|4096|16384},'bleed').music();
ok(radio.includes('Live radio')&&!radio.includes('data-progress'),'channel identifies radio');ok(radio.includes('alt="Station artwork"'),'station artwork from entity_picture');
ok(/data-do="music:previous"[^>]*disabled/.test(radio)&&/data-do="music:next"[^>]*disabled/.test(radio)&&/data-do="music:shuffle"[^>]*disabled/.test(radio),'radio keeps disabled transport slots');
const httpOnly=musicCard({media_channel:undefined,media_duration:undefined,media_content_id:'http://stream'},'wash').music();
ok(!httpOnly.includes('Live radio'),'an http stream with no channel is not assumed to be radio');
for(const bad of ['javascript:alert(1)','//evil.example/x.jpg','http://insecure/x.jpg']){const h=musicCard({entity_picture:bad},'wash');ok(!h.music().includes(bad)&&!h.musicBackdrop().includes(bad),'unsafe artwork rejected: '+bad);}
const noArt=musicCard({entity_picture:undefined,media_title:'T'.repeat(300)},'bleed');ok(noArt.music().includes('class="disc"')&&noArt.musicBackdrop().includes('bd-colour'),'missing artwork uses the fallback cover and colour layer');
const failed=musicCard({},'wash');failed.failedArt.add(song.attributes.entity_picture);ok(failed.music().includes('class="disc"'),'artwork that failed to load falls back');
const pal=musicCard({},'colour');for(let i=0;i<30;i++)pal.palette('/art/'+i);ok(pal.palettes.size<=12,'palette cache is bounded');
const loads=[];sandbox.Image=class{constructor(){loads.push(this);}};const pal2=musicCard({},'colour');pal2.shadowRoot.querySelector=()=>null;pal2.ownerDocument={createElement:()=>({getContext:()=>{throw new Error('tainted');}})};for(let i=0;i<20;i++)pal2.palette('/late/'+i);loads.forEach(img=>img.onload());ok(pal2.palettes.size<=12,'late artwork loads cannot regrow the palette cache');delete sandbox.Image;
// Transport payloads
const sent=[];const tc=musicCard({},'wash');tc._hass.callWS=async m=>{sent.push(m.args);return {};};
tc.click('music:shuffle');eq(JSON.stringify(sent[0]),JSON.stringify({action:'shuffle',shuffle:true}),'shuffle sends the opposite of the current state');
ok(tc.music().includes('data-do="music:pause"'),'playing song offers pause');
tc._hass.states[P].state='paused';ok(tc.music().includes('data-do="music:resume"'),'paused song offers play');
// Missing, unavailable or featureless players offer nothing, even with stale attributes.
const slots=h=>['previous','pause','resume','next','shuffle'].filter(x=>new RegExp(`data-do="music:${x}"(?![^>]*disabled)`).test(h));
const gone=musicCard({},'wash');gone._hass.states[P].state='unavailable';const goneHtml=gone.music();
eq(slots(goneHtml).length,0,'unavailable player disables transport');ok(/id="volume"[^>]*disabled/.test(goneHtml)&&goneHtml.includes('Speaker unavailable'),'unavailable player disables volume and says so');
const missing=musicCard({},'wash');missing._hass.states={};eq(slots(missing.music()).length,0,'missing player disables transport');
eq(slots(musicCard({supported_features:undefined},'wash').music()).length,0,'no reported features means no controls');
// Controls: only this Echo's entities, only real services, within limits
const svc=[];const cc=new sandbox.Card();cc.config={device:'kitchen'};cc.render=()=>{};
cc.data={profile:{controls:['light.kitchen_spot','light.kitchen_lamp','light.kitchen_gone','climate.kitchen','climate.range']},timers:[]};
cc._hass={config:{unit_system:{temperature:'°C'}},callService:async(...a)=>{svc.push(a);},states:{
 'light.kitchen_spot':{state:'on',attributes:{friendly_name:'Kitchen Spot Lights'}},'light.kitchen_lamp':{state:'off',attributes:{friendly_name:'Kitchen Lamp Lights'}},'light.kitchen_gone':{state:'unavailable',attributes:{friendly_name:'Kitchen Wall'}},'light.other_room':{state:'off',attributes:{}},
 'climate.kitchen':{state:'heat',attributes:{friendly_name:'Kitchen',current_temperature:18.4,temperature:29.5,min_temp:5,max_temp:30,target_temp_step:.5,hvac_action:'heating',supported_features:1}},
 'climate.range':{state:'heat_cool',attributes:{friendly_name:'Range',current_temperature:20,target_temp_low:18,target_temp_high:22,min_temp:5,max_temp:30,supported_features:2}}}};
cc.click('light:light.kitchen_spot');cc.click('light:light.kitchen_lamp');cc.click('light:light.kitchen_gone');cc.click('light:light.other_room');
eq(JSON.stringify(svc.slice(0,2)),JSON.stringify([['light','turn_off',{entity_id:'light.kitchen_spot'}],['light','turn_on',{entity_id:'light.kitchen_lamp'}]]),'lights toggle with real services only');
eq(svc.length,2,'unavailable and foreign lights are never called');
cc.click('heat:climate.kitchen:1');eq(JSON.stringify(svc[2]),JSON.stringify(['climate','set_temperature',{entity_id:'climate.kitchen',temperature:30}]),'raise by one step');
cc._hass.states['climate.kitchen'].attributes.temperature=30;cc.click('heat:climate.kitchen:1');eq(svc.length,3,'never above max_temp');
cc.click('heat:climate.range:1');eq(svc.length,3,'heat_cool ranges are not adjusted');
cc._hass.states['climate.range'].attributes.temperature=20;cc._hass.states['climate.range'].attributes.supported_features=1;cc.click('heat:climate.range:1');eq(svc.length,3,'heat_cool is blocked even with a single temperature');
cc._hass.states['climate.range'].state='heat';cc._hass.states['climate.range'].attributes={...cc._hass.states['climate.range'].attributes,target_temp_low:null,target_temp_high:null,supported_features:undefined};cc.click('heat:climate.range:1');eq(svc.length,3,'no target-temperature capability bit, no change');
cc._hass.states['climate.range']={state:'heat_cool',attributes:{friendly_name:'Range',current_temperature:20,target_temp_low:18,target_temp_high:22,min_temp:5,max_temp:30,supported_features:2}};
const ctlHtml=cc.controls();ok(ctlHtml.includes('Kitchen lights')&&ctlHtml.includes('<b>Spot Lights</b>'),'shared room name becomes the group heading');ok(/Raise Kitchen target"[^>]*disabled/.test(ctlHtml),'raise disabled at max');ok(!ctlHtml.includes('Raise Range target'),'no +/- for a range thermostat');ok(ctlHtml.includes('Unavailable'),'unavailable state is labelled');
const info=[];cc.dispatchEvent=e=>info.push(e.detail.entityId);global.CustomEvent=sandbox.CustomEvent=class{constructor(t,o){this.detail=o.detail;}};
cc.click('info:light.kitchen_spot');cc.click('info:light.other_room');eq(info.join(),'light.kitchen_spot','more-info only for assigned controls');
const amb=new sandbox.Card();amb.config={device:'kitchen',ambient:true};amb.data=cc.data;amb._hass=cc._hass;amb.render=()=>{};amb.toggleLight('light.kitchen_spot');amb.stepClimate('climate.kitchen',-1);amb.click('music:pause');eq(svc.length,3,'ambient mode never changes anything');
// Weather and HomeGuide markup
const wc=new sandbox.Card();wc.config={device:'kitchen'};wc._hass={states:{}};const hour=new Date(Date.now()+3600e3).toISOString();
wc.data={profile:{},timers:[],forecast:{source:'Met <i>',fetched_at:Date.now()/1000,condition:'rainy',temperature:12,temperature_unit:'°F',hourly:[{datetime:hour,condition:'rainy',temperature:11,precipitation_probability:150},{datetime:hour,condition:'rainy',temperature:null,precipitation_probability:null}],daily:[]}};
const wx=wc.weather();ok(wx.includes('height:100%')&&wx.includes('100%</small>'),'rain chance is clamped to 0-100%');ok(wx.includes('—</small>')&&wx.includes('<strong>—</strong>'),'missing values show a dash');ok(wx.includes('°F')&&wx.includes('Met &lt;i&gt;'),'unit kept and source escaped');ok(/class="hour" title="[^"]*: Rainy, 11°, 100% chance of rain"/.test(wx),'hourly items carry a full text tooltip');
const gc=new sandbox.Card();gc.config={device:'kitchen'};gc.data={profile:{kiosk_hold:'switch.hold'},timers:[]};gc._hass={states:{'switch.hold':{state:'off'},'sensor.homeguide_library':{attributes:{appliances:[{id:'microwave',name:'Microwave',manufacturer:'Panasonic',model:'NN-ST46KB'}]}}}};
const balanced=h=>(h.match(/<div\b/g)||[]).length===(h.match(/<\/div>/g)||[]).length&&(h.match(/<header\b/g)||[]).length===(h.match(/<\/header>/g)||[]).length;
const lib=gc.guide();ok(balanced(lib)&&/<\/header><div class="view-body guide">/.test(lib),'guide heading closes before the grid');ok(lib.includes('NN-ST46KB'),'real library entries shown');
gc.result={view:'guide',payload:{appliance_id:'microwave',question:'Defrost?',guide:{answer:'Use <b>defrost</b>',results:[{document:'Manual',page:3,text:'x'}]}}};const ans=gc.guide();ok(balanced(ans)&&ans.includes('Use &lt;b&gt;defrost&lt;/b&gt;')&&ans.includes('Manual, page 3'),'guide answer and sources render escaped');
// ---- 0.8.1: answer, conversion and timer layouts ----
const view=(result,data={})=>{const c=new sandbox.Card();c.config={device:'kitchen'};c.data={profile:{},timers:[],ringing:[],...data};c._hass={states:{}};c.result=result;c.render=()=>{};return c;};
const shortAns=view({view:'answer',payload:{question:'Q <i>?',speech:'Yes <b>really</b>.'}}).answer();
ok(shortAns.includes('is-short')&&shortAns.includes('Q &lt;i&gt;?')&&shortAns.includes('Yes &lt;b&gt;really&lt;/b&gt;.')&&!shortAns.includes('<b>'),'short answer escaped with its question');
const longText='Line one\nLine two <script>\n'+'word '.repeat(80);const longAns=view({view:'answer',payload:{speech:longText}}).answer();
ok(longAns.includes('is-long')&&longAns.includes('answer-scroll')&&longAns.includes('Line one\nLine two &lt;script&gt;'),'long answer scrolls in its own region with line breaks kept');
ok(!longAns.includes('answer-q'),'no invented question line');ok(balanced(shortAns)&&balanced(longAns),'answer markup balanced');
ok(view(null).answer().includes('What would you like to know?'),'truthful empty state');
const convHtml=r=>view({view:'answer',payload:r}).answer();
const zero=convHtml({equation:'0 g = 0 oz',value:0,from_unit:'g',to_unit:'oz',result:0});ok(zero.includes('<strong>0</strong>')&&zero.includes('<span>0</span> <span>g</span>')&&zero.includes('fit-l'),'zero conversion shows 0, not an empty state');
const neg=convHtml({equation:'-40 °C = -40 °F',value:-40,from_unit:'°C',to_unit:'°F',result:-40});ok(neg.includes('<strong>-40</strong>')&&neg.includes('°F'),'negative conversion');
const big=convHtml({equation:'x',value:1e15,from_unit:'mm',to_unit:'km',result:1e12});ok(big.includes('1,000,000,000,000')&&big.includes('fit-s'),'large result steps the type down instead of truncating');
ok(convHtml({equation:'x',value:1,from_unit:'<u>',to_unit:'<u>',result:1}).includes('&lt;u&gt;')&&balanced(big),'conversion units escaped');
const pasta={id:'p1',name:'Pasta <b>',is_active:true,seconds_left:540,sampled_at:Date.now()/1000},eggs={id:'e1',name:'Eggs',is_active:false,seconds_left:125,sampled_at:0};
const empty=view(null).timers();ok(empty.includes('layout-empty')&&empty.includes('Something on the stove?')&&empty.includes('id="timer-form"'),'empty timers keep the creation form');
const form=/<form id="timer-form"[^>]*><input name="name"[^>]*maxlength="80"[^>]*><input name="minutes"[^>]*type="number" min="0.02" max="1440" step="any"[^>]*required>/;ok(form.test(empty),'timer form fields and validation unchanged');
const one=view(null,{timers:[pasta]}).timers();ok(one.includes('layout-one')&&one.includes('data-countdown="p1"')&&one.includes('9:00')&&one.includes('Running')&&one.includes('Pasta &lt;b&gt;'),'single timer: large, named, running');
ok(['timer:pause:p1','timer:add:p1','timer:cancel:p1'].every(x=>one.includes(`data-do="${x}"`))&&form.test(one),'single timer keeps pause, +1 min, cancel and the form');
const paused=view(null,{timers:[eggs]}).timers();ok(paused.includes('is-paused')&&/timer-state">[^]*?<span>Paused<\/span>/.test(paused)&&paused.includes('data-do="timer:resume:e1"')&&paused.includes('2:05'),'paused state in words with resume');
const three=view(null,{timers:[pasta,eggs,{...pasta,id:'r1',name:'Rice'}]}).timers();ok(three.includes('layout-few')&&three.indexOf('p1')<three.indexOf('e1')&&three.indexOf('e1')<three.indexOf('r1'),'several timers keep server order');
ok(view(null,{timers:[pasta,eggs]}).timers().includes('layout-two')&&view(null,{timers:Array.from({length:6},(_,i)=>({...pasta,id:'t'+i}))}).timers().includes('layout-many'),'layout adapts to the count');
const ringingHtml=view(null,{timers:[pasta],ringing:[{id:'f1',name:'Roast',finished_at:0}]}).timers();
ok(ringingHtml.indexOf('is-finished')<ringingHtml.indexOf('is-running')&&ringingHtml.includes('Finished')&&ringingHtml.includes('Say “stop” or tap the alert'),'finished alarm shown first, in words');
ok(!ringingHtml.includes('data-countdown="f1"')&&!/data-do="timer:[a-z]+:f1"/.test(ringingHtml),'finished alarm offers no card-side dismissal; Voice Satellite owns it');
ok(view(null,{timers:[pasta,eggs],ringing:[{id:'f1',name:'Roast'}]}).timers().includes('1 finished · 1 running · 1 paused'),'summary counts each state');ok(balanced(ringingHtml)&&balanced(three),'timer markup balanced');
const hours=view(null,{timers:[{...pasta,seconds_left:86400}]}).timers();ok(hours.includes('countdown is-long')&&hours.includes('24:00:00'),'hour-long countdown steps down to fit');ok(!one.includes('is-long'),'short countdown keeps full size');
const src=fs.readFileSync(process.argv[2],'utf8');ok(/\.answer-q\{[^}]*max-height:[^}]*overflow:auto/.test(src)&&/\.answer-scroll\{[^}]*min-height:min\(/.test(src),'long question is capped and scrolls, leaving the answer room');
ok(view({view:'answer',payload:{question:'Q '.repeat(400),speech:'A'}}).answer().includes('Q '.repeat(399)),'long question kept in full, not truncated');
// Home timer chips: larger, Home-only, bounded so they never run under the weather button or the clock.
const strip=view(null,{timers:[pasta,eggs]});strip.view='home';const stripHtml=strip.timerStrip();
ok((stripHtml.match(/data-do="view:timers"/g)||[]).length===2&&stripHtml.includes('data-countdown="p1"')&&/data-countdown="e1">2:05<\/b><small>Paused<\/small>/.test(stripHtml)&&stripHtml.includes('Pasta &lt;b&gt;'),'home chips still open Timers, count down and mark paused');
const homeStrip=(src.match(/\.view-home \.timer-strip\{[^}]*\}/)||[''])[0];ok(/--chip-count:clamp\(24px,/.test(homeStrip)&&/right:calc\(/.test(homeStrip)&&/max-height:/.test(homeStrip)&&/overflow-y:auto/.test(homeStrip),'home strip is larger, stops before the weather button and is capped above the clock');
ok(/\.timer-strip\{[^}]*\}\.timer-chip\{[^}]*font-size:19px/.test(src)&&!/[^e] \.timer-chip b\{[^}]*--chip-count/.test(src.replace(/\.view-home \.timer-chip b/g,'')),'other views keep the compact chips');
ok(!/baseline\/|echo-experience-0\.8\.0|home-compare|production-check|mockups\//.test(src),'production card carries no preview baseline or comparison paths');
const tsent=[];const tcard=view(null,{timers:[pasta]});tcard._hass.callWS=async m=>{tsent.push(m);return {};};tcard.click('timer:pause:p1');
eq(JSON.stringify(tsent[0]),JSON.stringify({type:'echo_experience/action',device:'kitchen',action:'timer',args:{operation:'pause',timer_id:'p1'}}),'timer action payload unchanged');
const ambT=view(null,{timers:[pasta]});ambT.config.ambient=true;ambT._hass.callWS=async m=>{tsent.push(m);};ambT.click('timer:cancel:p1');eq(tsent.length,1,'ambient never changes timers');
// A focused form survives background renders; resizing updates the height without re-rendering.
const keep=view(null,{timers:[pasta]});delete keep.render;keep.view='timers';keep.shadowRoot.activeElement={matches:s=>s.startsWith('input')};keep.shadowRoot.innerHTML='typing';keep.render();eq(keep.shadowRoot.innerHTML,'typing','focused timer form is not replaced');
const sized=view(null);sized._hass=undefined;const props={};sized.style={setProperty:(k,v)=>props[k]=v};sized.getBoundingClientRect=()=>({top:40});sandbox.window.innerHeight=640;let rerender=0;sized.render=()=>rerender++;
const listeners={};sandbox.window.addEventListener=(t,f)=>listeners[t]=f;sandbox.window.removeEventListener=t=>delete listeners[t];sized.connectedCallback();sandbox.window.innerHeight=600;listeners.resize();
eq(props['--echo-height'],'560px','resize recomputes the available height');eq(rerender,0,'resize does not re-render');sized.disconnectedCallback();ok(!listeners.resize,'resize listener removed on disconnect');
// The native Kiosk satellite is watched like the browser one, so a native turn re-renders the card.
const watch=new sandbox.Card();watch.config={device:'kitchen'};let renders=0;watch.render=()=>{renders++;};watch.data={profile:{satellite:'assist_satellite.kitchen',native:{satellite:'assist_satellite.ks_kitchen'},music_player:'media_player.kitchen'},timers:[]};
const before={states:{'assist_satellite.ks_kitchen':{state:'idle'}}};watch._hass=before;watch.hass={states:{'assist_satellite.ks_kitchen':{state:'listening'}}};assert.equal(renders,1,'native satellite change re-renders');
let ambient=new sandbox.Card();ambient.config={device:'kitchen',ambient:true};ambient.data=playback.data;ambient._hass=playback._hass;ambient.render=()=>{};ambient.syncPlayback();ambient.receive({device:'kitchen',result:{view:'music'}});assert.equal(ambient.view,'home','Screensaver stays on the clock');
// Ringing timer dismissal: the card replays Voice Satellite's own dismissal gestures in the Echo's browser and
// reports honestly. A fake document stands in for the page that hosts the native .vs-timer-alert element inside
// #voice-satellite-ui, with Voice Satellite's browser identity (localStorage vs-satellite-entity / vs-panel-config).
(async()=>{
 const same=(a,b)=>assert.equal(JSON.stringify(a),JSON.stringify(b));
 const makeDoc=(alerts,onGesture,{ui=true,satellite='assist_satellite.kitchen',external=false}={})=>{
  const store={'vs-panel-config':JSON.stringify({satellite_entity:satellite,debug:false})};if(!external&&satellite)store['vs-satellite-entity']=satellite;
  const doc={alerts,listeners:[],body:{},defaultView:{KeyboardEvent:class{constructor(t,o){this.type=t;this.key=o.key;}},MouseEvent:class{constructor(t){this.type=t;}},localStorage:{getItem:k=>store[k]??null}}};
  if(external)doc.defaultView.__vsExternalSettings={get:()=>({satellite})};
  doc.getElementById=id=>ui&&id==='voice-satellite-ui'?{}:null;
  doc.querySelector=()=>doc.alerts>0?{}:null;doc.dispatchEvent=e=>onGesture(doc,e);doc.body.dispatchEvent=e=>onGesture(doc,e);return doc;};
 const calls=[];const card=(ringing,docOpts)=>{const c=new sandbox.Card();c.config={device:'kitchen'};c.data={profile:{satellite:'assist_satellite.kitchen'},timers:[],ringing};c.render=()=>{};c._hass={callWS:async m=>{calls.push(m);return {};}};return c;};
 const pasta=()=>[{id:'t1',name:'Pasta',finished_at:0}];
 const ring=card(pasta());let taps=0;ring.ownerDocument=makeDoc(1,(doc,e)=>{if(e.type==='click'&&++taps===2)doc.alerts=0;});
 await ring.dismiss({request:'abc',timers:[{id:'t1',name:'Pasta'}]});
 same(calls[0].args,{operation:'dismissed',request:'abc',timers:['t1'],present:true,dismissed:true});assert.equal(taps,2,'two taps within 400 ms');same(ring.data.ringing,[]);
 const stuck=card(pasta());stuck.ownerDocument=makeDoc(1,()=>{});await stuck.dismiss({request:'def',timers:[{id:'t1'}]});
 assert.equal(calls[1].args.dismissed,false,'a surviving alert is never reported as dismissed');assert.equal(stuck.data.ringing.length,1);
 // No DOM alert and no Voice Satellite session: the card cannot know whether the device is sounding, so it says so.
 const gone=card(pasta());gone.ownerDocument=makeDoc(0,()=>{throw new Error('no gesture without an alert');});await gone.dismiss({request:'ghi',timers:[{id:'t1'}]});
 same(calls[2].args,{operation:'dismissed',request:'ghi',timers:[],present:false,dismissed:false,unknown:true});assert.equal(gone.data.ringing.length,1,'unknown state clears nothing');
 const idle=card(pasta());idle.ownerDocument=makeDoc(0,()=>{});for(let i=0;i<5;i++)idle.checkRinging();assert.equal(calls.length,3,'no silence report without evidence');assert.equal(idle.data.ringing.length,1);
 // With the session present (Voice Satellite 2026.9.10+, native Kiosk alerts, no DOM element) its alertActive flag decides.
 const withSession=(alertActive,onDismiss)=>{const doc=makeDoc(0,()=>{throw new Error('DOM gesture must not be used when the session is available');});doc.defaultView.__vsSession={timer:{alertActive,dismissAlert(){onDismiss?.(this);}}};return doc;};
 const native=card(pasta());native.ownerDocument=withSession(true,t=>{t.alertActive=false;});
 await native.dismiss({request:'nat',timers:[{id:'t1',name:'Pasta'}]});same(calls[3].args,{operation:'dismissed',request:'nat',timers:['t1'],present:true,dismissed:true});same(native.data.ringing,[]);
 const nativeStuck=card(pasta());nativeStuck.ownerDocument=withSession(true,()=>{});
 await nativeStuck.dismiss({request:'nst',timers:[{id:'t1'}]});assert.equal(calls[4].args.dismissed,false,'session still ringing is never reported as dismissed');assert.equal(nativeStuck.data.ringing.length,1);
 const nativeQuiet=card(pasta());nativeQuiet.ownerDocument=withSession(false,()=>{throw new Error('nothing to dismiss');});
 await nativeQuiet.dismiss({request:'nq',timers:[{id:'t1'}]});same(calls[5].args,{operation:'dismissed',request:'nq',timers:['t1'],present:false,dismissed:false});
 const nativeIdle=card(pasta());nativeIdle.ownerDocument=withSession(false);nativeIdle.checkRinging();nativeIdle.checkRinging();assert.equal(calls.length,6,'needs three quiet ticks');nativeIdle.checkRinging();
 same(calls[6].args,{operation:'dismissed',timers:['t1'],present:false,dismissed:false});same(nativeIdle.data.ringing,[]);
 const recent=card([{id:'t1',name:'Pasta',finished_at:Date.now()/1000}]);recent._hass={callWS:async()=>{throw new Error('too early');}};recent.ownerDocument=withSession(false);
 for(let i=0;i<5;i++)recent.checkRinging();assert.equal(recent.data.ringing.length,1,'a just-finished alert may still be deferred by Voice Satellite');
 // Only the requested ids are cleared locally; a timer that finished after the request keeps ringing.
 const partial=card([...pasta(),{id:'t2',name:'Eggs',finished_at:0}]);partial.ownerDocument=makeDoc(1,(doc,e)=>{if(e.type==='keydown')doc.alerts=0;});
 await partial.dismiss({request:'jkl',timers:[{id:'t1'}]});same(partial.data.ringing.map(t=>t.id),['t2']);same(calls[7].args.timers,['t1']);
 // Gesture replay: no second tap once the first already cleared the alert.
 let single=0;const quick=card(pasta());quick.ownerDocument=makeDoc(1,(doc,e)=>{if(e.type==='click'){single++;doc.alerts=0;}});
 await quick.dismiss({request:'mno',timers:[{id:'t1'}]});assert.equal(single,1,'second tap withheld after the first cleared the alert');assert.equal(calls[8].args.dismissed,true);
 // Browser ownership: a second dashboard (phone/laptop) or a browser running another satellite never acts or reports.
 const before=calls.length;
 for(const [label,opts] of [['no Voice Satellite UI',{ui:false}],['another satellite',{satellite:'assist_satellite.bedroom'}],['no satellite known',{satellite:null}]]){
  const foreign=card(pasta());foreign.ownerDocument=makeDoc(1,()=>{throw new Error('gesture from a non-hosting browser: '+label);},opts);
  await foreign.dismiss({request:'pqr',timers:[{id:'t1'}]});assert.equal(foreign.data.ringing.length,1,label);
  foreign.ownerDocument.alerts=0;for(let i=0;i<4;i++)foreign.checkRinging();assert.equal(foreign.data.ringing.length,1,label+': no silence report');
 }
 assert.equal(calls.length,before,'non-hosting cards send nothing');
 // __vsExternalSettings (Kiosk-facing API) is honoured when localStorage has no vs-satellite-entity yet.
 const viaApi=card(pasta());viaApi.ownerDocument=makeDoc(1,(doc,e)=>{if(e.type==='keydown')doc.alerts=0;},{external:true});
 await viaApi.dismiss({request:'stu',timers:[{id:'t1'}]});assert.equal(calls[before].args.dismissed,true);
 a.receive({device:'kitchen',ringing:[{id:'t1',name:'Pasta'}],timer_event:{event_type:'finished'}});assert.equal(a.view,'timers');assert.equal(a.data.ringing.length,1);
 a.view='guide';a.receive({device:'kitchen',timer_event:{event_type:'finished'}});assert.equal(a.view,'guide','a pinned guide stays');
 const other=new sandbox.Card();other.config={device:'kitchen'};other.data={timers:[]};other.render=()=>{};other.dismiss=()=>{throw new Error('foreign dismissal');};
 other.receive({device:'bedroom',dismiss:{request:'zzz'}});
 // HA restart: the card connects before the integration registers its commands, then must recover by itself.
 {const listeners={};let fail=true,subs=0,unsubs=0;
  const conn={addEventListener:(t,f)=>{listeners[t]=f;},removeEventListener:(t,f)=>{if(listeners[t]===f)delete listeners[t];},
   subscribeMessage:async()=>{subs++;if(fail)throw new Error('Unknown command.');return ()=>{unsubs++;};}};
  const boot=new sandbox.Card();boot.config={device:'kitchen'};boot.isConnected=true;boot.render=()=>{};
  boot._hass={connection:conn,states:{},callWS:async()=>({profile:{},timers:[]})};
  await boot.connect();eq(boot.error,'Unknown command.','startup error is shown');ok(boot.retryHandle,'a retry is scheduled');
  eq(boot.connection,conn,'hass updates do not trigger a reconnect storm');
  clearTimeout(boot.retryHandle);fail=false;await boot.connect();eq(boot.error,'','the startup error clears once connected');eq(subs,2,'retry subscribes again');
  boot.error='That action could not be completed';await boot.refresh();eq(boot.error,'That action could not be completed','action errors are not wiped by a refresh');
  boot.error='';listeners.ready();await new Promise(r=>setTimeout(r,0));eq(subs,3,'a reconnect subscribes afresh');eq(unsubs,1,'the old subscription is dropped');
  boot.disconnectedCallback();ok(!listeners.ready,'the reconnect listener is removed');}
 console.log(`${56+added} frontend behaviour assertions passed`);
})().catch(err=>{console.error(err);process.exit(1);});
