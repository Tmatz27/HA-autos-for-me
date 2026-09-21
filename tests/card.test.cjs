const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
class Element {
  constructor(tag='editor'){this.tagName=tag;this.children=[];this.dataset={};this.listeners={};}
  appendChild(node){this.children.push(node);return node;}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.children=nodes;}
  setAttribute(key,value){this[key]=value;}
  addEventListener(key,fn){this.listeners[key]=fn;}
  dispatchEvent(event){this.lastEvent=event;}
  querySelectorAll(selector){return this.children.flatMap(n=>[
    ...((selector==='ha-form'&&n.tagName==='ha-form')||(selector==='details[open]'&&n.tagName==='details'&&n.open)?[n]:[]),
    ...n.querySelectorAll(selector)]);}
}
const context = vm.createContext({HTMLElement:Element,customElements:{define(){}},window:{},console,
  document:{createElement:tag=>new Element(tag)},CustomEvent:class {constructor(type,data){this.type=type;Object.assign(this,data);}},setTimeout});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../dist/window-fan-card.js'),'utf8')+
  '\nglobalThis.api={WindowFanCard,WindowFanCardEditor,decodeWatts,DEFAULT_WATTS,WATT_SCHEMA,discoverFans,resolveConfig,sensorField};',context);
const {WindowFanCard,WindowFanCardEditor,decodeWatts,DEFAULT_WATTS,WATT_SCHEMA,discoverFans,resolveConfig,sensorField}=context.api;
function card() {
  const c=new WindowFanCard();
  c.setConfig({name:'Bedroom <Fan>',power_sensor:'sensor.power',state_sensor:'sensor.bedroom_fan_state',
    controller_script:'script.bedroom_fan_set_state',status_sensor:'sensor.status',calibration_prefix:'bedroom_fan',managed:true,
    power_switch:'switch.legacy',override_boolean:'input_boolean.legacy'});
  const error={textContent:''};
  c._root={querySelector:s=>s==='.wfc-error'?error:null}; c._built=true;
  c._hass={states:{'script.bedroom_fan_set_state':{state:'off'},'sensor.power':{state:'36'},'sensor.bedroom_fan_state':{state:'cool_high'},
    'sensor.status':{state:'Sleep lock',attributes:{error:'IR not confirmed'}}},callService:async(...args)=>c.calls.push(args)};
  c.calls=[];return c;
}
(async()=>{
  const c=card(); c._render();
  assert.equal(c._state().mode,'cool'); // always shares backend decoding, never recalculates from another table
  assert.ok(c._root.innerHTML.includes('Bedroom &lt;Fan&gt;'));
  assert.ok(c._root.innerHTML.includes('Cool • High'));
  assert.ok(!c._root.innerHTML.includes('data-action="power"'));
  assert.ok(!c._root.innerHTML.includes('data-action="override"'));
  assert.equal(c._root.querySelector('.wfc-error').textContent,'IR not confirmed');
  for (const state of ['exhaust_low','exhaust_med','exhaust_high','circulate_low','circulate_med','circulate_high','cool_low','cool_med','cool_high']) {
    c._hass.states['sensor.bedroom_fan_state'].state=state;
    assert.equal(c._state().mode+'_'+c._state().speed,state);
  }
  c._hass.states['sensor.bedroom_fan_state'].state='unknown';
  assert.equal(c._state().on,null);
  await c._setState('cool',null);
  assert.equal(c.calls.length,1); assert.equal(c.calls[0][0],'script'); assert.equal(c.calls[0][1],'bedroom_fan_set_state');
  assert.equal(c.calls[0][2].event,'manual'); assert.equal(c.calls[0][2].target_function,'cool');
  await c._setState(null,'low'); await c._setState('circulate',null); c._togglePower(); c._toggleOverride();
  assert.equal(c.calls.length,1);
  await c._setState(null,'high'); assert.equal(c.calls[1][2].target_function,''); // speed correction alone must not start bedtime
  await Promise.all([c._setState('cool',null),c._setState('exhaust',null)]);
  assert.equal(c.calls.length,3);
  const fields=WATT_SCHEMA;
  assert.equal(fields.filter(x=>/^(cool|exhaust|circulate)_/.test(x.name)).length,9);
  const w={...DEFAULT_WATTS,circulate_low:39,circulate_med:42,circulate_high:54};
  for(const mode of ['cool','exhaust','circulate']) for(const speed of ['low','med','high']) {
    assert.equal(decodeWatts(w[mode+'_'+speed],w).mode,mode);
    assert.equal(decodeWatts(w[mode+'_'+speed],w).speed,speed);
  }
  const states={};
  for(let i=0;i<20000;i++) states['sensor.unrelated_'+i]={state:'1',attributes:{device_class:'battery',unit_of_measurement:'%'}};
  for(const room of ['bedroom','den']) {
    states[`sensor.${room}_fan_state`]={state:'exhaust_high',attributes:{friendly_name:room+' Fan State',
      calibration_prefix:room+'_fan',power_sensor:`sensor.${room}_power`,temperature_sensor:`sensor.${room}_temp`,humidity_sensor:`sensor.${room}_rh`}};
    states[`script.${room}_fan_set_state`]={state:'off',attributes:{}};
    states[`sensor.${room}_power`]={state:'36',attributes:{device_class:'power',unit_of_measurement:'W'}};
    states[`sensor.${room}_temp`]={state:'72',attributes:{device_class:'temperature',unit_of_measurement:'°F'}};
    states[`sensor.${room}_rh`]={state:'60',attributes:{device_class:'humidity',unit_of_measurement:'%'}};
  }
  const hass={states,callService:async(...args)=>c.calls.push(args)};
  assert.equal(discoverFans(hass).length,2);
  const partial={remote:'remote.den',power_sensor:'sensor.den_power',status_sensor:'sensor.den_fan_control_status',
    calibration_prefix:'den_fan',managed:false};
  const fixed=resolveConfig(partial,hass);
  assert.equal(fixed.controller_script,'script.den_fan_set_state'); assert.equal(fixed.managed,true);
  assert.equal(fixed.state_sensor,'sensor.den_fan_state'); assert.equal(fixed.temperature_sensor,'sensor.den_temp');
  const minimal=resolveConfig({fan_package:'sensor.bedroom_fan_state'},hass);
  assert.equal(minimal.humidity_sensor,'sensor.bedroom_rh');
  assert.equal(resolveConfig({...partial,setup_mode:'standalone'},hass).controller_script,undefined);
  assert.equal(resolveConfig({...partial,state_sensor:'sensor.bedroom_fan_state'},hass).fan_package,undefined);
  assert.equal(resolveConfig({fan_package:'sensor.missing',controller_script:'script.den_fan_set_state'},hass).controller_script,undefined);
  assert.equal(WindowFanCard.getStubConfig(hass).fan_package,undefined); // never choose an arbitrary room
  for(const [key,kind] of [['power_sensor','power'],['temperature_sensor','temperature'],['humidity_sensor','humidity']]) {
    const ids=sensorField(key,kind,hass).selector.entity.include_entities;
    assert.equal(ids.length,2);assert.ok(!ids.some(id=>id.includes('unrelated')));
  }
  assert.ok(sensorField('temperature_sensor','temperature',hass,'sensor.custom').selector.entity.include_entities.includes('sensor.custom'));
  const editor=new WindowFanCardEditor(); editor.setConfig(partial); editor.hass=hass;
  const select=editor.children.find(n=>n.tagName==='label').children[0];
  assert.equal(select.value,'sensor.den_fan_state'); assert.equal(select.children.length,4);
  assert.equal(editor.querySelectorAll('ha-form').length,2); // name plus collapsed display options; no wiring form
  assert.equal(editor._rangeRows.length,10); // Off plus all nine modes/speeds
  states['input_number.den_fan_watts_cool_med_upper']={state:'50'};
  editor.hass={...hass};
  assert.equal(editor._rangeRows[9].value.textContent,'≥ 50 W');
  states['input_number.den_fan_watts_cool_med_upper']={state:'50.5'};
  editor.hass={...hass};
  assert.equal(editor._rangeRows[9].value.textContent,'≥ 50.5 W');
  const originalForms=editor.querySelectorAll('ha-form'); editor.hass={...hass};
  assert.equal(editor.querySelectorAll('ha-form')[0],originalForms[0]); // don't steal focus on sensor updates
  editor._choose('sensor.bedroom_fan_state');
  assert.equal(editor.lastEvent.detail.config.fan_package,'sensor.bedroom_fan_state');
  assert.equal(editor.lastEvent.detail.config.power_sensor,undefined);
  assert.equal(resolveConfig(editor.lastEvent.detail.config,hass).power_sensor,'sensor.bedroom_power');
  editor._choose('standalone');
  assert.equal(editor.lastEvent.detail.config.controller_script,undefined);
  assert.ok(editor.querySelectorAll('ha-form').some(f=>f.schema.some(s=>s.name==='remote')));
  c.setConfig(partial); c._built=true; c.hass=hass;
  assert.equal(c._config.managed,true);assert.equal(c._state().mode,'exhaust');
  assert.ok(!c._root.innerHTML.includes('Continuous automatic control'));
  assert.ok(!c._root.innerHTML.includes('Shared wattage calibration'));
  assert.ok(!c._root.innerHTML.includes('Measure all nine'));
  assert.ok(!c._root.innerHTML.includes('data-action="power"'));
  c.setConfig({fan_package:'sensor.missing'});c._built=true;c.hass=hass;
  const before=c.calls.length;await c._setState('cool',null);assert.equal(c.calls.length,before);
  assert.equal(c._error,'Select a fan in the card editor.');
  console.log('PASS: package discovery among 20,000 unrelated sensors; partial-config repair; minimal config; filtered sensors; editor room switching; unavailable-package guard; uncluttered card.');
  console.log('PASS: all nine shared states; managed service routing; manual bedtime intent; high-only controls; no Off; duplicate clicks; calibration fields; standalone decoding.');
})().catch(e=>{console.error(e);process.exitCode=1;});
