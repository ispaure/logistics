"""Logistics native/runtime test policy over the disposable Android lifecycle."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from build_manager.android_emulators import AndroidEmulator
from Scripts.mobile_processes import command, interrupt
from Scripts.mobile_runtime import checksum


def sdk_build_identity():
    sdk=Path(os.environ['ANDROID_HOME'])
    files=[]
    for group in ('build-tools','platforms','ndk'):
        files.extend((sdk/group).glob('*/source.properties'))
    files.extend(path for path in (sdk/'platform-tools/source.properties',sdk/'cmdline-tools/latest/source.properties') if path.is_file())
    return dict(root=str(sdk),packages={str(path.relative_to(sdk)):checksum(path) for path in sorted(files)})


def build(root, output):
    mobile=root/'mobile_build'
    apk=mobile/'build/logisticsmobile/android/gradle/app/build/outputs/apk/debug/app-debug.apk'
    record=mobile/'build/manager-android-cache.json'
    source=json.loads((root/'.manager-source.json').read_text())['source']
    key=dict(source=source,sdk=sdk_build_identity(),java=subprocess.check_output([str(Path(os.environ['JAVA_HOME'])/'bin/java'),'-version'],stderr=subprocess.STDOUT,text=True).strip(),
             briefcase=subprocess.check_output([sys.executable,'-m','briefcase','--version'],text=True).strip())
    started=time.monotonic();reused=False
    if record.exists():
        saved=json.loads(record.read_text())
        reused=saved['key']==key and apk.exists() and saved['apk_sha256']==checksum(apk)
    if not reused:
        command([sys.executable,'tools.py','stage','payload','--repo',str(root),'--allow-dirty'],mobile)
        command([sys.executable,'cloud_build.py','licenses'],mobile)
        command([sys.executable,'-m','briefcase','create','android','--no-input'],mobile)
        command([sys.executable,'cloud_build.py','android'],mobile)
        command([sys.executable,'-m','briefcase','build','android','--test','--no-input'],mobile)
    from mobile_build.validation.ui_tools import verify_prebuilt_android
    os.chdir(mobile);verify_prebuilt_android()
    key['sdk']=sdk_build_identity()
    value=dict(key=key,apk=str(apk),apk_sha256=checksum(apk),reused=reused,seconds=time.monotonic()-started,status='passed')
    record.write_text(json.dumps(value,indent=2)+'\n');output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(value,indent=2)+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['build','ready','native','runtime','cleanup'])
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--workspace',type=Path,required=True)
    parser.add_argument('--result',type=Path)
    parser.add_argument('--runtime-cache',type=Path)
    parser.add_argument('--image',default='system-images;android-36;google_apis;arm64-v8a')
    parser.add_argument('--model',default='pixel_9')
    args=parser.parse_args()
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,interrupt)
    emulator=AndroidEmulator(os.environ['ANDROID_HOME'],args.workspace)
    if args.action=='build':return build(args.root,args.result)
    if args.action=='cleanup':return emulator.cleanup()
    if args.action=='ready':
        try:
            started=time.monotonic();record=emulator.start(args.image,args.model)
            record.update(abi=emulator.invoke('-s',record['serial'],'shell','getprop','ro.product.cpu.abi'),
                          api_level=emulator.invoke('-s',record['serial'],'shell','getprop','ro.build.version.sdk'),
                          android_build=emulator.invoke('-s',record['serial'],'shell','getprop','ro.build.fingerprint'),
                          readiness_seconds=time.monotonic()-started,status='ready')
            if record['abi']!='arm64-v8a':raise ValueError('Selected Mac ARM plan requires an ARM64 Android runtime.')
            args.result.parent.mkdir(parents=True,exist_ok=True);args.result.write_text(json.dumps(record,indent=2)+'\n')
        except BaseException:
            emulator.cleanup();raise
        return
    record=json.loads(emulator.marker.read_text());emulator.verify(record)
    args.result.parent.mkdir(parents=True,exist_ok=True)
    if args.action=='runtime':
        from Scripts.mobile_runtime import test
        return test(args.root,args.runtime_cache,record['serial'],args.result)
    from mobile_build.validation.ui_tools import run
    os.chdir(args.root/'mobile_build')
    try:
        report=run('android',record['serial'],local=True,no_update=True)
        args.result.write_text(json.dumps(report,indent=2)+'\n')
    finally:
        import shutil
        for log in (args.root/'mobile_build/logs').glob('android-*'):
            if log.is_file():shutil.copy2(log,args.result.parent/log.name)


if __name__=='__main__':main()
