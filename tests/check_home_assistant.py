"""Run Home Assistant's own configuration checker on complete generated packages.

Run in a supported Linux Python environment with Home Assistant installed.
This validates HA schemas; it does not contact or operate physical equipment.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import den_controller
import dehumidifier_controller

def main():
    with tempfile.TemporaryDirectory() as folder:
        config=Path(folder)
        (config/'packages').mkdir()
        for name,package in [('den',den_controller.build()),('shared',dehumidifier_controller.build())]:
            (config/'packages'/f'{name}.yaml').write_text(den_controller.dump(package)+'\n',encoding='utf-8')
        (config/'configuration.yaml').write_text('homeassistant:\n  name: Fan software validation\n  latitude: 0\n  longitude: 0\n  elevation: 0\n  unit_system: imperial\n  time_zone: UTC\n  packages: !include_dir_named packages\n',encoding='utf-8')
        subprocess.run([sys.executable,'-m','homeassistant','--script','check_config','--config',str(config)],check=True)

if __name__=='__main__': main()
