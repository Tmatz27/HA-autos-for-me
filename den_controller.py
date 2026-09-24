"""Den controller with measured, possibly overlapping ranges and one IR writer.

The CLI emits generic examples. Pass a private JSON config to build an installation.
"""
from pathlib import Path
import argparse
import json

VERSION = '1.5.0'
MODES = ['cool', 'exhaust', 'circulate']
SPEEDS = ['low', 'med', 'high']
STATES = [f'{m}_{s}' for m in MODES for s in SPEEDS]
RANGES = {'cool_low': [46,47], 'cool_med': [48,50], 'cool_high': [50,53],
          'exhaust_low': [32,33], 'exhaust_med': [34,35], 'exhaust_high': [35,38],
          'circulate_low': [39,40], 'circulate_med': [42,43], 'circulate_high': [44,46]}
DEFAULTS = dict(power='sensor.den_fan_power', plug='switch.den_fan_plug',
    remote='remote.den_fan_remote', device='Den Fan', mode_command='mode_toggle',
    speed_command='speed_toggle', power_command='', temperature='sensor.den_temperature',
    humidity='sensor.den_humidity', manual_minutes=120, cool_at=78, cool_stop=74,
    max_rh=70, burst_minutes=30, recovery_minutes=15, feedback_timeout=60,
    stable_seconds=8, off_seconds=15, off_below=10, range_tolerance=0.5, boot_state='cool_low', ranges=RANGES)

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
def txt(key, value): return a('input_text.set_value','input_text.den_fan_'+key,{'value':value})
def select(key, value): return a('input_select.select_option','input_select.den_fan_'+key,{'option':value})
def timestamp(key, expr): return a('input_datetime.set_datetime','input_datetime.den_fan_'+key,{'timestamp':t(expr)})
def stamp(key): return f"(state_attr('input_datetime.den_fan_{key}', 'timestamp') | float(0))"
def delay(seconds): return {'delay':{'seconds':seconds}}
def halt(message): return {'stop':message}
def bool_set(key, on): return a('input_boolean.turn_'+('on' if on else 'off'),'input_boolean.den_fan_'+key)

def dump(obj, indent=0):
    pad=' '*indent
    if isinstance(obj,dict):
        rows=[]
        for key,value in obj.items():
            if isinstance(value,(dict,list)) and value: rows.append(f'{pad}{key}:\n'+dump(value,indent+2))
            else: rows.append(f'{pad}{key}: '+json.dumps(value,ensure_ascii=False))
        return '\n'.join(rows)
    return '\n'.join(pad+'- '+dump(item,indent+2).lstrip() if isinstance(item,(dict,list))
                     else pad+'- '+json.dumps(item,ensure_ascii=False) for item in obj)

def build(settings=None):
    cfg={**DEFAULTS, **(settings or {})}
    assert set(cfg['ranges']) == set(STATES)
    assert all(0 <= low <= high for low,high in cfg['ranges'].values())
    assert cfg['boot_state'] in STATES
    candidates='sensor.den_fan_power_candidates'
    confirmed='input_select.den_fan_confirmed_state'
    state='sensor.den_fan_state'
    raw=f"states('{cfg['power']}')"
    ranges=json.dumps(cfg['ranges'])
    candidate_template=("{% set p = states('"+cfg['power']+"') %}"
        "{% if not is_number(p) or p | float < 0 %}unknown"
        "{% elif p | float < "+str(cfg['off_below'])+" %}off{% else %}"
        "{% set ranges = "+ranges+" %}{% set ns = namespace(matches=[]) %}"
        "{% for name, bounds in ranges.items() %}"
        "{% if bounds[0] - "+str(cfg['range_tolerance'])+" <= p | float <= bounds[1] + "+str(cfg['range_tolerance'])+" %}{% set ns.matches = ns.matches + [name] %}{% endif %}"
        "{% endfor %}{{ ns.matches | join('|') if ns.matches else 'unknown' }}{% endif %}")
    state_template=("{% set seen = states('"+candidates+"').split('|') %}"
        "{% set known = states('"+confirmed+"') %}"
        "{{ known if known in seen and known != 'unknown' else 'unknown' }}")
    attributes={
        'power_sensor':cfg['power'], 'calibration_prefix':'den_fan', 'manual_control':t('true'),
        'controller_script':'script.den_fan_set_state','status_sensor':'sensor.den_fan_control_status',
        'temperature_sensor':cfg['temperature'],'humidity_sensor':cfg['humidity'],
        'calibration_kind':'ranges','calibration_ranges':t(ranges), 'controller_version':VERSION,
        'range_tolerance':t(str(cfg['range_tolerance'])),
        'confirm_script':'script.den_fan_confirm_state',
        'confidence':t("'unconfirmed' if is_state('sensor.den_fan_state','unknown') else ('tracked' if '|' in states('sensor.den_fan_power_candidates') else 'measured')")}
    # Fixed range values are centralized in cfg and emitted consistently into all templates.
    sensor=[dict(name='Den Fan Power Candidates', unique_id='den_fan_power_candidates',
                 state=candidate_template),
            dict(name='Den Fan State',unique_id='den_fan_state',icon='mdi:fan',state=state_template,attributes=attributes),
            dict(name='Den Fan Control Status',unique_id='den_fan_control_status',icon='mdi:fan-auto',
                 state=("{% if "+stamp('manual_until')+" > now().timestamp() %}Manual hold"
                        "{% elif states('input_text.den_fan_reason').startswith('Manual') %}Manual hold ended; awaiting Auto evaluation"
                        "{% else %}{{ states('input_text.den_fan_reason') }}{% endif %}"),
                 attributes={'manual_until_timestamp':t(stamp('manual_until')),
                    'manual_active':t(stamp('manual_until')+' > now().timestamp()'),
                    'error':t("states('input_text.den_fan_error')"),
                    'requested_mode':t("states('input_select.den_fan_requested_mode')"),
                    'requested_speed':t("states('input_select.den_fan_requested_speed')"),
                    'cycle':t("states('input_select.den_fan_cycle')"),
                    'cycle_end_timestamp':t(stamp('cycle_end')),
                    'blocked':t("is_state('input_boolean.den_fan_command_fault','on')"),
                    'controller_version':VERSION})]
    package={'input_boolean':{f'den_fan_{k}':{'name':'Den Fan '+name} for k,name in
                 [('command_fault','Command Fault'),('boot_pending','Startup Pending')]},
       'input_select':{
         'den_fan_confirmed_state':{'name':'Den Fan Confirmed State','options':['unknown','off']+STATES},
         'den_fan_cycle':{'name':'Den Fan Cycle','options':['normal','burst','extended','recovery']},
         **{f'den_fan_{key}':{'name':'Den Fan '+key.replace('_',' ').title(),'options':options}
            for key,options in [('requested_mode',MODES),('requested_speed',SPEEDS),('manual_mode',MODES),('manual_speed',SPEEDS)]}},
       'input_datetime':{f'den_fan_{key}':{'name':'Den Fan '+key.replace('_',' ').title(),'has_date':True,'has_time':True}
           for key in ['manual_until','cycle_end','command_guard_until','last_command_time']},
       'input_text':{f'den_fan_{key}':{'name':'Den Fan '+key.title(),'max':255} for key in ['reason','error']},
       'template':[{'sensor':sensor}]}
    if cfg.get('led_device'):
        package['template'].append({'switch':[{'name':'Den LED Strip','unique_id':'den_led_strip',
            'turn_on':[a('remote.send_command',cfg['remote'],{'device':cfg['led_device'],'command':'on'})],
            'turn_off':[a('remote.send_command',cfg['remote'],{'device':cfg['led_device'],'command':'off'})]}]})

    def fail(message):
        return [bool_set('command_fault',True), select('confirmed_state','unknown'), txt('error',message), halt(message)]
    def wait_for(expr, message):
        return [{'repeat':{'sequence':[delay(1)],'until':[c('('+expr+') or now().timestamp() >= deadline')]}},
                iff('not ('+expr+')',fail(message))]
    def compatible(label):
        return f"is_number(states(cfg.power)) and {label} in cfg.ranges and cfg.ranges[{label}][0] - cfg.range_tolerance <= states(cfg.power) | float <= cfg.ranges[{label}][1] + cfg.range_tolerance"
    def settled():
        return f"now().timestamp() - as_timestamp(states['{candidates}'].last_changed, 0) >= cfg.stable_seconds"

    # This script is the only place that sends remote commands. It never switches the plug off.
    driver=[v(cfg=cfg),
        iff("operation | default('apply') == 'power_on'",[
            iff(f"states('{candidates}') == 'off' and now().timestamp() - as_timestamp(states['{candidates}'].last_changed,0) >= cfg.off_seconds",[
                iff("is_state(cfg.plug,'off')",[a('switch.turn_on',cfg['plug'])],
                    [iff("cfg.power_command != ''",[a('remote.send_command',cfg['remote'],{'device':cfg['device'],'command':t('cfg.power_command')})])])]),
            halt('Power-on recovery requested; waiting for the startup reference.')]),
        v(target="{{ target_function ~ '_' ~ target_speed }}"),
        iff('target not in cfg.ranges',fail('Invalid requested fan setting.')),
        v(current=t(f"states('{confirmed}')")),
        iff('not ('+compatible('current')+')',fail('Current fan setting is uncertain. Confirm the physical setting before sending toggles.')),
        iff('current == target',[bool_set('command_fault',False),txt('error',''),halt('Already at requested setting; no commands sent.')]),
        v(mode_order=MODES,speed_order=SPEEDS),
        v(mode_presses="{{ (mode_order.index(target_function) - mode_order.index(current.split('_')[0])) % 3 }}")]
    for axis in ['mode','speed']:
        if axis == 'speed':
            driver += [v(current=t(f"states('{confirmed}')")),
                       v(speed_presses="{{ (speed_order.index(target_speed) - speed_order.index(current.split('_')[1])) % 3 }}")]
        expected=("mode_order[(mode_order.index(before.split('_')[0])+1)%3] ~ '_' ~ before.split('_')[1]" if axis=='mode'
                  else "before.split('_')[0] ~ '_' ~ speed_order[(speed_order.index(before.split('_')[1])+1)%3]")
        evidence=compatible('expected')+' and not ('+compatible('before')+") and as_timestamp(states[cfg.power].last_updated,0) > sent_at and "+settled()
        driver.append({'alias':'Confirm each '+axis+' press', 'repeat':{'count':t(axis+'_presses'),'sequence':[
            v(before=t(f"states('{confirmed}')")),
            iff('not ('+compatible('before')+')',fail('Power no longer supports the last confirmed setting. No further presses sent.')),
            v(expected=t(expected),sent_at=t('now().timestamp()'),deadline=t('now().timestamp() + cfg.feedback_timeout')),
            timestamp('command_guard_until','deadline + cfg.stable_seconds + 5'),
            # Do not suppress service errors: the coordinator has already latched a fault before entering this driver.
            a('remote.send_command',cfg['remote'],{'device':cfg['device'],'command':cfg[axis+'_command']}),
            *wait_for(evidence,"{{ ('Unconfirmed ' ~ expected ~ ': ' ~ states(cfg.power) ~ ' W. Automatic retries paused; confirm the fan setting.')[:255] }}"),
            select('confirmed_state',t('expected'))]}})
    driver += [iff('not ('+compatible('target')+')',fail('Final setting is not supported by current power.')),
               timestamp('last_command_time','now().timestamp()'),timestamp('command_guard_until','now().timestamp()+cfg.stable_seconds+2'),
               txt('error','')]
    # A persisted fault is set before driver entry. A runtime error or interrupted
    # sequence leaves it set. Only fully verified success clears it.
    driver += [bool_set('command_fault',False)]

    common_fields={'event':{'selector':{'select':{'options':['evaluate','observe','startup','manual','resume_auto','synchronize']}}},
                   'target_function':{'selector':{'select':{'options':MODES}}},
                   'target_speed':{'selector':{'select':{'options':SPEEDS}}}}
    coordinator=[v(cfg=cfg), v(event="{{ event | default('evaluate') }}",requested="{{ target_function | default('') }}",
        requested_speed="{{ target_speed | default('') }}",now_ts=t('now().timestamp()'),boot_recovered=t('false')),
        iff("event == 'manual' and (requested not in ['', 'cool','exhaust','circulate'] or requested_speed not in ['', 'low','med','high'] or (requested == '' and requested_speed == ''))",[halt('Invalid manual request.')]),
        # Take manual ownership before any sensor reconciliation or hardware work.
        iff("event in ['manual','synchronize']",[
            timestamp('manual_until','now_ts + cfg.manual_minutes * 60'),select('cycle','normal'),timestamp('cycle_end','now_ts'),
            txt('reason','Manual hold')]),
        iff("event == 'resume_auto'",[timestamp('manual_until','now_ts'),select('cycle','normal'),timestamp('cycle_end','now_ts')]),
        # Never trust restored state alone after HA was offline; physical changes may have happened.
        iff("event == 'startup'",[select('confirmed_state','unknown')]),
        v(known=t(f"states('{confirmed}')"), seen=t(f"states('{candidates}').split('|')"),
          stable=t(settled()),was_blocked=t("is_state('input_boolean.den_fan_command_fault','on')")),
        iff("seen == ['off']",[
            iff(f"now_ts - as_timestamp(states['{candidates}'].last_changed,0) >= cfg.off_seconds",[
                bool_set('boot_pending',True),select('confirmed_state','off'),
                a('script.den_fan_apply_state',data={'operation':'power_on'})]),
            txt('reason','Fan off; waiting for startup at Cool/Low'),halt('Waiting for fan startup.')]),
        iff("is_state('input_boolean.den_fan_boot_pending','on')",[
            iff('stable and ('+compatible('cfg.boot_state')+')',[
                select('confirmed_state',t('cfg.boot_state')),bool_set('boot_pending',False),bool_set('command_fault',False),txt('error',''),
                v(known=t('cfg.boot_state'),was_blocked=t('false'),boot_recovered=t('true'))],
                [halt('Waiting for measured startup at Cool/Low.')])]),
        iff("event == 'synchronize'",[
            v(chosen="{{ requested ~ '_' ~ requested_speed }}"),
            iff('not ('+compatible('chosen')+')',[txt('error','Physical selection does not match the measured range.'),halt('Synchronization rejected.')]),
            select('confirmed_state',t('chosen')),select('manual_mode',t('requested')),select('manual_speed',t('requested_speed')),
            bool_set('command_fault',False),txt('error',''),halt('Physical setting confirmed; manual hold active. No remote commands sent.')]),
        # Compatible overlap retains history. Incompatible measurements must settle before reacquisition.
        iff('not ('+compatible('known')+')',[
            iff("stable and seen | length == 1 and seen[0] in cfg.ranges",[
                select('confirmed_state',t('seen[0]')),
                iff("known in cfg.ranges and not was_blocked and now_ts > "+stamp('command_guard_until')+" and event not in ['manual','resume_auto','startup']",[
                    select('manual_mode',t("seen[0].split('_')[0]")),select('manual_speed',t("seen[0].split('_')[1]")),
                    timestamp('manual_until','now_ts + cfg.manual_minutes*60'),select('cycle','normal'),timestamp('cycle_end','now_ts'),
                    txt('reason','Manual hold: external fan change')]),
                v(known=t('seen[0]'))],
                [txt('error','Fan state uncertain. Wait for a distinct reading or confirm the physical setting.'),halt('No toggle commands sent.')])]),
        iff("event in ['manual','resume_auto']",[bool_set('command_fault',False),txt('error','')]),
        iff("is_state('input_boolean.den_fan_command_fault','on')",[halt('Previous command failed. Automatic retries remain paused.')]),
        iff("event == 'manual' or (boot_recovered and "+stamp('manual_until')+" > now_ts)",[
            iff("event == 'manual'",[
                select('manual_mode',t("requested if requested else known.split('_')[0]")),
                select('manual_speed',t("requested_speed if requested_speed else known.split('_')[1]"))]),
            v(desired_mode=t("states('input_select.den_fan_manual_mode')"),desired_speed=t("states('input_select.den_fan_manual_speed')"))],
            [iff(stamp('manual_until')+' > now_ts',[halt('Manual hold: automatic output suspended.')]),
             iff("event == 'observe' and not boot_recovered",[halt('Observed state updated; climate evaluation runs once per minute.')]),
             v(temp="{% set n=states(cfg.temperature) %}{{ (n | float * 9/5+32 if state_attr(cfg.temperature,'unit_of_measurement') == '°C' else n | float) if is_number(n) else none }}",
               rh="{{ states(cfg.humidity) | float(none) }}",cycle=t("states('input_select.den_fan_cycle')"),cycle_end=t(stamp('cycle_end'))),
             iff('temp is none or rh is none or not (-100 < temp < 150 and 0 <= rh <= 100)',[
                 txt('reason','Climate unavailable; keeping current fan setting'),halt('No climate decision with invalid data.')]),
             v(plan=POLICY),select('cycle',t('plan.cycle')),timestamp('cycle_end','plan.end'),txt('reason',t('plan.reason')),
             v(desired_mode=t('plan.mode'),desired_speed='high')]),
        select('requested_mode',t('desired_mode')),select('requested_speed',t('desired_speed')),
        iff("known == desired_mode ~ '_' ~ desired_speed",[txt('error',''),halt('Requested setting already confirmed; no hardware actions.')]),
        bool_set('command_fault',True),txt('error','Command in progress; if interrupted, confirm the fan setting before retrying.'),
        a('script.den_fan_apply_state',data={'target_function':t('desired_mode'),'target_speed':t('desired_speed')})]
    # Only the driver owns output, including power-on recovery.
    package['script']={
      'den_fan_set_state':{'alias':'Den Fan - Serialized Controller','mode':'queued','max':10,'max_exceeded':'silent',
                          'trace':{'stored_traces':20},'fields':common_fields,'sequence':coordinator},
      'den_fan_apply_state':{'alias':'Den Fan - Apply Confirmed State','mode':'single','trace':{'stored_traces':20},
                            'fields':{k:common_fields[k] for k in ['target_function','target_speed']},'sequence':driver},
      'den_fan_confirm_state':{'alias':'Den Fan - Confirm Physical Setting','mode':'queued',
        'description':'Select the setting verified on the physical fan. Sends no remote commands; starts a manual hold.',
        'fields':{'setting':{'required':True,'selector':{'select':{'options':STATES}}}},
        'sequence':[iff('setting not in '+repr(STATES),[halt('Invalid setting.')]),
           a('script.den_fan_set_state',data={'event':'synchronize','target_function':t("setting.split('_')[0]"),'target_speed':t("setting.split('_')[1]")})]}}
    package['automation']=[{
      'id':'den_fan_continuous_control_v2','alias':'Den Fan - Continuous Control','mode':'queued','max':3,'max_exceeded':'silent',
      'trace':{'stored_traces':20},
      'triggers':[{'trigger':'time_pattern','minutes':'/1','id':'evaluate'},
                  {'trigger':'homeassistant','event':'start','id':'startup'},
                  {'trigger':'state','entity_id':candidates,'for':{'seconds':cfg['off_seconds']},'id':'observe'}],
      'actions':[a('script.den_fan_set_state',data={'event':t("trigger.id | default('evaluate')")})]}]
    return package

POLICY="""{% set p=namespace(mode='exhaust',cycle=cycle,end=cycle_end,reason='Exhaust: continuous ventilation') %}
{% if p.cycle in ['burst','extended'] %}
  {% if temp <= cfg.cool_stop or (p.cycle == 'extended' and rh > cfg.max_rh) %}
    {% set p.cycle='recovery' %}{% set p.end=now_ts+cfg.recovery_minutes*60 %}
  {% elif now_ts >= p.end %}
    {% if rh <= cfg.max_rh %}{% set p.cycle='extended' %}{% set p.end=now_ts+cfg.burst_minutes*60 %}
    {% else %}{% set p.cycle='recovery' %}{% set p.end=now_ts+cfg.recovery_minutes*60 %}{% endif %}
  {% endif %}
{% endif %}
{% if p.cycle == 'recovery' and now_ts >= p.end %}{% set p.cycle='normal' %}{% set p.end=0 %}{% endif %}
{% if p.cycle in ['burst','extended'] %}{% set p.mode='cool' %}{% set p.reason='Cooling: heat relief' %}
{% elif p.cycle == 'recovery' %}{% set p.reason='Exhaust: recovery interval' %}
{% elif temp >= cfg.cool_at %}{% set p.mode='cool' %}{% set p.cycle='burst' %}{% set p.end=now_ts+cfg.burst_minutes*60 %}{% set p.reason='Cooling: room at temperature limit' %}
{% endif %}
{{ dict(mode=p.mode,cycle=p.cycle,end=p.end,reason=p.reason) }}"""

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',type=Path)
    parser.add_argument('--output',type=Path,default=Path('window_fan_den.yaml'))
    args=parser.parse_args()
    package=build(json.loads(args.config.read_text(encoding='utf-8')) if args.config else None)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text('# Den window fan controller '+VERSION+'\n# Replace the old den package; never install both.\n'+dump(package)+'\n',encoding='utf-8')
