"""Generate only the generic den package and independent dehumidifier."""
from pathlib import Path
import den_controller
import dehumidifier_controller

ROOT=Path(__file__).resolve().parent

def main():
    dest=ROOT/'packages'
    dest.mkdir(exist_ok=True)
    (dest/'window_fan_den.yaml').write_text(
        '# Den fan '+den_controller.VERSION+' - GENERIC EXAMPLE, configure privately before installing.\n'+
        den_controller.dump(den_controller.build())+'\n',encoding='utf-8',newline='\n')
    # Retain the shared package byte-for-byte when its inputs have not changed.
    (dest/'shared_dehumidifier.yaml').write_text(
        '# Shared dehumidifier controller 1.6.0. Install once.\n'+
        den_controller.dump(dehumidifier_controller.build())+'\n',encoding='utf-8',newline='\r\n')
    (ROOT/'examples'/'den-card.yaml').write_text(den_controller.dump({
        'type':'custom:window-fan-card','name':'Den Window Fan',
        'fan_package':'sensor.den_fan_state','setup_mode':'package'})+'\n',encoding='utf-8',newline='\n')
    print('Built generic den package, card configuration and unchanged shared dehumidifier.')

if __name__=='__main__': main()
