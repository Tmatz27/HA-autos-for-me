"""Scenario tests against the Jinja decisions and actual generated YAML script.
Requires PyYAML and Jinja2. Run: python tests/test_control.py
"""
import ast
from copy import deepcopy
from datetime import datetime, timedelta
import math
from pathlib import Path
import sys
import unittest
from zoneinfo import ZoneInfo
import yaml
from jinja2 import StrictUndefined
from jinja2.nativetypes import NativeEnvironment

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import build
TZ=ZoneInfo('UTC')
def dt(s): return datetime.fromisoformat(s).replace(tzinfo=TZ)
def number(v):
    try: return math.isfinite(float(v))
    except (ValueError,TypeError): return False
def ts(v,default=0):
    try: return v.timestamp() if isinstance(v,datetime) else float(v)
    except (ValueError,TypeError,AttributeError): return default
def native(v):
    if not isinstance(v,str): return v
    v=v.strip()
    try: return ast.literal_eval(v)
    except (ValueError,SyntaxError): return v

class State:
    def __init__(self,value='unknown',attrs=None,when=None):
        self.state=str(value); self.attributes=attrs or {}
        self.last_changed=self.last_updated=self.last_reported=when or dt('2025-01-01T12:00:00')
class Domain:
    def __init__(self,store,domain): self.store,self.domain=store,domain
    def __getattr__(self,key): return self.store[self.domain+'.'+key]
class States:
    def __init__(self): self.data={}
    def __call__(self,key): return self[key].state
    def __getitem__(self,key): return self.data.get(key,State())
    def __getattr__(self,key): return Domain(self,key)

class Halt(Exception):
    def __init__(self,message,error=False): self.error=error; super().__init__(message)

class Harness:
    """Small script executor with independent motor physics and delayed reports."""
    def __init__(self,room,when='2025-01-01T12:00:00',mode='exhaust',speed='high'):
        self.room=room; self.prefix=room+'_fan'; self.package=yaml.safe_load((ROOT/'packages'/f'window_fan_{room}.yaml').read_text(encoding='utf-8'))
        self.script=self.package['script'][self.prefix+'_set_state']
        self.cfg=self.script['sequence'][0]['variables']['cfg']
        self.now=dt(when); self.states=States(); self.mode=mode; self.speed=speed
        self.calls=[]; self.pending=[]; self.report_delay=2; self.miss=False; self.reporting=True; self.boot=True
        self.motor_watts={'exhaust_low':31,'exhaust_med':33,'exhaust_high':36,'circulate_low':39,
          'circulate_med':43,'circulate_high':45,'cool_low':47,'cool_med':49,'cool_high':51}
        self.env=NativeEnvironment(undefined=StrictUndefined)
        self.env.globals.update(states=self.states,is_number=number,now=lambda:self.now,
          state_attr=lambda e,a:self.states[e].attributes.get(a),is_state=lambda e,s:self.states(e)==s,
          as_timestamp=ts,timedelta=timedelta,today_at=lambda t:datetime.combine(self.now.date(),datetime.strptime(t,'%H:%M:%S').time(),TZ),
          as_datetime=lambda v:datetime.fromtimestamp(float(v),TZ),as_local=lambda v:v.astimezone(TZ))
        for kind in ['input_boolean','input_datetime','input_number','input_text','input_select']:
            for key,spec in self.package.get(kind,{}).items():
                value={'input_boolean':'off','input_datetime':'unknown','input_number':0,'input_text':''}.get(kind)
                if kind=='input_select': value=spec['options'][0]
                self.put(kind+'.'+key,value)
        for entity,value,attrs in [(self.cfg['power'],self.motor_watts[mode+'_'+speed],{'unit_of_measurement':'W'}),
          (self.cfg['plug'],'on',{}),(self.cfg['temperature'],74,{'unit_of_measurement':'°F'}),
          (self.cfg['humidity'],65,{'unit_of_measurement':'%'}),(self.cfg['outdoor_temperature'],60,{'unit_of_measurement':'°F'}),
          (self.cfg['outdoor_humidity'],92,{'unit_of_measurement':'%'})]: self.put(entity,value,attrs)
        self.put('script.'+self.prefix+'_set_state','off')
        self.refresh()
    def put(self,key,value,attrs=None):
        old=self.states[key]; item=State(value,attrs if attrs is not None else old.attributes,self.now)
        if item.state==old.state: item.last_changed=old.last_changed
        self.states.data[key]=item
    def render(self,v,ctx=None):
        ctx=ctx or {}
        if isinstance(v,dict): return {k:self.render(x,ctx) for k,x in v.items()}
        if isinstance(v,list): return [self.render(x,ctx) for x in v]
        if isinstance(v,str) and ('{{' in v or '{%' in v): return native(self.env.from_string(v).render(**ctx))
        return v
    def refresh(self):
        for sensor in self.package['template'][0]['sensor']:
            entity='sensor.'+sensor['unique_id']
            self.put(entity,self.render(sensor['state']),self.render(sensor.get('attributes',{})))
        for block in self.package['template']:
            for sensor in block.get('binary_sensor',[]):
                available=self.render(sensor.get('availability',True))
                self.put('binary_sensor.'+sensor['unique_id'],('on' if self.render(sensor['state']) else 'off') if available else 'unavailable')
    def advance(self,seconds):
        target=self.now+timedelta(seconds=seconds)
        self.now=target
        due=[x for x in self.pending if x[0]<=target]
        self.pending=[x for x in self.pending if x[0]>target]
        for _,value in due: self.put(self.cfg['power'],value)
        if self.reporting:
            for key in ['power','temperature','humidity','outdoor_temperature','outdoor_humidity']:
                self.states[self.cfg[key]].last_reported=self.now
        self.refresh()
    def sensor(self,key,value): self.put(self.cfg[key],value); self.refresh()
    def helper(self,kind,key,value): self.put(kind+'.'+self.prefix+'_'+key,value); self.refresh()
    def execute(self,items,ctx):
        for item in items:
            if 'variables' in item:
                for k,v in item['variables'].items(): ctx[k]=self.render(v,ctx)
            elif 'if' in item:
                branch='then' if all(self.render(c['value_template'],ctx) for c in item['if']) else 'else'
                self.execute(item.get(branch,[]),ctx)
            elif 'delay' in item:
                delay=self.render(item['delay'],ctx)
                self.advance(float(delay.get('seconds',0))+float(delay.get('minutes',0))*60)
            elif 'repeat' in item:
                spec=item['repeat']; count=int(self.render(spec.get('count',500),ctx))
                for i in range(count):
                    self.execute(spec['sequence'],ctx)
                    if 'until' in spec and all(self.render(c['value_template'],ctx) for c in spec['until']): break
                else:
                    if 'until' in spec: raise AssertionError('Unbounded feedback loop')
            elif 'stop' in item: raise Halt(self.render(item['stop'],ctx),item.get('error',False))
            elif 'action' in item:
                name=self.render(item['action'],ctx); data=self.render(item.get('data',{}),ctx)
                entity=item.get('target',{}).get('entity_id'); self.calls.append((name,entity,data))
                if name.startswith('input_boolean.'):
                    self.put(entity,'on' if name.endswith('turn_on') else 'off')
                elif name=='input_number.set_value': self.put(entity,data['value'])
                elif name=='input_select.select_option': self.put(entity,data['option'])
                elif name=='input_text.set_value': self.put(entity,data['value'])
                elif name=='input_datetime.set_datetime':
                    t=float(data['timestamp']); self.put(entity,datetime.fromtimestamp(t,TZ).strftime('%Y-%m-%d %H:%M:%S'),{'timestamp':t})
                elif name=='remote.send_command':
                    if not self.miss:
                        if data['command']==self.cfg['mode_command']: self.mode=build.MODES[(build.MODES.index(self.mode)+1)%3]
                        elif data['command']=='speed_toggle': self.speed=build.SPEEDS[(build.SPEEDS.index(self.speed)+1)%3]
                        else: raise AssertionError('Unexpected command')
                        self.pending.append((self.now+timedelta(seconds=self.report_delay),self.motor_watts[self.mode+'_'+self.speed]))
                elif name=='switch.turn_on':
                    self.put(entity,'on')
                    if self.boot:
                        self.mode,self.speed='cool','low'; self.pending.append((self.now+timedelta(seconds=2),47))
                else: raise AssertionError('Unexpected action: '+str(name))
                self.refresh()
            else: raise AssertionError('Unhandled script action: '+str(item))
    def run(self,**fields):
        self.put('script.'+self.prefix+'_set_state','on')
        try: self.execute(self.script['sequence'],dict(fields)); self.halt=None
        except Halt as e: self.halt=e
        finally: self.put('script.'+self.prefix+'_set_state','off')
        return self
    @property
    def remote_calls(self): return [c for c in self.calls if c[0]=='remote.send_command']
    @property
    def error(self): return self.states('input_text.'+self.prefix+'_error')

def auto(h, key):
    """Find an automation by id fragment so inserting one cannot break tests."""
    for a in h.package['automation']:
        if key in a['id']: return a
    raise KeyError(key)

class Tests(unittest.TestCase):
    def policy(self,room='bedroom',**overrides):
        h=Harness(room)
        ctx=dict(cfg=h.cfg,event='evaluate',requested='',now_ts=100000,clock='12:00:00',event_clock='12:00:00',
            bedtime_clock='22:00:00',morning_clock='06:00:00',latest_morning=90000,next_morning=176400,
            morning_at=90000,night=False,morning=False,protection=False,sleep_end=0,cycle='normal',cycle_end=0,
            climate_valid=True,weather_valid=True,temp=72,rh=60,outside_temp=60,outside_rh=63,previous_mode='exhaust',
            phase='balance',best_rh=100,best_at=100000,stalled=False,tv_off_now=False)
        # The phase is the single owner; keep the legacy flags consistent with it.
        if overrides.get('night'): overrides.setdefault('phase','sleep')
        if overrides.get('morning'): overrides.setdefault('phase','dry')
        ctx.update(overrides)
        source=next(x['variables']['plan'] for x in h.script['sequence'] if 'plan' in x.get('variables',{}))
        return h.render(source,ctx)
    def test_01_window_opening_with_tv_off_starts_sleep(self):
        # A plain evaluation must not start Sleep on its own...
        self.assertFalse(self.policy(clock='22:00:00',event_clock='22:00:00')['night'])
        # ...but the bedtime check finding the TV already off must, otherwise the
        # day policy runs all night and cycles the fan.
        p=self.policy(event='bedtime_check',tv_off_now=True,clock='22:00:00',event_clock='22:00:00')
        self.assertTrue(p['night']); self.assertEqual(p['mode'],'cool'); self.assertEqual(p['phase'],'sleep')
        self.assertFalse(self.policy(event='bedtime_check',tv_off_now=False,clock='22:00:00')['night'])
    def test_02_actual_bedtime_events(self):
        for event in ['tv_off','observed_cool','manual']:
            p=self.policy(event=event,requested='cool',clock='22:30:00',event_clock='22:30:00',rh=85,outside_rh=96)
            self.assertTrue(p['night']); self.assertEqual(p['mode'],'cool'); self.assertFalse(p['morning'])
        self.assertFalse(self.policy(event='tv_off',clock='22:00:05',event_clock='21:59:55')['night'])
    def test_03_sleep_has_absolute_climate_priority(self):
        for valid in [True,False]:
            p=self.policy(clock='03:00:00',event_clock='03:00:00',night=True,sleep_end=176400,climate_valid=valid,rh=99,temp=50,outside_temp=80)
            self.assertEqual(p['mode'],'cool')
    def test_04_morning_and_restart_catchup(self):
        p=self.policy(clock='06:00:00',night=True,sleep_end=99999,morning_at=0,temp=72,rh=80)
        self.assertFalse(p['night']); self.assertTrue(p['morning']); self.assertEqual(p['mode'],'exhaust')
        self.assertFalse(self.policy(morning=True,temp=72,rh=60)['morning'])
        self.assertFalse(self.policy(morning=True,temp=74,rh=62)['morning'])
        self.assertTrue(self.policy(morning=True,temp=73,rh=62)['morning'])
        self.assertTrue(self.policy(morning=True,temp=74,rh=62.1)['morning'])
    def test_05_day_humidity_and_temperature(self):
        self.assertEqual(self.policy(temp=73,rh=62)['mode'],'cool')
        self.assertEqual(self.policy(temp=69,rh=62,previous_mode='cool')['mode'],'cool')
        self.assertEqual(self.policy(temp=74,rh=62.1)['mode'],'exhaust')
        self.assertEqual(self.policy(temp=74,outside_temp=78)['mode'],'cool')
    def test_06_humidity_protection_hysteresis(self):
        self.assertTrue(self.policy(rh=60,outside_rh=75)['protection'])
        self.assertTrue(self.policy(protection=True,rh=60,outside_rh=68)['protection'])
        self.assertFalse(self.policy(protection=True,rh=60,outside_rh=67.9)['protection'])
        self.assertEqual(self.policy(temp=75,outside_rh=96)['mode'],'exhaust')
        self.assertEqual(self.policy(temp=75.1,outside_rh=96)['cycle'],'burst')
    def test_07_bedroom_burst_extension_and_recovery(self):
        p=self.policy(cycle='burst',cycle_end=99999,temp=76,rh=63,outside_rh=96)
        self.assertEqual(p['cycle'],'extension'); self.assertEqual(p['end'],101800)
        for rh in [64,80]: self.assertEqual(self.policy(cycle='burst',cycle_end=99999,temp=76,rh=rh)['cycle'],'recovery')
        self.assertEqual(self.policy(cycle='extension',cycle_end=99999,temp=76,rh=60)['cycle'],'recovery')
        self.assertEqual(self.policy(cycle='extension',cycle_end=100900,temp=76,rh=64)['cycle'],'recovery')
        self.assertEqual(self.policy(cycle='burst',cycle_end=100900,temp=73,rh=60)['cycle'],'recovery')
        self.assertEqual(self.policy(cycle='recovery',cycle_end=100001,temp=80,rh=80)['mode'],'exhaust')
        self.assertEqual(self.policy(cycle='recovery',cycle_end=100000,temp=80,rh=80)['cycle'],'burst')
    def test_08_den_limits_and_extension(self):
        self.assertEqual(self.policy('den',temp=77.9)['mode'],'exhaust')
        self.assertEqual(self.policy('den',temp=78,rh=80)['cycle'],'burst')
        for temp in [76,78,81]:
            p=self.policy('den',temp=temp,rh=70,cycle='burst',cycle_end=100000)
            self.assertEqual(p['cycle'],'extended')
        self.assertEqual(self.policy('den',temp=79,rh=70.1,cycle='burst',cycle_end=100000)['cycle'],'recovery')
        self.assertEqual(self.policy('den',temp=79,rh=71,cycle='extended',cycle_end=100900)['cycle'],'recovery')
        self.assertEqual(self.policy('den',temp=74,cycle='burst',cycle_end=100900)['cycle'],'recovery')
    def test_09_sensor_failures_default_exhaust(self):
        for room in ['bedroom','den']:
            self.assertEqual(self.policy(room,climate_valid=False,cycle='burst',cycle_end=101800)['mode'],'exhaust')
    def test_10_yaml_and_jinja_parse_and_no_fan_off(self):
        for room in ['bedroom','den']:
            h=Harness(room)
            def walk(v):
                if isinstance(v,dict):
                    self.assertNotEqual(v.get('action'),'switch.turn_off')
                    for x in v.values(): walk(x)
                elif isinstance(v,list):
                    for x in v: walk(x)
                elif isinstance(v,str) and ('{{' in v or '{%' in v): h.env.parse(v)
            walk(h.package)
            self.assertEqual(h.script['mode'],'queued')
            self.assertNotIn('off',h.script['fields']['target_function']['selector']['select']['options'])
    def test_28_routine_evaluation_is_bounded(self):
        for room in ['bedroom','den']:
            h=Harness(room)
            triggers=h.package['automation'][0]['triggers']
            self.assertEqual(triggers,[{'trigger':'homeassistant','event':'start'},
                {'trigger':'time_pattern','minutes':'/1'}])
            self.assertEqual(h.package['automation'][0]['mode'],'single')
            h.run(); previous=len(h.remote_calls)
            for _ in range(5):
                h.advance(60); h.run()
            self.assertEqual(len(h.remote_calls),previous)
        h=Harness('bedroom')
        self.assertEqual(auto(h,'continuous_control')['triggers'][1]['trigger'],'time_pattern')
        self.assertEqual(auto(h,'manual_cool')['triggers'][0]['trigger'],'state')

    def test_11_actual_driver_all_running_states(self):
        for room in ['bedroom','den']:
            for mode in build.MODES:
                for speed in build.SPEEDS:
                    for desired in ['cool','exhaust']:
                        with self.subTest(room=room,mode=mode,speed=speed,desired=desired):
                            h=Harness(room,when='2025-01-01T23:00:00' if room=='bedroom' else '2025-01-01T12:00:00',mode=mode,speed=speed)
                            if desired=='cool':
                                h.sensor('temperature',79)
                                h.run(event='manual',target_function='cool',target_speed='high')
                            else:
                                h.sensor('temperature',72); h.run(event='manual',target_function='exhaust',target_speed='high')
                            self.assertEqual(h.error,''); self.assertEqual((h.mode,h.speed),(desired,'high'))
                            expected=(build.MODES.index(desired)-build.MODES.index(mode))%3+(2-build.SPEEDS.index(speed))%3
                            self.assertEqual(len(h.remote_calls),expected)
    def test_12_missed_press_stops_and_rate_limits(self):
        h=Harness('den',mode='cool',speed='low'); h.sensor('temperature',72); h.miss=True; h.run()
        self.assertEqual(len(h.remote_calls),1); self.assertTrue(h.error)
        h.advance(60); h.run(); self.assertEqual(len(h.remote_calls),1)
        h.miss=False; h.advance(301); h.run(); self.assertEqual(h.error,''); self.assertEqual((h.mode,h.speed),('exhaust','high'))
    def test_13_missing_power_no_remote_presses(self):
        for value in ['unavailable','unknown','NaN',-1]:
            h=Harness('den'); h.sensor('power',value); h.run()
            self.assertTrue(h.error); self.assertEqual(len(h.remote_calls),0)
    def test_14_delayed_power_report(self):
        h=Harness('den',mode='cool',speed='low'); h.sensor('temperature',72); h.report_delay=12; h.run()
        self.assertEqual(h.error,''); self.assertEqual((h.mode,h.speed),('exhaust','high'))
    def test_15_power_restore_and_off_while_plug_on(self):
        h=Harness('den'); h.sensor('power',0); h.put(h.cfg['plug'],'off'); h.run()
        self.assertEqual(h.error,''); self.assertEqual((h.mode,h.speed),('exhaust','high'))
        h=Harness('den'); h.sensor('power',0); h.run()
        self.assertTrue(h.error); self.assertEqual(len(h.remote_calls),0)
    def test_16_calibration_restores_and_matches_source_ranges(self):
        h=Harness('den'); h.run()
        points={0:'off',9.9:'off',10:'exhaust_low',31.99:'exhaust_low',32:'exhaust_med',34.5:'exhaust_high',
            37:'circulate_low',41:'circulate_med',44:'circulate_high',46:'cool_low',48:'cool_med',50:'cool_high',51:'cool_high'}
        for w,s in points.items(): h.sensor('power',w); self.assertEqual(h.states('sensor.den_fan_state'),s)
        h.helper('input_number','watts_circulate_low_upper',40.5); h.run()
        self.assertEqual(h.states('input_number.den_fan_watts_circulate_low_upper'),'40.5')
        h.helper('input_number','watts_circulate_low_upper',20)
        self.assertEqual(h.states('sensor.den_fan_state'),'unknown')
    def test_17_temperature_units(self):
        h=Harness('den'); h.put(h.cfg['temperature'],26,{'unit_of_measurement':'°C'}); h.run()
        self.assertEqual(h.states('input_select.den_fan_requested_mode'),'cool')
    def test_18_actual_sleep_to_morning_resume(self):
        h=Harness('bedroom',when='2025-01-01T23:00:00'); h.run(event='manual',target_function='cool')
        self.assertEqual(h.states('input_boolean.bedroom_fan_night_phase'),'on')
        h.advance(7*3600); h.run()
        self.assertEqual(h.states('input_boolean.bedroom_fan_night_phase'),'off')
        self.assertEqual(h.states('input_boolean.bedroom_fan_morning_recovery'),'on')
        self.assertEqual((h.mode,h.speed),('exhaust','high'))
    def test_19_actual_den_expiry_without_sensor_change(self):
        h=Harness('den'); h.sensor('temperature',79); h.sensor('humidity',71); h.run()
        self.assertEqual(h.states('input_select.den_fan_cycle'),'burst')
        h.advance(1800); h.run()
        self.assertEqual(h.states('input_select.den_fan_cycle'),'recovery'); self.assertEqual(h.mode,'exhaust')
    def test_20_tv_and_remote_attribution(self):
        h=Harness('bedroom')
        tv=auto(h,'tv_off')['conditions'][0]['value_template']
        for prior,wanted in [('on',True),('off',False),('standby',False),('unavailable',False),('unknown',False)]:
            self.assertEqual(h.render(tv,{'trigger':{'from_state':State(prior)}}),wanted)
        h.run(); h.helper('input_select','requested_mode','exhaust')
        observer=auto(h,'manual_cool')['conditions'][0]['value_template']
        trigger={'from_state':State('off'),'to_state':State('on',when=h.now+timedelta(seconds=20))}
        self.assertTrue(h.render(observer,{'trigger':trigger}))
        # A completed automation sequence records a timestamp after its own mode transition.
        h.put('input_datetime.bedroom_fan_last_command_time','done',{'timestamp':h.now.timestamp()+30})
        self.assertFalse(h.render(observer,{'trigger':trigger}))
    def test_21_weather_temperature_is_context_not_a_veto(self):
        for room in ['bedroom','den']:
            h=Harness(room,when='2025-01-01T23:00:00')
            h.sensor('temperature',79); h.sensor('outdoor_temperature',85); h.run(event='manual',target_function='cool')
            self.assertEqual(h.mode,'cool'); self.assertEqual(h.error,'')
        h=Harness('den'); h.sensor('temperature',79); h.sensor('outdoor_temperature','unavailable'); h.sensor('outdoor_humidity','unavailable'); h.run()
        self.assertEqual(h.mode,'cool'); self.assertEqual(h.error,'')
    def test_22_missing_weather_keeps_bedroom_heat_exception(self):
        self.assertEqual(self.policy(temp=74,weather_valid=False)['mode'],'exhaust')
        self.assertEqual(self.policy(temp=76,weather_valid=False)['cycle'],'burst')
    def test_23_stale_power_vs_unchanged_fresh_reports(self):
        h=Harness('den'); h.cfg['power_max_age']=120; h.run(); h.reporting=False; h.advance(121); h.sensor('temperature',79); h.run()
        self.assertIn('expired',h.error); self.assertEqual(len(h.remote_calls),0)
        h=Harness('den'); h.run(); h.advance(600); h.run()
        self.assertEqual(h.error,''); self.assertEqual(len(h.remote_calls),0)
    def test_24_missing_room_reading_does_not_become_extreme_temperature(self):
        h=Harness('den',mode='cool'); h.sensor('temperature','unavailable'); h.run()
        self.assertEqual(h.mode,'exhaust'); self.assertEqual(h.error,'')
    def test_25_deadlines_survive_unrelated_sensor_events(self):
        h=Harness('den'); h.sensor('temperature',79); h.run()
        deadline=h.states['input_datetime.den_fan_cycle_end'].attributes['timestamp']
        for i in range(4):
            h.advance(60); h.sensor('outdoor_humidity',91+i); h.run()
            self.assertEqual(h.states['input_datetime.den_fan_cycle_end'].attributes['timestamp'],deadline)
    def test_26_bedroom_extension_cannot_repeat_indefinitely(self):
        h=Harness('bedroom'); h.sensor('temperature',76); h.sensor('humidity',63); h.run()
        self.assertEqual(h.states('input_select.bedroom_fan_cycle'),'burst')
        h.advance(1800); h.run(); self.assertEqual(h.states('input_select.bedroom_fan_cycle'),'extension')
        h.advance(1800); h.run(); self.assertEqual(h.states('input_select.bedroom_fan_cycle'),'recovery'); self.assertEqual(h.mode,'exhaust')
    def test_27_manual_mode_edge_survives_speed_changes(self):
        h=Harness('bedroom'); h.run(); h.advance(20)
        h.sensor('power',47)
        edge=h.states['binary_sensor.bedroom_fan_is_cool'].last_changed
        h.advance(2); h.sensor('power',49); h.advance(2); h.sensor('power',51)
        self.assertEqual(h.states['binary_sensor.bedroom_fan_is_cool'].last_changed,edge)
        h.helper('input_select','requested_mode','cool')
        trigger={'from_state':State('off'),'to_state':h.states['binary_sensor.bedroom_fan_is_cool']}
        self.assertTrue(h.render(auto(h,'manual_cool')['conditions'][0]['value_template'],{'trigger':trigger}))


    def test_29_change_only_reporting_does_not_expire(self):
        h=Harness('den'); h.run(); h.reporting=False; h.advance(3600)
        h.sensor('temperature',79); h.sensor('humidity',65); h.run()
        self.assertEqual(h.error,''); self.assertEqual((h.mode,h.speed),('cool','high'))
        self.assertEqual(len(h.remote_calls),2)
    def test_30_unchanged_reports_do_not_confirm_a_missed_press(self):
        h=Harness('den',mode='cool',speed='low'); h.miss=True; h.run()
        self.assertEqual(len(h.remote_calls),1)
        self.assertIn('Expected exhaust_low; read cool_low at 47 W',h.error)
    def test_31_explicit_bedtime_request_retries_after_failure(self):
        h=Harness('bedroom',when='2025-01-01T23:00:00'); h.miss=True
        h.run(event='manual',target_function='cool'); self.assertTrue(h.error)
        h.miss=False; h.run(event='manual',target_function='cool')
        self.assertEqual(h.error,''); self.assertEqual((h.mode,h.speed),('cool','high'))
        self.assertEqual(h.states('input_boolean.bedroom_fan_night_phase'),'on')
    def test_32_remote_cool_recovers_after_old_error(self):
        h=Harness('bedroom',when='2025-01-01T23:00:00'); h.run()
        h.helper('input_text','error','Previous command failed')
        h.helper('input_datetime','command_guard_until','unknown')
        h.advance(120); h.sensor('power',51)
        trigger={'to_state':h.states['binary_sensor.bedroom_fan_is_cool']}
        predicate=auto(h,'manual_cool')['conditions'][0]['value_template']
        self.assertTrue(h.render(predicate,{'trigger':trigger}))
        h.put('input_datetime.bedroom_fan_command_guard_until','future',{'timestamp':h.now.timestamp()+60})
        self.assertFalse(h.render(predicate,{'trigger':trigger}))
    def test_33_night_drying_does_not_claim_it_is_morning(self):
        p=self.policy(clock='23:00:00',event_clock='23:00:00',morning=True,rh=70)
        self.assertFalse(p['night']); self.assertIn('Night drying',p['reason'])
        p=self.policy(clock='23:00:00',event_clock='23:00:00',morning=True,rh=70,event='manual',requested='cool')
        self.assertTrue(p['night']); self.assertIn('Sleep',p['reason'])
    def _drive(self,minutes,temp,rh0,outside_rh,clock,phase='balance',rate=0.03,house_rh=57.0):
        """Run consecutive one-minute evaluations with the physical feedback that
        cooling pulls room humidity toward outdoor air and exhaust pulls it toward
        drier house air. Applies the controller's minimum-hold the same way the
        generated script does. Returns the mode changes that actually happened."""
        h=Harness('bedroom')
        src=next(x['variables']['plan'] for x in h.script['sequence'] if 'plan' in x.get('variables',{}))
        hold=h.cfg['minimum_mode_seconds']
        mem=dict(phase=phase,cycle='normal',cycle_end=0,night=(phase=='sleep'),morning=(phase=='dry'),
            protection=False,sleep_end=(10**9 if phase=='sleep' else 0),morning_at=90000,
            best_rh=rh0,best_at=100000,stalled=False)
        rh,mode,now,last,changes=rh0,'exhaust',100000,0,[]
        for _ in range(minutes):
            p=h.render(src,dict(cfg=h.cfg,event='evaluate',requested='',now_ts=now,clock=clock,
                event_clock=clock,tv_off_now=False,bedtime_clock='22:00:00',morning_clock='06:00:00',
                latest_morning=90000,next_morning=10**9,climate_valid=True,weather_valid=True,
                temp=temp,rh=rh,outside_temp=70,outside_rh=outside_rh,previous_mode=mode,**mem))
            nxt=p['mode']
            if nxt!=mode and p['phase']==mem['phase'] and p['cycle']==mem['cycle'] and now-last<hold:
                nxt=mode
            if nxt!=mode: changes.append(now-last); last=now
            mode=nxt
            for k in ['phase','cycle','night','morning','protection','sleep_end','morning_at','best_rh','best_at','stalled']:
                mem[k]=p[k]
            mem['cycle_end']=p['end']
            rh+=((outside_rh if mode=='cool' else house_rh)-rh)*rate
            rh=max(20.0,min(99.0,rh))
            now+=60
        return changes,rh,mem
    def test_35_policy_does_not_oscillate_near_thresholds(self):
        # Every one of these cycled the fan once a minute before the rewrite.
        for label,kw in [('day warm',dict(temp=74,rh0=62,outside_rh=66,clock='14:00:00')),
            ('day warm, wetter outside',dict(temp=74,rh0=62,outside_rh=69,clock='14:00:00')),
            ('day mild',dict(temp=73,rh0=62,outside_rh=64,clock='14:00:00')),
            ('overnight without sleep',dict(temp=74,rh0=70,outside_rh=76,clock='23:30:00')),
            ('morning drying',dict(temp=74,rh0=68,outside_rh=72,clock='07:00:00',phase='dry'))]:
            changes,_,_=self._drive(180,**kw)
            self.assertLessEqual(len(changes),9,f'{label}: {len(changes)} mode changes in 3 h')
            for gap in changes[1:]:
                self.assertGreaterEqual(gap,self.hold(),f'{label}: switched after only {gap}s')
    def hold(self):
        return Harness('bedroom').cfg['minimum_mode_seconds']
    def test_36_sleep_never_switches_mode(self):
        changes,_,mem=self._drive(480,temp=74,rh0=85,outside_rh=96,clock='23:30:00',phase='sleep')
        self.assertLessEqual(len(changes),1)   # at most the initial move to Cool
        self.assertEqual(mem['phase'],'sleep')
    def test_37_stalled_drying_gives_up_then_re_arms(self):
        # House air as wet as outside: exhaust cannot dry, so drying must stop.
        _,_,mem=self._drive(240,temp=74,rh0=72,outside_rh=95,clock='07:00:00',phase='dry',house_rh=94.0)
        self.assertTrue(mem['stalled']); self.assertEqual(mem['phase'],'balance')
        # Switching to Cool adds 2-3 points by itself, so that must NOT count as
        # a new situation, or the fan re-arms drying against its own intake.
        for rh in [72,73,74.9]:
            self.assertTrue(self.policy(phase='balance',stalled=True,best_rh=70,rh=rh,temp=74)['stalled'],
                f'{rh}% re-armed drying on the fan\'s own humidity bump')
        # A genuinely wetter room is a new situation; drying must be retried.
        p=self.policy(phase='balance',stalled=True,best_rh=70,rh=75,temp=74)
        self.assertFalse(p['stalled'])
    def test_38_mode_is_held_when_nothing_demands_a_change(self):
        # Inside the deadband the policy must keep whatever is already running.
        for previous in ['cool','exhaust']:
            p=self.policy(phase='balance',rh=64,temp=74,previous_mode=previous)
            self.assertEqual(p['mode'],previous)
            self.assertIn('Holding',p['reason'])
    def test_34_slow_changed_reports_can_complete(self):
        h=Harness('den',mode='cool',speed='low'); h.report_delay=45; h.run()
        self.assertEqual(h.error,''); self.assertEqual((h.mode,h.speed),('exhaust','high'))


    def test_35_screenshot_manual_cool_at_73_degrees(self):
        h=Harness('den'); h.sensor('temperature',73.04); h.sensor('humidity',56)
        h.run(event='manual',target_function='cool')
        self.assertEqual(h.error,''); self.assertEqual((h.mode,h.speed),('cool','high'))
        self.assertEqual(len(h.remote_calls),2)
        deadline=h.states['input_datetime.den_fan_manual_until'].attributes['timestamp']
        h.advance(60); h.run()
        self.assertEqual(h.mode,'cool'); self.assertEqual(len(h.remote_calls),2)
        self.assertEqual(h.states['input_datetime.den_fan_manual_until'].attributes['timestamp'],deadline)
    def test_36_all_nine_explicit_manual_selections(self):
        for mode in build.MODES:
            for speed in build.SPEEDS:
                with self.subTest(mode=mode,speed=speed):
                    h=Harness('den'); h.sensor('temperature',73.04); h.sensor('humidity',56)
                    h.run(event='manual',target_function=mode,target_speed=speed)
                    self.assertEqual(h.error,''); self.assertEqual((h.mode,h.speed),(mode,speed))
                    h.advance(60); h.run()
                    self.assertEqual((h.mode,h.speed),(mode,speed))
    def test_37_manual_hold_expires_to_auto_high(self):
        h=Harness('den'); h.run(event='manual',target_function='circulate',target_speed='low')
        deadline=h.states['input_datetime.den_fan_manual_until'].attributes['timestamp']
        h.advance(deadline-h.now.timestamp()-1); h.run()
        self.assertEqual((h.mode,h.speed),('circulate','low'))
        h.advance(2); h.run()
        self.assertEqual(h.error,''); self.assertEqual((h.mode,h.speed),('exhaust','high'))
        self.assertFalse(h.states['sensor.den_fan_control_status'].attributes['manual_active'])
    def test_38_resume_auto_applies_policy_immediately(self):
        h=Harness('den'); h.run(event='manual',target_function='cool',target_speed='low')
        h.run(event='resume_auto')
        self.assertEqual(h.error,''); self.assertEqual((h.mode,h.speed),('exhaust','high'))
    def test_39_hold_survives_restart_without_extending(self):
        h=Harness('den'); h.run(event='manual',target_function='circulate',target_speed='med')
        h.advance(600)
        restarted=Harness('den',when=h.now.replace(tzinfo=None).isoformat(),mode=h.mode,speed=h.speed)
        for key,value in h.states.data.items():
            if key.startswith(('input_select.','input_datetime.','input_boolean.','input_number.','input_text.')):
                restarted.states.data[key]=deepcopy(value)
        restarted.refresh(); restarted.run()
        self.assertEqual((restarted.mode,restarted.speed),('circulate','med'))
        self.assertEqual(restarted.states['input_datetime.den_fan_manual_until'].attributes['timestamp'],
                         h.states['input_datetime.den_fan_manual_until'].attributes['timestamp'])
    def test_40_bedtime_cool_hold_resumes_sleep_then_morning(self):
        h=Harness('bedroom',when='2025-01-01T23:00:00',speed='low')
        h.run(event='manual',target_function='cool')
        self.assertEqual((h.mode,h.speed),('cool','high'))
        self.assertEqual(h.states('input_boolean.bedroom_fan_night_phase'),'on')
        h.advance(1801); h.run(); self.assertEqual((h.mode,h.speed),('cool','high'))
        deadline=h.states['input_datetime.bedroom_fan_sleep_until'].attributes['timestamp']
        h.advance(deadline-h.now.timestamp()+1); h.run()
        self.assertEqual((h.mode,h.speed),('exhaust','high'))
    def test_41_invalid_or_unknown_manual_axis_sends_nothing(self):
        h=Harness('den'); h.run(event='manual',target_function='invalid')
        self.assertTrue(h.error); self.assertEqual(len(h.remote_calls),0)
        h=Harness('den'); h.sensor('power','unavailable'); h.run(event='manual',target_speed='low')
        self.assertTrue(h.error); self.assertEqual(len(h.remote_calls),0)
    def test_42_tv_bedtime_takes_over_a_manual_hold(self):
        h=Harness('bedroom',when='2025-01-01T23:00:00')
        h.run(event='manual',target_function='exhaust',target_speed='low')
        h.run(event='tv_off')
        self.assertEqual((h.mode,h.speed),('cool','high'))
        self.assertFalse(h.states['sensor.bedroom_fan_control_status'].attributes['manual_active'])
    def test_43_single_axis_buttons_preserve_other_axis(self):
        h=Harness('den',mode='exhaust',speed='med'); h.sensor('temperature',79)
        h.run(event='manual',target_speed='low')
        self.assertEqual((h.mode,h.speed),('exhaust','low'))
        h.run(event='manual',target_function='cool')
        self.assertEqual((h.mode,h.speed),('cool','low'))

if __name__=='__main__': unittest.main(verbosity=2)
