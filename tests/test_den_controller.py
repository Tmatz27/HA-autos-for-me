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
        self.calls=[]; self.pending=[]; self.report_delay=2; self.miss=False; self.reporting=True; self.heartbeat=True; self.boot=True; self.powered=True; self.running=True; self.service_error=False; self.after_action=None; self.inflight=set(); self.queue=[]
        self.motor_watts={key:sum(bounds)/2 for key,bounds in build.RANGES.items()}; self.motor_watts.update(cool_low=47, exhaust_med=34)
        self.templates={}; self.env=NativeEnvironment(undefined=StrictUndefined)
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
        if isinstance(v,str) and ('{{' in v or '{%' in v):
            if v not in self.templates: self.templates[v]=self.env.from_string(v)
            return native(self.templates[v].render(**ctx))
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
        for _,value in due:
            if self.reporting: self.put(self.cfg['power'],value)
        if self.reporting and self.heartbeat:
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
                    if self.service_error: raise RuntimeError('BroadLink service unavailable')
                    if not self.miss:
                        if data['command']==self.cfg['mode_command']: self.mode=build.MODES[(build.MODES.index(self.mode)+1)%3]
                        elif data['command']==self.cfg['speed_command']: self.speed=build.SPEEDS[(build.SPEEDS.index(self.speed)+1)%3]
                        elif data['command']==self.cfg['power_on_command']:
                            if self.powered and self.boot: self.mode,self.speed='cool','low'; self.running=True
                        else: raise AssertionError('Unexpected command: '+data['command'])
                        self.pending.append((self.now+timedelta(seconds=self.report_delay),self.motor_watts[self.mode+'_'+self.speed] if self.running else 0))
                elif name=='switch.turn_on':
                    self.put(entity,'on')
                    self.powered=True  # Restoring the plug does NOT start the motor.
                elif name=='switch.turn_off':
                    self.put(entity,'off'); self.powered=False; self.running=False
                    self.pending=[]; self.pending.append((self.now+timedelta(seconds=2),0))
                elif name.startswith('script.'):
                    nested=self.package['script'][name.split('.')[1]]
                    if name in self.inflight:
                        assert nested['mode']=='queued'
                        self.queue.append((name,data)); continue
                    self.inflight.add(name); self.put(name,'on')
                    try: self.execute(nested['sequence'],dict(data))
                    except Halt as result:
                        if result.error: raise
                    except RuntimeError:
                        if not item.get('continue_on_error'): raise
                    finally: self.inflight.remove(name); self.put(name,'off')
                    while self.queue and self.queue[0][0] not in self.inflight:
                        queued_name,queued_data=self.queue.pop(0)
                        self.execute([{'action':queued_name,'data':queued_data}],{})
                elif name.startswith('persistent_notification.'): pass
                elif name.startswith('humidifier.'):
                    attrs=dict(self.states[entity].attributes)
                    if name=='humidifier.set_mode': attrs['mode']=data['mode']
                    elif name=='humidifier.set_humidity': attrs['humidity']=data['humidity']
                    elif name!='humidifier.turn_on': raise AssertionError(name)
                    self.put(entity,'on' if name=='humidifier.turn_on' else self.states(entity),attrs)
                else: raise AssertionError('Unexpected action: '+str(name))
                self.refresh()
                if self.after_action: self.after_action(name,entity,data)
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
        h.run(event='synchronize',target_function=mode,target_speed=speed)
        h.put('input_datetime.den_fan_manual_until','1970-01-01 00:00:00',{'timestamp':0})
        h.calls=[]; h.refresh(); return h
    def test_all_81_cyclic_transitions_preserve_independent_axes(self):
        for before in build.STATES:
            for target in build.STATES:
                with self.subTest(before=before,target=target):
                    h=self.start(*before.split('_')); m,s=target.split('_')
                    h.run(event='manual',target_function=m,target_speed=s)
                    self.assertEqual((h.mode,h.speed),(m,s)); self.assertEqual(h.error,'')
                    bm,bs=before.split('_')
                    expected=(build.MODES.index(m)-build.MODES.index(bm))%3+(build.SPEEDS.index(s)-build.SPEEDS.index(bs))%3
                    self.assertEqual(len(h.remote_calls),expected)
                    self.assertFalse(any(c[0].startswith('switch.') for c in h.calls))
    def test_all_nine_reset_targets_and_exact_power_order(self):
        for target in build.STATES:
            with self.subTest(target=target):
                h=self.start('circulate','high'); m,s=target.split('_')
                h.run(event='recover',target_function=m,target_speed=s)
                actions=[c[0] for c in h.calls if c[0].startswith(('switch.','remote.'))]
                self.assertEqual(actions[:3],['switch.turn_off','switch.turn_on','remote.send_command'])
                self.assertEqual(h.remote_calls[0][2]['command'],h.cfg['power_on_command'])
                self.assertEqual((h.mode,h.speed),(m,s)); self.assertEqual(h.error,'')
                self.assertEqual(h.states('input_select.den_fan_recovery'),'complete')
    def test_cool_high_to_exhaust_medium_is_one_mode_two_speed(self):
        h=self.start('cool','high'); h.run(event='manual',target_function='exhaust',target_speed='med')
        self.assertEqual([c[2]['command'] for c in h.remote_calls],[h.cfg['mode_command'],h.cfg['speed_command'],h.cfg['speed_command']])
    def test_each_single_axis_preserves_the_other(self):
        h=self.start('circulate','med'); h.run(event='manual',target_speed='low')
        self.assertEqual((h.mode,h.speed),('circulate','low'))
        h.run(event='manual',target_function='cool'); self.assertEqual((h.mode,h.speed),('cool','low'))
    def test_manual_without_climate_and_timer_restarts(self):
        h=self.start(); h.sensor('temperature','unknown'); h.sensor('humidity','unavailable')
        started=h.now.timestamp(); h.run(event='manual',target_function='cool')
        first=h.states['input_datetime.den_fan_manual_until'].attributes['timestamp']
        self.assertEqual(first-started,7200)
        h.advance(60); h.run(event='manual',target_speed='med')
        self.assertGreater(h.states['input_datetime.den_fan_manual_until'].attributes['timestamp'],first)
        self.assertEqual((h.mode,h.speed),('cool','med'))
    def test_hold_expiration_and_resume_auto(self):
        for resume in [False,True]:
            h=self.start(temp=80,rh=75); h.run(event='manual',target_function='circulate',target_speed='low')
            count=len(h.remote_calls); h.advance(3600); h.run()
            self.assertEqual(len(h.remote_calls),count)
            if resume: h.run(event='resume_auto')
            else: h.advance(3601); h.run()
            self.assertEqual((h.mode,h.speed),('cool','high'))
    def test_ambiguous_50_4_retains_high_and_never_resets(self):
        h=self.start('cool','high',temp=72,rh=57); h.sensor('power',50.4)
        for _ in range(4): h.run(); h.advance(60)
        self.assertEqual(h.states('sensor.den_fan_state'),'cool_high')
        self.assertEqual(h.error,''); self.assertEqual(h.remote_calls,[])
        self.assertFalse(any(c[0].startswith('switch.') for c in h.calls))
        self.assertIn('Overlapping',h.states['sensor.den_fan_control_status'].attributes['evidence'])
    def test_overlap_after_press_is_inferred_not_independently_confirmed(self):
        h=self.start('cool','med'); h.motor_watts['cool_high']=50.4
        h.run(event='manual',target_speed='high')
        self.assertEqual(h.states('sensor.den_fan_state'),'cool_high')
        self.assertEqual(h.states('input_select.den_fan_confidence'),'inferred')
        self.assertEqual(h.error,''); self.assertIn('unproven',h.states('input_text.den_fan_outcome'))
    def test_restart_restores_hold_history_and_downgrades_confidence(self):
        h=self.start(); h.run(event='manual',target_function='circulate',target_speed='low')
        hold=h.states['input_datetime.den_fan_manual_until'].attributes['timestamp']; count=len(h.remote_calls)
        h.run(event='startup')
        self.assertEqual(h.states('sensor.den_fan_state'),'circulate_low')
        self.assertEqual(h.states('input_select.den_fan_confidence'),'inferred')
        self.assertEqual(h.states['input_datetime.den_fan_manual_until'].attributes['timestamp'],hold)
        self.assertEqual(len(h.remote_calls),count)
        for domain in ['input_select','input_boolean','input_datetime']:
            self.assertTrue(all('initial' not in x for x in h.package[domain].values()))
    def test_physical_power_loss_preserves_history_blocks_toggles(self):
        h=self.start(); h.put(h.cfg['plug'],'off'); h.sensor('power',0)
        h.run(event='power_lost'); h.run(event='manual',target_function='cool')
        self.assertEqual(h.remote_calls,[])
        self.assertEqual(h.states('sensor.den_fan_state'),'exhaust_high')
        self.assertEqual(h.states('input_boolean.den_fan_running'),'off')
        self.assertEqual(h.states('input_select.den_fan_confidence'),'uncertain')
    def test_failed_power_on_stops_without_toggles_or_infinite_retries(self):
        h=self.start(); h.boot=False; h.run(event='recover',target_function='circulate',target_speed='high')
        self.assertEqual(len(h.remote_calls),1); self.assertIn('Power On',h.error)
        self.assertEqual(h.states('input_select.den_fan_recovery'),'failed')
        h.advance(7201)
        for _ in range(4): h.run(); h.advance(60)
        self.assertEqual(len(h.remote_calls),1)
        self.assertEqual(sum(c[0]=='switch.turn_off' for c in h.calls),1)
    def test_recovery_accepts_change_only_off_and_startup_reports(self):
        h=self.start(); h.heartbeat=False; h.run(event='recover',target_function='circulate',target_speed='med')
        self.assertEqual((h.mode,h.speed),('circulate','med'))
        self.assertEqual(h.states('input_select.den_fan_recovery'),'complete'); self.assertEqual(h.error,'')

    def test_no_running_evidence_from_stale_pre_reset_reading(self):
        h=self.start(); h.reporting=False; h.run(event='recover')
        self.assertEqual(h.remote_calls,[]); self.assertIn('stopped-power',h.error)
    def test_missed_press_blocks_remaining_presses_and_auto_retry(self):
        h=self.start(); h.miss=True; h.run(event='manual',target_function='cool',target_speed='low')
        self.assertEqual(len(h.remote_calls),1); self.assertIn('contradicts',h.error)
        self.assertEqual(h.states('sensor.den_fan_state'),'circulate_high') # first commanded step retained as uncertain history
        self.assertEqual(h.states('input_select.den_fan_confidence'),'uncertain')
        h.advance(7201)
        for _ in range(3): h.run()
        self.assertEqual(len(h.remote_calls),1)
    def test_delayed_and_unchanged_fresh_reports(self):
        h=self.start(); h.report_delay=20; h.run(event='manual',target_function='cool')
        self.assertEqual(h.mode,'cool'); self.assertEqual(h.error,'')
        h=self.start('cool','med'); h.motor_watts['cool_med']=50.4; h.motor_watts['cool_high']=50.4
        h.sensor('power',50.4); h.run(event='manual',target_speed='high')
        self.assertEqual(h.error,''); self.assertEqual(h.speed,'high')
    def test_unavailable_or_stale_power_reports_inference_without_erasing_history(self):
        for value in ['unknown','unavailable',50.4]:
            h=self.start('cool','high'); h.sensor('power',value); h.reporting=False
            h.states[h.cfg['power']].last_reported=h.now-timedelta(seconds=300)
            h.run(event='manual',target_function='circulate',target_speed='low')
            self.assertEqual((h.mode,h.speed),('circulate','low'))
            self.assertEqual(h.states('input_select.den_fan_confidence'),'inferred')
            self.assertEqual(h.error,'')
            self.assertIn('unavailable or stale',h.states['sensor.den_fan_control_status'].attributes['evidence'])
    def test_confirm_conflicting_watts_accepts_selected_state_without_commands(self):
        h=self.start(); h.sensor('power',50.4)
        h.run(event='synchronize',target_function='circulate',target_speed='med')
        self.assertEqual(h.states('sensor.den_fan_state'),'circulate_med')
        self.assertIn('wattage disagrees',h.error); self.assertEqual(h.remote_calls,[])
        self.assertEqual(h.states('input_select.den_fan_confidence'),'established')
    def test_user_confirmation_outweighs_conflicting_baseline_wattage(self):
        h=self.start('exhaust','high'); h.sensor('power',49)
        h.run(event='synchronize',target_function='exhaust',target_speed='high')
        self.assertIn('wattage disagrees',h.error)
        h.run(event='manual',target_function='circulate')
        self.assertEqual(h.mode,'circulate'); self.assertEqual(h.error,'')

    def test_unknown_state_requires_reference_and_no_blind_toggles(self):
        h=Harness('den'); h.run(event='manual',target_function='cool')
        self.assertEqual(h.remote_calls,[]); self.assertIn('Unknown starting',h.error)
        h.run(event='manual',target_function='cool',target_speed='high')
        self.assertEqual(h.remote_calls,[]); self.assertIn('State uncertain',h.error)
    def test_duplicate_request_executes_no_duplicate_toggles(self):
        h=self.start(); h.run(event='manual',target_function='cool',target_speed='low')
        count=len(h.remote_calls); h.run(event='manual',target_function='cool',target_speed='low')
        self.assertEqual(len(h.remote_calls),count)
    def test_manual_arrives_during_auto_and_uses_shared_queue(self):
        h=self.start(temp=78,rh=70); fired=False
        def during(name,entity,data):
            nonlocal fired
            if name=='remote.send_command' and not fired:
                fired=True; h.run(event='manual',target_function='circulate',target_speed='low')
        h.after_action=during; h.run()
        self.assertTrue(fired); self.assertEqual((h.mode,h.speed),('circulate','low'))
        self.assertEqual(h.queue,[]); self.assertEqual(h.error,'')
        # Only the first auto mode press was allowed; manual used its result.
        self.assertEqual(len(h.remote_calls),2)
    def test_manual_arrives_during_recovery_waits_for_completed_reference(self):
        h=self.start(); fired=False
        def during(name,entity,data):
            nonlocal fired
            if name=='switch.turn_off' and not fired:
                fired=True; h.run(event='manual',target_function='circulate',target_speed='med')
        h.after_action=during; h.run(event='recover',target_function='cool',target_speed='low')
        self.assertEqual((h.mode,h.speed),('circulate','med'))
        self.assertEqual(sum(c[0]=='switch.turn_off' for c in h.calls),1)
    def test_service_error_is_persisted_and_restart_cannot_resume_blindly(self):
        h=self.start(); h.service_error=True; h.run(event='manual',target_function='cool')
        self.assertEqual(h.states('input_boolean.den_fan_command_in_progress'),'on')
        status=h.states['sensor.den_fan_control_status']
        self.assertFalse(status.attributes['command_active']); self.assertIn('interrupted',status.attributes['error'])
        count=len(h.remote_calls); h.service_error=False; h.run(event='startup'); h.run(event='resume_auto')
        self.assertEqual(len(h.remote_calls),count)
        self.assertEqual(h.states('input_select.den_fan_confidence'),'uncertain')
        h.run(event='synchronize',target_function=h.mode,target_speed=h.speed)
        self.assertEqual(h.error,'')
    def test_interruption_after_send_before_history_write_requires_reference(self):
        h=self.start()
        def interrupt(name,entity,data):
            if name=='remote.send_command': raise RuntimeError('Process interrupted')
        h.after_action=interrupt; h.run(event='manual',target_function='cool')
        self.assertEqual(h.mode,'circulate'); self.assertEqual(h.states('sensor.den_fan_state'),'exhaust_high')
        h.after_action=None; h.run(event='startup'); h.run(event='resume_auto')
        self.assertEqual(len(h.remote_calls),1); self.assertEqual(h.states('input_select.den_fan_confidence'),'uncertain')
    def test_automatic_recovery_is_one_persistent_attempt(self):
        h=Harness('den'); h.cfg['auto_recovery']=True
        # Both scripts have their own embedded immutable cfg in real HA.
        for script in h.package['script'].values():
            if script['sequence'][0].get('variables',{}).get('cfg'): script['sequence'][0]['variables']['cfg']['auto_recovery']=True
        h.boot=False; h.run()
        self.assertEqual(sum(c[0]=='switch.turn_off' for c in h.calls),1)
        for _ in range(4): h.run(event='startup'); h.advance(60); h.run()
        self.assertEqual(sum(c[0]=='switch.turn_off' for c in h.calls),1)
    def test_valid_climate_is_required_except_original_heat_exemption(self):
        h=self.start(temp=74,rh=55); h.sensor('temperature','unknown'); h.run()
        self.assertEqual(h.remote_calls,[]); self.assertIn('Climate unavailable',h.states('input_text.den_fan_reason'))
        h.sensor('temperature',74); h.sensor('humidity','unavailable'); h.run(); self.assertEqual(h.remote_calls,[])
        h.sensor('temperature',78); h.run(); self.assertEqual(h.mode,'cool')
    def test_no_op_has_no_unnecessary_reset_and_fresh_conflict_blocks_change(self):
        h=self.start(); h.run(event='manual',target_function='exhaust',target_speed='high'); self.assertEqual(h.remote_calls,[])
        h.sensor('power',51); h.helper('input_select','confidence','inferred'); h.run(event='manual',target_function='cool')
        self.assertEqual(h.remote_calls,[]); self.assertIn('conflicts',h.error)

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


if __name__=='__main__': unittest.main(verbosity=2)
