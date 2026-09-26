"""Scenario tests against the Jinja decisions and actual generated YAML script.
Requires PyYAML and Jinja2. Run: python tests/test_control.py
"""
import ast
from copy import deepcopy
from datetime import datetime, timedelta
import math
import json
import os
from pathlib import Path
import sys
import unittest
from zoneinfo import ZoneInfo
import yaml
from jinja2 import StrictUndefined
from jinja2.nativetypes import NativeEnvironment

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import den_controller as build
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

TEST_SETTINGS=json.loads(Path(os.environ['DEN_TEST_CONFIG']).read_text()) if os.environ.get('DEN_TEST_CONFIG') else None

class Harness:
    """Small script executor with independent motor physics and delayed reports."""
    def __init__(self,room,when='2025-01-01T12:00:00',mode='exhaust',speed='high'):
        self.room=room; self.prefix=room+'_fan'; self.package=yaml.safe_load(build.dump(build.build(TEST_SETTINGS)))
        self.script=self.package['script'][self.prefix+'_set_state']
        self.cfg=self.script['sequence'][0]['variables']['cfg']
        self.now=dt(when); self.states=States(); self.mode=mode; self.speed=speed
        self.calls=[]; self.pending=[]; self.report_delay=2; self.miss=False; self.reporting=True; self.boot=True
        self.motor_watts={key:sum(bounds)/2 for key,bounds in build.RANGES.items()}; self.motor_watts.update(cool_low=47, exhaust_med=34)
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
          (self.cfg['humidity'],65,{'unit_of_measurement':'%'})]: self.put(entity,value,attrs)
        self.put('script.'+self.prefix+'_set_state','off')
        self.refresh(); self.advance(16)
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
            for key in ['power','temperature','humidity']:
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
                elif name=='input_select.select_option':
                    assert data['option'] in self.package['input_select'][entity.split('.')[1]]['options']
                    self.put(entity,data['option'])
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
                        self.mode,self.speed='cool','low'; self.pending.append((self.now+timedelta(seconds=2),self.motor_watts['cool_low']))
                elif name.startswith('script.'):
                    nested=self.package['script'][name.split('.')[1]]
                    self.put(name,'on')
                    try: self.execute(nested['sequence'],dict(data))
                    except Halt as result:
                        if result.error: raise
                    finally: self.put(name,'off')
                elif name.startswith('persistent_notification.'): pass
                elif name.startswith('humidifier.'):
                    attrs=dict(self.states[entity].attributes)
                    if name=='humidifier.set_mode': attrs['mode']=data['mode']
                    elif name=='humidifier.set_humidity': attrs['humidity']=data['humidity']
                    elif name!='humidifier.turn_on': raise AssertionError(name)
                    self.put(entity,'on' if name=='humidifier.turn_on' else self.states(entity),attrs)
                else: raise AssertionError('Unexpected action: '+str(name))
                self.refresh()
            else: raise AssertionError('Unhandled script action: '+str(item))
    def run(self,**fields):
        self.put('script.'+self.prefix+'_set_state','on')
        try: self.execute(self.script['sequence'],dict(fields)); self.halt=None
        except Halt as e: self.halt=e
        finally:
            self.put('script.'+self.prefix+'_set_state','off'); self.refresh()
        return self
    @property
    def remote_calls(self): return [c for c in self.calls if c[0]=='remote.send_command']
    @property
    def error(self): return self.states('input_text.'+self.prefix+'_error')

class Tests(unittest.TestCase):
    def start(self,mode='exhaust',speed='high',temp=69,rh=45):
        h=Harness('den',mode=mode,speed=speed)
        h.sensor('temperature',temp); h.sensor('humidity',rh)
        return h
    def test_01_measured_exhaust_high_never_causes_a_toggle(self):
        for watts in [36,37,38,38.4]:
            h=self.start(); h.sensor('power',watts); h.advance(16); h.run()
            self.assertEqual(h.states('sensor.den_fan_state'),'exhaust_high')
            self.assertEqual(len(h.remote_calls),0)
    def test_02_manual_cool_holds_two_hours_at_75_and_78(self):
        for temp in [75,78]:
            h=self.start(temp=temp); h.run(event='manual',target_function='cool')
            self.assertEqual((h.mode,h.speed),('cool','high')); self.assertEqual(h.error,'')
            count=len(h.remote_calls)
            for _ in range(6): h.advance(60); h.run()
            self.assertEqual(len(h.remote_calls),count)
            h.advance(3600); h.run(); self.assertEqual(h.mode,'cool')
    def test_03_manual_expiry_rechecks_climate_at_high(self):
        h=self.start(); h.run(event='manual',target_function='circulate',target_speed='low')
        h.advance(7201); h.run()
        self.assertEqual((h.mode,h.speed),('exhaust','high')); self.assertEqual(h.error,'')
    def test_04_all_nine_manual_targets(self):
        for setting in build.STATES:
            with self.subTest(setting=setting):
                h=self.start(); mode,speed=setting.split('_'); h.run(event='manual',target_function=mode,target_speed=speed)
                self.assertEqual((h.mode,h.speed),(mode,speed)); self.assertEqual(h.error,'')
    def test_05_overlap_retains_confirmed_history_without_toggles(self):
        for setting,watts in [('exhaust_high',35),('cool_high',50),('circulate_high',46),('cool_low',46)]:
            h=self.start(*setting.split('_')); h.run(event='manual',target_function=h.mode,target_speed=h.speed)
            h.sensor('power',watts); h.advance(60); h.run()
            self.assertEqual(h.states('sensor.den_fan_state'),setting); self.assertEqual(len(h.remote_calls),0)
    def test_06_overlap_without_history_is_unknown(self):
        for watts in [35,46,50]:
            h=self.start(); h.sensor('power',watts); h.advance(16); h.run(event='startup')
            self.assertEqual(h.states('sensor.den_fan_state'),'unknown'); self.assertEqual(len(h.remote_calls),0)
    def test_07_missed_press_fault_stops_all_automatic_retries(self):
        h=self.start(); h.miss=True; h.run(event='manual',target_function='cool')
        self.assertEqual(len(h.remote_calls),1); self.assertTrue(h.error)
        for _ in range(6): h.advance(360); h.run()
        self.assertEqual(len(h.remote_calls),1)
        self.assertEqual(h.states('input_boolean.den_fan_command_fault'),'on')
    def test_08_ambiguous_post_press_cannot_confirm_high(self):
        h=self.start('cool','med'); h.motor_watts['cool_high']=50
        h.run(event='manual',target_speed='high')
        self.assertTrue(h.error); self.assertEqual(len(h.remote_calls),1)
        self.assertEqual(h.states('input_boolean.den_fan_command_fault'),'on')
    def test_09_confirm_physical_setting_sends_no_commands(self):
        h=self.start('cool','high'); h.sensor('power',50)
        h.run(event='synchronize',target_function='cool',target_speed='high')
        self.assertEqual(h.states('sensor.den_fan_state'),'cool_high'); self.assertEqual(len(h.remote_calls),0)
        self.assertEqual(h.states('input_boolean.den_fan_command_fault'),'off')
    def test_10_external_remote_change_starts_manual_hold(self):
        h=self.start(); h.run(); h.advance(60)
        h.mode,h.speed='cool','low'; h.sensor('power',47); h.advance(16); h.run()
        self.assertEqual(len(h.remote_calls),0)
        self.assertGreater(h.states['input_datetime.den_fan_manual_until'].attributes['timestamp'],h.now.timestamp()+7100)
        h.advance(300); h.run(); self.assertEqual(h.mode,'cool')
    def test_11_real_off_on_bootstrap_accepts_overlap_at_46(self):
        h=self.start(); h.sensor('power',0); h.put(h.cfg['plug'],'off'); h.advance(16); h.motor_watts['cool_low']=46
        h.run(); self.assertEqual(h.states('input_boolean.den_fan_boot_pending'),'on')
        h.advance(16); h.advance(16); h.run(event='observe')
        self.assertEqual(h.states('sensor.den_fan_state'),'exhaust_high')
        self.assertEqual(len(h.remote_calls),3)
        self.assertFalse(any(name=='switch.turn_off' for name,_,_ in h.calls))
    def test_12_brief_power_dip_does_not_reset_state(self):
        h=self.start(); h.run(); h.sensor('power',0); h.advance(2); h.run(event='observe')
        self.assertEqual(h.states('input_boolean.den_fan_boot_pending'),'off')
        h.sensor('power',37); h.advance(16); h.run(); self.assertEqual(len(h.remote_calls),0)
    def test_13_den_78_starts_cooling_even_with_old_unchanged_climate(self):
        h=self.start(temp=78,rh=52); h.reporting=False; h.advance(3600); h.run()
        self.assertEqual((h.mode,h.speed),('cool','high')); self.assertEqual(h.error,'')
    def test_14_heat_priority_ignores_humidity_until_75(self):
        h=self.start(temp=78,rh=52); h.run(); self.assertEqual(h.states('input_select.den_fan_cycle'),'heat_relief')
        h.sensor('temperature',76); h.advance(1801); h.run()
        self.assertEqual(h.states('input_select.den_fan_cycle'),'heat_relief')
        h.sensor('humidity',71); h.run(); self.assertEqual(h.mode,'cool')
        h.sensor('temperature',75); h.run(); self.assertEqual(h.mode,'exhaust')
        self.assertEqual(h.states('input_select.den_fan_cycle'),'recovery')
        h.sensor('temperature',79); h.advance(60); h.run(); self.assertEqual(h.mode,'cool')
    def test_15_heat_relief_ends_at_75_when_humid(self):
        h=self.start(temp=78,rh=72); h.run(); h.sensor('temperature',75); h.run()
        self.assertEqual(h.mode,'exhaust'); self.assertEqual(h.states('input_select.den_fan_cycle'),'recovery')
    def test_16_unavailable_climate_does_not_create_fictitious_dry_reading(self):
        h=self.start('cool','high'); h.sensor('humidity','unavailable'); h.run()
        self.assertEqual(len(h.remote_calls),0); self.assertIn('Climate unavailable',h.states('input_text.den_fan_reason'))
    def test_17_resume_auto_ends_hold(self):
        h=self.start(); h.run(event='manual',target_function='cool'); h.run(event='resume_auto')
        self.assertEqual(h.mode,'exhaust'); self.assertEqual(h.error,'')
    def test_18_only_driver_sends_remote_commands(self):
        p=build.build()
        for key,script in p['script'].items():
            if key != 'den_fan_apply_state': self.assertNotIn('remote.send_command',json.dumps(script))
        self.assertNotIn('switch.turn_off',json.dumps(p)); self.assertNotIn('switch.toggle',json.dumps(p))
    def test_19_every_template_attribute_is_string(self):
        for sensor in build.build()['template'][0]['sensor']:
            for value in sensor.get('attributes',{}).values(): self.assertIsInstance(value,str)
    def test_20_restart_reconciles_expired_cycle(self):
        h=self.start(temp=79,rh=72); h.run(); h.advance(1801); h.run(event='startup')
        self.assertEqual(h.states('input_select.den_fan_cycle'),'heat_relief'); self.assertEqual(h.mode,'cool')
    def test_21_transient_external_change_keeps_reference_for_manual_detection(self):
        h=self.start(); h.run(); h.advance(30)
        h.mode,h.speed='cool','high'; h.sensor('power',51); h.run(event='observe')
        self.assertEqual(h.states('sensor.den_fan_state'),'unknown')
        h.advance(16); h.run()
        self.assertEqual(h.states('sensor.den_fan_state'),'cool_high')
        self.assertGreater(h.states['input_datetime.den_fan_manual_until'].attributes['timestamp'],h.now.timestamp())
        self.assertEqual(len(h.remote_calls),0)
    def test_22_service_exception_leaves_persisted_fault(self):
        h=self.start(); original=h.execute
        def broken(items,ctx):
            if any(item.get('action') == 'script.den_fan_apply_state' for item in items):
                # Inject the exception exactly at the nested script call after the latch was set.
                for item in items:
                    if item.get('action') == 'script.den_fan_apply_state': raise RuntimeError('Service unavailable')
                    original([item],ctx)
            else: original(items,ctx)
        h.execute=broken
        with self.assertRaises(RuntimeError): h.run(event='manual',target_function='cool')
        self.assertEqual(h.states('input_boolean.den_fan_command_fault'),'on')
        h.execute=original; h.advance(7201); h.run()
        self.assertEqual(len(h.remote_calls),0)
    def test_23_updated_climate_targets_do_not_reset_burst_deadline(self):
        h=self.start(temp=78,rh=52); h.run()
        end=h.states['input_datetime.den_fan_cycle_end'].attributes['timestamp']
        for temp in [79,77,76]:
            h.sensor('temperature',temp); h.advance(60); h.run()
            self.assertEqual(h.states['input_datetime.den_fan_cycle_end'].attributes['timestamp'],end)
    def test_24_single_axis_manual_preserves_other_axis(self):
        h=self.start('circulate','med'); h.run(event='manual',target_speed='low')
        self.assertEqual((h.mode,h.speed),('circulate','low'))
        h.run(event='manual',target_function='cool'); self.assertEqual((h.mode,h.speed),('cool','low'))
    def test_25_power_restore_reapplies_manual_setting_without_extending_hold(self):
        h=self.start(); h.run(event='manual',target_function='circulate',target_speed='med')
        end=h.states['input_datetime.den_fan_manual_until'].attributes['timestamp']
        h.sensor('power',0); h.put(h.cfg['plug'],'off'); h.advance(16); h.run(event='observe')
        h.advance(16); h.advance(16); h.run(event='observe')
        self.assertEqual((h.mode,h.speed),('circulate','med')); self.assertEqual(h.error,'')
        self.assertEqual(h.states['input_datetime.den_fan_manual_until'].attributes['timestamp'],end)
    def test_26_tolerance_does_not_resolve_overlap_by_guessing(self):
        h=self.start(); h.sensor('power',35.4); h.advance(16); h.run(event='startup')
        self.assertEqual(h.states('sensor.den_fan_state'),'unknown'); self.assertEqual(len(h.remote_calls),0)
        h.run(event='synchronize',target_function='exhaust',target_speed='high')
        for watts in [35,35.4,37,38.4]:
            h.sensor('power',watts); h.advance(60); h.run()
            self.assertEqual(h.states('sensor.den_fan_state'),'exhaust_high')
        self.assertEqual(len(h.remote_calls),0)

    def test_27_celsius_temperature_is_converted(self):
        h=self.start(rh=52)
        h.put(h.cfg['temperature'],26,{'unit_of_measurement':'°C'})
        h.run()
        self.assertEqual((h.mode,h.speed),('cool','high'))
        self.assertEqual(h.error,'')

    def test_28_dynamic_restart_thresholds_and_interpolation(self):
        for temp,limit in [(70,58),(72,58),(73,59),(74,60),(75,61),(76,62),(77,63.5)]:
            for rh,expected in [(limit,'cool'),(limit+0.1,'exhaust')]:
                with self.subTest(temp=temp,rh=rh):
                    h=self.start(temp=temp,rh=rh); h.run(); self.assertEqual(h.mode,expected)
                    self.assertEqual(h.states['sensor.den_fan_control_status'].attributes['humidity_restart_limit'],limit)

    def test_29_normal_cooling_latches_until_68_or_65_percent(self):
        h=self.start(temp=72,rh=57); h.run()
        h.sensor('temperature',69); h.sensor('humidity',63); h.advance(1801); h.run()
        self.assertEqual(h.mode,'cool')
        h.sensor('temperature',68); h.run(); self.assertEqual(h.mode,'exhaust')
        h=self.start(temp=74,rh=59); h.run(); h.sensor('humidity',65); h.run()
        self.assertEqual(h.mode,'exhaust')

    def test_30_more_than_eight_points_in_ten_minutes(self):
        h=self.start(temp=72,rh=54); h.run()
        h.put('sensor.den_fan_humidity_min_10m',54)
        h.sensor('humidity',62); h.run(); self.assertEqual(h.mode,'cool')
        h.sensor('humidity',62.1); h.run(); self.assertEqual(h.mode,'exhaust')
        # The rapid-rise guard also prevents an immediate restart after recovery.
        h.sensor('temperature',77); h.advance(601); h.run(); self.assertEqual(h.mode,'exhaust')
        h.put('sensor.den_fan_humidity_min_10m',62.1); h.run(); self.assertEqual(h.mode,'cool')

    def test_31_heat_overrides_rapid_rise_and_missing_humidity(self):
        h=self.start(temp=79,rh=75); h.put('sensor.den_fan_humidity_min_10m',50); h.run()
        self.assertEqual(h.mode,'cool')
        h.sensor('temperature',76); h.sensor('humidity','unavailable'); h.advance(1801); h.run()
        self.assertEqual(h.mode,'cool'); self.assertIn('heat priority',h.states('input_text.den_fan_reason'))

    def test_32_drying_can_take_an_hour_without_forced_cooling(self):
        h=self.start(temp=72,rh=57); h.run(); h.sensor('humidity',65); h.run()
        for rh in [64,63,62,61,60,59]:
            h.sensor('humidity',rh); h.advance(600); h.run(); self.assertEqual(h.mode,'exhaust')
        h.sensor('humidity',58); h.run(); self.assertEqual(h.mode,'cool')

    def test_33_minimum_recovery_does_not_block_heat_override(self):
        h=self.start(temp=72,rh=57); h.run(); h.sensor('humidity',65); h.run()
        h.sensor('humidity',57); h.advance(60); h.run(); self.assertEqual(h.mode,'exhaust')
        h.sensor('temperature',78); h.run(); self.assertEqual(h.mode,'cool')

    def test_34_interrupted_command_status_and_explicit_recovery(self):
        h=self.start(temp=79,rh=60); h.run(event='synchronize',target_function='exhaust',target_speed='high')
        h.helper('input_boolean','command_fault','on')
        h.helper('input_text','error','Command in progress; if interrupted, confirm the fan setting before retrying.')
        status=h.states['sensor.den_fan_control_status']
        self.assertIn('paused',status.state); self.assertIn('interrupted',status.attributes['error'])
        h.run(event='resume_auto'); self.assertEqual(h.mode,'cool'); self.assertEqual(h.error,'')

    def test_35_manual_hold_still_overrides_heat_priority(self):
        h=self.start(temp=80,rh=75); h.run(event='manual',target_function='circulate',target_speed='low')
        h.advance(3600); h.run(); self.assertEqual((h.mode,h.speed),('circulate','low'))
        h.advance(3601); h.run(); self.assertEqual((h.mode,h.speed),('cool','high'))

    def test_36_wet_heat_exit_recovery_and_dry_heat_exit_continuation(self):
        h=self.start(temp=79,rh=55); h.run(); h.sensor('temperature',75); h.sensor('humidity',64); h.run()
        self.assertEqual(h.mode,'cool'); self.assertEqual(h.states('input_select.den_fan_cycle'),'cooling')
        h.sensor('humidity',65); h.run(); self.assertEqual(h.mode,'exhaust')

    def test_37_statistics_window_matches_guard(self):
        s=build.build()['sensor'][0]
        self.assertEqual(s['state_characteristic'],'value_min')
        self.assertEqual(s['max_age'],{'minutes':10})
        self.assertEqual(s['entity_id'],'sensor.den_fan_humidity_sample')
        h=self.start(); h.advance(60)
        sample=h.states['sensor.den_fan_humidity_sample']
        self.assertEqual(float(sample.state),45)
        self.assertEqual(sample.attributes['sampled_at'],h.now.isoformat())

if __name__=='__main__':
    import json
    unittest.main(verbosity=2)
