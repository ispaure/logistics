"""Focused Android native cancellation using a previously verified test APK."""
import argparse
import json
import os
from pathlib import Path
import sys
from threading import Event,Thread
import time

from build_manager import Executor,Phase,Plan


def run(project, snapshot, workspace, output, python, sdk, java, runtime_cache=None):
    source=json.loads((snapshot/'.manager-source.json').read_text())['source']
    device=workspace/'device'
    env=dict(PYTHONPATH=os.pathsep.join((str(project),str(project/'Python'))),ANDROID_HOME=str(sdk),
             ANDROID_SDK_ROOT=str(sdk),JAVA_HOME=str(java),PYTHONUNBUFFERED='1')
    base=(str(python),'-m','Scripts.android_backend')
    common=('--root',str(snapshot),'--workspace',str(device))
    phases=(Phase('ready',(*base,'ready',*common,'--result',str(workspace/'ready.json')),str(project),timeout=360,environment=env),
            Phase('native',(*base,'native',*common,'--result',str(workspace/'native.json')),str(project),timeout=180,environment=env,dependencies=('ready',)),
            Phase('remaining-device', (str(python),'-c','raise AssertionError("must not start after cancellation")'),str(project),dependencies=('native',)),
            Phase('cleanup',(*base,'cleanup',*common),str(project),timeout=180,environment=env,always=True,kind='cleanup'))
    if runtime_cache is not None:
        phase = Phase('runtime', (*base,'runtime',*common,'--runtime-cache',str(runtime_cache),'--result',str(workspace/'runtime.json')),
                      str(project),timeout=300,environment=env,dependencies=('ready',),artifacts=(str(workspace/'runtime.json'),))
        phases = (phases[0],phase,*phases[1:])
    cancelled,finished,triggered=Event(),Event(),Event()
    def monitor():
        deadline=time.monotonic()+120
        while not finished.wait(.1) and time.monotonic()<deadline:
            path=output/'native.log'
            if path.exists() and 'Native checkpoint: native_hub' in path.read_text(errors='replace'):
                triggered.set();cancelled.set();return
    worker=Thread(target=monitor,daemon=True);worker.start()
    try:
        result=Executor(cancelled=cancelled).run(Plan('Logistics','Focused native cancellation',
            dict(scope='cancellation only; not complete native acceptance',native_binary_source=source),phases,str(workspace/'operation')),
            output)
    finally:finished.set();worker.join(timeout=2)
    verified=(triggered.is_set() and result['status']=='cancelled' and
              [row['status']for row in result['phases']]==(['passed','passed','cancelled','skipped','passed'] if runtime_cache is not None else ['passed','cancelled','skipped','passed']) and
              not (device/'lease.json').exists() and (device/'removed-lease.json').is_file())
    report=dict(verified=verified,result=str(output/'result.json'),native_binary_source=source,
                ready=json.loads((workspace/'ready.json').read_text()) if (workspace/'ready.json').exists() else None)
    (output/'probe.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True)
    return 0 if verified else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('project','snapshot','workspace','output','python','sdk','java'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--runtime-cache',type=Path)
    args=parser.parse_args()
    return run(**vars(args))


if __name__=='__main__':raise SystemExit(main())
