"""Build/mapping invariants, YAML/template validation, and v1.6 differential policy."""
import ast
from itertools import product
import json
from pathlib import Path
import sys
import unittest
import yaml
from jinja2.nativetypes import NativeEnvironment

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import build
import den_controller as den
import dehumidifier_controller as dehum
from fixtures.v1_6_0_policy import POLICY as ORIGINAL, HUMIDITY_LIMIT as ORIGINAL_LIMIT, CLIMATE_DEFAULTS
from test_den_controller import Harness

class Tests(unittest.TestCase):
    def test_policy_verbatim_and_differential_scenarios(self):
        self.assertEqual({k:den.DEFAULTS[k] for k in den.CLIMATE_KEYS},CLIMATE_DEFAULTS)
        self.assertEqual(den.POLICY,ORIGINAL); self.assertEqual(den.HUMIDITY_LIMIT,ORIGINAL_LIMIT)
        env=NativeEnvironment(); old=env.from_string(ORIGINAL); new=env.from_string(den.POLICY)
        cases=0
        for temp,rh,cycle,end,rh_min in product(
            [67.9,68,69.9,70,72,73,74,75,75.1,76,77,77.9,78,80],
            [50,58,58.1,60,62,63.5,64.9,65,75],
            ['normal','burst','extended','cooling','recovery','heat_relief'],[999,1000,1600],[None,50,57]):
            context=dict(cfg=den.DEFAULTS,temp=temp,rh=rh,cycle=cycle,cycle_end=end,rh_min=rh_min,now_ts=1000)
            before=old.render(**context); after=new.render(**context)
            self.assertEqual(after,before,context)
            self.assertEqual(set(after),{'mode','cycle','end','reason'})
            cases+=1
        # Missing humidity remains legal only on the original heat-priority path.
        for temp,cycle in [(78,'normal'),(76,'heat_relief')]:
            context=dict(cfg=den.DEFAULTS,temp=temp,rh=None,cycle=cycle,cycle_end=1000,rh_min=None,now_ts=1000)
            self.assertEqual(new.render(**context),old.render(**context)); cases+=1
        self.assertEqual(cases,6806)
    def test_generated_yaml_is_current_and_shared_package_unchanged(self):
        build.main()
        for name in ['window_fan_den','shared_dehumidifier']:
            data=yaml.safe_load((ROOT/'packages'/f'{name}.yaml').read_text(encoding='utf-8'))
            self.assertEqual(data,den.build() if name=='window_fan_den' else dehum.build())
        self.assertFalse((ROOT/'packages/window_fan_bedroom.yaml').exists())
    def test_only_one_serialized_executor_has_hardware_actions(self):
        p=den.build(); self.assertEqual(p['script']['den_fan_executor']['mode'],'queued')
        self.assertEqual(len(p['automation']),1)
        for name,s in p['script'].items():
            if name!='den_fan_executor':
                for action in ['remote.send_command','switch.turn_on','switch.turn_off']:
                    self.assertNotIn(action,json.dumps(s))
        self.assertNotIn('den_fan_apply_state',json.dumps(p))
    def test_all_jinja_templates_parse_and_sensor_attributes_render(self):
        h=Harness('den')
        def walk(node):
            if isinstance(node,dict):
                for v in node.values(): walk(v)
            elif isinstance(node,list):
                for v in node: walk(v)
            elif isinstance(node,str) and ('{{' in node or '{%' in node): h.env.parse(node)
        walk(h.package); h.refresh()
        for sensor in h.package['template'][0]['sensor']:
            self.assertTrue(all(isinstance(v,str) for v in sensor.get('attributes',{}).values()))
    def test_confirmed_mappings_propagate_and_no_stale_samples(self):
        cfg=dict(power='sensor.private_watts',plug='switch.private_plug',remote='remote.private_ir',
            device='private_test_device',mode_command='test-mode',speed_command='test-speed',
            power_on_command='test-on',power_off_command='test-off',temperature='sensor.private_t',humidity='sensor.private_rh')
        p=den.build(cfg); data=json.dumps(p)
        for key in ['power','plug','remote','temperature','humidity']:
            self.assertIn(cfg[key],data); self.assertNotIn(den.DEFAULTS[key],data)
        self.assertEqual(p['sensor'][0]['entity_id'],'sensor.den_fan_humidity_sample')
        sample=p['template'][0]['sensor'][0]
        self.assertIn(cfg['humidity'],sample['state']); self.assertIn(cfg['humidity'],sample['availability'])
        triggers=json.dumps(p['automation'][0]['triggers'])
        self.assertIn(cfg['temperature'],triggers); self.assertIn(cfg['humidity'],triggers); self.assertIn(cfg['power'],triggers)
    def test_private_builder_rejects_unconfirmed_mapping_and_policy_changes(self):
        with self.assertRaises(ValueError): den.validate({},private=True)
        with self.assertRaises(ValueError): den.build({'cool_at':71})
        with self.assertRaises(ValueError): den.build({'power_command':'old_unsupported_key'})
        with self.assertRaises(ValueError): den.build({'auto_recovery':'false'})
        with self.assertRaises(ValueError): den.build({'command_delay':float('nan')})
        with self.assertRaises(ValueError): den.build({'remote':'remote.fake; bad'})
    def test_climate_timing_manual_priority_and_original_guard(self):
        p=den.build(); triggers=p['automation'][0]['triggers']
        self.assertIn({'trigger':'time_pattern','minutes':'/1','id':'evaluate'},triggers)
        self.assertTrue(all(t['id']=='observe' for t in triggers if t.get('entity_id')==[den.DEFAULTS['temperature'],den.DEFAULTS['humidity']]))
        h=Harness('den'); h.run(event='synchronize',target_function='circulate',target_speed='med')
        h.sensor('temperature',80); h.sensor('humidity',80); h.run()
        self.assertEqual(h.remote_calls,[])
        self.assertEqual(h.states('sensor.den_fan_state'),'circulate_med')

if __name__=='__main__': unittest.main(verbosity=2)
