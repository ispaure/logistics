"""Project check inventory delegates child ownership and timeouts to the manager."""
from pathlib import Path
import shutil
from uuid import uuid4
from build_manager import Executor, Phase, Plan


def run_check(name, argv, *, root, results, environment, timeout):
    results = Path(results)
    execution = results/'checks'/name/uuid4().hex
    from logistics_build.test_evidence import with_reuse
    outputs = tuple(str(argv[index + 1]) for index, value in enumerate(argv[:-1]) if value in {'--junit', '--report'})
    phase = Phase(name, tuple(argv), str(root), timeout=timeout, environment=environment, effect='test',
                  artifacts=outputs, artifact_types={path: 'junit' if path.endswith('.xml') else 'json' for path in outputs})
    plan = Plan('Logistics', 'Native platform check: '+name, {'check': name},
                (phase,),
                str(execution/'workspace'), effect='test')
    plan = with_reuse(plan)
    import os
    if os.environ.get('GITHUB_ACTIONS') == 'true':
        from logistics_build.release_test_evidence import matched_proof
        proof = matched_proof(root, plan.phases[0])
        if proof:
            import json
            execution.mkdir(parents=True, exist_ok=True)
            results.mkdir(parents=True, exist_ok=True)
            (results / (name + '.log')).write_text(
                'Reused verified signed local test evidence: ' + json.dumps(proof, sort_keys=True) + '\n')
            row = dict(name=name, exit_code=0, seconds=0, status='passed', reused=True,
                       evidence=proof, execution=str(execution))
            (execution / 'signed-reuse.json').write_text(json.dumps(row, indent=2) + '\n')
            return row
    def progress(event):
        if event.get('type') == 'output':
            print(event['text'], end='', flush=True)
    report = Executor(event=progress).run(plan, execution/'result')
    row = report['phases'][0]
    shutil.copy2(execution/'result'/row['log'], results/(name+'.log'))
    code = 0 if row['status']=='passed' else 124 if row['status']=='timeout' else row.get('exit_code') or 1
    return dict(name=name, exit_code=code, seconds=round(row['seconds'],2), status=row['status'],
                execution=str(execution/'result'),
                **{key: row[key] for key in ('error', 'cleanup_error') if row.get(key)})
