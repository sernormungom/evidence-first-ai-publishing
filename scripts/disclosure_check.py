"""Fail closed on unexpected tracked files and sensitive-looking public output."""
from pathlib import Path
import re
import subprocess
ROOT=Path(__file__).resolve().parents[1]
def main():
    files=subprocess.check_output(['git','ls-files'],cwd=ROOT,text=True).splitlines()
    allowed=(ROOT/'publication-files.txt').read_text().splitlines()
    errors=[p for p in files if p not in allowed]
    candidates=[ROOT/p for p in files]+list((ROOT/'dist/portfolio').rglob('*'))
    patterns=[r'(?i)\b(?:' + ''.join(map(chr,[109,112,121,97])) + r'|'+ ''.join(map(chr,[115,105,109,112,108,111,121,101,114])) + r')\b',r'(?i)https?://[^\s]*[?&](?:RequestKey|access_token|token)=',r'(?i)AKIA[A-Z0-9]{16}',r'-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----',r'(?i)[a-z0-9._%+-]+@(?!example\.invalid|users\.noreply\.github\.com)[a-z0-9.-]+\.[a-z]{2,}',r'/home/[a-zA-Z0-9_-]+/']
    for p in candidates:
        if p.is_file():
            try: data=p.read_text()
            except UnicodeDecodeError: errors.append(str(p));continue
            if p.name=='disclosure_check.py': continue
            data = data.replace('https://demo.invalid/?RequestKey=INVENTED', '')
            if any(re.search(rule,data) for rule in patterns): errors.append(str(p.relative_to(ROOT)))
    if errors: raise SystemExit('Publication review required: '+repr(sorted(set(errors))))
    print('Publication allowlist and disclosure checks passed')
if __name__=='__main__': main()
