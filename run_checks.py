"""Run regression checks in a disposable copy; preserve the supplied projects."""
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import shutil
import subprocess
import sys

source = Path(__file__).resolve().parent
with TemporaryDirectory(prefix='stramo-tests-') as temporary:
    target = Path(temporary)
    for pattern in ('*.py','*.json'):
        for path in source.glob(pattern):
            shutil.copy2(path,target/path.name)
    shutil.copytree(source/'assets',target/'assets')
    # Existing calculation/UI regressions exercise the protected app, after the
    # dedicated test_portal.py suite has verified the gate. Only this disposable
    # test copy substitutes the gate; production has no bypass setting.
    if (source/'login.py').exists():
        (target/'login.py').write_text('def require_login():\n    return None\n',encoding='utf-8')
    for name in ('output/pdf','qa','tmp/pdfs'):
        (target/name).mkdir(parents=True,exist_ok=True)
    env = dict(os.environ, MPLBACKEND='Agg', MPLCONFIGDIR=str(target/'mpl-cache'), PYTHONIOENCODING='utf-8')
    failures=[]
    checks=[p for p in sorted(target.glob('check_*.py')) if p.name!='check_delivery.py']
    if sys.argv[1:]:
        requested=set(sys.argv[1:])
        unknown=requested-{p.name for p in checks}
        if unknown:
            raise SystemExit('Unknown tests: '+', '.join(sorted(unknown)))
        checks=[p for p in checks if p.name in requested]
    for check in checks:
        for project in source.glob('*.json'):
            shutil.copy2(project,target/project.name)
        result=subprocess.run([sys.executable,str(check)],cwd=target,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=240)
        print(('PASS' if result.returncode==0 else 'FAIL')+' '+check.name,flush=True)
        if result.returncode:
            failures.append(check.name)
            print(result.stdout[-3000:]+result.stderr[-3000:],flush=True)
    print(f'{len(checks)-len(failures)}/{len(checks)} checks passed')
    sys.exit(bool(failures))
