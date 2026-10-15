"""Build an allowlisted PUBLIC release bundle. Never include private outputs."""
from pathlib import Path
import hashlib
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import build
import den_controller

def main():
    build.main()
    dest=ROOT/'release'
    dest.mkdir(exist_ok=True)
    files={
        'window-fan-card.js':ROOT/'dist/window-fan-card.js',
        'window_fan_den.example.yaml':ROOT/'packages/window_fan_den.yaml',
        'shared_dehumidifier.example.yaml':ROOT/'packages/shared_dehumidifier.yaml',
        'den-card.yaml':ROOT/'examples/den-card.yaml',
        'room-config.example.json':ROOT/'examples/room-config.example.json',
        'INSTALLATION.md':ROOT/'docs/INSTALL.md',
        'CONTROL.md':ROOT/'docs/CONTROL.md',
        'VERIFICATION.md':ROOT/'docs/VERIFICATION.md',
    }
    assert 'GENERIC EXAMPLE' in files['window_fan_den.example.yaml'].read_text(encoding='utf-8')
    sums=''.join(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+name+'\n' for name,path in files.items())
    archive=dest/f'window-fan-control-{den_controller.VERSION}-examples.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for name,path in files.items(): z.write(path,arcname=name)
        z.writestr('SHA256SUMS.txt',sums)
    with zipfile.ZipFile(archive) as z: assert z.testzip() is None
    print(archive)

if __name__=='__main__': main()
