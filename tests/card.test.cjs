const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');
(async () => {
  const browser=await chromium.launch({headless:true,...(process.env.FAN_TEST_BROWSER ? {channel:process.env.FAN_TEST_BROWSER} : {})});
  try {
    const page=await browser.newPage({viewport:{width:430,height:950}});
    const errors=[]; page.on('pageerror',e=>errors.push(e.message));
    await page.setContent('<html><body style="margin:12px;background:#101820;color:#edf4fa;font-family:system-ui;--primary-text-color:#edf4fa;--secondary-text-color:#adc0ce;--divider-color:#345"></body></html>');
    await page.addScriptTag({path:path.join(__dirname,'../dist/window-fan-card.js')});
    await page.evaluate(() => {
      window.calls=[];
      const card=document.createElement('window-fan-card'); window.card=card;
      card.setConfig({name:'Den <Fan>',fan_package:'sensor.den_fan_state'});
      window.hass={states:{
        'sensor.den_fan_state':{state:'cool_high',attributes:{controller_script:'script.den_fan_set_state',status_sensor:'sensor.den_fan_control_status',manual_control:true,power_sensor:'sensor.test_power',temperature_sensor:'sensor.test_t',humidity_sensor:'sensor.test_rh'}},
        'script.den_fan_set_state':{state:'off'},'sensor.test_power':{state:'50.4',attributes:{unit_of_measurement:'W'}},
        'sensor.test_t':{state:'unknown',attributes:{unit_of_measurement:'°F'}},'sensor.test_rh':{state:'unavailable',attributes:{unit_of_measurement:'%'}},
        'sensor.den_fan_control_status':{state:'Climate unavailable',attributes:{confidence:'inferred',running:true,evidence:'Overlapping power bands; expected setting retained',last_outcome:'IR receipt unproven',recovery:'idle',manual_until_timestamp:0,error:''}}
      },callService:async(...args)=>window.calls.push(args)};
      document.body.append(card); card.hass=window.hass;
    });
    assert.match(await page.locator('.wfc-title').innerText(),/Den <Fan>/);
    assert.equal(await page.locator('script').count(),1);
    assert.match(await page.locator('.wfc').innerText(),/50.4 W/);
    assert.match(await page.locator('.wfc').innerText(),/unknown °F/);
    assert.match(await page.locator('.wfc').innerText(),/unavailable%/);
    assert.match(await page.locator('.wfc').innerText(),/inferred/);
    assert.equal(await page.locator('[data-action="mode"]').count(),3);
    assert.equal(await page.locator('[data-action="speed"]').count(),3);
    for(const mode of ['cool','exhaust','circulate']) {
      await page.locator(`[data-action="mode"][data-value="${mode}"]`).click();
    }
    for(const speed of ['low','med','high']) {
      await page.locator(`[data-action="speed"][data-value="${speed}"]`).click();
    }
    const calls=await page.evaluate(()=>window.calls);
    assert.equal(calls.length,6);
    for(let i=0;i<6;i++) {
      assert.deepEqual(calls[i].slice(0,2),['script','turn_on']);
      assert.equal(calls[i][2].entity_id,'script.den_fan_set_state');
      assert.equal(calls[i][2].variables.event,'manual');
      assert.equal(calls[i][2].variables.target_function,i<3 ? ['cool','exhaust','circulate'][i] : '');
      assert.equal(calls[i][2].variables.target_speed,i>=3 ? ['low','med','high'][i-3] : '');
    }
    // Every shared state, including unknown/off, renders without wattage decoding.
    for(const mode of ['cool','exhaust','circulate']) for(const speed of ['low','med','high']) {
      assert.equal(await page.evaluate(([m,s])=>{hass.states['sensor.den_fan_state'].state=`${m}_${s}`; card.hass=hass; const st=card._state(); return `${st.mode}_${st.speed}`;},[mode,speed]),`${mode}_${speed}`);
    }
    await page.evaluate(()=>{hass.states['sensor.den_fan_state'].state='unknown'; card.hass=hass;});
    await page.locator('[data-action="confirm-open"]').click();
    await page.locator('[data-action="confirm"]').click();
    assert.match(await page.locator('.wfc-error').innerText(),/Select both/);
    await page.locator('[data-physical="mode"]').selectOption('exhaust');
    await page.locator('[data-physical="speed"]').selectOption('med');
    await page.locator('[data-action="confirm"]').click();
    assert.deepEqual(await page.evaluate(()=>calls.at(-1)[2].variables),{event:'synchronize',target_function:'exhaust',target_speed:'med'});
    await page.locator('[data-action="recover"]').click();
    assert.equal(await page.evaluate(()=>calls.at(-1)[2].variables.event),'recover');
    await page.evaluate(()=>{hass.states['sensor.den_fan_control_status'].attributes.manual_until_timestamp=Date.now()/1000+1800; card.hass=hass;});
    assert.match(await page.locator('.wfc-manual-row').innerText(),/Manual · 30 min/);
    await page.locator('[data-action="resume"]').click();
    assert.equal(await page.evaluate(()=>calls.at(-1)[2].variables.event),'resume_auto');
    await page.evaluate(()=>{const s=hass.states['sensor.den_fan_control_status']; s.attributes.manual_until_timestamp=0; s.attributes.blocked=true; s.attributes.error='Recover: Power On failed <test>'; card.hass=hass;});
    assert.match(await page.locator('.wfc-manual-row').innerText(),/Auto paused/);
    assert.equal(await page.locator('.wfc-error').innerText(),'Recover: Power On failed <test>');
    assert.equal(await page.locator('test').count(),0);
    await page.evaluate(()=>{hass.callService=async()=>{throw new Error('HA service unavailable');};});
    await page.locator('[data-action="mode"][data-value="cool"]').click();
    assert.equal(await page.locator('.wfc-error').innerText(),'HA service unavailable');
    assert.equal(await page.evaluate(()=>card._busy),false);
    // A transport timeout clears busy and never automatically retries the action.
    await page.clock.install();
    await page.evaluate(()=>{window.hungCalls=0; hass.callService=()=>{window.hungCalls++;return new Promise(()=>{});}; card._request({event:'manual',target_speed:'high'});});
    await page.clock.fastForward(10001);
    assert.equal(await page.evaluate(()=>card._busy),false);
    assert.equal(await page.evaluate(()=>hungCalls),1);
    assert.match(await page.locator('.wfc-error').innerText(),/did not acknowledge/);
    // No package means no service call and a useful setup error.
    await page.evaluate(()=>{delete hass.states['script.den_fan_set_state']; card.hass=hass;});
    await page.locator('[data-action="mode"][data-value="cool"]').click();
    assert.match(await page.locator('.wfc-error').innerText(),/Select the installed den package/);
    assert.equal(await page.evaluate(()=>hungCalls),1);
    const source=fs.readFileSync(path.join(__dirname,'../dist/window-fan-card.js'),'utf8');
    assert.ok(!source.includes('remote.send_command')); assert.ok(!source.includes('decodeWatts'));
    assert.deepEqual(errors,[]);
    if(process.env.FAN_CARD_SCREENSHOT) {
      await page.evaluate(()=>{card._error=''; card._confirmOpen=false; hass.states['script.den_fan_set_state']={state:'off'}; hass.states['sensor.den_fan_state'].state='cool_high'; const a=hass.states['sensor.den_fan_control_status'].attributes; a.error='';a.blocked=false;card.hass=hass;});
      await page.locator('window-fan-card').screenshot({path:process.env.FAN_CARD_SCREENSHOT});
    }
    console.log('PASS: rendered browser controls, all nine states, recovery/confirmation, hold/resume, unavailable climate, errors, timeout, and no direct IR.');
  } finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exitCode=1;});
