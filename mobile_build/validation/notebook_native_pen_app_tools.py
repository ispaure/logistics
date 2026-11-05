"""Fresh normal Toga QA build for native Pencil mounting/chrome/persisted dots.

No reusable-shell option: compiled producer must be built from selected source.
Run only in a coordinator-granted native slot; no personal device is selected.
"""
import argparse
from contextlib import ExitStack
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from threading import Event
from urllib.request import urlopen

from build_manager.resources import HostResourceSlots

from logistics_build.build_retention import scratch, compiler_cache
from logistics_build.build_snapshots import materialize
from mobile_build.deployment import manager_settings
from mobile_build.tools import stage
from mobile_build.validation import document_storage_tools as driver


OWNED_SOURCES = (
    'Python/features/notebooks/mobile/ios/NotebookInputWindow.m',
    'Python/features/notebooks/mobile/ios_native_pen.py',
    'Python/mobile/ios_notebook_window.py',
    'mobile_build/build_support/scene_build.py',
    'mobile_build/native_tests/tests/logisticsmobile/notebook_native_pen_probe.py',
    'mobile_build/validation/document_storage_tools.py',
    'mobile_build/validation/notebook_native_pen_app_tools.py',
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--runtime', required=True)
    parser.add_argument('--family', choices=('iPhone', 'iPad', 'iPhone Duo'), default='iPhone Duo')
    parser.add_argument('--pose', choices=('open', 'closed', 'partial'))
    args = parser.parse_args()
    if args.pose is not None and args.family != 'iPhone Duo':
        parser.error('--pose is only supported for the owned iPhone Duo Simulator')
    root = Path(__file__).resolve().parents[2]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()
    selected = git('rev-parse', args.revision + '^{commit}')
    if selected != git('rev-parse', 'HEAD') or git('status', '--porcelain', '--ignore-submodules=none'):
        raise ValueError('Normal QA requires the selected exact clean HEAD, including submodules')
    options, _ = manager_settings.settings(root / 'mobile_build')
    config = output / 'no-sdk-stat-cache.xcconfig'
    config.write_text('SDK_STAT_CACHE_ENABLE = NO\n')
    env = dict(os.environ, DEVELOPER_DIR=options['tools.xcode'],
        GOTOOLCHAIN='local', GOTELEMETRY='off', GOMAXPROCS='2',
        XCODE_XCCONFIG_FILE=str(config),
        PATH=os.pathsep.join((str(Path(sys.executable).parent), str(root / 'mobile_build/.tools/go/bin'), os.environ.get('PATH', ''))))
    wheels = root / 'mobile_build/.tools/release-wheels'
    if wheels.is_dir():
        env['PIP_FIND_LINKS'] = str(wheels)
    os.environ.update(env)
    hashes = {name: sha256((root / name).read_bytes()).hexdigest() for name in OWNED_SOURCES}
    proof = dict(diagnostic_only=True, physical_pencil_tested=False, fresh_native_build=True,
                 source_hashes=hashes)
    try:
        with ExitStack() as leases:
            cache = leases.enter_context(compiler_cache('notebook-native-pen-go', root))
            for name, sub in [('GOCACHE', 'go-build'), ('GOMODCACHE', 'modules'),
                              ('GOPATH', 'path'), ('GOTMPDIR', 'tmp')]:
                path = cache / sub
                path.mkdir(exist_ok=True)
                env[name] = str(path)
            os.environ.update(env)
            resources = {'host.mobile-build': 1, 'host.signing-keychain': 1}
            leases.enter_context(HostResourceSlots().acquire(resources, resources,
                cancelled=Event(), timeout=1800))
            work = leases.enter_context(scratch(root))
            env['LOGISTICS_DEPLOY_WORKSPACE'] = os.environ['LOGISTICS_DEPLOY_WORKSPACE'] = str(work)
            shutil.copyfile(root / 'mobile_build/pyproject.toml', work / 'pyproject.toml')
            source = work / 'source'
            proof['committed_source'] = materialize(root, source, revision=args.revision)
            for name, digest in hashes.items():
                if sha256((source / name).read_bytes()).hexdigest() != digest:
                    raise ValueError('Selected committed source differs from active build owner: ' + name)
            # copy_payload must read every QA module from this committed snapshot.
            driver.SOURCE = source
            payload = work / 'payload'
            proof['payload'] = stage(source, payload)
            (output / 'source-provenance.json').write_text(json.dumps(proof, indent=2))
            # Existing owner patches Xcode Support with the current native source,
            # rebuilds it, then creates/removes its own disposable Simulator.
            duoctl = None
            if args.pose is not None:
                approved = {'duoctl': '9d9d151afb303ddec426beffadb9bfb21309e8ca9ce52fdd6cc4dcc3fd1dbf45',
                    'duoctl-helper.m': 'b2d8fb45b0abab1802316ac0c0fa953e9cf644ac54dfbf06281593d4bae28b1f'}
                folder = work / 'duo-pose-tool'
                folder.mkdir()
                for name, digest in approved.items():
                    url = 'https://raw.githubusercontent.com/skarol/duoctl/caad72ec15cae2e6090a4ae2749c6fed721b275e/skills/duoctl/scripts/' + name
                    with urlopen(url, timeout=30) as response:
                        data = response.read(256 * 1024 + 1)
                    if len(data) > 256 * 1024 or sha256(data).hexdigest() != digest:
                        raise ValueError('Pinned owning pose helper bytes changed: ' + name)
                    (folder / name).write_bytes(data)
                if args.pose == 'open':
                    env['SIMCTL_CHILD_LOGISTICS_NATIVE_PEN_EXPECT_OPEN'] = '1'
                duoctl = folder / 'duoctl'
                env['XDG_CACHE_HOME'] = str(work / 'duo-tool-cache')
                (output / 'pose-tool.json').write_text(json.dumps(approved, indent=2))
            driver.run_ios(work, payload, output, env,
                bundle='io.github.ispaure.logisticsnotebookqa',
                entry_point='tests.logisticsmobile.notebook_native_pen_probe',
                result_name='notebook-native-pen-result.json',
                family=args.family, runtime_id=args.runtime, pose=args.pose, duoctl=duoctl)
            if selected != git('rev-parse', 'HEAD') or git('status', '--porcelain', '--ignore-submodules=none'):
                raise ValueError('Exact clean build HEAD changed during QA')
            for name, digest in hashes.items():
                if sha256((root / name).read_bytes()).hexdigest() != digest:
                    raise ValueError('Build owner source changed during normal QA build: ' + name)
            proof['source_unchanged_after_build'] = True
    finally:
        (output / 'source-provenance.json').write_text(json.dumps(proof, indent=2))


if __name__ == '__main__':
    main()
