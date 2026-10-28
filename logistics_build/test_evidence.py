"""Logistics-owned conservative input identities for portable host test reuse."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

HOST_SUITES = {'commonutils', 'logistics', 'portable-contracts', 'desktop-ui', 'mobile-host', 'release-tooling', 'manager-contracts', 'compression-parity'}


def toolchain():
    return dict(python=sys.version, executable_sha256=hashlib.sha256(Path(sys.executable).resolve().read_bytes()).hexdigest(),
                os=platform.platform(), architecture=platform.machine(),
                packages=sorted((d.metadata.get('Name', '').lower(), d.version) for d in importlib.metadata.distributions()))


def phase_toolchain(phase):
    # Inspect the interpreter that will execute the tests, never the manager's
    # possibly different environment. No application or sibling import occurs.
    script = ("import hashlib,importlib.metadata as m,json,platform,sys;from pathlib import Path;"
              "print(json.dumps(dict(python=sys.version,"
              "executable_sha256=hashlib.sha256(Path(sys.executable).resolve().read_bytes()).hexdigest(),"
              "os=platform.platform(),architecture=platform.machine(),"
              "packages=sorted((d.metadata.get('Name','').lower(),d.version) for d in m.distributions()))))")
    result = subprocess.run([phase.argv[0], '-I', '-c', script], cwd=phase.cwd,
                            env=dict(os.environ, **phase.environment), capture_output=True,
                            text=True, check=True, timeout=30)
    return json.loads(result.stdout)


class UnverifiableInputs(ValueError):
    """A working-tree inventory cannot safely supply a reusable receipt."""


def inputs(root, scopes):
    root = Path(root)
    def reject_link(name):
        relative = Path(name)
        if any((root / part).is_symlink() for part in (relative, *relative.parents[:-1])):
            raise ValueError('A symlink cannot prove complete test inputs: ' + str(name))

    def inventory(checkout, selected):
        result = subprocess.run(['git', '-C', str(checkout), 'ls-files', '--stage', '-z', '--', *selected],
                                capture_output=True, check=True, timeout=30)
        extra = subprocess.run(['git', '-C', str(checkout), 'ls-files', '-z', '--others', '--exclude-standard', '--', *selected],
                               capture_output=True, check=True, timeout=30)
        names = set(os.fsdecode(name) for name in extra.stdout.split(b'\0') if name)
        for entry in result.stdout.split(b'\0'):
            if not entry:
                continue
            metadata, encoded = entry.split(b'\t', 1)
            name = os.fsdecode(encoded)
            if metadata.split()[0] != b'160000':
                names.add(name)
                continue
            # Snapshots clone the pinned dependency in place without registering
            # it as an active submodule. Git's recursive listing then emits the
            # gitlink directory itself. Enumerate its own index explicitly.
            shared = checkout / name
            reject_link(shared.relative_to(root))
            if not (shared / '.git').exists():
                raise ValueError('Test input submodule is not initialized: ' + name)
            names.update((Path(name) / child).as_posix() for child in inventory(shared, []))
        return names

    names = sorted(inventory(root, scopes))
    if not names:
        raise ValueError('Test input inventory is empty.')
    digest = hashlib.sha256()
    for name in names:
        path = root / name
        # Never follow a tracked link into another checkout or private directory.
        reject_link(name)
        if not path.is_file():
            raise UnverifiableInputs('Test input is missing: ' + name)
        digest.update(name.encode() + b'\0')
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def host_environment(phase, source):
    """Use one configured Mac host environment for identical host-only suites."""
    if phase.id.rsplit('.', 1)[-1] not in HOST_SUITES or sys.platform != 'darwin':
        return dict(phase.environment)
    values = source.get('effective_settings', {}).get('values', {})
    mobile_python = values.get('tools.mobile_python')
    if not mobile_python:
        return dict(phase.environment)
    mobile = Path(mobile_python).parents[2]
    if mobile.name != 'mobile_build':
        return dict(phase.environment)
    env = dict(phase.environment, LOGISTICS_REQUIRE_LOCALCRYPT_TESTS='1',
               PIP_FIND_LINKS=str(mobile / '.tools/release-wheels'),
               PATH=str(mobile / '.tools/go/bin') + os.pathsep + os.environ.get('PATH', ''),
               GRADLE_OPTS='-Dorg.gradle.daemon=false')
    for setting, variable in (('tools.xcode', 'DEVELOPER_DIR'), ('tools.android_sdk', 'ANDROID_HOME'),
                              ('tools.java', 'JAVA_HOME')):
        if values.get(setting):
            env[variable] = values[setting]
    if env.get('ANDROID_HOME'):
        env['ANDROID_SDK_ROOT'] = env['ANDROID_HOME']
    return env


def key_for(phase, *, runtime=None):
    suite = phase.id.rsplit('.', 1)[-1]
    if suite not in HOST_SUITES or phase.kind != 'test' or phase.always or phase.effect not in ('test', 'inherit'):
        return ''
    root = Path(phase.cwd)
    if not (root / '.git').exists():
        return ''  # Synthetic fixture plans have no verifiable tracked inputs.
    if suite == 'commonutils':
        scopes = ['Python/commonUtils', 'Python/tests/run_regressions.py', 'Python/tests/regression_timing.py']
    elif suite == 'release-tooling':
        scopes = ['.github/scripts', 'logistics_build/manager_suites.py']
    elif suite == 'compression-parity':
        scopes = ['Python/tests/compare_comic_zip_versions.py', 'Python/tests/parity_workspace.py', 'Python/commonUtils', 'Python/features/comics']
    else:
        # Deliberately conservative until narrower dependency contracts exist.
        scopes = ['Python', 'Scripts', 'logistics_build', 'mobile_build', '.github/scripts', 'dev.py', 'launch_config.ini', 'build-project.json', 'build-manager-dependency.json', '.github/workflows']
    command = []
    skip = False
    for arg in phase.argv:
        if skip:
            skip = False
            continue
        if arg in ('--junit', '--report', '--output-dir'):
            skip = True
            continue
        command.append(arg.replace(str(root), '$SOURCE'))
    command[0] = '$PYTHON'
    import build_manager
    manager = Path(build_manager.__file__).resolve().parents[2]
    def normalized(value):
        value = value.replace(str(manager), '$MANAGER').replace(str(root), '$SOURCE')
        if root.name.startswith('source-') or root.name == 'source':
            value = value.replace(str(root.parent), '$WORKSPACE')
        return value
    environment = {k: normalized(v) for k, v in phase.environment.items()
                   if k not in {'LOGISTICS_MANAGER_PROFILE', 'LOGISTICS_MANAGER_ACCOUNT_DEFAULTS'}}
    for name in ('LOGISTICS_MANAGER_PROFILE', 'LOGISTICS_MANAGER_ACCOUNT_DEFAULTS'):
        if phase.environment.get(name):
            path = Path(phase.environment[name])
            environment[name] = hashlib.sha256(path.read_bytes() if path.is_file() else phase.environment[name].encode()).hexdigest()
    for name in ('QT_QPA_PLATFORM', 'DISPLAY', 'WAYLAND_DISPLAY', 'LANG', 'LC_ALL', 'TZ', 'PYTHONHASHSEED'):
        if name not in environment and name in os.environ:
            environment[name] = os.environ[name]
    try:
        input_identity = inputs(root, scopes)
        manager_identity = inputs(manager, ['Python']) if suite in {'manager-contracts', 'logistics', 'release-tooling'} else None
    except UnverifiableInputs:
        # Tracked removals are valid captured working-tree changes. Run the
        # complete suite fresh when the index cannot prove reusable inputs.
        return ''
    data = dict(schema=2, suite=suite, inputs=input_identity, command=command,
                environment=environment, toolchain=runtime if runtime is not None else phase_toolchain(phase),
                artifacts=[phase.artifact_types.get(path, 'file') for path in phase.artifacts])
    if suite in {'manager-contracts', 'logistics', 'release-tooling'}:
        data['manager_inputs'] = manager_identity
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def with_reuse(plan):
    """Bind final environment and an execution-time probe to immutable receipts."""
    from dataclasses import asdict, replace
    from uuid import uuid4
    from build_manager.profiles import save_json
    from logistics_build.release_test_evidence import reuse_disabled
    disabled = plan.source.get('run_overrides', {}).get('testing.reuse_verified_results', 'on') == 'off'
    if disabled or any(p.environment.get('LOGISTICS_REUSE_TEST_RESULTS') == 'off' for p in plan.phases) or reuse_disabled(plan.phases[0].cwd):
        return replace(plan, phases=tuple(replace(phase, reuse_key='', reuse_probe=(),
            environment=dict(phase.environment, LOGISTICS_REUSE_TEST_RESULTS='off')) for phase in plan.phases))
    phases = []
    for phase in plan.phases:
        if phase.id.rsplit('.', 1)[-1] not in HOST_SUITES or phase.kind != 'test' or phase.always:
            phases.append(phase)
            continue
        candidate = replace(phase, environment=host_environment(phase, plan.source))
        key = key_for(candidate)
        if not key:
            phases.append(candidate)
            continue
        recipe = Path(plan.workspace) / 'evidence-inputs' / (uuid4().hex + '.json')
        save_json(recipe, asdict(candidate))
        digest = hashlib.sha256(recipe.read_bytes()).hexdigest()
        phases.append(replace(candidate, effect='test', reuse_key=key,
            reuse_probe=(candidate.argv[0], '-m', 'logistics_build.test_evidence', '--probe', str(recipe), '--sha256', digest)))
    return replace(plan, phases=tuple(phases))


def main():
    import argparse
    from build_manager import Phase
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    args = parser.parse_args()
    data = args.probe.read_bytes()
    if hashlib.sha256(data).hexdigest() != args.sha256:
        raise ValueError('Evidence input recipe changed.')
    print(key_for(Phase(**json.loads(data))))


if __name__ == '__main__':
    main()
