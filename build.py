"""Build configurable example HA packages from the policy templates.
Uses only the Python standard library. Run from any working directory.
"""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent
DEST = ROOT/'packages'
EXAMPLES = ROOT/'examples'
EXAMPLES.mkdir(exist_ok=True)
DEST.mkdir(exist_ok=True)
MODES=['cool','exhaust','circulate']
SPEEDS=['low','med','high']
VALID=[f'{m}_{s}' for m in MODES for s in SPEEDS]
BANDS={'off_below':10,'exhaust_low_upper':32,'exhaust_med_upper':34.5,
 'exhaust_high_upper':37,'circulate_low_upper':41,'circulate_med_upper':44,
 'circulate_high_upper':46,'cool_low_upper':48,'cool_med_upper':50}
HARDWARE={
 'bedroom':dict(power='sensor.bedroom_fan_power',plug='switch.bedroom_fan_plug',
   remote='remote.bedroom_fan_remote',device='Bedroom Fan',mode_command='mode_toggle',press_delay=1,
   temperature='sensor.bedroom_temperature',humidity='sensor.bedroom_humidity'),
 'den':dict(power='sensor.den_fan_power',plug='switch.den_fan_plug',remote='remote.den_fan_remote',
   device='Den Fan',mode_command='mode_toggle',press_delay=1.5,
   temperature='sensor.den_temperature',humidity='sensor.den_humidity')}

def scalar(v):
    if isinstance(v,bool): return 'true' if v else 'false'
    if v is None: return 'null'
    return json.dumps(v,ensure_ascii=False)
def dump(v,indent=0):
    pad=' '*indent; out=[]
    if isinstance(v,dict):
        for k,x in v.items():
            if isinstance(x,(dict,list)) and x:
                out.append(f'{pad}{k}:\n{dump(x,indent+2)}')
            elif isinstance(x,str) and '\n' in x:
                out.append(f'{pad}{k}: >-\n'+'\n'.join(' '*(indent+2)+line for line in x.splitlines()))
            else: out.append(f'{pad}{k}: {scalar(x)}')
    elif isinstance(v,list):
        for x in v:
            if isinstance(x,(dict,list)):
                content=dump(x,indent+2).splitlines()
                out.append(pad+'- '+content[0].lstrip()+'\n'+'\n'.join(content[1:]))
            else: out.append(pad+'- '+scalar(x))
    return '\n'.join(out)
def action(name,entity=None,data=None,**kw):
    d={'action':name}
    if entity: d['target']={'entity_id':entity}
    if data is not None: d['data']=data
    return dict(d,**kw)
def condition(t): return {'condition':'template','value_template':t}
def iff(t,then,otherwise=None):
    d={'if':[condition(t)],'then':then}
    if otherwise: d['else']=otherwise
    return d
def variables(**kw): return {'variables':kw}
def template(expr): return '{{ '+expr+' }}'
def time_set(entity,expr): return action('input_datetime.set_datetime',entity,{'timestamp':template(expr)})
def set_bool(entity,expr): return action("{{ 'input_boolean.turn_on' if "+expr+" else 'input_boolean.turn_off' }}",entity)
def state(e): return f"states('{e}')"
def timestamp(e): return f"state_attr('{e}', 'timestamp') | float(0)"

def build(room):
    h=HARDWARE[room]; prefix=room+'_fan'; title=room.title()+' Fan'
    ent=lambda kind,key:f'{kind}.{prefix}_{key}'
    cfg=dict(h,outdoor_temperature='sensor.outdoor_temperature',outdoor_humidity='sensor.outdoor_humidity',
        power_command='',speed_command='speed_toggle',feedback_timeout=60,settle_seconds=2,
        retry_seconds=300,power_max_age=0,room_max_age=900,weather_max_age=7200,
        manual_minutes=30,minimum_mode_seconds=1200,burst_minutes=30,recovery_minutes=20)
    if room=='bedroom': cfg.update(bedtime_time='22:00:00',morning_time='06:00:00',cool_at=73,
        dry_target=60,dry_release=62,dry_resume=66,protect_on=15,protect_off=8,
        burst_at=75,burst_stop=73,extension_rh=64,stall_minutes=60,stall_margin=1,
        tv='media_player.bedtime_tv')
    else: cfg.update(cool_at=78,cool_stop=74,max_rh=70)
    booleans={'calibration_initialized':{'name':title+' Calibration Initialized'}}
    if room=='bedroom':
        for k in ['night_phase','morning_recovery','humidity_protection','dry_stalled']:
            booleans[k]={'name':title+' '+k.replace('_',' ').title()}
    datetimes={k:{'name':title+' '+k.replace('_',' ').title(),'has_date':True,'has_time':True}
               for k in ['last_command_time','command_guard_until','cycle_end','retry_after','manual_until']+(['sleep_until','last_morning','dry_best_at'] if room=='bedroom' else [])}
    numbers={prefix+'_watts_'+key:{'name':title+' Watts '+key.replace('_',' ').title(),
        'min':0,'max':500,'step':0.1,'mode':'box','unit_of_measurement':'W'} for key in BANDS}
    if room=='bedroom':
        numbers[prefix+'_dry_best_rh']={'name':title+' Dry Best Rh','min':0,'max':100,
            'step':0.1,'mode':'box','unit_of_measurement':'%'}
    selects={
         prefix+'_cycle':{'name':title+' Cycle','options':['normal','burst','extension' if room=='bedroom' else 'extended','recovery']},
         prefix+'_manual_mode':{'name':title+' Manual Mode','options':MODES},
         prefix+'_manual_speed':{'name':title+' Manual Speed','options':SPEEDS},
         prefix+'_requested_mode':{'name':title+' Requested Mode','options':MODES}}
    if room=='bedroom':
        # One explicit owner of the fan at any moment; no overlapping flags.
        selects[prefix+'_phase']={'name':title+' Phase','options':['sleep','dry','balance']}
    package={
      'input_boolean':{prefix+'_'+k:v for k,v in booleans.items()},
      'input_datetime':{prefix+'_'+k:v for k,v in datetimes.items()},
      'input_select':selects,
      'input_text':{prefix+'_'+k:{'name':title+' '+k.title(),'max':255} for k in ['reason','error']},
      'input_number':numbers}

    bound_values=', '.join(state(ent('input_number','watts_'+key))+' | float(-1)' for key in BANDS)
    decoder="""{% set raw = states('POWER') %}
{% set bounds = [BOUNDS] %}
{% set ns = namespace(valid=true) %}
{% for i in range(1, bounds | length) %}
  {% if bounds[i] <= bounds[i-1] %}{% set ns.valid = false %}{% endif %}
{% endfor %}
{% if not is_state('INIT', 'on') or not ns.valid or bounds[0] < 0 %}unknown
{% elif not is_number(raw) or raw | float < 0 %}unknown
{% elif raw | float < bounds[0] %}off
{% else %}
  {% set labels = ['exhaust_low', 'exhaust_med', 'exhaust_high', 'circulate_low', 'circulate_med', 'circulate_high', 'cool_low', 'cool_med', 'cool_high'] %}
  {% set match = namespace(value='cool_high', found=false) %}
  {% for i in range(1, bounds | length) %}
    {% if not match.found and raw | float < bounds[i] %}
      {% set match.value = labels[i-1] %}{% set match.found = true %}
    {% endif %}
  {% endfor %}
  {{ match.value }}
{% endif %}""".replace('POWER',h['power']).replace('BOUNDS',bound_values).replace('INIT',ent('input_boolean','calibration_initialized'))
    attrs={'power_sensor':h['power'],'calibration_prefix':prefix,'manual_control':True,
        'controller_script':f'script.{prefix}_set_state','status_sensor':f'sensor.{prefix}_control_status',
        'temperature_sensor':h['temperature'],'humidity_sensor':h['humidity'],
        **{key:template(state(ent('input_number','watts_'+key))+' | float(0)') for key in BANDS}}
    sensors=[{'name':title+' State','unique_id':prefix+'_state','icon':'mdi:fan','state':decoder,'attributes':attrs},
      {'name':title+' Control Status','unique_id':prefix+'_control_status','icon':'mdi:fan-auto',
       'state':template(state(ent('input_text','reason'))),
       'attributes':{'manual_until_timestamp':template(timestamp(ent('input_datetime','manual_until'))),
        'manual_active':template(timestamp(ent('input_datetime','manual_until'))+' > now().timestamp()'),
        'error':template(state(ent('input_text','error'))),
        'requested_mode':template(state(ent('input_select','requested_mode'))),
        'cycle':template(state(ent('input_select','cycle'))),
        'cycle_end':template(state(ent('input_datetime','cycle_end'))),
        'cycle_end_timestamp':template(timestamp(ent('input_datetime','cycle_end')))}}]
    if room=='bedroom':
        sensors[1]['attributes'].update(night=template("is_state('"+ent('input_boolean','night_phase')+"','on')"),
            morning_drying=template("is_state('"+ent('input_boolean','morning_recovery')+"','on')"))
    package['template']=[{'sensor':sensors}]
    if room=='bedroom':
        package['template'].append({'binary_sensor':[{'name':'Bedroom Fan Is Cool','unique_id':'bedroom_fan_is_cool',
          'availability':template("states('sensor.bedroom_fan_state') in "+repr(VALID+['off'])),
          'state':"{{ states('sensor.bedroom_fan_state').startswith('cool_') }}"}]})

    def failure(message):
        return [action('input_text.set_value',ent('input_text','error'),{'value':message}),
           time_set(ent('input_datetime','retry_after'),'now().timestamp() + cfg.retry_seconds'),
           {'stop':message,'error':True}]
    def valid_power(after=None,expected=None):
        q=f"is_number(states(cfg.power)) and states(cfg.power) | float >= 0 and states('{prefix_state}') in {VALID!r} and (cfg.power_max_age <= 0 or (now().timestamp() - as_timestamp(states[cfg.power].last_reported, 0)) <= cfg.power_max_age)"
        if after: q+=f' and as_timestamp(states[cfg.power].last_updated, 0) > {after}'
        if expected: q+=f" and states('{prefix_state}') == {expected}"
        return template(q)
    prefix_state=ent('sensor','state')
    def poll(predicate):
        # Polling also observes unchanged-value state reports (last_reported).
        return [{'repeat':{'sequence':[{'delay':{'seconds':1}}],
          'until':[condition(template('('+predicate[3:-3]+') or now().timestamp() >= feedback_deadline'))]}},
          iff(template('not ('+predicate[3:-3]+')'),failure("{{ 'Expected ' ~ (expected_state | default('running fan')) ~ '; read ' ~ states('sensor." + prefix + "_state') ~ ' at ' ~ states(cfg.power) ~ ' W. No more presses sent; check the power update and calibration.' }}"))]

    seq=[variables(cfg=cfg),
      iff(template("not is_state('"+ent('input_boolean','calibration_initialized')+"', 'on')"),[
        *[action('input_number.set_value',ent('input_number','watts_'+key),{'value':value}) for key,value in BANDS.items()],
        action('input_boolean.turn_on',ent('input_boolean','calibration_initialized')),
        {'delay':{'seconds':1}}]),
      variables(event="{{ event | default('manual' if target_function is defined or target_speed is defined else 'evaluate') }}",
         requested="{{ target_function | default('') }}",requested_speed="{{ target_speed | default('') }}",now_ts='{{ now().timestamp() }}',
         temp="{% set v = states(cfg.temperature) %}{{ (v | float * 9 / 5 + 32 if state_attr(cfg.temperature, 'unit_of_measurement') == '°C' else v | float) if is_number(v) else 0 }}",
         rh='{{ states(cfg.humidity) | float(0) }}',outside_rh='{{ states(cfg.outdoor_humidity) | float(0) }}',
         outside_temp="{% set v = states(cfg.outdoor_temperature) %}{{ (v | float * 9 / 5 + 32 if state_attr(cfg.outdoor_temperature, 'unit_of_measurement') == '°C' else v | float) if is_number(v) else 0 }}",
         cycle=template(state(ent('input_select','cycle'))),cycle_end=template(timestamp(ent('input_datetime','cycle_end'))),
         previous_mode=template(state(ent('input_select','requested_mode')))),
      variables(climate_valid="""{% set ns = namespace(ok=true) %}
{% for id in [cfg.temperature, cfg.humidity] %}
  {% set age = cfg.room_max_age %}
  {% if not is_number(states(id)) %}{% set ns.ok = false %}
  {% elif now().timestamp() - as_timestamp(states[id].last_reported, 0) > age %}{% set ns.ok = false %}{% endif %}
{% endfor %}
{{ ns.ok and 0 <= rh <= 100 and -100 < temp < 150 }}""",
         weather_valid="{{ is_number(states(cfg.outdoor_humidity)) and 0 <= outside_rh <= 100 and now().timestamp() - as_timestamp(states[cfg.outdoor_humidity].last_reported, 0) <= cfg.weather_max_age }}")]
    if room=='bedroom':
        seq.append(variables(phase=template(state(ent('input_select','phase'))),
          night=template("is_state('"+ent('input_boolean','night_phase')+"','on')"),
          morning=template("is_state('"+ent('input_boolean','morning_recovery')+"','on')"),
          protection=template("is_state('"+ent('input_boolean','humidity_protection')+"','on')"),
          stalled=template("is_state('"+ent('input_boolean','dry_stalled')+"','on')"),
          best_rh=template(state(ent('input_number','dry_best_rh'))+' | float(100)'),
          best_at=template(timestamp(ent('input_datetime','dry_best_at'))),
          tv_off_now=template("states('"+cfg['tv']+"') in ['off','standby','unavailable']"),
          sleep_end=template(timestamp(ent('input_datetime','sleep_until'))),
          morning_at=template(timestamp(ent('input_datetime','last_morning'))),clock="{{ now().strftime('%H:%M:%S') }}",
          bedtime_clock='{{ cfg.bedtime_time }}',morning_clock='{{ cfg.morning_time }}',
          event_clock="{{ as_local(as_datetime(event_at)).strftime('%H:%M:%S') if event_at is defined else clock }}",
          latest_morning="{{ as_timestamp(today_at(cfg.morning_time) if now() >= today_at(cfg.morning_time) else today_at(cfg.morning_time) - timedelta(days=1)) }}",
          next_morning="{{ as_timestamp(today_at(cfg.morning_time) if now() < today_at(cfg.morning_time) else today_at(cfg.morning_time) + timedelta(days=1)) }}"))
        # Give the external-remote observer a chance to recognize settled Cool.
        seq.append(iff("{{ event == 'evaluate' and (clock >= bedtime_clock or clock < morning_clock) and is_state('binary_sensor.bedroom_fan_is_cool','on') and (state_attr('input_datetime.bedroom_fan_last_command_time','timestamp') | float(0)) < as_timestamp(states.binary_sensor.bedroom_fan_is_cool.last_changed, 0) and now().timestamp() - as_timestamp(states.binary_sensor.bedroom_fan_is_cool.last_changed, 0) < 10 }}",[
          {'stop':'Waiting briefly for a possible manual bedtime selection.'}]))
    # Explicit selections bypass climate policy for a bounded manual hold.
    # The other axis comes from observed state, never from an assumed default.
    bedtime_event = "event in ['tv_off','observed_cool'] and (clock >= bedtime_clock or clock < morning_clock) and (event_clock >= bedtime_clock or event_clock < morning_clock)" if room=='bedroom' else 'false'
    morning_end = "event == 'evaluate' and night and (now_ts >= sleep_end or not (clock >= bedtime_clock or clock < morning_clock))" if room=='bedroom' else 'false'
    bedtime_cool = "requested == 'cool' and (clock >= bedtime_clock or clock < morning_clock)" if room=='bedroom' else 'false'
    seq.extend([
      iff("{{ event == 'manual' and (requested not in ['', 'cool', 'exhaust', 'circulate'] or requested_speed not in ['', 'low', 'med', 'high']) }}",failure('Invalid manual mode or speed.')),
      variables(manual_request="{{ event == 'manual' and (requested != '' or requested_speed != '') }}",observed_state=template(state(prefix_state))),
      iff(template("manual_request and observed_state not in "+repr(VALID)+" and (requested == '' or requested_speed == '')"),failure('Fan state unavailable; cannot preserve the other mode/speed setting. Check power and calibration.')),
      iff(template("event == 'resume_auto' or ("+bedtime_event+") or ("+morning_end+")"),[time_set(ent('input_datetime','manual_until'),'now_ts')]),
      iff('{{ manual_request }}',[
        variables(selected_mode="{{ requested if requested != '' else observed_state.split('_')[0] }}",
          selected_speed=template("requested_speed if requested_speed != '' else ('high' if ("+bedtime_cool+") else observed_state.split('_')[1])")),
        action('input_select.select_option',ent('input_select','manual_mode'),{'option':'{{ selected_mode }}'}),
        action('input_select.select_option',ent('input_select','manual_speed'),{'option':'{{ selected_speed }}'}),
        time_set(ent('input_datetime','manual_until'),'now_ts + cfg.manual_minutes * 60')]),
      variables(manual_active=template(timestamp(ent('input_datetime','manual_until'))+' > now_ts'),
        desired_speed=template(state(ent('input_select','manual_speed'))+" if "+timestamp(ent('input_datetime','manual_until'))+" > now_ts else 'high'")),
      variables(plan=(ROOT/'templates'/f'{room}_policy.jinja').read_text()),
      iff('{{ manual_active }}',[variables(plan=template("dict(plan, mode="+state(ent('input_select','manual_mode'))+", cycle='normal', end=0, reason='Manual: ' ~ "+state(ent('input_select','manual_mode'))+" ~ ' / ' ~ desired_speed ~ '; Auto resumes after hold')"))])])
    if room=='bedroom':
        seq.extend([action('input_select.select_option',ent('input_select','phase'),{'option':'{{ plan.phase }}'}),
            set_bool(ent('input_boolean','night_phase'),'plan.night'),
            set_bool(ent('input_boolean','morning_recovery'),'plan.morning'),
            set_bool(ent('input_boolean','humidity_protection'),'plan.protection'),
            set_bool(ent('input_boolean','dry_stalled'),'plan.stalled'),
            action('input_number.set_value',ent('input_number','dry_best_rh'),{'value':template('[[plan.best_rh, 0] | max, 100] | min')}),
            time_set(ent('input_datetime','dry_best_at'),'plan.best_at if plan.best_at > 0 else now_ts'),
            time_set(ent('input_datetime','sleep_until'),'plan.sleep_end if plan.sleep_end > 0 else now_ts'),
            time_set(ent('input_datetime','last_morning'),'[plan.morning_at, 1] | max')])
    seq.extend([action('input_select.select_option',ent('input_select','cycle'),{'option':'{{ plan.cycle }}'}),
       time_set(ent('input_datetime','cycle_end'),'plan.end if plan.end > 0 else now_ts'),
       action('input_text.set_value',ent('input_text','reason'),{'value':'{{ plan.reason }}'}),
       # Every queued request is evaluated anew. Throttle normal mode changes,
       # but never delay bedtime, morning start, burst/recovery transitions or manual requests.
       iff(template("event == 'evaluate' and not manual_active and plan.cycle == cycle and plan.mode != previous_mode and " +
         ("plan.phase == phase and " if room=='bedroom' else '')+
         f"now_ts - ({timestamp(ent('input_datetime','last_command_time'))}) < cfg.minimum_mode_seconds and states('{prefix_state}') == previous_mode ~ '_high'"),[
           action('input_text.set_value',ent('input_text','reason'),{'value':'Waiting for minimum mode interval; reevaluating each minute'}),
           {'stop':'Avoid rapid changes between modes.'}]),
       action('input_select.select_option',ent('input_select','requested_mode'),{'option':'{{ plan.mode }}'}),
       iff(template(f"event == 'evaluate' and now_ts < ({timestamp(ent('input_datetime','retry_after'))})"),[{'stop':'Waiting after an unconfirmed command; see controller error.'}]),
       variables(target_state="{{ plan.mode ~ '_' ~ desired_speed }}"),
       iff(template(f"states('{prefix_state}') == target_state and "+valid_power()[3:-3]),[
           action('input_text.set_value',ent('input_text','error'),{'value':''}),{'stop':'Target already confirmed; no remote presses needed.'}]),
       iff(template("not is_number(states(cfg.power)) or states(cfg.power) | float < 0 or (cfg.power_max_age > 0 and now().timestamp() - as_timestamp(states[cfg.power].last_reported, 0) > cfg.power_max_age)"),failure("{{ 'Power unavailable or expired: ' ~ cfg.power ~ ' = ' ~ states(cfg.power) ~ '. Check the plug power sensor.' }}")),
       iff(template(f"states('{prefix_state}') == 'off'"),[
          iff("{{ is_state(cfg.plug, 'off') }}",[
             action('switch.turn_on',h['plug']),{'delay':{'seconds':4}}]),
          iff(template(f"states('{prefix_state}') == 'off' and cfg.power_command != ''"),[
             action('remote.send_command',h['remote'],{'device':h['device'],'command':'{{ cfg.power_command }}'},continue_on_error=True)]),
          variables(feedback_deadline='{{ now().timestamp() + cfg.feedback_timeout }}'),*poll(valid_power())]),
       iff(template('not ('+valid_power()[3:-3]+')'),failure('Unrecognized fan state; inspect the shared calibration ranges.')),
       {'delay':{'seconds':'{{ cfg.settle_seconds }}'}},
       iff(template('not ('+valid_power()[3:-3]+')'),failure('Power feedback became invalid before sending commands.')),
       variables(current_state=template(state(prefix_state)),mode_order=MODES,speed_order=SPEEDS),
       variables(mode_presses="{{ (mode_order.index(plan.mode) - mode_order.index(current_state.split('_')[0])) % 3 }}")])

    def press_loop(axis,count):
        command=h['mode_command'] if axis=='mode' else 'speed_toggle'
        expr="mode_order[(mode_order.index(before_state.split('_')[0])+1)%3] ~ '_' ~ before_state.split('_')[1]" if axis=='mode' else "before_state.split('_')[0] ~ '_' ~ speed_order[(speed_order.index(before_state.split('_')[1])+1)%3]"
        return {'repeat':{'count':template(count),'sequence':[
          iff(template('not ('+valid_power()[3:-3]+')'),failure('Invalid power feedback before a remote press.')),
          variables(before_state=template(state(prefix_state))),variables(expected_state=template(expr),command_at='{{ now().timestamp() }}',feedback_deadline='{{ now().timestamp() + cfg.feedback_timeout }}'),
          time_set(ent('input_datetime','command_guard_until'),'now().timestamp() + cfg.feedback_timeout + cfg.settle_seconds + 10'),
          action('remote.send_command',h['remote'],{'device':h['device'],'command':command},continue_on_error=True),
          {'delay':{'seconds':'{{ cfg.press_delay }}'}},
          *poll(valid_power('command_at','expected_state')),
          {'delay':{'seconds':'{{ cfg.settle_seconds }}'}},
          iff(template('not ('+valid_power('command_at','expected_state')[3:-3]+')'),failure('Fan feedback did not settle at the expected state; stopping the sequence.'))]}}
    seq.append(press_loop('mode','mode_presses'))
    seq.extend([variables(after_mode=template(state(prefix_state))),
       iff(template(f"states('{prefix_state}').split('_')[0] != plan.mode"),failure('Mode not confirmed; speed commands were not sent.')),
       variables(speed_presses="{{ (speed_order.index(desired_speed) - speed_order.index(after_mode.split('_')[1])) % 3 }}"),
       press_loop('speed','speed_presses'),
       iff(template('not ('+valid_power(expected='target_state')[3:-3]+')'),failure('Final target was not confirmed.')),
       time_set(ent('input_datetime','command_guard_until'),'now().timestamp()'),
       time_set(ent('input_datetime','last_command_time'),'now().timestamp()'),
       action('input_text.set_value',ent('input_text','error'),{'value':''})])
    package['script']={prefix+'_set_state':{'alias':title+' - Serialized Controller','mode':'queued','max':5,'max_exceeded':'silent',
       'description':'All card and automation requests enter this queue. Automatic control uses High; manual selections hold for 30 minutes. Never turns the fan off.',
       'fields':{'event':{'name':'Request source','selector':{'select':{'options':['evaluate','manual','resume_auto','tv_off','observed_cool','bedtime_check']}}},
         'target_function':{'name':'Manual mode request','selector':{'select':{'options':MODES}}},
         'target_speed':{'name':'Manual speed request','selector':{'select':{'options':SPEEDS}}}},
       'sequence':seq}}
    primary={'alias':title+' - Continuous Control','id':prefix+'_continuous_control_v2','mode':'single','max_exceeded':'silent',
       # Routine decisions run once per minute, never on high-frequency sensor reports.
       'triggers':[{'trigger':'homeassistant','event':'start'}, {'trigger':'time_pattern','minutes':'/1'}],
       'actions':[action('script.'+prefix+'_set_state',data={'event':'evaluate'})]}
    package['automation']=[primary]
    if room=='bedroom':
        package['automation'].extend([
         # The window opening with the TV already off must also start Sleep,
         # otherwise the day policy runs all night and cycles the fan.
         {'alias':title+' - Bedtime Window Opens','id':prefix+'_bedtime_check_v2','mode':'single',
          'triggers':[{'trigger':'time','at':cfg['bedtime_time']}],
          'conditions':[condition("{{ states('"+cfg['tv']+"') in ['off','standby','unavailable'] }}")],
          'actions':[action('script.'+prefix+'_set_state',data={'event':'bedtime_check'})]},
         {'alias':title+' - TV Turned Off','id':prefix+'_tv_off_v2','mode':'single',
          'triggers':[{'trigger':'state','entity_id':cfg['tv'],'to':['off','standby','unavailable'],'for':{'seconds':10}}],
          'conditions':[condition("{{ trigger.from_state is not none and trigger.from_state.state not in ['off','standby','unknown','unavailable'] }}")],
          'actions':[action('script.bedroom_fan_set_state',data={'event':'tv_off','event_at':'{{ as_timestamp(trigger.to_state.last_changed) }}'})]},
         {'alias':title+' - Manual Remote Cool','id':prefix+'_manual_cool_v2','mode':'single',
          'triggers':[{'trigger':'state','entity_id':'binary_sensor.bedroom_fan_is_cool','from':'off','to':'on','for':{'seconds':8}}],
          'conditions':[condition("{{ is_state('script.bedroom_fan_set_state','off') and as_timestamp(trigger.to_state.last_changed, 0) > (state_attr('input_datetime.bedroom_fan_command_guard_until','timestamp') | float(0)) and as_timestamp(trigger.to_state.last_changed, 0) > (state_attr('input_datetime.bedroom_fan_last_command_time','timestamp') | float(0)) }}")],
          'actions':[action('script.bedroom_fan_set_state',data={'event':'observed_cool','event_at':'{{ as_timestamp(trigger.to_state.last_changed) }}'})]}])
    return package

for room in HARDWARE:
    package=build(room)
    header=f'''# Window Fan - {room.title()} - continuous High-speed control
# Replace the previous {room} package; do not enable both versions.
# SETTINGS: edit cfg in script.{room}_fan_set_state.sequence[0].variables.
# Calibration helpers restore their values. First run seeds EXAMPLE ranges.
# Measure all nine states before enabling control; edit via card or Helpers.
# No fan-off commands. All external entity IDs are placeholders.
# Power-command name is optional and blank until you supply a learned on/off code.
'''
    (DEST/f'window_fan_{room}.yaml').write_text(header+dump(package)+'\n',encoding='utf-8')
    (EXAMPLES/f'{room}-card.yaml').write_text(dump({'type':'custom:window-fan-card','name':room.title()+' Window Fan',
       'fan_package':f'sensor.{room}_fan_state','setup_mode':'package'})+'\n',encoding='utf-8')
print('Built both packages and both card configurations.')
