/* Controlled browser-geolocation callbacks; never requests a real user's location. */
const test = require('node:test');
const assert = require('node:assert/strict');
const gps = require('../citizen_web/app.js');
const fix = (accuracy = 8) => ({coords:{latitude:41.0623456,longitude:39.7512345,accuracy},timestamp:1793448000123});

test('GPS is explicit; success preserves latitude, longitude, accuracy and device timestamp', () => {
  const state = gps.createState(); let calls = 0;
  const env = {isSecureContext:true,navigator:{geolocation:{getCurrentPosition(success,error,options) {
    calls++; assert.equal(options.maximumAge,0); assert.equal(options.timeout,15000); success(fix());
  }}}};
  assert.equal(calls,0); assert.equal(state.candidate,null);
  gps.requestGps(state,env,()=>{});
  assert.equal(calls,1); assert.equal(state.busy,false); assert.equal(state.confirmed,false);
  assert.equal(state.candidate.latitude,fix().coords.latitude);
  assert.equal(state.candidate.longitude,fix().coords.longitude);
  assert.equal(state.candidate.accuracy_m,8);
  assert.equal(state.candidate.captured_at,new Date(fix().timestamp).toISOString());
  assert.throws(()=>gps.confirmedPayload(state));
  gps.confirmLocation(state,false); assert.equal(gps.confirmedPayload(state).location_confirmed,true);
});

test('permission denied, unavailable GPS and timeout offer manual alternative and remove old confirmation', () => {
  for (const code of [1,2,3]) {
    const state = gps.createState(); gps.selectGps(state,fix()); gps.confirmLocation(state,false);
    gps.requestGps(state,{isSecureContext:true,navigator:{geolocation:{getCurrentPosition(ok,fail){fail({code});}}}},()=>{});
    assert.equal(state.candidate,null); assert.equal(state.confirmed,false); assert.equal(state.busy,false);
    assert.match(state.error,/Haritadan|haritadan/);
    if(code===1) assert.match(state.error,/izni|izin/i);
  }
});

test('low accuracy requires an explicit acknowledgement; manual selection never invents accuracy', () => {
  const state = gps.createState(); gps.selectGps(state,fix(350));
  assert.throws(()=>gps.confirmLocation(state,false),/doğruluğu/);
  assert.equal(state.confirmed,false); gps.confirmLocation(state,true);
  gps.selectManual(state,-11.12345678,72.98765432,1793448000123);
  assert.equal(state.confirmed,false); assert.equal(state.candidate.accuracy_m,null);
  assert.equal(state.candidate.location_source,'manual_map');
  assert.equal(state.candidate.latitude,-11.12345678); assert.equal(state.candidate.longitude,72.98765432);
  gps.confirmLocation(state,false); assert.equal(gps.confirmedPayload(state).accuracy_m,null);
});

test('second click replaces selection; a late GPS callback cannot move a manually selected point', () => {
  const state = gps.createState(); let callback;
  gps.requestGps(state,{isSecureContext:true,navigator:{geolocation:{getCurrentPosition(ok){callback=ok;}}}},()=>{});
  gps.selectManual(state,41.01,39.70); gps.confirmLocation(state,false);
  gps.selectManual(state,41.02,39.71);
  assert.equal(state.confirmed,false); callback(fix());
  assert.equal(state.candidate.latitude,41.02); assert.equal(state.candidate.longitude,39.71);
});

test('insecure contexts, unsupported browsers, thrown errors and invalid coordinates fail clearly', () => {
  for (const env of [
    {isSecureContext:false,navigator:{}}, {isSecureContext:true,navigator:{}},
    {isSecureContext:true,navigator:{geolocation:{getCurrentPosition(){throw Error('fixture');}}}}
  ]) {
    const state = gps.createState(); gps.requestGps(state,env,()=>{});
    assert.ok(state.error); assert.equal(state.busy,false); assert.equal(state.candidate,null);
  }
  const state = gps.createState(); gps.selectGps(state,fix(-1));
  assert.equal(state.candidate,null); assert.ok(state.error);
  assert.throws(()=>gps.selectManual(state,91,39));
});

function fakePage() {
  const elements = {}, markers = [], circles = []; let click, success, failure, calls = 0, tileError;
  const element = id => elements[id] ||= {hidden:false,checked:false,disabled:false,textContent:'',files:[],
    events:{},addEventListener(event,handler){this.events[event]=handler;},focus(){}};
  const map = {setView(){return this;},on(event,handler){if(event==='click')click=handler;return this;}};
  const env = {document:{getElementById:element},isSecureContext:true,
    navigator:{geolocation:{getCurrentPosition(ok,fail){calls++; success=ok;failure=fail;}}},
    fetch:async()=>({json:async()=>({ready:true})}),
    L:{map:()=>map,tileLayer:()=>({addTo(){return this;},on(event,handler){if(event==='tileerror') tileError=handler; return this;}}),
      marker:coords=>{const marker={coords,removed:false,addTo(){return this;},bindPopup(){return this;},remove(){this.removed=true;}};markers.push(marker);return marker;},
      circle:(coords,options)=>{const circle={coords,options,removed:false,addTo(){return this;},remove(){this.removed=true;}};circles.push(circle);return circle;}}};
  return {env,element,markers,circles,mapClick:(lat,lng)=>click({latlng:{lat,lng}}),
    tileFailure:()=>tileError(),
    gpsSuccess:value=>success(value),gpsFailure:value=>failure(value),calls:()=>calls};
}

test('page buttons render a temporary Leaflet marker/circle, then require confirmation; denial enables manual flow', async () => {
  const page = fakePage(); gps.init(page.env);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(page.calls(),0); assert.equal(page.markers.length,0);
  page.element('photo').files=[{type:'image/jpeg',size:100}];
  page.element('gps').events.click(); assert.equal(page.calls(),1);
  page.gpsSuccess(fix());
  assert.deepEqual(page.markers.at(-1).coords,[fix().coords.latitude,fix().coords.longitude]);
  assert.equal(page.circles.at(-1).options.radius,8);
  assert.equal(page.element('submit').disabled,true);
  page.element('confirm').events.click(); assert.equal(page.element('submit').disabled,false);
  page.element('gps').events.click(); page.gpsFailure({code:1});
  assert.match(page.element('location-status').textContent,/izni/);
  assert.equal(page.element('submit').disabled,true);
  page.mapClick(40.12345678,38.98765432);
  assert.deepEqual(page.markers.at(-1).coords,[40.12345678,38.98765432]);
  assert.match(page.element('accuracy').textContent,/Bilinmiyor/);
  assert.equal(page.element('accuracy-warning').hidden,true);
  page.element('confirm').events.click(); assert.equal(page.element('submit').disabled,false);
});

test('tile failure leaves the form usable and exposes a non-blocking warning', async () => {
  const page = fakePage(); gps.init(page.env);
  await new Promise(resolve=>setImmediate(resolve));
  page.tileFailure();
  assert.equal(page.element('map-error').hidden, false);
  page.mapClick(40.12345678,38.98765432);
  assert.equal(page.element('confirm').disabled, false);
});

test('page low-accuracy warning blocks confirmation until the checkbox is selected', async () => {
  const page = fakePage(); gps.init(page.env);
  await new Promise(resolve=>setImmediate(resolve));
  page.element('photo').files=[{type:'image/jpeg',size:100}];
  page.element('gps').events.click(); page.gpsSuccess(fix(400));
  assert.equal(page.element('accuracy-warning').hidden,false);
  page.element('confirm').events.click(); assert.equal(page.element('submit').disabled,true);
  page.element('accuracy-ack').checked=true;
  page.element('confirm').events.click(); assert.equal(page.element('submit').disabled,false);
  assert.equal(page.element('location-status').className,'');
});
