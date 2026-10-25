"""Project check inventory delegates child ownership and timeouts to the manager."""
from pathlib import Path
import shutil
from uuid import uuid4
from build_manager import Executor, Phase, Plan


def run_check(name, argv, *, root, results, environment, timeout):
    results = Path(results)
    execution = results/'checks'/name/uuid4().hex
    plan = Plan('Logistics', 'Native platform check: '+name, {'check': name},
                (Phase(name, tuple(argv), str(root), timeout=timeout, environment=environment),),
                str(execution/'workspace'), effect='test')
    def progress(event):
        if event.get('type') == 'output':
            print(event['text'], end='', flush=True)
    report = Executor(event=progress).run(plan, execution/'result')
    row = report['phases'][0]
    shutil.copy2(execution/'result'/row['log'], results/(name+'.log'))
    code = 0 if row['status']=='passed' else 124 if row['status']=='timeout' else row.get('exit_code') or 1
    return dict(name=name, exit_code=code, seconds=round(row['seconds'],2), status=row['status'],
                execution=str(execution/'result'))
