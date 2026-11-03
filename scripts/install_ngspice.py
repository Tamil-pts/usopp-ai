"""Install the pinned Windows ngspice runtime under this checkout, without admin rights."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
URL = 'https://downloads.sourceforge.net/project/ngspice/ng-spice-rework/47/ngspice-47_64.7z'
SHA256 = '59225971bd68cdd1199443649aa4615a9e6d684933f205ab49006a3942518f5a'


def main():
    if os.name != 'nt':
        raise SystemExit('Install ngspice through your OS package manager or set USOPP_NGSPICE to its executable.')
    extractor = shutil.which('7z') or str(Path(os.environ.get('ProgramFiles', 'C:/Program Files'))/'7-Zip/7z.exe')
    if not Path(extractor).is_file():
        raise SystemExit('Install 7-Zip or add 7z.exe to PATH, then run this script again.')
    destination = ROOT/'local_simulators/ngspice'
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='usopp-ngspice-') as temporary:
        archive = Path(temporary)/'ngspice.7z'
        with urllib.request.urlopen(URL, timeout=120) as response, archive.open('wb') as output:
            total = 0
            while chunk := response.read(1024*1024):
                total += len(chunk)
                if total > 100*1024*1024:
                    raise SystemExit('Download exceeds the pinned release size budget.')
                output.write(chunk)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
            raise SystemExit('Release SHA-256 mismatch. Nothing was extracted.')
        listing = subprocess.run([extractor, 'l', '-slt', str(archive)], capture_output=True, text=True, check=True).stdout
        for line in listing.split('----------', 1)[-1].splitlines():
            if line.startswith('Path = '):
                target = (destination/line[7:]).resolve()
                if not target.is_relative_to(destination.resolve()):
                    raise SystemExit('Archive contains an unsafe path. Nothing was extracted.')
            if line.startswith(('Symbolic Link = ', 'Hard Link = ')):
                raise SystemExit('Archive links are not accepted.')
        subprocess.run([extractor, 'x', '-y', '-o'+str(destination), str(archive)], check=True, capture_output=True)
    binary = destination/'Spice64/bin/ngspice_con.exe'
    subprocess.run([str(binary), '--version'], check=True)
    (destination/'installation.json').write_text(json.dumps({'version':47,'source':URL,'sha256':SHA256}, indent=2), encoding='utf-8')
    print('Local circuit simulator ready. License: '+str(destination/'Spice64/docs/COPYING'))


if __name__ == '__main__':
    main()
