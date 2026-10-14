"""Select an installed Apple toolchain with the SDK required for Duo bars."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess


def version(value):
    if not re.fullmatch(r'\d+(?:\.\d+){1,2}', value):
        raise ValueError('Expected a numeric SDK version.')
    return tuple(int(part) for part in value.split('.')) + (0,) * (3 - len(value.split('.')))


def choose(candidates, minimum='27.1'):
    supported = [(version(sdk), path, sdk) for path, sdk in candidates if version(sdk) >= version(minimum)]
    if not supported:
        raise RuntimeError(f'Install Xcode with an iOS Simulator SDK >= {minimum}; older SDKs do not opt into Duo bars.')
    _, path, sdk = max(supported)
    return path, sdk


def installed():
    paths = {str(path / 'Contents/Developer') for path in Path('/Applications').glob('Xcode*.app')}
    if os.environ.get('DEVELOPER_DIR'):
        paths.add(os.environ['DEVELOPER_DIR'])
    candidates = []
    for path in sorted(paths):
        result = subprocess.run(['xcrun', '--sdk', 'iphonesimulator', '--show-sdk-version'],
            env=dict(os.environ, DEVELOPER_DIR=path), capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            candidates.append((path, result.stdout.strip()))
    return candidates


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--minimum-sdk', default='27.1')
    parser.add_argument('--github-env', type=Path)
    parser.add_argument('--path-only', action='store_true')
    args = parser.parse_args()
    path, sdk = choose(installed(), args.minimum_sdk)
    if args.github_env:
        with args.github_env.open('a') as stream:
            stream.write('DEVELOPER_DIR=' + path + '\n')
    print(path if args.path_only else json.dumps(dict(developer_dir=path, simulator_sdk=sdk)))
