"""State-first den package. Only den_fan_executor owns physical output.

Climate policy below is frozen from v1.6.0. Public defaults are examples.
Installation-specific JSON belongs outside the repository.
"""
from pathlib import Path
import argparse
import json
import math
import re

VERSION = '1.7.0'
MODES = ['cool', 'exhaust', 'circulate']
SPEEDS = ['low', 'med', 'high']
STATES = [f'{m}_{s}' for m in MODES for s in SPEEDS]
RANGES = {'cool_low': [46,47], 'cool_med': [48,50], 'cool_high': [50,53],
          'exhaust_low': [32,33], 'exhaust_med': [34,35], 'exhaust_high': [35,38],
          'circulate_low': [39,40], 'circulate_med': [42,43], 'circulate_high': [44,46]}
DEFAULTS = dict(power='sensor.example_fan_power', plug='switch.example_fan_plug',
    remote='remote.example_remote', device='EXAMPLE_FAN', mode_command='EXAMPLE_MODE',
    speed_command='EXAMPLE_SPEED', power_on_command='EXAMPLE_ON', power_off_command='EXAMPLE_OFF',
    temperature='sensor.example_temperature', humidity='sensor.example_humidity',
    manual_minutes=120, cool_at=70, cool_stop=68, max_rh=65, heat_at=78, heat_stop=75,
    burst_minutes=30, recovery_minutes=10, rapid_rise_points=8,
    off_seconds=15, plug_delay=3, startup_delay=8, command_delay=3,
    feedback_timeout=30, power_stale_seconds=120, off_below=10, range_tolerance=0.5,
    auto_recovery=False, ranges=RANGES, led_device='', led_on_command='on', led_off_command='off')
CLIMATE_KEYS = ('cool_at','cool_stop','max_rh','heat_at','heat_stop','burst_minutes',
                'recovery_minutes','rapid_rise_points')

def t(s): return '{{ ' + s + ' }}'
def v(**kw): return {'variables':kw}
def a(service, entity=None, data=None):
    result={'action':service}
    if entity: result['target']={'entity_id':entity}
    if data is not None: result['data']=data
    return result
def c(expr): return {'condition':'template','value_template':t(expr)}
def iff(expr, yes, no=None):
    result={'if':[c(expr)],'then':yes}
    if no is not None: result['else']=no
    return result
def txt(key,value): return a('input_text.set_value','input_text.den_fan_'+key,{'value':value})
def select(key,value): return a('input_select.select_option','input_select.den_fan_'+key,{'option':value})
def timestamp(key,expr): return a('input_datetime.set_datetime','input_datetime.den_fan_'+key,{'timestamp':t(expr)})
def stamp(key): return f"(state_attr('input_datetime.den_fan_{key}', 'timestamp') | float(0))"
def delay(seconds): return {'delay':{'seconds':seconds}}
def halt(message): return {'stop':message}
def bool_set(key,on): return a('input_boolean.turn_'+('on' if on else 'off'),'input_boolean.den_fan_'+key)

def dump(obj,indent=0):
    pad=' '*indent
    if isinstance(obj,dict):
        rows=[]
        for key,value in obj.items():
            if isinstance(value,(dict,list)) and value: rows.append(f'{pad}{key}:\n'+dump(value,indent+2))
            else: rows.append(f'{pad}{key}: '+json.dumps(value,ensure_ascii=False))
        return '\n'.join(rows)
    return '\n'.join(pad+'- '+dump(item,indent+2).lstrip() if isinstance(item,(dict,list))
                     else pad+'- '+json.dumps(item,ensure_ascii=False) for item in obj)

def validate(settings,private=False):
    unknown=set(settings)-set(DEFAULTS)
    if unknown: raise ValueError('Unknown settings: '+', '.join(sorted(unknown)))
    cfg={**DEFAULTS,**settings}
    for key in CLIMATE_KEYS:
        if cfg[key] != DEFAULTS[key]: raise ValueError('v1.6.0 climate setting is frozen: '+key)
    for key,domain in [('power','sensor'),('plug','switch'),('remote','remote'),('temperature','sensor'),('humidity','sensor')]:
        if not isinstance(cfg[key],str) or not re.fullmatch(domain+r'\.[a-z0-9_]+',cfg[key]): raise ValueError('Invalid entity: '+key)
    for key in ['device','mode_command','speed_command','power_on_command','power_off_command']:
        if not isinstance(cfg[key],str) or not cfg[key].strip(): raise ValueError('Required learned name: '+key)
    if not isinstance(cfg['led_device'],str): raise ValueError('led_device must be a string')
    if cfg['led_device']:
        for key in ['led_on_command','led_off_command']:
            if not isinstance(cfg[key],str) or not cfg[key].strip(): raise ValueError('Required learned name: '+key)
    for key in ['manual_minutes','off_seconds','plug_delay','startup_delay','command_delay','feedback_timeout','power_stale_seconds','off_below','range_tolerance']:
        value=cfg[key]
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value <= 0:
            raise ValueError('Expected positive finite setting: '+key)
    if cfg['manual_minutes'] > 1440: raise ValueError('manual_minutes must be at most 1440')
    if type(cfg['auto_recovery']) is not bool: raise ValueError('auto_recovery must be a boolean')
    if set(cfg['ranges']) != set(STATES): raise ValueError('Supply all nine wattage bands')
    for bounds in cfg['ranges'].values():
        if len(bounds)!=2 or any(not isinstance(x,(int,float)) or not math.isfinite(x) for x in bounds) or not 0<=bounds[0]<=bounds[1]:
            raise ValueError('Invalid wattage band')
    if private:
        required=['power','plug','remote','device','mode_command','speed_command','power_on_command',
                  'power_off_command','temperature','humidity','off_seconds','plug_delay','startup_delay',
                  'command_delay','off_below','ranges','auto_recovery','manual_minutes']
        missing=[k for k in required if k not in settings or 'example' in str(settings[k]).lower()]
        if missing: raise ValueError('Private build requires confirmed values: '+', '.join(missing))
    return cfg

def build(settings=None):
    cfg=validate(settings or {})
    known="states('input_select.den_fan_confirmed_state')"
    confidence="states('input_select.den_fan_confidence')"
    active="is_state('script.den_fan_executor','on')"
    interrupted="is_state('input_boolean.den_fan_command_in_progress','on') and not "+active
    manual=stamp('manual_until')+' > now().timestamp()'
    # Supporting evidence never substitutes another setting for command history.
    candidates=("{% set p=states('"+cfg['power']+"') %}{% if not is_number(p) or p|float < 0 %}unknown"
        "{% elif p|float < "+str(cfg['off_below'])+" %}off{% else %}{% set ranges="+json.dumps(cfg['ranges'])+" %}"
        "{% set ns=namespace(matches=[]) %}{% for name,b in ranges.items() %}"
        "{% if b[0]-"+str(cfg['range_tolerance'])+" <= p|float <= b[1]+"+str(cfg['range_tolerance'])+" %}"
        "{% set ns.matches=ns.matches+[name] %}{% endif %}{% endfor %}{{ ns.matches|join('|') if ns.matches else 'unknown' }}{% endif %}")
    fresh="is_number(states(cfg.power)) and states(cfg.power)|float >= 0 and now().timestamp()-as_timestamp(states[cfg.power].last_reported,0) <= cfg.power_stale_seconds"
    compatible="expected in cfg.ranges and cfg.ranges[expected][0]-cfg.range_tolerance <= states(cfg.power)|float <= cfg.ranges[expected][1]+cfg.range_tolerance"
    evidence=("{% set cfg="+repr(cfg)+" %}"
        "{% set expected="+known+" %}{% if not ("+fresh+") %}Power unavailable or stale; command history retained"
        "{% elif states(cfg.power)|float < cfg.off_below %}Fan appears stopped; recover or confirm physical state"
        "{% elif not ("+compatible+") %}Power conflicts with expected setting; inspect fan or recover"
        "{% elif '|' in states('sensor.den_fan_power_candidates') %}Overlapping power bands; expected setting retained"
        "{% else %}Power corroborates expected setting; IR delivery is not independently proven{% endif %}")
    status_attrs={
        'manual_until_timestamp':t(stamp('manual_until')),'manual_active':t(manual),
        'command_active':t(active),'blocked':t("is_state('input_boolean.den_fan_command_fault','on') or "+interrupted),
        'error':t("'Command interrupted or service failed. Confirm physical state or Recover. Last step: ' ~ states('input_text.den_fan_error') if "+interrupted+" else states('input_text.den_fan_error')"),
        'confidence':t("'uncertain' if "+interrupted+" else "+confidence),
        'expected_state':t(known),'running':t("is_state('input_boolean.den_fan_running','on')"),
        'evidence':evidence,'last_outcome':t("states('input_text.den_fan_outcome')"),
        'recovery':t("'failed' if "+interrupted+" and is_state('input_select.den_fan_recovery','in_progress') else states('input_select.den_fan_recovery')"),
        'requested_mode':t("states('input_select.den_fan_requested_mode')"),
        'requested_speed':t("states('input_select.den_fan_requested_speed')"),
        'cycle':t("states('input_select.den_fan_cycle')"),'cycle_end_timestamp':t(stamp('cycle_end')),
        'humidity_restart_limit':HUMIDITY_LIMIT.replace('TEMP_ENTITY',cfg['temperature']),
        'humidity_rise_10m':t("states('"+cfg['humidity']+"')|float - states('sensor.den_fan_humidity_min_10m')|float if is_number(states('"+cfg['humidity']+"')) and is_number(states('sensor.den_fan_humidity_min_10m')) else none"),
        'controller_version':VERSION}
    sensors=[{'name':'Den Fan Humidity Sample','unique_id':'den_fan_humidity_sample',
        'device_class':'humidity','unit_of_measurement':'%',
        'availability':t("is_number(states('"+cfg['humidity']+"')) and 0 <= states('"+cfg['humidity']+"')|float <= 100"),
        'state':t("states('"+cfg['humidity']+"')|float(none)"),'attributes':{'sampled_at':t('now().isoformat()')}},
        {'name':'Den Fan Power Candidates','unique_id':'den_fan_power_candidates','state':candidates},
        {'name':'Den Fan State','unique_id':'den_fan_state','icon':'mdi:fan',
         'state':t(known), 'attributes':{'power_sensor':cfg['power'],'calibration_prefix':'den_fan',
            'manual_control':t('true'),'controller_script':'script.den_fan_set_state',
            'status_sensor':'sensor.den_fan_control_status','temperature_sensor':cfg['temperature'],
            'humidity_sensor':cfg['humidity'],'controller_version':VERSION,
            'confidence':status_attrs['confidence']}},
        {'name':'Den Fan Control Status','unique_id':'den_fan_control_status','icon':'mdi:fan-auto',
         'state':t("'Applying setting' if "+active+" else 'Manual hold' if "+manual+" else 'Auto paused: recovery required' if is_state('input_boolean.den_fan_command_fault','on') or "+interrupted+" else states('input_text.den_fan_reason')"),
         'attributes':status_attrs}]
    package={
        'input_boolean':{f'den_fan_{key}':{'name':'Den Fan '+label} for key,label in [
            ('command_fault','Command Fault'),('command_in_progress','Command In Progress'),
            ('running','Believed Running'),('auto_recovery_used','Automatic Recovery Used')]},
        'input_select':{
            # Keep the v1.6 entity ID so existing restored history survives the upgrade.
            'den_fan_confirmed_state':{'name':'Den Fan Expected State','options':['unknown','off']+STATES},
            'den_fan_confidence':{'name':'Den Fan Confidence','options':['uncertain','inferred','established']},
            'den_fan_recovery':{'name':'Den Fan Recovery','options':['idle','in_progress','complete','failed']},
            'den_fan_cycle':{'name':'Den Fan Cycle','options':['normal','burst','extended','recovery','cooling','heat_relief']},
            **{f'den_fan_{key}':{'name':'Den Fan '+key.replace('_',' ').title(),'options':options}
                for key,options in [('requested_mode',MODES),('requested_speed',SPEEDS),('manual_mode',MODES),('manual_speed',SPEEDS)]}},
        'input_datetime':{f'den_fan_{key}':{'name':'Den Fan '+key.replace('_',' ').title(),'has_date':True,'has_time':True}
            for key in ['manual_until','cycle_end','last_command_time']},
        'input_text':{f'den_fan_{key}':{'name':'Den Fan '+key.title(),'max':255} for key in ['reason','error','outcome']},
        'template':[{'sensor':sensors}],
        'sensor':[{'platform':'statistics','name':'Den Fan Humidity Min 10m','unique_id':'den_fan_humidity_min_10m',
            'entity_id':'sensor.den_fan_humidity_sample','state_characteristic':'value_min','max_age':{'minutes':10},'sampling_size':600}]}

    def fail(message):
        return [select('confidence','uncertain'),bool_set('command_fault',True),txt('error',message),
            txt('outcome','Stopped safely; physical reference required'),
            iff("is_state('input_select.den_fan_recovery','in_progress')",[select('recovery','failed')]),
            bool_set('command_in_progress',False),halt(message)]
    def wait_for(expr,message):
        return [v(deadline=t('now().timestamp()+cfg.feedback_timeout')),
            {'repeat':{'sequence':[delay(1)],'until':[c('('+expr+') or now().timestamp() >= deadline')]}},
            iff('not ('+expr+')',fail(message))]
    def guard():
        return [iff("not is_state(cfg.plug,'on')",[bool_set('running',False),*fail('Plug is not on. Recover after power is restored.')]),
            iff('('+fresh+') and states(cfg.power)|float < cfg.off_below',[
                bool_set('running',False),*fail('Fan appears stopped. Recover before sending toggles.')])]
    def preempt():
        return [iff("event not in ['manual','recover','synchronize'] and "+stamp('manual_until')+" > now().timestamp()",[
            bool_set('command_in_progress',False),txt('error',''),txt('outcome','Auto yielded to manual request'),halt('Manual request takes priority.')])]

    # Parallel admission accepts manual ownership immediately, even while Auto is
    # waiting on feedback. The queued executor owns ALL helpers describing state
    # and ALL plug/IR actions. No script.turn_on fire-and-forget hardware calls.
    events=['evaluate','observe','startup','power_lost','manual','resume_auto','recover','synchronize','led_on','led_off']
    fields={'event':{'selector':{'select':{'options':events}}},
        'target_function':{'selector':{'select':{'options':MODES}}},'target_speed':{'selector':{'select':{'options':SPEEDS}}}}
    admission=[v(cfg=cfg),v(event=t("event|default('evaluate')"),
        requested=t("target_function|default('')"),requested_speed=t("target_speed|default('')")),
        iff('event not in '+repr(events),[halt('Invalid event.')]),
        iff("requested not in ['', 'cool','exhaust','circulate'] or requested_speed not in ['', 'low','med','high']",[halt('Invalid setting.')]),
        iff("event == 'manual' and requested == '' and requested_speed == ''",[halt('Select a mode or speed.')]),
        iff("event == 'synchronize' and (requested == '' or requested_speed == '')",[halt('Select both physical axes.')]),
        iff("event in ['manual','synchronize','recover']",[
            timestamp('manual_until','now().timestamp()+cfg.manual_minutes*60')]),
        {**a('script.den_fan_executor',data={'event':t('event'),'target_function':t('requested'),'target_speed':t('requested_speed')}),'continue_on_error':True}]

    executor=[v(cfg=cfg),v(event=t("event|default('evaluate')"),requested=t("target_function|default('')"),
        requested_speed=t("target_speed|default('')"),now_ts=t('now().timestamp()')),
        # Room LED controls use the same transmitter queue but do not change
        # fan history, faults, climate decisions or the fan's manual hold.
        iff("event in ['led_on','led_off']",[
            iff("cfg.led_device == ''",[halt('LED control is not configured.')]),
            a('remote.send_command',cfg['remote'],{'device':cfg['led_device'],
                'command':t("cfg.led_on_command if event == 'led_on' else cfg.led_off_command"),'num_repeats':1}),
            delay(cfg['command_delay']),halt('Room LED command sent; physical receipt is not confirmed.')]),
        # A persisted intent is set before each side effect. A service exception
        # or restart cannot silently authorize another sequence of toggles.
        iff("is_state('input_boolean.den_fan_command_in_progress','on')",[
            select('confidence','uncertain'),bool_set('command_fault',True),
            txt('error','Previous command interrupted or failed. Confirm physical state or Recover.'),
            txt('outcome','Previous sequence incomplete'),bool_set('command_in_progress',False),
            iff("is_state('input_select.den_fan_recovery','in_progress')",[select('recovery','failed')])]),
        iff("event == 'startup'",[
            iff(known+" in "+repr(STATES)+" and not is_state('input_boolean.den_fan_command_fault','on')",[select('confidence','inferred')])]),
        iff("event == 'synchronize'",[
            select('confirmed_state',t("requested ~ '_' ~ requested_speed")),select('confidence','established'),bool_set('running',True),
            select('manual_mode',t('requested')),select('manual_speed',t('requested_speed')),
            select('requested_mode',t('requested')),select('requested_speed',t('requested_speed')),
            select('cycle','normal'),timestamp('cycle_end','now_ts'),bool_set('command_fault',False),
            bool_set('auto_recovery_used',False),select('recovery','idle'),txt('reason','Manual hold: physical setting confirmed'),
            v(expected=t("requested ~ '_' ~ requested_speed")),
            txt('error',t("'Physical setting accepted; wattage disagrees or is unavailable. Check evidence before the next change.' if not (("+fresh+') and ('+compatible+")) else ''")),
            txt('outcome','Physical setting accepted without IR commands'),halt('Physical state confirmed.')]),
        # Plug-off events delivered after an intentional recovery must not undo
        # the newly established reference. Current state is authoritative here.
        iff("event == 'power_lost' and is_state(cfg.plug,'on')",[halt('Old plug-off event; power already restored.')]),
        iff("event == 'resume_auto'",[timestamp('manual_until','now_ts'),select('cycle','normal'),timestamp('cycle_end','now_ts')]),
        iff("not is_state(cfg.plug,'on') or (("+fresh+") and states(cfg.power)|float < cfg.off_below)",[
            bool_set('running',False),select('confidence','uncertain'),bool_set('command_fault',True),
            txt('error','Fan power lost or fan stopped. Recover / Reinitialize before further toggles.')]),
        *preempt(),
        v(known=t(known)),
        iff("event == 'manual'",[
            # Keep an unspecified axis from established history, never defaults.
            iff("known not in cfg.ranges and (requested == '' or requested_speed == '')",fail('Unknown starting state. Confirm both axes or Recover before a one-axis request.')),
            v(desired_mode=t("requested if requested else known.split('_')[0]"),
              desired_speed=t("requested_speed if requested_speed else known.split('_')[1]")),
            select('manual_mode',t('desired_mode')),select('manual_speed',t('desired_speed')),
            select('cycle','normal'),timestamp('cycle_end','now_ts'),txt('reason','Manual hold')],
            [iff(stamp('manual_until')+" > now_ts",[
                iff("event != 'recover'",[halt('Manual hold: automatic output suspended.')]),
                v(desired_mode=t("states('input_select.den_fan_manual_mode')"),desired_speed=t("states('input_select.den_fan_manual_speed')"))],
                [iff("event == 'observe'",[halt('Evidence updated; policy evaluates once per minute.')]),
                 v(temp="{% set n=states(cfg.temperature) %}{{ (n | float * 9/5+32 if state_attr(cfg.temperature,'unit_of_measurement') == '°C' else n | float) if is_number(n) else none }}",
                   rh="{{ states(cfg.humidity) | float(none) }}",cycle=t("states('input_select.den_fan_cycle')"),cycle_end=t(stamp('cycle_end')),
                   rh_min="{{ states('sensor.den_fan_humidity_min_10m') | float(none) }}"),
                 iff('temp is none or not (-100 < temp < 150) or ((rh is none or not (0 <= rh <= 100)) and not (temp >= cfg.heat_at or (cycle == "heat_relief" and temp > cfg.heat_stop)))',[
                     txt('reason','Climate unavailable; keeping current fan setting'),halt('No climate decision with invalid data.')]),
                 v(plan=POLICY),select('cycle',t('plan.cycle')),timestamp('cycle_end','plan.end'),txt('reason',t('plan.reason')),
                 v(desired_mode=t('plan.mode'),desired_speed='high')])]),
        # Explicit recovery may supply a full destination, otherwise use the last
        # manual selection (or last requested state, seeded Cool/Low on install).
        iff("event == 'recover'",[
            v(desired_mode=t("requested if requested else states('input_select.den_fan_requested_mode')"),
              desired_speed=t("requested_speed if requested_speed else states('input_select.den_fan_requested_speed')")),
            select('manual_mode',t('desired_mode')),select('manual_speed',t('desired_speed')),
            txt('reason','Manual hold: recovery requested')]),
        select('requested_mode',t('desired_mode')),select('requested_speed',t('desired_speed')),
        v(needs_reference=t("known not in cfg.ranges or is_state('input_select.den_fan_confidence','uncertain') or is_state('input_boolean.den_fan_command_fault','on')")),
        iff("event == 'recover' or (needs_reference and cfg.auto_recovery and not is_state('input_boolean.den_fan_auto_recovery_used','on') and event not in ['manual','observe','power_lost'])",[
            bool_set('auto_recovery_used',True),bool_set('command_in_progress',True),bool_set('command_fault',True),
            select('recovery','in_progress'),select('confidence','uncertain'),bool_set('running',False),
            txt('error','Recovery step: cutting plug power. If interrupted, run Recover manually.'),
            v(off_at=t('now().timestamp()')),
            a('switch.turn_off',cfg['plug']),
            *wait_for("is_state(cfg.plug,'off')",'Recovery failed: plug did not report OFF.'),
            delay(cfg['off_seconds']),
            *wait_for('('+fresh+') and states(cfg.power)|float < cfg.off_below and as_timestamp(states[cfg.power].last_reported,0) >= off_at',
                'Recovery failed: no fresh stopped-power reading while plug OFF. No Power On sent.'),
            txt('error','Recovery step: restoring plug power.'),a('switch.turn_on',cfg['plug']),
            *wait_for("is_state(cfg.plug,'on')",'Recovery failed: plug did not report ON.'),delay(cfg['plug_delay']),
            txt('error','Recovery step: sending Power On; waiting for fresh running wattage.'),v(sent_at=t('now().timestamp()')),
            a('remote.send_command',cfg['remote'],{'device':cfg['device'],'command':cfg['power_on_command'],'num_repeats':1}),
            delay(cfg['startup_delay']),
            *wait_for('('+fresh+') and states(cfg.power)|float >= cfg.off_below and as_timestamp(states[cfg.power].last_reported,0) > sent_at',
                'Recovery failed: Power On produced no fresh running evidence. Inspect plug, fan and BroadLink.'),
            select('confirmed_state','cool_low'),select('confidence','established'),bool_set('running',True),
            bool_set('command_fault',False),v(known='cool_low'),
            txt('outcome','Cool/Low reference established after power reset')],
            [iff('needs_reference',fail('State uncertain. Confirm Physical State or Recover / Reinitialize; no toggles sent.'))]),
        *guard(),
        v(expected=t(known)),
        # Fresh conflicting evidence blocks toggles without erasing history.
        iff('('+fresh+") and not ("+compatible+") and not is_state('input_select.den_fan_confidence','established')",
            fail('Power conflicts with expected state. Confirm physical setting or Recover; history retained.')),
        v(mode_order=MODES,speed_order=SPEEDS),
        v(mode_presses=t("(mode_order.index(desired_mode)-mode_order.index(known.split('_')[0]))%3"),
          speed_presses=t("(speed_order.index(desired_speed)-speed_order.index(known.split('_')[1]))%3"))]
    for axis in ['mode','speed']:
        next_state=("mode_order[(mode_order.index(before.split('_')[0])+1)%3] ~ '_' ~ before.split('_')[1]" if axis=='mode'
            else "before.split('_')[0] ~ '_' ~ speed_order[(speed_order.index(before.split('_')[1])+1)%3]")
        executor.append({'repeat':{'count':t(axis+'_presses'),'sequence':[
            *preempt(),*guard(),
            v(before=t(known)),v(expected=t(next_state)),
            bool_set('command_in_progress',True),select('confidence','inferred'),
            txt('error',t("'Sending "+axis+" press toward ' ~ expected ~ '. If interrupted, confirm state or Recover.'")),
            v(sent_at=t('now().timestamp()')),
            a('remote.send_command',cfg['remote'],{'device':cfg['device'],'command':cfg[axis+'_command'],'num_repeats':1}),
            # Record expected state only after the service call returns; never
            # call this independent physical confirmation.
            select('confirmed_state',t('expected')),timestamp('last_command_time','now().timestamp()'),
            delay(cfg['command_delay']),
            # Give delayed reports the full bounded window to become compatible.
            # Overlap and identical *fresh* readings are acceptable corroboration.
            v(deadline=t('now().timestamp()+cfg.feedback_timeout')),
            {'repeat':{'sequence':[delay(1)],'until':[c('now().timestamp() >= deadline or (('+fresh+') and ('+compatible+') and as_timestamp(states[cfg.power].last_reported,0) > sent_at)')]}},
            *guard(),
            iff('('+fresh+') and as_timestamp(states[cfg.power].last_reported,0) > sent_at and not ('+compatible+')',
                fail('Wattage contradicts the last press after timeout. Sequence stopped; confirm or Recover.')),
            txt('outcome',t("'Expected ' ~ expected ~ '; power corroborates, delivery unproven' if ("+fresh+') and ('+compatible+") and as_timestamp(states[cfg.power].last_reported,0) > sent_at else 'Expected ' ~ expected ~ '; fresh power unavailable, delivery unproven'")),
            bool_set('command_in_progress',False)]}})
    executor += [bool_set('command_in_progress',False),bool_set('command_fault',False),txt('error',''),
        iff("is_state('input_select.den_fan_recovery','in_progress')",[select('recovery','complete')]),
        iff("event == 'recover'",[bool_set('auto_recovery_used',False)]),
        txt('outcome',t("'Expected ' ~ states('input_select.den_fan_confirmed_state') ~ '; ' ~ states('input_select.den_fan_confidence') ~ '. See wattage evidence; IR receipt is unproven.'"))]
    package['script']={
        'den_fan_set_state':{'alias':'Den Fan - Request','mode':'parallel','max':20,'fields':fields,'sequence':admission},
        'den_fan_executor':{'alias':'Den Fan - Serialized Hardware Executor','mode':'queued','max':20,
            'trace':{'stored_traces':20},'fields':fields,'sequence':executor},
        'den_fan_confirm_state':{'alias':'Den Fan - Confirm Physical State','mode':'parallel','max':10,
            'fields':{'setting':{'required':True,'selector':{'select':{'options':STATES}}}},
            'sequence':[iff('setting not in '+repr(STATES),[halt('Invalid physical setting.')]),
                a('script.den_fan_set_state',data={'event':'synchronize','target_function':t("setting.split('_')[0]"),'target_speed':t("setting.split('_')[1]")})]}}
    package['automation']=[{'id':'den_fan_continuous_control_v2','alias':'Den Fan - Continuous Control',
        'mode':'parallel','max':5,'trace':{'stored_traces':20},
        'triggers':[{'trigger':'time_pattern','minutes':'/1','id':'evaluate'},
            {'trigger':'homeassistant','event':'start','id':'startup'},
            {'trigger':'state','entity_id':[cfg['temperature'],cfg['humidity']],'id':'observe'},
            {'trigger':'time','at':'input_datetime.den_fan_manual_until','id':'evaluate'},
            {'trigger':'state','entity_id':cfg['plug'],'to':'off','id':'power_lost'},
            {'trigger':'state','entity_id':cfg['power'],'to':None,'id':'observe'}],
        'actions':[a('script.den_fan_set_state',data={'event':t("trigger.id|default('evaluate')")})]}]
    if cfg['led_device']:
        # Retain the existing name/unique ID so existing LED dashboard controls
        # continue to use the same switch when the room package is replaced.
        package['template'].append({'switch':[{'name':'Den LED Strip','unique_id':'den_led_strip',
            'turn_on':[a('script.den_fan_set_state',data={'event':'led_on'})],
            'turn_off':[a('script.den_fan_set_state',data={'event':'led_off'})]}]})
    return package

HUMIDITY_LIMIT="""{% set n=states('TEMP_ENTITY') %}
{% if is_number(n) %}
{% set temp=n | float * 9/5+32 if state_attr('TEMP_ENTITY','unit_of_measurement') == '°C' else n | float %}
{{ (58 if temp <= 72 else 58+(temp-72) if temp <= 76 else 62+(temp-76)*1.5 if temp < 78 else 65) | round(1) }}
{% else %}{{ none }}{% endif %}"""

POLICY="""{% set p=namespace(mode='exhaust',cycle=cycle,end=cycle_end,reason='Exhaust: building a humidity buffer') %}
{% set limit=58 if temp <= 72 else 58+(temp-72) if temp <= 76 else 62+(temp-76)*1.5 if temp < 78 else 65 %}
{% set rapid=rh is not none and rh_min is not none and rh-rh_min > cfg.rapid_rise_points %}
{% if temp >= cfg.heat_at or (cycle == 'heat_relief' and temp > cfg.heat_stop) %}
  {% set p.mode='cool' %}{% set p.cycle='heat_relief' %}{% set p.reason='Cooling: heat priority until ' ~ cfg.heat_stop ~ '°F; humidity limits suspended' %}
  {% if cycle != 'heat_relief' or now_ts >= p.end %}{% set p.end=now_ts+cfg.burst_minutes*60 %}{% endif %}
{% else %}
  {% if cycle in ['burst','extended','heat_relief'] %}{% set p.cycle='cooling' %}{% endif %}
  {% if p.cycle == 'cooling' %}
    {% if temp <= cfg.cool_stop or rh >= cfg.max_rh or rapid %}
      {% set p.cycle='recovery' %}{% set p.end=now_ts+cfg.recovery_minutes*60 %}
    {% else %}
      {% set p.mode='cool' %}{% set p.reason='Cooling: working toward ' ~ cfg.cool_stop ~ '°F' %}
      {% if now_ts >= p.end %}{% set p.end=now_ts+cfg.burst_minutes*60 %}{% endif %}
    {% endif %}
  {% endif %}
  {% if p.mode == 'exhaust' %}
    {% if p.cycle == 'recovery' and now_ts >= p.end %}{% set p.cycle='normal' %}{% set p.end=0 %}{% endif %}
    {% if p.cycle == 'recovery' %}{% set p.reason='Exhaust: drying; minimum recovery interval' %}
    {% elif temp >= cfg.cool_at and rh <= limit and not rapid %}
      {% set p.mode='cool' %}{% set p.cycle='cooling' %}{% set p.end=now_ts+cfg.burst_minutes*60 %}
      {% set p.reason='Cooling: humidity buffer available' %}
    {% elif temp >= cfg.cool_at %}{% set p.reason='Exhaust: drying toward ' ~ (limit | round(1)) ~ '% RH before cooling' %}
    {% endif %}
  {% endif %}
{% endif %}
{{ dict(mode=p.mode,cycle=p.cycle,end=p.end,reason=p.reason) }}"""


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,help='Private confirmed installation JSON; never commit it')
    parser.add_argument('--output',type=Path,default=Path('window_fan_den.yaml'))
    args=parser.parse_args()
    settings=json.loads(args.config.read_text(encoding='utf-8')) if args.config else {}
    validate(settings,private=bool(args.config))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    label='PRIVATE INSTALLATION' if args.config else 'GENERIC EXAMPLE - NOT INSTALLATION READY'
    args.output.write_text('# Den fan '+VERSION+' - '+label+'\n# Replace the old package; never install both.\n'+dump(build(settings))+'\n',encoding='utf-8',newline='\n')
