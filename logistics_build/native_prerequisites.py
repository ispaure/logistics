"""Read-only native host-tool inspection; never install or download tooling."""
import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from uuid import uuid4

EXPECTED = {'briefcase': '0.4.5', 'pip': '26.3', 'go': '1.26.9'}
BUILD_PHASES = {'ios-build', 'android-build', 'android-native', 'build-release-archive', 'prepare-verified-artifact'}
RUNTIME_PHASES = {'ios-runtime', 'ios-runtime-tools', 'android-runtime', 'android-runtime-tools'}
PROBE_TIMEOUT = 10
MAX_OUTPUT = 8192


def with_prerequisites(plan, target, interpreter):
    """Inspect only capabilities required by the phases actually retained."""
    if target not in {'ios', 'android'} or plan.backend == 'GitHub':
        return plan
    builds = [phase for phase in plan.phases if phase.id in BUILD_PHASES]
    runtimes = [phase for phase in plan.phases if phase.id in RUNTIME_PHASES]
    if not builds and not runtimes:
        return plan
    from build_manager import Phase
    subject = (builds or runtimes)[0]
    capability = 'native' if builds else 'runtime'
    output = Path(plan.workspace) / ('native-prerequisites-' + uuid4().hex + '.json')
    gate = Phase('native-prerequisites', (str(interpreter), '-m', 'logistics_build.native_prerequisites',
        '--python', subject.argv[0], '--capability', capability, '--output', str(output),
        '--wheel-directory', dict(subject.environment).get('PIP_FIND_LINKS', str(Path(subject.cwd) / 'mobile_build/.tools/release-wheels'))),
        subject.cwd, timeout=45, environment=dict(subject.environment), kind='setup', effect='inspect',
        artifacts=(str(output),), dependencies=('test-structure',) if any(p.id == 'test-structure' for p in plan.phases) else (),
        label='Check native host prerequisites', description='Read-only tool versions; no installation, download or device operation.')
    phases = [phase if phase.id == 'test-structure' or phase.always or phase.kind == 'cleanup' else
              replace(phase, dependencies=tuple(dict.fromkeys((*phase.dependencies, gate.id)))) for phase in plan.phases]
    index = next((i + 1 for i, phase in enumerate(phases) if phase.id == 'test-structure'), 0)
    phases.insert(index, gate)
    return replace(plan, phases=tuple(phases))


def inspect(python, capability, *, environment=None, wheel_directory=None):
    if capability not in {'native', 'runtime'}:
        raise ValueError('Choose the native or runtime prerequisite capability.')
    env = dict(os.environ if environment is None else environment,
               GOTOOLCHAIN='local', GOTELEMETRY='off', PIP_DISABLE_PIP_VERSION_CHECK='1',
               PIP_NO_INDEX='1', PYTHONDONTWRITEBYTECODE='1')
    python = str(Path(python).absolute())
    selected = ['briefcase', 'pip', 'go'] if capability == 'native' else ['pip']
    rows = []
    for name in selected:
        executable = shutil.which('go', path=env.get('PATH', '')) if name == 'go' else python
        remedy = ('Explicitly Update project tooling to prepare Go ' + EXPECTED['go'] + '; no toolchain download was attempted by this check.'
                  if name == 'go' else 'Run python3 dev.py setup mobile for the selected project-owned mobile environment.')
        row = dict(tool=name, expected=EXPECTED[name], executable=executable, ready=False)
        if not executable or not Path(executable).is_file():
            row['error'] = 'Required executable is missing. ' + remedy
            rows.append(row)
            continue
        row['resolved_executable'] = str(Path(executable).resolve())
        command = [executable, 'version'] if name == 'go' else [executable, '-m', name, '--version']
        try:
            result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=PROBE_TIMEOUT)
            text = result.stdout.strip()
            if len(result.stdout.encode('utf-8')) + len(result.stderr.encode('utf-8')) > MAX_OUTPUT:
                raise ValueError('Version output exceeds the bounded inspection size.')
            pattern = r'go version go([^\s]+)' if name == 'go' else r'pip ([^\s]+)' if name == 'pip' else r'([^\s]+)'
            match = re.match(pattern, text)
            version = match[1] if match else None
            row.update(version=version, exit_code=result.returncode, output=text)
            row['ready'] = result.returncode == 0 and version == EXPECTED[name]
            if not row['ready']:
                row['error'] = 'Required tool version is missing or differs. ' + remedy
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            row['error'] = type(error).__name__ + ': version inspection failed. ' + remedy
        rows.append(row)
    if capability == 'native':
        from logistics_build.native_tooling import ROOT, wheel_status
        wheel = wheel_status(ROOT, directory=wheel_directory)
        rows.append(dict(tool='langdetect-wheel', **wheel))
    return dict(schema=1, capability=capability, ready=all(row['ready'] for row in rows), tools=rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', required=True)
    parser.add_argument('--capability', required=True, choices=('native', 'runtime'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--wheel-directory', type=Path)
    args = parser.parse_args()
    report = inspect(args.python, args.capability, wheel_directory=args.wheel_directory)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    for row in report['tools']:
        print(row['tool'] + ': ' + (row.get('version', row.get('filename', '')) if row['ready'] else row.get('error', row.get('message', 'Not ready'))), flush=True)
    return int(not report['ready'])


if __name__ == '__main__':
    raise SystemExit(main())
