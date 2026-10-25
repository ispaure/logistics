"""Pinned upstream CPython preparation and source-verified mobile runtime tests."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tarfile
import urllib.request

from build_manager.locking import workspace_lock
from Scripts.ios_backend import command, interrupt


def checksum(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source(cache, pin):
    archive = cache.parent/('cpython-'+pin['revision']+'.tar.gz')
    if not archive.exists():
        partial = archive.with_suffix('.download')
        with urllib.request.urlopen(pin['archive'],timeout=60) as incoming, partial.open('wb') as output:
            shutil.copyfileobj(incoming,output)
        if checksum(partial)!=pin['sha256']:
            partial.unlink()
            raise ValueError('Pinned CPython archive digest mismatch.')
        partial.rename(archive)
    if checksum(archive)!=pin['sha256']:
        raise ValueError('Pinned CPython cache archive digest differs.')
    if not cache.exists():
        cache.mkdir()
        with tarfile.open(archive) as stream:
            for item in stream:
                item.name = '/'.join(Path(item.name).parts[1:])
                if item.name:
                    stream.extract(item,cache,filter='data')
    # Reject a modified upstream source cache; generated cross-build/testbed
    # output is separate from the archive's immutable source members.
    with tarfile.open(archive) as stream:
        for item in stream:
            relative = Path(*Path(item.name).parts[1:])
            if item.isfile():
                with stream.extractfile(item) as incoming:
                    expected = hashlib.sha256(incoming.read()).hexdigest()
                if not (cache/relative).is_file() or checksum(cache/relative)!=expected:
                    raise ValueError('Pinned CPython source cache changed: '+str(relative))


def prepare(cache, result):
    pin = json.loads(Path(__file__).with_name('mobile_runtime_tools.json').read_text())['cpython']
    cache.parent.mkdir(parents=True,exist_ok=True)
    with workspace_lock(cache.parent/'mobile-runtime.lock'):
        source(cache,pin)
        target=pin['android_target']
        host=cache/'cross-build/build/python.exe'
        if not host.exists():host=cache/'cross-build/build/python'
        library=cache/'cross-build'/target/'prefix/lib/libpython3.14.so'
        record=cache/'prepared-manager.json'
        if record.exists():
            saved=json.loads(record.read_text())
            if saved['revision']==pin['revision'] and host.exists() and library.exists() and saved['host_sha256']==checksum(host) and saved['library_sha256']==checksum(library):
                result.parent.mkdir(parents=True,exist_ok=True)
                result.write_text(json.dumps(dict(saved,reused=True),indent=2)+'\n')
                return
            raise ValueError('Prepared runtime artifacts changed; inspect the cache before rebuilding.')
        if not host.exists() or not library.exists():
            previous=dict(os.environ)
            try:
                sdk=subprocess.check_output(['xcrun','--sdk','macosx','--show-sdk-path'],text=True).strip()
                developer=Path(os.environ.get('DEVELOPER_DIR') or subprocess.check_output(['xcode-select','-p'],text=True).strip())
                for link,target_path in [(cache/'macos-sdk',Path(sdk)),(cache/'xcode-toolchain',developer/'Toolchains/XcodeDefault.xctoolchain')]:
                    if not link.exists():link.symlink_to(target_path,target_is_directory=True)
                os.environ.update(SDKROOT=str(cache/'macos-sdk'),CC=str(cache/'xcode-toolchain/usr/bin/clang'),
                    CXX=str(cache/'xcode-toolchain/usr/bin/clang++'),
                    PATH=str(developer/'usr/bin')+os.pathsep+str(cache/'xcode-toolchain/usr/bin')+os.pathsep+os.environ.get('PATH',''))
                command([sys.executable,'Android/android.py','build','build','--','--with-openssl=/opt/homebrew/opt/openssl@3'],cache,1800)
            finally:
                os.environ.clear();os.environ.update(previous)
            command([sys.executable,'Android/android.py','build',pin['android_target']],cache,1800)
        version=subprocess.check_output([str(host),'-c','import platform;print(platform.python_version())'],text=True).strip()
        if version!=pin['version']:raise ValueError('Pinned CPython host version mismatch.')
        record.write_text(json.dumps(dict(revision=pin['revision'],version=version,target=target,
            host_sha256=checksum(host),library_sha256=checksum(library),archive_sha256=pin['sha256'],status='prepared'),indent=2)+'\n')
        result.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(record,result)


def test(root, cache, serial, output):
    from mobile_build import tools
    payload=output.parent/'runtime-payload'
    output.parent.mkdir(parents=True,exist_ok=True)
    manifest=tools.stage(root,payload,testbed=True,allow_dirty=True)
    # These two pure-Python packages are the exact dependencies declared by the
    # canonical runtime workflow; they never contain native host binaries.
    command([sys.executable,'-m','pip','install','--target',str(payload),'--no-deps',
             'markdown-it-py==4.2.0','mdurl==0.1.2'],root,180)
    with workspace_lock(cache.parent/'mobile-runtime.lock'):
        with output.with_suffix('.log').open('w') as log:
            process=subprocess.Popen([sys.executable,'Android/android.py','test','--connected',serial,
                '--site-packages',str(payload),'--','-m','mobile.smoke','--target','android','--local-source-sha256',manifest['source_sha256']],cwd=cache,
                stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            try:
                code=process.wait(timeout=1800)
            finally:
                from build_manager.executor import stop_process
                stop_process(process)
        if code:raise RuntimeError('Pinned Android runtime testbed failed: '+str(code))
        report=tools.verify(output.with_suffix('.log'),'android',output,local_manifest=payload/'source.json')
        if report['source']!=manifest:raise ValueError('Runtime source identity changed.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','test'])
    parser.add_argument('--cache',type=Path,required=True)
    parser.add_argument('--result',type=Path,required=True)
    parser.add_argument('--root',type=Path)
    parser.add_argument('--serial')
    args=parser.parse_args()
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,interrupt)
    if args.action=='prepare':prepare(args.cache,args.result)
    else:test(args.root,args.cache,args.serial,args.result)


if __name__=='__main__':
    main()
