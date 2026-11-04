"""Source-bound image/password acceptance via owning disposable mobile helpers."""
import argparse
import base64
from hashlib import sha256
from io import BytesIO
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
from zipfile import ZipFile

from logistics_build.build_retention import scratch
from logistics_build.build_snapshots import materialize
from mobile_build.deployment import manager_settings
from mobile_build.tools import stage


def fixtures(source, rclone):
    spec=importlib.util.spec_from_file_location('image_qa_fixture',source/'Python/tests/notebooks/image_fixtures.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    data=module.fixture_bytes()
    password=subprocess.check_output([str(rclone),'obscure','image-qa-crypt-password'],text=True,timeout=15).strip()
    credentials=BytesIO()
    with ZipFile(credentials,'w') as archive:
        archive.writestr('Cloud.txt','[Cloud]\ntype=memory\n')
        archive.writestr('Secret.txt','[Secret]\ntype=crypt\nremote=Cloud:image-qa\npassword='+password+'\n')
    return json.dumps(dict(rmdoc=base64.b64encode(data).decode(),
                           credentials=base64.b64encode(credentials.getvalue()).decode())).encode()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('platform',choices=('ios','android'))
    parser.add_argument('--revision',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--rclone',type=Path,required=True,help='Verified host fixture tool; never a user remote')
    parser.add_argument('--ios-shell-receipt',type=Path)
    android=parser.add_mutually_exclusive_group()
    android.add_argument('--android-build',action='store_true',help='Explicitly allow a fresh isolated QA build')
    android.add_argument('--android-shell-receipt',type=Path,help='Restage Python/assets in a verified immutable QA APK')
    args=parser.parse_args()
    if args.platform=='ios' and args.ios_shell_receipt is None:
        parser.error('iOS is copy-only and requires an explicit compiled-shell receipt')
    if args.platform=='android' and not (args.android_build or args.android_shell_receipt):
        parser.error('Android requires --android-build or --android-shell-receipt')
    root=Path(__file__).resolve().parents[2]
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    options,_=manager_settings.settings(root/'mobile_build')
    env=dict(os.environ,DEVELOPER_DIR=options['tools.xcode'],ANDROID_HOME=options['tools.android_sdk'],
             ANDROID_SDK_ROOT=options['tools.android_sdk'],JAVA_HOME=options['tools.java'])
    os.environ.update(env)
    with scratch(root) as work:
        env['LOGISTICS_DEPLOY_WORKSPACE']=os.environ['LOGISTICS_DEPLOY_WORKSPACE']=str(work)
        env['XDG_CACHE_HOME']=str(work/'probe-tools')
        env['GRADLE_USER_HOME']=str(work/'gradle-cache')
        (output/'workspace.json').write_text(json.dumps(dict(path=str(work),owned=True)))
        shutil.copyfile(root/'mobile_build/pyproject.toml',work/'pyproject.toml')
        source=work/'source'
        captured=materialize(root,source,revision=args.revision)
        (output/'committed-source.json').write_text(json.dumps(captured,indent=2))
        fixture=fixtures(source,args.rclone)
        (output/'fixtures.json').write_text(json.dumps(dict(sha256=sha256(fixture).hexdigest(),synthetic=True)))
        payload=work/'payload';manifest=stage(source,payload)
        (output/'source.json').write_text(json.dumps(manifest,indent=2))
        spec=importlib.util.spec_from_file_location('image_qa_driver',source/'mobile_build/validation/document_storage_tools.py')
        driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
        original_copy=driver.copy_payload
        def copy_with_fixture(payload,target,**kwargs):
            original_copy(payload,target,**kwargs)
            (target/'tests/logisticsmobile/notebook-image-fixture.json').write_bytes(fixture)
        driver.copy_payload=copy_with_fixture
        profile=dict(bundle='io.github.ispaure.logisticsnotebookqa',
                     entry_point='tests.logisticsmobile.notebook_image_probe',result_name='notebook-image-result.json')
        try:
            if args.platform=='ios':
                receipt=json.loads(args.ios_shell_receipt.read_text())
                from mobile_build.validation.drawer_privacy_tools import verify_shell
                verified=verify_shell(receipt,captured['logistics_commit'])
                verified['scope']='Notebook image/password iPad simulator acceptance; synthetic pointer delivery'
                (output/'verified-ios-shell.json').write_text(json.dumps(verified,indent=2))
                (output/'compiled-shell.json').write_text(json.dumps(receipt,indent=2))
                driver.run_ios(work,payload,output,env,family='iPad',source_app=Path(receipt['app']),**profile)
            elif args.android_shell_receipt:
                from mobile_build.validation.notebook_template_tools import android_shell
                # Synthetic test data is injected only into this owned materialized
                # source, after recording its committed identity and fixture hash.
                fixture_path=source/'mobile_build/native_tests/tests/logisticsmobile/notebook-image-fixture.json'
                fixture_path.write_bytes(fixture)
                (work/'repack').mkdir()
                apk=android_shell(args.android_shell_receipt,source,work,output,env,probe='notebook_image_probe')
                driver.exercise_android_app(apk,work,output,env,options,probe_timeout=240,**profile)
            else:
                driver.run_android(work,payload,output,env,options,probe_timeout=240,**profile)
        finally:
            report_path=output/(args.platform+'-result.json')
            if report_path.exists():
                report=json.loads(report_path.read_text());artifacts=report.pop('artifacts',{})
                evidence=output/'image-evidence';evidence.mkdir(exist_ok=True)
                for name,data in artifacts.items():
                    if Path(name).name!=name or Path(name).suffix not in ('.png','.rmdoc'):
                        raise ValueError('Unexpected image evidence filename')
                    (evidence/name).write_bytes(base64.b64decode(data,validate=True))
                report['artifact_names']=list(artifacts)
                report_path.write_text(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
