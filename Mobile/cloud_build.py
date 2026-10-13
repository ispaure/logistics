"""Build and link the pinned read-only rclone bridge into generated native apps."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
FLAGS = '-s -w -X github.com/rclone/rclone/fs.Version=v1.74.1'


def run(*args, env=None, cwd=ROOT / 'rclone_bridge'):
    subprocess.run(args, check=True, env=env, cwd=cwd)


def android():
    sdk = Path(os.environ.get('ANDROID_HOME') or os.environ['ANDROID_SDK_ROOT'])
    ndk = sdk / 'ndk' / '27.2.12479018'
    if not ndk.is_dir():
        manager = sdk / 'cmdline-tools/latest/bin/sdkmanager'
        run(str(manager), 'ndk;27.2.12479018')
    host = 'linux-x86_64' if platform.system() == 'Linux' else 'darwin-x86_64'
    tools = ndk / 'toolchains/llvm/prebuilt' / host / 'bin'
    project = ROOT / 'build/logisticsmobile/android/gradle'
    for arch, abi, compiler in [('arm64', 'arm64-v8a', 'aarch64-linux-android24-clang'),
                                 ('amd64', 'x86_64', 'x86_64-linux-android24-clang')]:
        destination = project / 'app/src/main/jniLibs' / abi
        destination.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, CGO_ENABLED='1', GOOS='android', GOARCH=arch, CC=str(tools / compiler),
                   CGO_LDFLAGS='-Wl,-z,max-page-size=16384')
        run('go', 'build', '-trimpath', '-ldflags=' + FLAGS, '-buildmode=c-shared',
            '-o', str(destination / 'liblogisticscloud.so'), '.', env=env)
        headers = subprocess.check_output([str(tools / 'llvm-readelf'), '-l', '--wide',
                                            str(destination / 'liblogisticscloud.so')], text=True)
        loads = [line.split() for line in headers.splitlines() if line.strip().startswith('LOAD ')]
        if not loads or any(int(row[-1], 16) < 16384 for row in loads):
            raise ValueError('The Android rclone library is missing 16 KiB ELF load alignment.')
        (destination / 'liblogisticscloud.h').unlink()


def ios():
    project = ROOT / 'build/logisticsmobile/ios/xcode'
    support = project / 'Support'
    support.mkdir(parents=True, exist_ok=True)
    arch = {'arm64': 'arm64', 'aarch64': 'arm64', 'x86_64': 'amd64'}[platform.machine()]
    for sdk, variant, go_arch, target in [
        ('iphonesimulator', 'simulator', arch, ('arm64' if arch == 'arm64' else 'x86_64') + '-apple-ios15.0-simulator'),
        ('iphoneos', 'device', 'arm64', 'arm64-apple-ios15.0')]:
        path = subprocess.check_output(['xcrun', '--sdk', sdk, '--show-sdk-path'], text=True).strip()
        env = dict(os.environ, CGO_ENABLED='1', GOOS='ios', GOARCH=go_arch,
                   CC=f'clang -target {target} -isysroot {path}')
        run('go', 'build', '-trimpath', '-ldflags=' + FLAGS, '-buildmode=c-archive',
            '-o', str(support / f'liblogisticscloud-{variant}.a'), '.', env=env)
    pbx = project / 'Logistics Mobile.xcodeproj/project.pbxproj'
    data = json.loads(subprocess.check_output(['plutil', '-convert', 'json', '-o', '-', str(pbx)]))
    found = 0
    for obj in data['objects'].values():
        if obj.get('isa') != 'XCBuildConfiguration' or 'PRODUCT_BUNDLE_IDENTIFIER' not in obj.get('buildSettings', {}):
            continue
        found += 1
        settings = obj['buildSettings']
        for sdk, variant in [('iphonesimulator', 'simulator'), ('iphoneos', 'device')]:
            settings[f'OTHER_LDFLAGS[sdk={sdk}*]'] = ['$(inherited)',
                f'-Wl,-force_load,$(SRCROOT)/Support/liblogisticscloud-{variant}.a',
                '-Wl,-u,_LogisticsCloud', '-Wl,-u,_LogisticsCloudFree', '-Wl,-export_dynamic',
                '-framework', 'CoreFoundation', '-framework', 'Security', '-lresolv']
    if found != 2:
        raise ValueError('Unexpected Briefcase iOS build configuration; refusing to silently omit the bridge.')
    pbx.write_bytes(plistlib.dumps(data, sort_keys=False))


def licenses():
    """Carry notices for the modules actually compiled into the native engine."""
    raw = subprocess.check_output(['go', 'list', '-deps', '-json', '.'], cwd=ROOT / 'rclone_bridge', text=True)
    decoder, modules = json.JSONDecoder(), {}
    while raw.strip():
        value, end = decoder.raw_decode(raw.lstrip())
        raw = raw.lstrip()[end:]
        module = value.get('Module', {})
        if module.get('Version'):
            modules[module['Path']] = module
    destination = ROOT / 'payload/logisticsmobile/native-licenses'
    destination.mkdir(parents=True, exist_ok=True)
    manifest = []
    for name, module in sorted(modules.items()):
        root = Path(module['Dir'])
        files = [p for p in root.iterdir() if p.is_file()
                 and p.name.upper().startswith(('LICENSE', 'COPYING', 'NOTICE'))]
        if not files:
            raise ValueError('No license notice found for native dependency: ' + name)
        records = []
        for source in files:
            if source.stat().st_size > 512 * 1024:
                raise ValueError('Unexpected native dependency notice size.')
            target = destination / (name.replace('/', '_') + '-' + module['Version'] + '-' + source.name)
            shutil.copyfile(source, target)
            records.append(dict(file=target.name, sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
        manifest.append(dict(module=name, version=module['Version'], notices=records))
    goroot = Path(subprocess.check_output(['go', 'env', 'GOROOT'], text=True).strip())
    shutil.copyfile(goroot / 'LICENSE', destination / 'Go-LICENSE')
    (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', choices=['android', 'ios', 'host', 'licenses'])
    args = parser.parse_args()
    if not shutil.which('go'):
        parser.error('Install the pinned Go 1.26.9 toolchain first.')
    if args.target == 'licenses':
        licenses()
        return
    run('go', 'test', './...')
    if args.target == 'android':
        android()
    elif args.target == 'ios':
        ios()
    else:
        destination = ROOT / 'build/cloud-host'
        destination.mkdir(parents=True, exist_ok=True)
        run('go', 'build', '-buildmode=c-shared', '-o', str(destination / 'liblogisticscloud.dylib'), '.')


if __name__ == '__main__':
    main()
