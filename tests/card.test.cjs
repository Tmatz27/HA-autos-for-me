const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const context = vm.createContext({HTMLElement:class {},customElements:{define(){}},window:{},console,
  document:{},CustomEvent:class {constructor(type,data){this.type=type;Object.assign(this,data);}},setTimeout});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../dist/window-fan-card.js'),'utf8')+
  '\nglobalThis.api={WindowFanCard,decodeWatts,DEFAULT_WATTS,EDITOR_SCHEMA};',context);
const {WindowFanCard,decodeWatts,DEFAULT_WATTS,EDITOR_SCHEMA}=context.api;
function card() {
  const c=new WindowFanCard();
  c.setConfig({name:'Bedroom <Fan>',power_sensor:'sensor.power',state_sensor:'sensor.bedroom_fan_state',
    controller_script:'script.bedroom_fan_set_state',status_sensor:'sensor.status',calibration_prefix:'bedroom_fan',managed:true,
    power_switch:'switch.legacy',override_boolean:'input_boolean.legacy'});
  const error={textContent:''};
  c._root={querySelector:s=>s==='.wfc-error'?error:null}; c._built=true;
  c._hass={states:{'sensor.power':{state:'36'},'sensor.bedroom_fan_state':{state:'cool_high'},
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
  const fields=EDITOR_SCHEMA.find(x=>x.name==='watts').schema;
  assert.equal(fields.filter(x=>/^(cool|exhaust|circulate)_/.test(x.name)).length,9);
  const w={...DEFAULT_WATTS,circulate_low:39,circulate_med:42,circulate_high:54};
  for(const mode of ['cool','exhaust','circulate']) for(const speed of ['low','med','high']) {
    assert.equal(decodeWatts(w[mode+'_'+speed],w).mode,mode);
    assert.equal(decodeWatts(w[mode+'_'+speed],w).speed,speed);
  }
  console.log('PASS: all nine shared states; managed service routing; manual bedtime intent; high-only controls; no Off; duplicate clicks; calibration fields; standalone decoding.');
})().catch(e=>{console.error(e);process.exitCode=1;});
