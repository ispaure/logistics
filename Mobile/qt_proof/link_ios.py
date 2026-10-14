"""Attach native rclone and non-Python resources to the generated proof project."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import shlex
import subprocess

REPO = Path(__file__).resolve().parents[2]

def prepare(source, go):
    source = source.resolve()
    output = source / 'deployment/ios_arm64_simulator'
    archive = output / 'liblogisticscloud.a'
    sdk = subprocess.check_output(['xcrun', '--sdk', 'iphonesimulator', '--show-sdk-path'], text=True).strip()
    env = dict(os.environ, CGO_ENABLED='1', GOOS='ios', GOARCH='arm64',
               CC=shlex.join(['clang', '-target', 'arm64-apple-ios17.0-simulator', '-isysroot', sdk]))
    subprocess.run([str(go), 'build', '-trimpath', '-ldflags=-s -w -X github.com/rclone/rclone/fs.Version=v1.74.1',
                    '-buildmode=c-archive', '-o', str(archive), '.'], cwd=REPO / 'Mobile/rclone_bridge', env=env, check=True)
    pbx = output / 'LogisticsQtProof.xcodeproj/project.pbxproj'
    project = json.loads(subprocess.check_output(['plutil', '-convert', 'json', '-o', '-', str(pbx)]))
    for item in project['objects'].values():
        settings = item.get('buildSettings', {})
        if item.get('isa') == 'XCBuildConfiguration' and 'PRODUCT_BUNDLE_IDENTIFIER' in settings:
            flags = settings.get('OTHER_LDFLAGS', [])
            if isinstance(flags, str):
                raise ValueError('Unexpected Qt linker flag format')
            additions = [f'-Wl,-force_load,{archive}', '-Wl,-u,_LogisticsCloud',
                '-Wl,-u,_LogisticsCloudFree', '-Wl,-export_dynamic', '-framework', 'CoreFoundation',
                '-framework', 'Security', '-lresolv']
            if f'-Wl,-force_load,{archive}' not in flags:
                settings['OTHER_LDFLAGS'] = flags + additions
            if '-lz' not in settings['OTHER_LDFLAGS']:
                settings['OTHER_LDFLAGS'].append('-lz')
        if (item.get('isa') == 'PBXShellScriptBuildPhase' and item.get('name') == 'Copy Python Packages'
                and 'rsync -a --exclude' not in item['shellScript']):
            item['shellScript'] += '\n' + '\n'.join(
                f'rsync -a --exclude="__pycache__" {shlex.quote(str(source / name))}/ "$CODESIGNING_FOLDER_PATH/{name}/"'
                for name in ('commonUtils', 'pygments')) + '\n'
    pbx.write_bytes(plistlib.dumps(project))
    info = output / 'Info.plist'
    values = plistlib.loads(info.read_bytes())
    # The isolated proof requests no contacts, camera, microphone or location.
    values = {key: value for key, value in values.items() if not key.endswith('UsageDescription')}
    info.write_bytes(plistlib.dumps(values))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--go', type=Path, required=True)
    args = parser.parse_args()
    prepare(args.source, args.go)
