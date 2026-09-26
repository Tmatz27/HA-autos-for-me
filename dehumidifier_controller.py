"""One independent owner of the shared dehumidifier; generic public mappings."""
import argparse
import json
from pathlib import Path
from den_controller import a, v, t, iff, halt, dump

DEFAULTS = dict(entity='humidifier.hallway_dehumidifier',
    humidity='sensor.hallway_dehumidifier_humidity', tank='sensor.hallway_dehumidifier_tank',
    sun='sun.sun', night_target=50, day_target=60, mode='Manual')

def build(settings=None):
    cfg={**DEFAULTS, **(settings or {})}
    status='input_text.shared_dehumidifier_status'
    level='input_select.shared_dehumidifier_tank_alert'
    notification='shared_dehumidifier_tank'
    def message(text): return a('input_text.set_value',status,{'value':text})
    def alert(value): return a('input_select.select_option',level,{'option':value})
    def notify(title,body):
        return a('persistent_notification.create',data={'notification_id':notification,'title':title,'message':body})
    seq=[v(cfg=cfg),v(tank=t('states(cfg.tank) | float(none)'),sun=t('states(cfg.sun)')),
         iff('tank is none or not (0 <= tank <= 100)',[
             message('Tank reading unavailable; automatic device commands paused'),halt('No assumed empty tank.')]),
         iff('tank >= 100',[
             iff("not is_state('"+level+"','full')",[
                 notify('Dehumidifier tank full','Empty and refit the tank. Dehumidification is unavailable until the tank is emptied.'),alert('full')]),
             message('Tank full: empty it to restore drying'),halt('Native tank-full protection remains in charge; no restart commands.')]),
         iff('tank >= 75',[
             iff("states('"+level+"') not in ['warning','full']",[
                 notify('Dehumidifier tank at 75%','Empty the tank soon. The dehumidifier will stop when it is full.'),alert('warning')])],
             [iff("not is_state('"+level+"','normal')",[
                 a('persistent_notification.dismiss',data={'notification_id':notification}),alert('normal')])]),
         iff("sun not in ['above_horizon','below_horizon']",[
             message('Sun state unavailable; retaining existing device settings'),halt('No guessed day/night target.')]),
         v(target=t("cfg.night_target if sun == 'below_horizon' else cfg.day_target")),
         iff("states(cfg.entity) not in ['on','off']",[
             message('Dehumidifier unavailable; waiting for connection'),halt('Device unavailable.')]),
         iff("cfg.mode not in (state_attr(cfg.entity,'available_modes') or []) or not (state_attr(cfg.entity,'min_humidity') | float(101) <= target <= state_attr(cfg.entity,'max_humidity') | float(-1))",[
             message('Configured mode or humidity target unsupported'),halt('Verify device capabilities.')]),
         iff('state_attr(cfg.entity,"mode") != cfg.mode',[
             a('humidifier.set_mode',cfg['entity'],{'mode':t('cfg.mode')})]),
         iff('state_attr(cfg.entity,"humidity") | float(-1) != target',[
             a('humidifier.set_humidity',cfg['entity'],{'humidity':t('target')})]),
         iff("is_state(cfg.entity,'off')",[a('humidifier.turn_on',cfg['entity'])]),
         message("{{ ('Night' if sun == 'below_horizon' else 'Day') ~ ': target ' ~ target ~ '% RH' ~ ('; tank needs emptying soon' if tank >= 75 else '') }}")]
    return {
      'input_text':{'shared_dehumidifier_status':{'name':'Shared Dehumidifier Status','max':255}},
      'input_select':{'shared_dehumidifier_tank_alert':{'name':'Shared Dehumidifier Tank Alert','options':['normal','warning','full']}},
      'template':[{'sensor':[{'name':'Shared Dehumidifier Control Status','unique_id':'shared_dehumidifier_control_status',
        'state':t("states('"+status+"')"),'attributes':{
          'device_humidity':t("states('"+cfg['humidity']+"') | float(none)"),
          'tank_percent':t("states('"+cfg['tank']+"') | float(none)"),
          'target_humidity':t(""+str(cfg['night_target'])+" if is_state('"+cfg['sun']+"','below_horizon') else "+str(cfg['day_target'])+" if is_state('"+cfg['sun']+"','above_horizon') else none"),
          'controller_version':'1.6.0'}}]}],
      'automation':[{'id':'shared_dehumidifier_control_v1','alias':'Shared Dehumidifier - Schedule and Tank Alerts',
        'mode':'single','max_exceeded':'silent','trace':{'stored_traces':20},
        'triggers':[{'trigger':'homeassistant','event':'start'},
                    {'trigger':'time_pattern','minutes':'/5'},
                    {'trigger':'state','entity_id':cfg['sun'],'to':['above_horizon','below_horizon']},
                    {'trigger':'state','entity_id':cfg['tank'],'for':{'seconds':30}}],
        'actions':seq}]}

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',type=Path)
    parser.add_argument('--output',type=Path,default=Path('shared_dehumidifier.yaml'))
    args=parser.parse_args()
    cfg=json.loads(args.config.read_text(encoding='utf-8')) if args.config else None
    args.output.write_text('# Shared dehumidifier controller 1.6.0. Install once.\n'+dump(build(cfg))+'\n',encoding='utf-8')
