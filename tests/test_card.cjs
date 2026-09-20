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
 console.log('47 frontend behaviour assertions passed');
})().catch(err=>{console.error(err);process.exit(1);});
