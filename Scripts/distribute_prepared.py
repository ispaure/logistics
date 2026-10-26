"""Consume an exact manager-reviewed prepared artifact; never rebuild for upload."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from uuid import uuid4
from commonUtils.runtime.streams import file_sha256


def reviewed(path):
    path=Path(path)
    digest=file_sha256(path)
    rows=json.loads(os.environ.get('BUILD_MANAGER_APPROVED_ARTIFACTS','[]'))
    if not os.environ.get('BUILD_MANAGER_APPROVED_PLAN') or not any(
            row.get('original_path')==str(path.resolve()) and row['sha256']==digest for row in rows):
        raise ValueError('Exact retained artifact report needs manager review before distribution.')
    return json.loads(path.read_text())


def distribute(report,receipt):
    data=reviewed(report);receipt=Path(receipt)
    attempt=receipt.with_suffix('.attempt.json')
    if receipt.exists() or attempt.exists():
        raise ValueError('Reconcile this recorded distribution attempt before retry; it will not be repeated blindly.')
    receipt.parent.mkdir(parents=True,exist_ok=True)
    provider=data['provider']
    if provider=='TestFlight':
        workspace=Path(data['workspace'])
        if data['release']['source']['dirty']:raise ValueError('Signed tester artifacts require committed source.')
        # Existing helper verifies archive, IPA checksum, identity, signature and
        # the captured profile's destination immediately before the upload.
        if (workspace/'upload-result.json').exists():raise ValueError('Existing uploaded build requires read-only reconciliation.')
        command=[sys.executable,'-m','mobile_build.deployment.testflight_tools','upload',
                 '--build-number',str(data['release']['build']['build_number'])]
        env=dict(os.environ,TESTFLIGHT_UPLOAD='1')
    elif provider=='Firebase':
        from build_manager.firebase import FirebaseCLI
        from mobile_build.deployment.firebase_deploy import ROOT,preflight
        apk=Path(data['apk'])
        if file_sha256(apk)!=data['apk_sha256']:raise ValueError('Reviewed APK changed.')
        local=ROOT/'.tools/firebase';cli=str(local) if local.is_file() else shutil.which('firebase')
        if not cli:raise ValueError('Install Firebase CLI explicitly before distribution.')
        config,group=preflight(cli,allow_login=False)
        if config!=data['destination']:raise ValueError('Reviewed Firebase destination changed.')
        transport=FirebaseCLI(cli,ROOT/'.tools',environment=dict(os.environ))
    else:raise ValueError('Unsupported prepared distribution provider.')
    attempt.write_text(json.dumps(dict(schema=1,operation_id=os.environ.get('BUILD_MANAGER_OPERATION_ID') or str(uuid4()),provider=provider,
        plan=os.environ['BUILD_MANAGER_APPROVED_PLAN'],status='unknown until reconciled'))+'\n')
    if provider=='Firebase':
        remote=transport.distribute(apk,app_id=config['app_id'],group=group,
            release_notes=apk.parent/'release-notes.txt',capture_result=True)
    else:
        subprocess.run(command,env=env,text=True,capture_output=True,check=True)
        remote=json.loads((workspace/'upload-result.json').read_text())
    value=dict(schema=1,provider=provider,status='completed',operation=json.loads(attempt.read_text())['operation_id'],
               destination=data['destination'],remote=remote)
    receipt.write_text(json.dumps(value,indent=2)+'\n');return value


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,required=True);parser.add_argument('--receipt',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(distribute(args.report,args.receipt)));return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as error:
        from build_manager.redaction import Redactor
        print(Redactor()(str(error)),file=sys.stderr);raise SystemExit(1)
