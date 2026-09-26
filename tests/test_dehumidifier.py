"""Execute generated dehumidifier actions against device state transitions."""
import unittest
from test_den_controller import Harness
import dehumidifier_controller as control

class Tests(unittest.TestCase):
    def start(self,sun='below_horizon',tank=25,state='on',target=55,mode='Manual'):
        h=Harness('den'); h.package=control.build(); h.script={'sequence':h.package['automation'][0]['actions']}
        h.put('input_text.shared_dehumidifier_status','')
        h.put('input_select.shared_dehumidifier_tank_alert','normal')
        h.put(control.DEFAULTS['tank'],tank); h.put(control.DEFAULTS['sun'],sun)
        h.put(control.DEFAULTS['humidity'],56)
        h.put(control.DEFAULTS['entity'],state,{'available_modes':['Manual','Continuous','Auto'],
            'mode':mode,'humidity':target,'min_humidity':35,'max_humidity':85})
        h.refresh(); return h
    def commands(self,h): return [c for c in h.calls if c[0].startswith('humidifier.')]
    def notices(self,h): return [c for c in h.calls if c[0]=='persistent_notification.create']
    def test_night_50_day_60_and_no_repeated_writes(self):
        h=self.start(); h.run(); self.assertEqual(self.commands(h)[0][2],{'humidity':50})
        h.run(); self.assertEqual(len(self.commands(h)),1)
        h.put('sun.sun','above_horizon'); h.run()
        self.assertEqual(self.commands(h)[-1][2],{'humidity':60})
        h.run(); self.assertEqual(len(self.commands(h)),2)
    def test_mode_and_power_are_explicit_never_toggle(self):
        h=self.start(state='off',mode='Continuous'); h.run()
        self.assertEqual([c[0] for c in self.commands(h)],['humidifier.set_mode','humidifier.set_humidity','humidifier.turn_on'])
        h.run(); self.assertEqual(len(self.commands(h)),3)
    def test_warning_escalates_once_and_full_blocks_all_device_commands(self):
        h=self.start(tank=75,target=50); h.run(); h.run()
        self.assertEqual(len(self.notices(h)),1)
        h.put(control.DEFAULTS['tank'],100); h.put(control.DEFAULTS['entity'],'off'); h.run(); h.run()
        self.assertEqual(len(self.notices(h)),2); self.assertEqual(self.commands(h),[])
        self.assertEqual(self.notices(h)[0][2]['notification_id'],self.notices(h)[1][2]['notification_id'])
        self.assertIn('Tank full',h.states('sensor.shared_dehumidifier_control_status'))
    def test_empty_tank_clears_warning_and_restores_device(self):
        h=self.start(tank=100,state='off'); h.run()
        h.put(control.DEFAULTS['tank'],25); h.run()
        self.assertTrue(any(c[0]=='persistent_notification.dismiss' for c in h.calls))
        self.assertEqual(self.commands(h)[-1][0],'humidifier.turn_on')
        self.assertEqual(h.states('input_select.shared_dehumidifier_tank_alert'),'normal')
    def test_unavailable_or_invalid_tank_never_assumes_empty(self):
        for value in ['unavailable','unknown',-1,101]:
            h=self.start(tank=value,state='off'); h.run(); self.assertEqual(self.commands(h),[])
    def test_unknown_sun_device_or_capability_pauses_commands(self):
        h=self.start(sun='unavailable'); h.run(); self.assertEqual(self.commands(h),[])
        h=self.start(state='unavailable'); h.run(); self.assertEqual(self.commands(h),[])
        h=self.start(); h.states[control.DEFAULTS['entity']].attributes['available_modes']=['Continuous']; h.run()
        self.assertEqual(self.commands(h),[])
        h=self.start(); h.states[control.DEFAULTS['entity']].attributes['min_humidity']=55; h.run()
        self.assertEqual(self.commands(h),[])
    def test_restored_warning_not_repeated_after_restart(self):
        h=self.start(tank=75,target=50); h.put('input_select.shared_dehumidifier_tank_alert','warning'); h.run()
        self.assertEqual(self.notices(h),[])
    def test_shared_owner_has_no_fan_or_temperature_dependency(self):
        import json
        data=json.dumps(control.build())
        for name in ['remote.send_command','den_fan_set_state','bedroom','temperature','switch.turn_off']:
            self.assertNotIn(name,data)

if __name__=='__main__': unittest.main(verbosity=2)
